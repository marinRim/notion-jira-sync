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
NOTION_FRONTEND_DB_ID = os.getenv('NOTION_FRONTEND_DB_ID')  # 프론트엔드 이슈 DB
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

# 선택적 기능 확인
if NOTION_FRONTEND_DB_ID:
    print("✅ 프론트엔드 DB 연동 활성화됨")
    FRONTEND_ENABLED = True
else:
    print("⚠️ 프론트엔드 DB 연동 비활성화됨")
    FRONTEND_ENABLED = False

if GITLAB_TOKEN and GITLAB_PROJECT_ID and NOTION_ACTIVITIES_DB_ID:
    print("✅ GitLab 연동 활성화됨")
    GITLAB_ENABLED = True
else:
    print("⚠️ GitLab 연동 비활성화됨")
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

# 사용자 매핑 테이블
def get_jira_user_id(notion_person_name):
    """Notion 담당자명을 Jira 사용자 ID로 매핑"""
    user_mapping = {
        "marinrRim": "marinrim23@gmail.com"
        # 필요시 팀원 추가: "이름": "이메일@company.com"
    }
    
    jira_email = user_mapping.get(notion_person_name)
    if not jira_email:
        return None
    
    # Jira에서 사용자 검색
    search_url = f"{JIRA_BASE_URL}/rest/api/3/user/search"
    params = {"query": jira_email}
    
    response = requests.get(
        search_url,
        headers=jira_headers,
        params=params,
        auth=(JIRA_EMAIL, JIRA_TOKEN)
    )
    
    if response.status_code == 200:
        users = response.json()
        if users:
            return users[0]["accountId"]
    
    return None

# 메인 이슈 DB 관련 함수들
def get_notion_issues():
    """메인 이슈 DB에서 새로운 이슈 가져오기"""
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
        print(f"❌ 메인 이슈 조회 오류: {response.status_code} - {response.text}")
        return []

def get_updated_notion_issues():
    """메인 이슈 DB에서 최근 수정된 이슈들 가져오기"""
    url = f"https://api.notion.com/v1/databases/{NOTION_ISSUES_DB_ID}/query"
    
    one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
    
    payload = {
        "filter": {
            "and": [
                {
                    "property": "Jira 이슈 키",
                    "rich_text": {
                        "is_not_empty": True
                    }
                },
                {
                    "property": "마지막 동기화",
                    "date": {
                        "before": one_hour_ago
                    }
                }
            ]
        },
        "sorts": [
            {
                "property": "Last edited time",
                "direction": "descending"
            }
        ]
    }
    
    response = requests.post(url, headers=notion_headers, json=payload)
    
    if response.status_code == 200:
        results = response.json()["results"]
        updated_issues = []
        for issue in results:
            last_edited = issue["last_edited_time"]
            last_sync = None
            
            if issue["properties"].get("마지막 동기화") and issue["properties"]["마지막 동기화"]["date"]:
                last_sync = issue["properties"]["마지막 동기화"]["date"]["start"]
            
            if not last_sync or last_edited > last_sync:
                updated_issues.append(issue)
        
        return updated_issues
    else:
        print(f"❌ 수정된 메인 이슈 조회 오류: {response.status_code} - {response.text}")
        return []

def get_all_notion_issues():
    """메인 이슈 DB에서 모든 이슈 가져오기"""
    url = f"https://api.notion.com/v1/databases/{NOTION_ISSUES_DB_ID}/query"
    
    response = requests.post(url, headers=notion_headers, json={})
    
    if response.status_code == 200:
        return response.json()["results"]
    else:
        print(f"❌ 메인 이슈 DB 조회 오류: {response.status_code} - {response.text}")
        return []

