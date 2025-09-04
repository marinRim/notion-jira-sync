import requests
import json
import os
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
import time

# .env 파일 로드 (로컬 개발 시)
load_dotenv()

# 환경변수에서 설정 읽기
NOTION_TOKEN = os.getenv('NOTION_TOKEN')
JIRA_BASE_URL = os.getenv('JIRA_BASE_URL', 'https://ssafy.atlassian.net')
JIRA_EMAIL = os.getenv('JIRA_EMAIL')
JIRA_TOKEN = os.getenv('JIRA_TOKEN')
NOTION_ISSUES_DB_ID = os.getenv('NOTION_ISSUES_DB_ID')  # 메인 이슈 DB
NOTION_ACTIVITIES_DB_ID = os.getenv('NOTION_ACTIVITIES_DB_ID')  # 개발 활동 DB
GITLAB_TOKEN = os.getenv('GITLAB_TOKEN')
GITLAB_PROJECT_ID = os.getenv('GITLAB_PROJECT_ID')
GITLAB_BASE_URL = os.getenv('GITLAB_BASE_URL', 'https://lab.ssafy.com')

# 필수 환경변수 체크
required_vars = [NOTION_TOKEN, JIRA_EMAIL, JIRA_TOKEN, NOTION_ISSUES_DB_ID]
if not all(required_vars):
    print("❌ 필수 환경변수가 설정되지 않았습니다!")
    print(f"NOTION_TOKEN: {'✅ 설정됨' if NOTION_TOKEN else '❌ 없음'}")
    print(f"JIRA_EMAIL: {'✅ 설정됨' if JIRA_EMAIL else '❌ 없음'}")
    print(f"JIRA_TOKEN: {'✅ 설정됨' if JIRA_TOKEN else '❌ 없음'}")
    print(f"NOTION_ISSUES_DB_ID: {'✅ 설정됨' if NOTION_ISSUES_DB_ID else '❌ 없음'}")
    exit(1)

# GitLab 설정 확인
if GITLAB_TOKEN and GITLAB_PROJECT_ID and NOTION_ACTIVITIES_DB_ID:
    print("✅ GitLab 연동 활성화됨")
    GITLAB_ENABLED = True
else:
    print("⚠️ GitLab 연동 비활성화됨 (일부 환경변수 없음)")
    GITLAB_ENABLED = False

print("✅ 모든 필수 환경변수가 올바르게 설정되었습니다.")

# API 헤더들
notion_headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

jira_headers = {
    "Content-Type": "application/json"
}

gitlab_headers = {
    "Authorization": f"Bearer {GITLAB_TOKEN}",
    "Content-Type": "application/json"
} if GITLAB_TOKEN else {}

def get_notion_issues():
    """Notion 이슈 DB에서 새로운 이슈 가져오기 (Jira 키가 없는 것들)"""
    url = f"https://api.notion.com/v1/databases/{NOTION_ISSUES_DB_ID}/query"
    
    payload = {
        "filter": {
            "property": "Jira 이슈 키",
            "rich_text": {
                "is_empty": True
            }
        }
    }
    
    response = requests.post(url, headers=notion_headers, json=payload)
    
    if response.status_code == 200:
        return response.json()["results"]
    else:
        print(f"❌ Notion 이슈 조회 오류: {response.status_code} - {response.text}")
        return []

def get_all_notion_issues():
    """메인 이슈 DB에서 모든 이슈 가져오기 (GitLab 연동용)"""
    url = f"https://api.notion.com/v1/databases/{NOTION_ISSUES_DB_ID}/query"
    
    response = requests.post(url, headers=notion_headers, json={})
    
    if response.status_code == 200:
        return response.json()["results"]
    else:
        print(f"❌ 이슈 DB 조회 오류: {response.status_code} - {response.text}")
        return []

