import os
import re
import uuid
import json
import datetime
import subprocess
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from config import settings
from database import engine, get_db, SessionLocal, Base
from models import User, FeishuToken, Task
from schemas import (
    UserCreate, UserResponse, Token,
    TaskResponse, TaskCreateFeishu, TaskUpdateSpeakerMap
)
from auth import (
    get_password_hash, verify_password, create_access_token, get_current_user
)
from feishu import (
    get_feishu_auth_url, exchange_code_for_token, get_user_info,
    get_valid_token, get_minute_metadata, download_minute_transcript,
    extract_minute_token
)
from asr import process_local_asr_task, HAS_WHISPER
from parser import generate_markdown

# Create database tables automatically
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="妙记归档员 (MinuteArchivist)",
    description="音频转 Markdown 知识管理工具",
    version="1.0.0"
)

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Background processing for Feishu tasks
def process_feishu_task(task_id: str):
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return
            
        task.status = "processing"
        task.progress = 15
        task.error_message = "正在准备飞书鉴权凭证..."
        db.commit()
        
        user = task.user
        if not user.feishu_token:
            task.status = "failed"
            task.progress = 0
            task.error_message = "获取失败：当前用户尚未绑定飞书账号"
            db.commit()
            return
            
        # Refresh and get valid token
        try:
            access_token = get_valid_token(user.feishu_token, db)
        except Exception as te:
            task.status = "failed"
            task.progress = 0
            task.error_message = f"飞书身份凭证刷新失败: {str(te)}"
            db.commit()
            return
            
        task.progress = 35
        task.error_message = "正在连接飞书并拉取妙记元数据..."
        db.commit()
        
        # Get metadata
        meta = get_minute_metadata(access_token, task.minute_token)
        if meta:
            task.title = meta.get("title", task.title or f"飞书妙记_{task.minute_token}")
            task.duration = float(meta.get("duration", 0)) / 1000.0  # seconds
            
        task.progress = 60
        task.error_message = "正在导出带说话人与时间戳的文字记录..."
        db.commit()
        
        # Download transcript text
        raw_transcript = download_minute_transcript(access_token, task.minute_token)
        
        # Save original raw transcript in result_markdown for speaker mapping regeneration
        task.result_markdown = raw_transcript
        
        task.progress = 85
        task.error_message = "正在编译渲染 Markdown 结构文档..."
        db.commit()
        
        # Generate markdown content
        speaker_map = json.loads(task.speaker_map) if task.speaker_map else {}
        markdown_content, speaker_count = generate_markdown(
            title=task.title or f"飞书妙记_{task.minute_token}",
            filename=task.filename or "飞书妙记云文档",
            method="feishu",
            duration_seconds=task.duration or 0.0,
            raw_text=raw_transcript,
            speaker_map=speaker_map,
            username=user.username
        )
        
        # Write markdown content to outputs folder
        output_filename = f"{task.id}.md"
        output_path = os.path.join(settings.OUTPUT_DIR, output_filename)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
            
        task.status = "completed"
        task.progress = 100
        task.error_message = None
        db.commit()
        
        # Send Feishu Bot Notification if user is bound
        if user.feishu_token:
            try:
                base_host = settings.FEISHU_REDIRECT_URI.replace("/api/auth/feishu/callback", "")
                download_url = f"{base_host}/api/tasks/public/{task.id}/download"
                from feishu import send_feishu_card_notification
                send_feishu_card_notification(
                    open_id=user.feishu_token.open_id,
                    task_title=task.title or "视频会议录制",
                    duration_seconds=task.duration or 0.0,
                    download_url=download_url
                )
            except Exception as notify_err:
                print(f"Failed to send Feishu Bot notification: {str(notify_err)}")
        
    except Exception as e:
        task.status = "failed"
        task.progress = 0
        task.error_message = str(e)
        db.commit()
    finally:
        db.close()

