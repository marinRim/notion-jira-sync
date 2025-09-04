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