def create_jira_issue(notion_page):
    """Notion 이슈를 기반으로 Jira 이슈 생성"""
    properties = notion_page["properties"]
    
    title = properties["제목"]["title"][0]["plain_text"] if properties["제목"]["title"] else "Untitled"
    description = properties["설명"]["rich_text"][0]["plain_text"] if properties["설명"]["rich_text"] else ""
    priority_map = {"높음": "High", "보통": "Medium", "낮음": "Low"}
    priority = priority_map.get(properties["우선순위"]["select"]["name"] if properties["우선순위"]["select"] else "보통", "Medium")
    
    print(f"🔄 Jira 이슈 생성 중: {title}")
    
    jira_payload = {
        "fields": {
            "project": {
                "key": "S13P21A402"
            },
            "summary": title,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": f"From Notion: {description}"
                            }
                        ]
                    }
                ]
            },
            "issuetype": {
                "name": "Task"
            },
            "priority": {
                "name": priority
            }
        }
    }
    
    jira_url = f"{JIRA_BASE_URL}/rest/api/3/issue"
    response = requests.post(
        jira_url,
        headers=jira_headers,
        json=jira_payload,
        auth=(JIRA_EMAIL, JIRA_TOKEN)
    )
    
    if response.status_code == 201:
        jira_issue = response.json()
        issue_key = jira_issue["key"]
        print(f"✅ Jira 이슈 생성 성공: {issue_key}")
        
        update_notion_page(notion_page["id"], issue_key)
        return issue_key
    else:
        print(f"❌ Jira 이슈 생성 실패: {response.status_code} - {response.text}")
        return None

def update_notion_page(page_id, jira_issue_key):
    """Notion 페이지에 Jira 이슈 키 업데이트"""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    
    payload = {
        "properties": {
            "Jira 이슈 키": {
                "rich_text": [
                    {
                        "text": {
                            "content": jira_issue_key
                        }
                    }
                ]
            },
            "마지막 동기화": {
                "date": {
                    "start": datetime.now().isoformat()
                }
            }
        }
    }
    
    response = requests.patch(url, headers=notion_headers, json=payload)
    
    if response.status_code == 200:
        print(f"✅ Notion 페이지 업데이트 성공: {jira_issue_key}")
    else:
        print(f"❌ Notion 페이지 업데이트 실패: {response.status_code} - {response.text}")

def sync_status_changes():
    """Notion의 상태 변경을 Jira에 동기화"""
    url = f"https://api.notion.com/v1/databases/{NOTION_ISSUES_DB_ID}/query"
    
    payload = {
        "filter": {
            "property": "Jira 이슈 키",
            "rich_text": {
                "is_not_empty": True
            }
        },
        "sorts": [
            {
                "property": "마지막 동기화",
                "direction": "ascending"
            }
        ]
    }
    
    response = requests.post(url, headers=notion_headers, json=payload)
    
    if response.status_code == 200:
        pages = response.json()["results"]
        print(f"🔄 상태 동기화 대상: {len(pages)}개 이슈")
        
        for page in pages:
            properties = page["properties"]
            jira_key = properties["Jira 이슈 키"]["rich_text"][0]["plain_text"] if properties["Jira 이슈 키"]["rich_text"] else None
            notion_status = properties["상태"]["select"]["name"] if properties["상태"]["select"] else None
            
            if jira_key and notion_status:
                update_jira_status(jira_key, notion_status)
                update_notion_page(page["id"], jira_key)
    else:
        print(f"❌ 상태 동기화 API 오류: {response.status_code} - {response.text}")

def update_jira_status(jira_key, notion_status):
    """Jira 이슈 상태 업데이트"""
    status_map = {
        "할 일": "11",
        "진행 중": "21",
        "완료": "31"
    }
    
    transition_id = status_map.get(notion_status)
    if not transition_id:
        print(f"⚠️ 매핑되지 않은 상태: {notion_status}")
        return
    
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{jira_key}/transitions"
    
    payload = {
        "transition": {
            "id": transition_id
        }
    }
    
    response = requests.post(
        url,
        headers=jira_headers,
        json=payload,
        auth=(JIRA_EMAIL, JIRA_TOKEN)
    )
    
    if response.status_code == 204:
        print(f"✅ Jira 상태 업데이트 성공: {jira_key} → {notion_status}")
    else:
        print(f"❌ Jira 상태 업데이트 실패: {jira_key} - {response.status_code}")