def create_jira_issue(notion_page):
    """메인 이슈를 기반으로 Jira 이슈 생성"""
    properties = notion_page["properties"]
    
    title = properties["제목"]["title"][0]["plain_text"] if properties["제목"]["title"] else "Untitled"
    description = properties["설명"]["rich_text"][0]["plain_text"] if properties["설명"]["rich_text"] else ""
    priority_map = {"높음": "High", "보통": "Medium", "낮음": "Low"}
    priority = priority_map.get(properties["우선순위"]["select"]["name"] if properties["우선순위"]["select"] else "보통", "Medium")
    
    # 담당자 처리
    assignee_account_id = None
    if properties.get("담당자") and properties["담당자"]["people"]:
        notion_person = properties["담당자"]["people"][0]["name"]
        assignee_account_id = get_jira_user_id(notion_person)
        print(f"담당자 매핑: {notion_person} → {assignee_account_id}")
    
    print(f"🔄 메인 Jira 이슈 생성 중: {title}")
    
    jira_payload = {
        "fields": {
            "project": {"key": "S13P21A402"},
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
                                "text": f"From Notion (Main): {description}"
                            }
                        ]
                    }
                ]
            },
            "issuetype": {"name": "Task"},
            "priority": {"name": priority}
        }
    }
    
    # 담당자가 매핑된 경우에만 추가
    if assignee_account_id:
        jira_payload["fields"]["assignee"] = {"accountId": assignee_account_id}
    
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
        print(f"✅ 메인 Jira 이슈 생성 성공: {issue_key}")
        
        update_notion_page(notion_page["id"], issue_key)
        return issue_key
    else:
        print(f"❌ 메인 Jira 이슈 생성 실패: {response.status_code} - {response.text}")
        return None

# 프론트엔드 이슈 DB 관련 함수들
def get_frontend_issues():
    """프론트엔드 DB에서 새로운 이슈 가져오기"""
    if not FRONTEND_ENABLED:
        return []
    
    url = f"https://api.notion.com/v1/databases/{NOTION_FRONTEND_DB_ID}/query"
    
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
        print(f"❌ 프론트엔드 이슈 조회 오류: {response.status_code} - {response.text}")
        return []

def get_updated_frontend_issues():
    """프론트엔드 DB에서 최근 수정된 이슈들 가져오기"""
    if not FRONTEND_ENABLED:
        return []
    
    url = f"https://api.notion.com/v1/databases/{NOTION_FRONTEND_DB_ID}/query"
    
    one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
    
    payload = {
        "filter": {
            "and": [
                {
                    "property": "Jira 이슈 키",
                    "rich_text": {
                        "is_not_empty": True
                    }
                },
                {
                    "property": "마지막 동기화",
                    "date": {
                        "before": one_hour_ago
                    }
                }
            ]
        },
        "sorts": [
            {
                "property": "Last edited time",
                "direction": "descending"
            }
        ]
    }
    
    response = requests.post(url, headers=notion_headers, json=payload)
    
    if response.status_code == 200:
        results = response.json()["results"]
        updated_issues = []
        for issue in results:
            last_edited = issue["last_edited_time"]
            last_sync = None
            
            if issue["properties"].get("마지막 동기화") and issue["properties"]["마지막 동기화"]["date"]:
                last_sync = issue["properties"]["마지막 동기화"]["date"]["start"]
            
            if not last_sync or last_edited > last_sync:
                updated_issues.append(issue)
        
        return updated_issues
    else:
        print(f"❌ 수정된 프론트엔드 이슈 조회 오류: {response.status_code} - {response.text}")
        return []

def get_all_frontend_issues():
    """프론트엔드 DB에서 모든 이슈 가져오기"""
    if not FRONTEND_ENABLED:
        return []
    
    url = f"https://api.notion.com/v1/databases/{NOTION_FRONTEND_DB_ID}/query"
    
    response = requests.post(url, headers=notion_headers, json={})
    
    if response.status_code == 200:
        return response.json()["results"]
    else:
        print(f"❌ 프론트엔드 이슈 DB 조회 오류: {response.status_code} - {response.text}")
        return []