# Background processing for local tasks
def process_local_task(task_id: str):
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return
            
        # Run ASR transcription
        process_local_asr_task(task_id, db)
        
        # Reload task to get generated transcription text
        db.refresh(task)
        if task.status == "completed":
            # Generate markdown document using the parsed transcript
            speaker_map = json.loads(task.speaker_map) if task.speaker_map else {}
            markdown_content, speaker_count = generate_markdown(
                title=task.title or task.filename,
                filename=task.filename,
                method="local",
                duration_seconds=task.duration or 0.0,
                raw_text=task.result_markdown,
                speaker_map=speaker_map,
                username=task.user.username
            )
            
            # Save to disk
            output_filename = f"{task.id}.md"
            output_path = os.path.join(settings.OUTPUT_DIR, output_filename)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
                
            db.commit()
    except Exception as e:
        task.status = "failed"
        task.progress = 0
        task.error_message = f"本地音频转写与编译失败: {str(e)}"
        db.commit()
    finally:
        db.close()

# --- Auth APIs ---

@app.post("/api/auth/register", response_model=UserResponse)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user_in.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="用户名已被注册")
    hashed_pwd = get_password_hash(user_in.password)
    new_user = User(username=user_in.username, hashed_password=hashed_pwd)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/api/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/auth/me")
def get_me(current_user: User = Depends(get_current_user)):
    feishu_bound = current_user.feishu_token is not None
    feishu_info = None
    if feishu_bound:
        feishu_info = {
            "name": current_user.feishu_token.name,
            "avatar_url": current_user.feishu_token.avatar_url,
            "open_id": current_user.feishu_token.open_id
        }
    return {
        "id": current_user.id,
        "username": current_user.username,
        "feishu_bound": feishu_bound,
        "feishu_info": feishu_info
    }

# --- Feishu OAuth Binding & Login APIs ---

@app.get("/api/auth/feishu/login_url")
def get_feishu_login_url():
    """
    Generate Feishu OAuth Authorize URL for direct login/register.
    """
    return {"url": get_feishu_auth_url(state="login")}

@app.get("/api/auth/feishu/url")
def get_feishu_url(current_user: User = Depends(get_current_user)):
    # Use user's username or id as OAuth state to link them
    return {"url": get_feishu_auth_url(state=str(current_user.id))}