# GitLab 관련 함수들
def get_recent_gitlab_activities():
    """최근 GitLab 활동 가져오기"""
    if not GITLAB_ENABLED:
        return []
    
    # 최근 24시간 내 활동만 조회
    since = (datetime.now() - timedelta(hours=24)).isoformat()
    
    activities = []
    
    try:
        # 최근 커밋 조회
        commits_url = f"{GITLAB_BASE_URL}/api/v4/projects/{GITLAB_PROJECT_ID}/repository/commits"
        commits_params = {
            "since": since,
            "per_page": 20
        }
        
        commits_response = requests.get(
            commits_url, 
            headers=gitlab_headers, 
            params=commits_params
        )
        
        if commits_response.status_code == 200:
            commits = commits_response.json()
            for commit in commits:
                activities.append({
                    "type": "commit",
                    "title": commit["title"],
                    "message": commit["message"],
                    "author": commit["author_name"],
                    "date": commit["created_at"],
                    "url": commit["web_url"],
                    "id": commit["id"][:8]  # 짧은 ID만 사용
                })
        else:
            print(f"⚠️ GitLab 커밋 조회 실패: {commits_response.status_code}")
        
        # 최근 Merge Request 조회
        mrs_url = f"{GITLAB_BASE_URL}/api/v4/projects/{GITLAB_PROJECT_ID}/merge_requests"
        mrs_params = {
            "state": "all",
            "updated_after": since,
            "per_page": 10
        }
        
        mrs_response = requests.get(
            mrs_url,
            headers=gitlab_headers,
            params=mrs_params
        )
        
        if mrs_response.status_code == 200:
            mrs = mrs_response.json()
            for mr in mrs:
                activities.append({
                    "type": "merge_request",
                    "title": mr["title"],
                    "description": mr["description"],
                    "author": mr["author"]["name"],
                    "date": mr["updated_at"],
                    "url": mr["web_url"],
                    "state": mr["state"],
                    "id": str(mr["iid"])
                })
        else:
            print(f"⚠️ GitLab MR 조회 실패: {mrs_response.status_code}")
        
        print(f"🔍 GitLab 활동 {len(activities)}개 발견")
        return activities
        
    except Exception as e:
        print(f"❌ GitLab API 오류: {str(e)}")
        return []

def extract_jira_keys_from_text(text):
    """텍스트에서 Jira 이슈 키 추출"""
    if not text:
        return []
    
    # S13P21A402-123 패턴 찾기
    pattern = r'S13P21A402-\d+'
    return re.findall(pattern, text)

def create_gitlab_activity_in_notion(activity, related_issue_id):
    """GitLab 활동을 개발 활동 데이터베이스에 생성"""
    url = f"https://api.notion.com/v1/pages"
    
    # 활동 타입 매핑
    activity_type_map = {
        "commit": "커밋",
        "merge_request": "MR"
    }
    
    payload = {
        "parent": {
            "database_id": NOTION_ACTIVITIES_DB_ID
        },
        "properties": {
            "제목": {
                "title": [
                    {
                        "text": {
                            "content": activity["title"][:100]  # 제목 길이 제한
                        }
                    }
                ]
            },
            "관련 이슈": {  # Relation 필드
                "relation": [
                    {
                        "id": related_issue_id
                    }
                ]
            },
            "활동 타입": {
                "select": {
                    "name": activity_type_map.get(activity["type"], "기타")
                }
            },
            "GitLab 링크": {
                "url": activity["url"]
            },
            "작성자": {
                "rich_text": [
                    {
                        "text": {
                            "content": activity["author"]
                        }
                    }
                ]
            },
            "생성일": {
                "date": {
                    "start": activity["date"][:10]  # YYYY-MM-DD 형식
                }
            },
            "상태": {
                "select": {
                    "name": "완료" if activity.get("state") == "merged" else "진행중"
                }
            }
        }
    }
    
    response = requests.post(url, headers=notion_headers, json=payload)
    
    if response.status_code == 200:
        print(f"✅ 개발 활동 생성 성공: {activity['title'][:30]}...")
        return response.json()["id"]
    else:
        print(f"❌ 개발 활동 생성 실패: {response.status_code} - {response.text}")
        return None