def create_frontend_jira_issue(notion_page):
    """프론트엔드 이슈를 기반으로 Jira 이슈 생성"""
    properties = notion_page["properties"]
    
    title = properties["제목"]["title"][0]["plain_text"] if properties["제목"]["title"] else "Untitled"
    description = properties["설명"]["rich_text"][0]["plain_text"] if properties["설명"]["rich_text"] else ""
    priority_map = {"높음": "High", "보통": "Medium", "낮음": "Low"}
    priority = priority_map.get(properties["우선순위"]["select"]["name"] if properties["우선순위"]["select"] else "보통", "Medium")
    
    # 프론트엔드 특화 정보 추출
    component = properties["컴포넌트"]["select"]["name"] if properties.get("컴포넌트") and properties["컴포넌트"]["select"] else None
    device = properties["디바이스"]["select"]["name"] if properties.get("디바이스") and properties["디바이스"]["select"] else None
    browsers = []
    if properties.get("브라우저") and properties["브라우저"]["multi_select"]:
        browsers = [item["name"] for item in properties["브라우저"]["multi_select"]]
    
    # 담당자 처리
    assignee_account_id = None
    if properties.get("담당자") and properties["담당자"]["people"]:
        notion_person = properties["담당자"]["people"][0]["name"]
        assignee_account_id = get_jira_user_id(notion_person)
        print(f"프론트엔드 담당자 매핑: {notion_person} → {assignee_account_id}")
    
    print(f"🔄 프론트엔드 Jira 이슈 생성 중: {title}")
    
    # 라벨 구성
    labels = ["Frontend"]
    if component:
        labels.append(f"Component:{component}")
    if device:
        labels.append(f"Device:{device}")
    if browsers:
        labels.extend([f"Browser:{browser}" for browser in browsers])
    
    # 설명에 프론트엔드 정보 포함
    frontend_info = []
    if component:
        frontend_info.append(f"컴포넌트: {component}")
    if device:
        frontend_info.append(f"디바이스: {device}")
    if browsers:
        frontend_info.append(f"브라우저: {', '.join(browsers)}")
    
    full_description = f"From Notion (Frontend): {description}"
    if frontend_info:
        full_description += f"\n\n--- 프론트엔드 정보 ---\n" + "\n".join(frontend_info)
    
    jira_payload = {
        "fields": {
            "project": {"key": "S13P21A402"},
            "summary": f"[FE] {title}",  # 프론트엔드 태그
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": full_description
                            }
                        ]
                    }
                ]
            },
            "issuetype": {"name": "Task"},
            "priority": {"name": priority},
            "labels": labels
        }
    }
    
    # 담당자가 매핑된 경우에만 추가
    if assignee_account_id:
        jira_payload["fields"]["assignee"] = {"accountId": assignee_account_id}
    
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
        print(f"✅ 프론트엔드 Jira 이슈 생성 성공: {issue_key}")
        
        update_frontend_notion_page(notion_page["id"], issue_key)
        return issue_key
    else:
        print(f"❌ 프론트엔드 Jira 이슈 생성 실패: {response.status_code} - {response.text}")
        return None

# 공통 업데이트 함수들
def update_notion_page(page_id, jira_issue_key):
    """메인 Notion 페이지에 Jira 이슈 키 업데이트"""
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
        print(f"✅ 메인 Notion 페이지 업데이트 성공: {jira_issue_key}")
    else:
        print(f"❌ 메인 Notion 페이지 업데이트 실패: {response.status_code} - {response.text}")

def update_frontend_notion_page(page_id, jira_issue_key):
    """프론트엔드 Notion 페이지에 Jira 이슈 키 업데이트"""
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
        print(f"✅ 프론트엔드 Notion 페이지 업데이트 성공: {jira_issue_key}")
    else:
        print(f"❌ 프론트엔드 Notion 페이지 업데이트 실패: {response.status_code} - {response.text}")