@app.get("/api/auth/feishu/callback")
def feishu_callback(code: str, state: str, db: Session = Depends(get_db)):
    """
    Feishu callback handler. Handles both direct login (state="login") and profile binding (state=user_id).
    Exchanges code for access/refresh token and closes window.
    """
    import secrets
    
    # 1. Exchange code for token
    try:
        token_data = exchange_code_for_token(code)
        user_info = get_user_info(token_data["access_token"])
    except Exception as e:
        return HTMLResponse(f"""
            <html>
            <head><title>授权失败</title></head>
            <body>
                <h3 style="text-align: center; font-family: sans-serif; margin-top: 50px; color: #ef4444;">
                    授权异常: {str(e)}
                </h3>
            </body>
            </html>
        """)

    open_id = token_data.get("open_id") or user_info.get("open_id")
    if not open_id:
        return HTMLResponse("<h3>授权失败：未获取到飞书用户的 OpenID。</h3>")

    now = datetime.datetime.utcnow()
    
    expires_in = token_data.get("expires_in")
    if expires_in is not None:
        expires_at = now + datetime.timedelta(seconds=int(expires_in))
    else:
        expires_at = now + datetime.timedelta(seconds=7200)

    refresh_token = token_data.get("refresh_token") or ""
    refresh_expires_in = token_data.get("refresh_expires_in")
    if refresh_expires_in is not None:
        refresh_expires_at = now + datetime.timedelta(seconds=int(refresh_expires_in))
    else:
        # Default to 30 days if refresh token is present, otherwise use now (no refresh available)
        refresh_expires_at = now + datetime.timedelta(days=30) if refresh_token else now

    # Case A: Direct Login & Register Flow
    if state == "login":
        try:
            # Check if this open_id is already bound
            db_token = db.query(FeishuToken).filter(FeishuToken.open_id == open_id).first()
            if db_token:
                user = db_token.user
                # Update tokens
                db_token.name = user_info.get("name", db_token.name)
                db_token.avatar_url = user_info.get("avatar_url", db_token.avatar_url)
                db_token.access_token = token_data["access_token"]
                db_token.refresh_token = refresh_token
                db_token.expires_at = expires_at
                db_token.refresh_expires_at = refresh_expires_at
                db_token.updated_at = now
                db.commit()
            else:
                # Create a new user automatically
                feishu_name = user_info.get("name") or f"feishu_{open_id[:8]}"
                username = feishu_name
                counter = 1
                while db.query(User).filter(User.username == username).first():
                    username = f"{feishu_name}_{counter}"
                    counter += 1
                
                random_password = secrets.token_hex(16)
                hashed_pwd = get_password_hash(random_password)
                user = User(username=username, hashed_password=hashed_pwd)
                db.add(user)
                db.commit()
                db.refresh(user)
                
                # Bind the Feishu token to this new user
                db_token = FeishuToken(
                    user_id=user.id,
                    open_id=open_id,
                    name=user_info.get("name"),
                    avatar_url=user_info.get("avatar_url"),
                    access_token=token_data["access_token"],
                    refresh_token=refresh_token,
                    expires_at=expires_at,
                    refresh_expires_at=refresh_expires_at
                )
                db.add(db_token)
                db.commit()

            # Generate local access token
            local_access_token = create_access_token(data={"sub": user.username})

            return HTMLResponse(f"""
                <html>
                <head><title>登录成功</title></head>
                <body>
                    <h3 style="text-align: center; font-family: sans-serif; margin-top: 50px; color: #10b981;">
                        飞书登录成功！正在进入系统...
                    </h3>
                    <script>
                        window.opener.postMessage({{ type: 'FEISHU_LOGIN_SUCCESS', token: '{local_access_token}' }}, '*');
                        window.close();
                    </script>
                </body>
                </html>
            """)
        except Exception as e:
            return HTMLResponse(f"""
                <html>
                <head><title>登录失败</title></head>
                <body>
                    <h3 style="text-align: center; font-family: sans-serif; margin-top: 50px; color: #ef4444;">
                        登录注册流程异常: {str(e)}
                    </h3>
                </body>
                </html>
            """)

    # Case B: Standard Profile Binding Flow
    else:
        try:
            user_id = int(state)
        except ValueError:
            return HTMLResponse("<h3>授权失败：无效的授权状态 (state)。</h3>")

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return HTMLResponse("<h3>授权失败：未找到本地关联用户。</h3>")

        try:
            db_token = db.query(FeishuToken).filter(FeishuToken.user_id == user_id).first()
            if db_token:
                db_token.open_id = open_id
                db_token.name = user_info.get("name")
                db_token.avatar_url = user_info.get("avatar_url")
                db_token.access_token = token_data["access_token"]
                db_token.refresh_token = refresh_token
                db_token.expires_at = expires_at
                db_token.refresh_expires_at = refresh_expires_at
                db_token.updated_at = now
            else:
                db_token = FeishuToken(
                    user_id=user_id,
                    open_id=open_id,
                    name=user_info.get("name"),
                    avatar_url=user_info.get("avatar_url"),
                    access_token=token_data["access_token"],
                    refresh_token=refresh_token,
                    expires_at=expires_at,
                    refresh_expires_at=refresh_expires_at
                )
                db.add(db_token)
                
            db.commit()
            
            return HTMLResponse("""
                <html>
                <head><title>授权成功</title></head>
                <body>
                    <h3 style="text-align: center; font-family: sans-serif; margin-top: 50px; color: #10b981;">
                        飞书绑定成功！正在返回应用...
                    </h3>
                    <script>
                        window.opener.postMessage({ type: 'FEISHU_AUTH_SUCCESS' }, '*');
                        window.close();
                    </script>
                </body>
                </html>
            """)
        except Exception as e:
            return HTMLResponse(f"""
                <html>
                <head><title>授权失败</title></head>
                <body>
                    <h3 style="text-align: center; font-family: sans-serif; margin-top: 50px; color: #ef4444;">
                        绑定授权异常: {str(e)}
                    </h3>
                </body>
                </html>
            """)

