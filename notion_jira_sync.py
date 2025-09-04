import requests
import json
import os
from datetime import datetime
from dotenv import load_dotenv
import time

# .env 파일 로드 (로컬 개발 시)
load_dotenv()

# 환경변수에서 설정 읽기
NOTION_TOKEN = os.getenv('NOTION_TOKEN')
JIRA_BASE_URL = os.getenv('JIRA_BASE_URL', 'https://ssafy.atlassian.net')
JIRA_EMAIL = os.getenv('JIRA_EMAIL')
JIRA_TOKEN = os.getenv('JIRA_TOKEN')
NOTION_DATABASE_ID = os.getenv('NOTION_DATABASE_ID')
NOTION_ISSUES_DB_ID = os.getenv('NOTION_ISSUES_DB_ID')  # 메인 이슈 DB
NOTION_ACTIVITIES_DB_ID = os.getenv('NOTION_ACTIVITIES_DB_ID')  # 개발 활동 DB

# 환경변수 체크
if not all([NOTION_TOKEN, JIRA_EMAIL, JIRA_TOKEN, NOTION_DATABASE_ID]):
    print("❌ 환경변수가 설정되지 않았습니다!")
    print(f"NOTION_TOKEN: {'✅ 설정됨' if NOTION_TOKEN else '❌ 없음'}")
    print(f"JIRA_EMAIL: {'✅ 설정됨' if JIRA_EMAIL else '❌ 없음'}")
    print(f"JIRA_TOKEN: {'✅ 설정됨' if JIRA_TOKEN else '❌ 없음'}")
    print(f"NOTION_DATABASE_ID: {'✅ 설정됨' if NOTION_DATABASE_ID else '❌ 없음'}")
    exit(1)

print("✅ 모든 환경변수가 올바르게 설정되었습니다.")

# Notion API 헤더
notion_headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# Jira API 헤더  
jira_headers = {
    "Content-Type": "application/json"
}

def get_notion_issues():
    """Notion 데이터베이스에서 새로운/수정된 이슈 가져오기"""
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    
    # Jira 이슈 키가 비어있는 항목들 찾기 (새로운 이슈)
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
        print(f"❌ Notion API 오류: {response.status_code} - {response.text}")
        return []

def create_jira_issue(notion_page):
    """Notion 이슈를 기반으로 Jira 이슈 생성"""
    
    # Notion 데이터 추출
    properties = notion_page["properties"]
    
    title = properties["제목"]["title"][0]["plain_text"] if properties["제목"]["title"] else "Untitled"
    description = properties["설명"]["rich_text"][0]["plain_text"] if properties["설명"]["rich_text"] else ""
    priority_map = {"높음": "High", "보통": "Medium", "낮음": "Low"}
    priority = priority_map.get(properties["우선순위"]["select"]["name"] if properties["우선순위"]["select"] else "보통", "Medium")
    
    print(f"🔄 Jira 이슈 생성 중: {title}")
    
    # Jira 이슈 생성 데이터
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
    
    # Jira API 호출
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
        
        # Notion 페이지에 Jira 이슈 키 업데이트
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
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    
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
    
    # 상태 매핑
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
                            "content": activity["title"]
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
        print(f"개발 활동 생성 성공: {activity['title'][:30]}...")
        return response.json()["id"]
    else:
        print(f"개발 활동 생성 실패: {response.status_code} - {response.text}")
        return None

def update_notion_with_gitlab_activity():
    """GitLab 활동을 개발 활동 DB에 반영"""
    if not (GITLAB_TOKEN and GITLAB_PROJECT_ID):
        print("GitLab 연동이 비활성화되어 있습니다.")
        return
    
    print("GitLab 활동을 개발 활동 DB에 동기화 중...")
    
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
    
    # 기존 활동 중복 체크를 위해 개발 활동 DB 조회
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
    
    print(f"새로운 GitLab 활동 {new_activities}개가 개발 활동 DB에 추가됨")

def get_existing_activities():
    """기존 개발 활동 조회 (중복 방지용)"""
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
                        commit_id = gitlab_url.split("/commit/")[-1]
                        existing.add(f"commit_{commit_id}")
                    elif "/merge_requests/" in gitlab_url:
                        mr_id = gitlab_url.split("/merge_requests/")[-1]
                        existing.add(f"merge_request_{mr_id}")
    except Exception as e:
        print(f"기존 활동 조회 오류: {str(e)}")
    
    return existing

def get_all_notion_issues():
    """메인 이슈 DB에서 모든 이슈 가져오기"""
    url = f"https://api.notion.com/v1/databases/{NOTION_ISSUES_DB_ID}/query"
    
    response = requests.post(url, headers=notion_headers, json={})
    
    if response.status_code == 200:
        return response.json()["results"]
    else:
        print(f"이슈 DB 조회 오류: {response.status_code} - {response.text}")
        return []

def main():
    """메인 동기화 함수"""
    print("=" * 50)
    print("🚀 Notion-Jira 동기화 시작")
    print(f"📅 실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    try:
        # 1. 새로운 Notion 이슈를 Jira에 생성
        new_issues = get_notion_issues()
        print(f"📋 새로운 이슈 {len(new_issues)}개 발견")
        
        success_count = 0
        for issue in new_issues:
            if create_jira_issue(issue):
                success_count += 1
            time.sleep(1)  # API 제한 고려
        
        print(f"📊 이슈 생성 완료: {success_count}/{len(new_issues)}")
        
        # 2. 상태 변경 동기화
        sync_status_changes()
        
        print("=" * 50)
        print("✅ 동기화 완료!")
        print("=" * 50)
        
    except Exception as e:
        print(f"❌ 동기화 중 오류 발생: {str(e)}")
        raise

if __name__ == "__main__":
    main()