def update_existing_jira_issue(notion_page):
    """기존 Jira 이슈를 Notion 내용으로 업데이트"""
    properties = notion_page["properties"]
    
    if not properties.get("Jira 이슈 키") or not properties["Jira 이슈 키"]["rich_text"]:
        return False
    
    jira_key = properties["Jira 이슈 키"]["rich_text"][0]["plain_text"]
    
    title = properties["제목"]["title"][0]["plain_text"] if properties["제목"]["title"] else "Untitled"
    description = properties["설명"]["rich_text"][0]["plain_text"] if properties["설명"]["rich_text"] else ""
    priority_map = {"높음": "High", "보통": "Medium", "낮음": "Low"}
    priority = priority_map.get(properties["우선순위"]["select"]["name"] if properties["우선순위"]["select"] else "보통", "Medium")
    
    print(f"🔄 Jira 이슈 업데이트 중: {jira_key} - {title}")
    
    update_payload = {
        "fields": {
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
                                "text": f"Updated from Notion: {description}"
                            }
                        ]
                    }
                ]
            },
            "priority": {"name": priority}
        }
    }
    
    jira_url = f"{JIRA_BASE_URL}/rest/api/3/issue/{jira_key}"
    response = requests.put(
        jira_url,
        headers=jira_headers,
        json=update_payload,
        auth=(JIRA_EMAIL, JIRA_TOKEN)
    )
    
    if response.status_code == 204:
        print(f"✅ Jira 이슈 업데이트 성공: {jira_key}")
        update_notion_page(notion_page["id"], jira_key)
        return True
    else:
        print(f"❌ Jira 이슈 업데이트 실패: {jira_key} - {response.status_code}")
        return False

# 상태 동기화 함수들
def sync_status_changes():
    """메인 DB의 상태 변경을 Jira에 동기화"""
    url = f"https://api.notion.com/v1/databases/{NOTION_ISSUES_DB_ID}/query"
    
    payload = {
        "filter": {
            "property": "Jira 이슈 키",
            "rich_text": {
                "is_not_empty": True
            }
        }
    }
    
    response = requests.post(url, headers=notion_headers, json=payload)
    
    if response.status_code == 200:
        pages = response.json()["results"]
        print(f"🔄 메인 상태 동기화 대상: {len(pages)}개 이슈")
        
        for page in pages:
            properties = page["properties"]
            jira_key = properties["Jira 이슈 키"]["rich_text"][0]["plain_text"] if properties["Jira 이슈 키"]["rich_text"] else None
            notion_status = properties["상태"]["select"]["name"] if properties["상태"]["select"] else None
            
            if jira_key and notion_status:
                update_jira_status(jira_key, notion_status)
                update_notion_page(page["id"], jira_key)
    else:
        print(f"❌ 메인 상태 동기화 API 오류: {response.status_code} - {response.text}")

def sync_frontend_status_changes():
    """프론트엔드 DB의 상태 변경을 Jira에 동기화"""
    if not FRONTEND_ENABLED:
        return
    
    url = f"https://api.notion.com/v1/databases/{NOTION_FRONTEND_DB_ID}/query"
    
    payload = {
        "filter": {
            "property": "Jira 이슈 키",
            "rich_text": {
                "is_not_empty": True
            }
        }
    }
    
    response = requests.post(url, headers=notion_headers, json=payload)
    
    if response.status_code == 200:
        pages = response.json()["results"]
        print(f"🔄 프론트엔드 상태 동기화 대상: {len(pages)}개 이슈")
        
        for page in pages:
            properties = page["properties"]
            jira_key = properties["Jira 이슈 키"]["rich_text"][0]["plain_text"] if properties["Jira 이슈 키"]["rich_text"] else None
            notion_status = properties["상태"]["select"]["name"] if properties["상태"]["select"] else None
            
            if jira_key and notion_status:
                update_jira_status(jira_key, notion_status)
                update_frontend_notion_page(page["id"], jira_key)
    else:
        print(f"❌ 프론트엔드 상태 동기화 API 오류: {response.status_code} - {response.text}")

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
    
    since = (datetime.now() - timedelta(hours=24)).isoformat()
    activities = []
    
    try:
        # 커밋 조회
        commits_url = f"{GITLAB_BASE_URL}/api/v4/projects/{GITLAB_PROJECT_ID}/repository/commits"
        commits_params = {"since": since, "per_page": 20}
        
        commits_response = requests.get(commits_url, headers=gitlab_headers, params=commits_params)
        
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
                    "id": commit["id"][:8]
                })
        
        # MR 조회
        mrs_url = f"{GITLAB_BASE_URL}/api/v4/projects/{GITLAB_PROJECT_ID}/merge_requests"
        mrs_params = {"state": "all", "updated_after": since, "per_page": 10}
        
        mrs_response = requests.get(mrs_url, headers=gitlab_headers, params=mrs_params)
        
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
        
        print(f"🔍 GitLab 활동 {len(activities)}개 발견")
        return activities
        
    except Exception as e:
        print(f"❌ GitLab API 오류: {str(e)}")
        return []