@app.post("/api/auth/feishu/unbind")
def feishu_unbind(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db_token = db.query(FeishuToken).filter(FeishuToken.user_id == current_user.id).first()
    if not db_token:
        raise HTTPException(status_code=400, detail="未绑定飞书账号")
    db.delete(db_token)
    db.commit()
    return {"message": "解绑飞书账号成功"}

# --- Task Management APIs ---

@app.get("/api/tasks", response_model=List[TaskResponse])
def list_tasks(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tasks = db.query(Task).filter(Task.user_id == current_user.id).order_by(Task.created_at.desc()).all()
    # Decode speaker_map from JSON String to dict before returning
    for t in tasks:
        if t.speaker_map:
            t.speaker_map = json.loads(t.speaker_map)
    return tasks

@app.post("/api/tasks/feishu", response_model=TaskResponse)
def create_feishu_task(
    payload: TaskCreateFeishu,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not current_user.feishu_token:
        raise HTTPException(status_code=400, detail="尚未绑定飞书，请先在右上角绑定飞书账号。")
        
    minute_token = extract_minute_token(payload.minute_url_or_token)
    if not minute_token:
        raise HTTPException(status_code=400, detail="无效的飞书妙记链接或 Token")
        
    # Check if duplicate active task is processing
    existing_task = db.query(Task).filter(
        Task.user_id == current_user.id,
        Task.minute_token == minute_token,
        Task.status.in_(["pending", "processing"])
    ).first()
    if existing_task:
        raise HTTPException(status_code=400, detail="该妙记转写任务已在处理队列中，请勿重复提交")
        
    task_id = str(uuid.uuid4())
    new_task = Task(
        id=task_id,
        user_id=current_user.id,
        task_type="feishu",
        status="pending",
        title=payload.title or f"飞书妙记_{minute_token}",
        minute_token=minute_token,
        progress=0
    )
    
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    
    background_tasks.add_task(process_feishu_task, task_id)
    
    return new_task

@app.post("/api/tasks/local", response_model=TaskResponse)
def create_local_task(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Check audio file extensions
    allowed_exts = {".mp3", ".wav", ".m4a", ".aac", ".mp4", ".ogg"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}。支持 mp3/wav/m4a/aac/mp4")
        
    task_id = str(uuid.uuid4())
    
    # Save uploaded file
    safe_filename = f"{task_id}{ext}"
    dest_path = os.path.join(settings.UPLOAD_DIR, safe_filename)
    
    # Read and save file content
    try:
        content = file.file.read()
        file_size = len(content)
        with open(dest_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存音频文件失败: {str(e)}")
        
    new_task = Task(
        id=task_id,
        user_id=current_user.id,
        task_type="local",
        status="pending",
        title=title or file.filename,
        filename=safe_filename,
        file_size=file_size,
        progress=0
    )
    
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    
    background_tasks.add_task(process_local_task, task_id)
    
    return new_task

@app.get("/api/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.speaker_map:
        task.speaker_map = json.loads(task.speaker_map)
    return task

@app.post("/api/tasks/{task_id}/update_speaker_map", response_model=TaskResponse)
def update_speaker_map(
    task_id: str,
    payload: TaskUpdateSpeakerMap,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="只能修改已完成任务的说话人映射")
        
    # Save mapping in DB
    task.speaker_map = json.dumps(payload.speaker_map)
    
    # Regenerate markdown file based on the original raw transcript stored in result_markdown
    try:
        markdown_content, speaker_count = generate_markdown(
            title=task.title or f"音频任务_{task.id}",
            filename=task.filename or "飞书妙记云文档",
            method=task.task_type,
            duration_seconds=task.duration or 0.0,
            raw_text=task.result_markdown,
            speaker_map=payload.speaker_map,
            username=current_user.username
        )
        
        # Save to disk
        output_filename = f"{task.id}.md"
        output_path = os.path.join(settings.OUTPUT_DIR, output_filename)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
            
        db.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新说话人重新编译 Markdown 失败: {str(e)}")
        
    # Set helper speaker_map dict for schemas response
    task.speaker_map = payload.speaker_map
    return task

@app.get("/api/tasks/{task_id}/download")
def download_task_markdown(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="任务尚未处理完成，无法下载")
        
    output_filename = f"{task.id}.md"
    file_path = os.path.join(settings.OUTPUT_DIR, output_filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="导出的 Markdown 文件丢失")
        
    safe_title = re.sub(r'[\/:*?"<>|]', '_', task.title or "妙记归档员转写记录")
    download_name = f"{safe_title}.md"
    
    return FileResponse(
        path=file_path,
        media_type="text/markdown",
        filename=download_name
    )

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
        
    # Delete uploaded audio file if local task
    if task.task_type == "local" and task.filename:
        audio_path = os.path.join(settings.UPLOAD_DIR, task.filename)
        if os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except Exception:
                pass
                
    # Delete output markdown file
    output_filename = f"{task.id}.md"
    file_path = os.path.join(settings.OUTPUT_DIR, output_filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass
            
    db.delete(task)
    db.commit()
    return {"message": "任务已成功删除"}

# --- ASR Info ---
@app.get("/api/asr/status")
def get_asr_status():
    return {
        "has_whisper": HAS_WHISPER,
        "device": "CPU (faster-whisper)" if HAS_WHISPER else "Simulation Mode (仿真测试环境)"
    }

# --- Feishu Webhook Events & Public Download APIs ---

def process_webhook_recording_event(user_id: int, meeting_id: str, open_id: str):
    """
    Background worker triggered by Webhook recording event.
    Fetches recording url -> extracts minute_token -> creates task -> triggers process.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.feishu_token:
            return
            
        # Refresh and get valid token
        access_token = get_valid_token(user.feishu_token, db)
        
        # Get meeting recording information
        from feishu import get_meeting_recording
        recording_info = get_meeting_recording(access_token, meeting_id)
        
        file_list = recording_info.get("recording_file_list", [])
        if not file_list:
            print(f"No recording files found for meeting_id {meeting_id}")
            return
            
        url = file_list[0].get("url")
        if not url:
            return
            
        minute_token = extract_minute_token(url)
        if not minute_token:
            return
            
        # Check if task already exists to avoid duplication
        existing = db.query(Task).filter(
            Task.user_id == user.id,
            Task.minute_token == minute_token
        ).first()
        if existing:
            print(f"Task already exists for minute_token {minute_token}")
            return
            
        # Create new Feishu task
        task_id = str(uuid.uuid4())
        new_task = Task(
            id=task_id,
            user_id=user.id,
            task_type="feishu",
            status="pending",
            title=f"会议录制_{meeting_id[:8]}",
            minute_token=minute_token,
            progress=0
        )
        db.add(new_task)
        db.commit()
        
        # Trigger actual async transcription processing
        process_feishu_task(task_id)
    except Exception as e:
        print(f"Error processing webhook recording event: {str(e)}")
    finally:
        db.close()

def process_webhook_minute_event(user_id: int, minute_token: str):
    """
    Background worker triggered by Webhook minutes.minute.generated_v1 event.
    Creates task -> triggers process directly.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.feishu_token:
            return
            
        # Check if task already exists to avoid duplication
        existing = db.query(Task).filter(
            Task.user_id == user.id,
            Task.minute_token == minute_token
        ).first()
        if existing:
            if existing.status == "completed":
                print(f"Task already completed for minute_token {minute_token}")
                return
            elif existing.status in ["pending", "processing"]:
                print(f"Task is already in {existing.status} status for minute_token {minute_token}")
                return
            else:
                # If the task exists but failed (e.g., because minutes were not ready when recording_ready fired),
                # reset its status to pending and re-process it now that the minutes are generated.
                print(f"Task exists in status '{existing.status}'. Resetting and processing for minute_token {minute_token}")
                existing.status = "pending"
                existing.progress = 0
                existing.error_message = None
                db.commit()
                process_feishu_task(existing.id)
                return
            
        # Create new Feishu task
        task_id = str(uuid.uuid4())
        new_task = Task(
            id=task_id,
            user_id=user.id,
            task_type="feishu",
            status="pending",
            title=f"妙记整理_{minute_token[:8]}",
            minute_token=minute_token,
            progress=0
        )
        db.add(new_task)
        db.commit()
        
        # Trigger actual async transcription processing
        process_feishu_task(task_id)
    except Exception as e:
        print(f"Error processing webhook minute event: {str(e)}")
    finally:
        db.close()

from fastapi import Request

@app.post("/api/feishu/events")
async def feishu_events(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Feishu Open Platform Event webhook callback endpoint.
    Handles URL verification, recording completion, and manual upload/generation events.
    """
    body = await request.json()
    
    # 1. URL Verification challenge
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge")}
        
    # 2. Parse event headers
    header = body.get("header", {})
    event_type = header.get("event_type")
    
    if event_type == "vc.meeting.recording_ready_v1":
        event_data = body.get("event", {})
        meeting_id = event_data.get("meeting_id")
        
        operator = event_data.get("operator", {})
        open_id = operator.get("id", {}).get("open_id")
        
        if not meeting_id or not open_id:
            return {"status": "ignored", "reason": "missing meeting_id or open_id"}
            
        # Find local user bound to this Feishu open_id
        feishu_token = db.query(FeishuToken).filter(FeishuToken.open_id == open_id).first()
        if not feishu_token:
            return {"status": "ignored", "reason": "No bound local user found for this open_id"}
            
        user = feishu_token.user
        
        # Dispatch background task to fetch details and process
        background_tasks.add_task(process_webhook_recording_event, user.id, meeting_id, open_id)
        return {"status": "processing"}
        
    elif event_type == "minutes.minute.generated_v1":
        event_data = body.get("event", {})
        minute_token = event_data.get("minute_token")
        
        # Safe extraction of user open_id across possible payload variations
        open_id = None
        if "owner_id" in event_data:
            open_id = event_data["owner_id"].get("open_id")
        elif "user_id" in event_data:
            open_id = event_data["user_id"].get("open_id")
        elif "operator" in event_data:
            open_id = event_data["operator"].get("id", {}).get("open_id")
            
        if not minute_token or not open_id:
            return {"status": "ignored", "reason": "missing minute_token or open_id"}
            
        # Find local user bound to this Feishu open_id
        feishu_token = db.query(FeishuToken).filter(FeishuToken.open_id == open_id).first()
        if not feishu_token:
            return {"status": "ignored", "reason": "No bound local user found for this open_id"}
            
        user = feishu_token.user
        
        # Dispatch background task directly since minute_token is provided
        background_tasks.add_task(process_webhook_minute_event, user.id, minute_token)
        return {"status": "processing"}
        
    return {"status": "ignored", "reason": "event type not handled"}

@app.get("/api/tasks/public/{task_id}/download")
def public_download_task_markdown(task_id: str, db: Session = Depends(get_db)):
    """
    Unauthenticated read-only endpoint for downloading generated Markdown.
    Used by Feishu Bot Card download buttons.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="任务尚未处理完成，无法下载")
        
    output_filename = f"{task.id}.md"
    file_path = os.path.join(settings.OUTPUT_DIR, output_filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="导出的 Markdown 文件不存在或已丢失")
        
    safe_title = re.sub(r'[\/:*?"<>|]', '_', task.title or "会议记录")
    download_name = f"{safe_title}.md"
    
    return FileResponse(
        path=file_path,
        media_type="text/markdown",
        filename=download_name
    )

# --- Static frontend serving ---

# Ensure directories exist
os.makedirs("static", exist_ok=True)

# Cache busting: 用 git commit hash 作为静态资源版本号
# 每次部署新代码 commit hash 变化 → index.html 里 ?v=xxx 变化 →
# 浏览器和 Cloudflare 视为新 URL，不会命中旧缓存。
# 这是前端工程化的标准实践（类似 Webpack/Vite 的 [contenthash] 机制）。
def _get_app_version() -> str:
    """获取 git commit short hash 作为应用版本号，失败时回退到 app.js 的 mtime。"""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(os.path.abspath(__file__)) or ".",
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        try:
            return str(int(os.path.getmtime("static/app.js")))
        except OSError:
            return "0"

APP_VERSION = _get_app_version()

# 预读 index.html 并把 __APP_VERSION__ 占位符替换为实际版本号
# 这样 app.js?v=__APP_VERSION__ 和 style.css?v=__APP_VERSION__ 会被自动填充
def _render_index_html() -> str:
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read().replace("__APP_VERSION__", APP_VERSION)

INDEX_HTML = _render_index_html()

NO_STORE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}

@app.get("/", include_in_schema=False)
async def serve_index_root():
    """根路径返回注入版本号的 index.html（禁用缓存）。"""
    return HTMLResponse(content=INDEX_HTML, headers=NO_STORE_HEADERS)

@app.get("/index.html", include_in_schema=False)
async def serve_index_html():
    """兼容直接访问 /index.html 的情况。"""
    return HTMLResponse(content=INDEX_HTML, headers=NO_STORE_HEADERS)

# Mount 静态目录处理 JS/CSS/图片等其他资源
# 自定义子类给 200 响应加 no-store，避免 Cloudflare/浏览器缓存旧版
class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

app.mount("/", NoCacheStaticFiles(directory="static", html=True), name="static")