def get_existing_activities():
    """기존 개발 활동 조회 (중복 방지용)"""
    if not NOTION_ACTIVITIES_DB_ID:
        return set()
        
    url = f"https://api.notion.com/v1/databases/{NOTION_ACTIVITIES_DB_ID}/query"
    
    # 최근 1주일 활동만 조회
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    
    payload = {
        "filter": {
            "property": "생성일",
            "date": {
                "after": week_ago[:10]
            }
        }
    }
    
    existing = set()
    
    try:
        response = requests.post(url, headers=notion_headers, json=payload)
        if response.status_code == 200:
            pages = response.json()["results"]
            for page in pages:
                # GitLab 링크에서 활동 식별자 추출
                properties = page["properties"]
                gitlab_url = properties.get("GitLab 링크", {}).get("url")
                if gitlab_url:
                    if "/commit/" in gitlab_url:
                        commit_id = gitlab_url.split("/commit/")[-1][:8]
                        existing.add(f"commit_{commit_id}")
                    elif "/merge_requests/" in gitlab_url:
                        mr_id = gitlab_url.split("/merge_requests/")[-1].split("#")[0]
                        existing.add(f"merge_request_{mr_id}")
    except Exception as e:
        print(f"⚠️ 기존 활동 조회 오류: {str(e)}")
    
    return existing

def update_notion_with_gitlab_activity():
    """GitLab 활동을 개발 활동 DB에 반영"""
    if not GITLAB_ENABLED:
        print("⚠️ GitLab 연동이 비활성화되어 있습니다.")
        return
    
    print("🔄 GitLab 활동을 개발 활동 DB에 동기화 중...")
    
    # GitLab 활동 가져오기
    gitlab_activities = get_recent_gitlab_activities()
    
    # 메인 이슈 DB에서 모든 이슈 가져오기
    notion_issues = get_all_notion_issues()
    
    # Jira 이슈 키별로 Notion 페이지 ID 매핑
    jira_to_notion = {}
    for issue in notion_issues:
        properties = issue["properties"]
        jira_key = None
        
        if properties.get("Jira 이슈 키") and properties["Jira 이슈 키"]["rich_text"]:
            jira_key = properties["Jira 이슈 키"]["rich_text"][0]["plain_text"]
        
        if jira_key:
            jira_to_notion[jira_key] = issue["id"]
    
    # 기존 활동 중복 체크
    existing_activities = get_existing_activities()
    
    # GitLab 활동을 개발 활동 DB에 생성
    new_activities = 0
    for activity in gitlab_activities:
        # 이미 존재하는 활동인지 확인
        activity_key = f"{activity['type']}_{activity['id']}"
        if activity_key in existing_activities:
            continue
            
        # 커밋 메시지나 MR 제목/설명에서 Jira 키 찾기
        text_to_search = f"{activity.get('title', '')} {activity.get('message', '')} {activity.get('description', '')}"
        jira_keys = extract_jira_keys_from_text(text_to_search)
        
        for jira_key in jira_keys:
            if jira_key in jira_to_notion:
                related_issue_id = jira_to_notion[jira_key]
                if create_gitlab_activity_in_notion(activity, related_issue_id):
                    new_activities += 1
                time.sleep(0.5)
                break  # 한 번만 생성
    
    print(f"📊 새로운 GitLab 활동 {new_activities}개가 개발 활동 DB에 추가됨")

def main():
    """메인 동기화 함수"""
    print("=" * 70)
    print("🚀 통합 동기화 시작 (Notion ↔ Jira ↔ GitLab)")
    print(f"📅 실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    try:
        # 1. 새로운 Notion 이슈를 Jira에 생성
        print("\n📋 1단계: Notion → Jira 이슈 생성")
        new_issues = get_notion_issues()
        print(f"🔍 새로운 이슈 {len(new_issues)}개 발견")
        
        success_count = 0
        for issue in new_issues:
            if create_jira_issue(issue):
                success_count += 1
            time.sleep(1)  # API 제한 고려
        
        print(f"📊 이슈 생성 완료: {success_count}/{len(new_issues)}")
        
        # 2. 상태 변경 동기화 (Notion → Jira)
        print("\n🔄 2단계: Notion → Jira 상태 동기화")
        sync_status_changes()
        
        # 3. GitLab 활동을 Notion에 반영 (GitLab이 활성화된 경우만)
        if GITLAB_ENABLED:
            print("\n🔗 3단계: GitLab → Notion 개발 활동 동기화")
            update_notion_with_gitlab_activity()
        else:
            print("\n⚠️ 3단계: GitLab 연동 건너뜀 (비활성화됨)")
        
        print("\n" + "=" * 70)
        print("✅ 통합 동기화 완료!")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ 동기화 중 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    main()