def extract_jira_keys_from_text(text):
    """텍스트에서 Jira 이슈 키 추출"""
    if not text:
        return []
    
    pattern = r'S13P21A402-\d+'
    return re.findall(pattern, text)

def create_gitlab_activity_in_notion(activity, related_issue_id):
    """GitLab 활동을 개발 활동 데이터베이스에 생성"""
    url = f"https://api.notion.com/v1/pages"
    
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
                            "content": activity["title"][:100]
                        }
                    }
                ]
            },
            "관련 이슈": {
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
                    "start": activity["date"][:10]
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
    """GitLab 활동을 개발 활동 DB에 반영 (메인 + 프론트엔드 통합)"""
    if not GITLAB_ENABLED:
        print("⚠️ GitLab 연동이 비활성화되어 있습니다.")
        return
    
    print("🔄 GitLab 활동을 개발 활동 DB에 동기화 중...")
    
    gitlab_activities = get_recent_gitlab_activities()
    
    # 메인 + 프론트엔드 이슈 모두 가져오기
    notion_issues = get_all_notion_issues()
    frontend_issues = get_all_frontend_issues()
    all_issues = notion_issues + frontend_issues
    
    # Jira 이슈 키별로 Notion 페이지 ID 매핑
    jira_to_notion = {}
    for issue in all_issues:
        properties = issue["properties"]
        jira_key = None
        
        if properties.get("Jira 이슈 키") and properties["Jira 이슈 키"]["rich_text"]:
            jira_key = properties["Jira 이슈 키"]["rich_text"][0]["plain_text"]
        
        if jira_key:
            jira_to_notion[jira_key] = issue["id"]
    
    existing_activities = get_existing_activities()
    
    new_activities = 0
    for activity in gitlab_activities:
        activity_key = f"{activity['type']}_{activity['id']}"
        if activity_key in existing_activities:
            continue
            
        text_to_search = f"{activity.get('title', '')} {activity.get('message', '')} {activity.get('description', '')}"
        jira_keys = extract_jira_keys_from_text(text_to_search)
        
        for jira_key in jira_keys:
            if jira_key in jira_to_notion:
                related_issue_id = jira_to_notion[jira_key]
                if create_gitlab_activity_in_notion(activity, related_issue_id):
                    new_activities += 1
                time.sleep(0.5)
                break
    
    print(f"📊 새로운 GitLab 활동 {new_activities}개가 개발 활동 DB에 추가됨")

def sync_notion_updates():
    """Notion에서 수정된 내용을 Jira에 반영"""
    print("🔄 Notion 수정사항을 Jira에 동기화 중...")
    
    # 메인 이슈 DB 수정사항
    updated_main_issues = get_updated_notion_issues()
    print(f"최근 수정된 메인 이슈 {len(updated_main_issues)}개 발견")
    
    success_count = 0
    for issue in updated_main_issues:
        if update_existing_jira_issue(issue):
            success_count += 1
        time.sleep(1)
    
    print(f"메인 이슈 업데이트 완료: {success_count}/{len(updated_main_issues)}")
    
    # 프론트엔드 이슈 DB 수정사항 (활성화된 경우)
    if FRONTEND_ENABLED:
        updated_frontend_issues = get_updated_frontend_issues()
        print(f"최근 수정된 프론트엔드 이슈 {len(updated_frontend_issues)}개 발견")
        
        fe_success_count = 0
        for issue in updated_frontend_issues:
            if update_existing_jira_issue(issue):  # 같은 업데이트 함수 재사용
                fe_success_count += 1
            time.sleep(1)
        
        print(f"프론트엔드 이슈 업데이트 완료: {fe_success_count}/{len(updated_frontend_issues)}")

def sync_assignee_changes():
    """담당자 변경사항만 별도로 동기화 (빠른 처리)"""
    print("담당자 변경사항 동기화 시작...")
    
    try:
        detect_assignee_changes()
        print("담당자 변경사항 동기화 완료")
    except Exception as e:
        print(f"담당자 동기화 중 오류: {str(e)}")

def main():
    """메인 동기화 함수 - 담당자 변경 감지 포함"""
    print("=" * 80)
    print("🚀 완전한 통합 동기화 시작 (메인+프론트엔드+수정감지+담당자변경+GitLab)")
    print(f"📅 실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    try:
        # 1. 새로운 이슈 생성 (메인)
        print("\n📋 1단계: 메인 이슈 DB → Jira")
        new_issues = get_notion_issues()
        print(f"🔍 새로운 메인 이슈 {len(new_issues)}개 발견")
        
        main_success = 0
        for issue in new_issues:
            if create_jira_issue(issue):
                main_success += 1
            time.sleep(1)
        
        print(f"📊 메인 이슈 생성 완료: {main_success}/{len(new_issues)}")
        
        # 2. 새로운 이슈 생성 (프론트엔드)
        if FRONTEND_ENABLED:
            print("\n🎨 1-2단계: 프론트엔드 이슈 DB → Jira")
            frontend_issues = get_frontend_issues()
            print(f"🔍 새로운 프론트엔드 이슈 {len(frontend_issues)}개 발견")
            
            fe_success = 0
            for issue in frontend_issues:
                if create_frontend_jira_issue(issue):
                    fe_success += 1
                time.sleep(1)
            
            print(f"📊 프론트엔드 이슈 생성 완료: {fe_success}/{len(frontend_issues)}")
        else:
            print("\n⚠️ 1-2단계: 프론트엔드 DB 건너뜀 (비활성화됨)")
        
        # 3. 수정된 이슈 업데이트 (담당자 변경 포함)
        print("\n✏️ 2단계: 수정된 이슈 → Jira 업데이트")
        sync_notion_updates()
        
        # 4. 담당자 변경사항 별도 처리 (빠른 동기화)
        print("\n👤 2-2단계: 담당자 변경사항 동기화")
        sync_assignee_changes()
        
        # 5. 상태 동기화 (메인)
        print("\n🔄 3단계: 메인 이슈 상태 동기화")
        sync_status_changes()
        
        # 6. 상태 동기화 (프론트엔드)
        if FRONTEND_ENABLED:
            print("\n🔄 3-2단계: 프론트엔드 이슈 상태 동기화")
            sync_frontend_status_changes()
        
        # 7. GitLab 활동 동기화
        if GITLAB_ENABLED:
            print("\n🔗 4단계: GitLab → Notion 개발 활동 동기화")
            update_notion_with_gitlab_activity()
        else:
            print("\n⚠️ 4단계: GitLab 연동 건너뜀 (비활성화됨)")
        
        print("\n" + "=" * 80)
        print("✅ 완전한 통합 동기화 완료!")
        print("🎯 처리된 항목: 이슈 생성, 내용 수정, 담당자 변경, 상태 동기화, GitLab 활동")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 동기화 중 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    main()