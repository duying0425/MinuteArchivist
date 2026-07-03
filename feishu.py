import re
import requests
import datetime
from sqlalchemy.orm import Session
from models import FeishuToken
from config import settings

def extract_minute_token(url_or_token: str) -> str:
    """
    Extract 24-char minute_token from URL or return raw if it looks like a token.
    e.g., https://sample.feishu.cn/minutes/obcnq3b9jl72l83w4f14xxxx -> obcnq3b9jl72l83w4f14xxxx
    """
    url_or_token = url_or_token.strip()
    if "/" in url_or_token:
        # Search for segment after /minutes/
        match = re.search(r"/minutes/([a-zA-Z0-9_-]{10,})", url_or_token)
        if match:
            return match.group(1)
    return url_or_token

def get_feishu_auth_url(state: str) -> str:
    """
    Generate Feishu OAuth Authorize URL.
    """
    return (
        f"https://open.feishu.cn/open-apis/authen/v1/index"
        f"?app_id={settings.FEISHU_APP_ID}"
        f"&redirect_uri={settings.FEISHU_REDIRECT_URI}"
        f"&state={state}"
    )

def exchange_code_for_token(code: str) -> dict:
    """
    Exchange auth code for user_access_token and refresh_token.
    """
    url = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
    headers = {
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.FEISHU_APP_ID,
        "client_secret": settings.FEISHU_APP_SECRET
    }
    
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    data = response.json()
    
    if data.get("code") != 0:
        raise Exception(f"Feishu OAuth error: {data.get('msg')}")
        
    return data.get("data", {})

def refresh_feishu_token(refresh_token: str) -> dict:
    """
    Refresh Feishu user_access_token.
    """
    url = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
    headers = {
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": settings.FEISHU_APP_ID,
        "client_secret": settings.FEISHU_APP_SECRET
    }
    
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    data = response.json()
    
    if data.get("code") != 0:
        raise Exception(f"Feishu token refresh error: {data.get('msg')}")
        
    return data.get("data", {})

def get_user_info(access_token: str) -> dict:
    """
    Get user profile details like name and avatar using access token.
    """
    url = "https://open.feishu.cn/open-apis/authen/v1/user_info"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    if data.get("code") != 0:
        raise Exception(f"Feishu get user info error: {data.get('msg')}")
    return data.get("data", {})

def get_valid_token(db_token: FeishuToken, db: Session) -> str:
    """
    Verify if token is expired, refresh it if needed, and return a valid access_token.
    """
    now = datetime.datetime.utcnow()
    # If token expires in less than 5 minutes, refresh it
    if now >= db_token.expires_at - datetime.timedelta(minutes=5):
        try:
            token_data = refresh_feishu_token(db_token.refresh_token)
            
            # Save new tokens to DB
            db_token.access_token = token_data["access_token"]
            db_token.refresh_token = token_data["refresh_token"]
            db_token.expires_at = now + datetime.timedelta(seconds=token_data["expires_in"])
            db_token.refresh_expires_at = now + datetime.timedelta(seconds=token_data["refresh_expires_in"])
            db_token.updated_at = now
            
            db.commit()
            db.refresh(db_token)
        except Exception as e:
            # If refresh fails, we could raise or handle
            raise Exception(f"Failed to refresh Feishu token: {str(e)}")
            
    return db_token.access_token

def get_minute_metadata(access_token: str, minute_token: str) -> dict:
    """
    Get meeting minutes metadata.
    """
    url = f"https://open.feishu.cn/open-apis/minutes/v1/minutes/{minute_token}"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    # Some apps might not have the get minute metadata scope, handle code != 0
    if data.get("code") != 0:
        return {}
    return data.get("data", {}).get("minute", {})

def download_minute_transcript(access_token: str, minute_token: str) -> str:
    """
    Download minute transcript file (text format).
    Returns the decoded text content of the transcript.
    """
    url = f"https://open.feishu.cn/open-apis/minutes/v1/minutes/{minute_token}/transcript"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    params = {
        "need_speaker": "true",
        "need_timestamp": "true",
        "file_format": "txt"
    }
    
    response = requests.get(url, headers=headers, params=params)
    
    # Handle common error responses that return JSON instead of file stream
    if response.status_code != 200:
        try:
            error_data = response.json()
            code = error_data.get("code")
            msg = error_data.get("msg")
            if code == 2091003:
                raise Exception("妙记仍在处理转写中，请稍后再试 (Minutes are not ready)")
            elif code == 2091002:
                raise Exception("未找到该妙记资源 (Minutes resource not found)")
            else:
                raise Exception(f"飞书妙记导出失败: {msg} (错误码: {code})")
        except ValueError:
            raise Exception(f"获取飞书妙记失败，HTTP 状态码: {response.status_code}")
            
    # Success, return text content (decode stream)
    return response.content.decode("utf-8")
