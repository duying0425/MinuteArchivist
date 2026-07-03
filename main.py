import os
import uuid
import json
import datetime
from typing import List
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
    title="声记工坊 (VoiceNote Forge)",
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
                duration_seconds=task.duration or 81.0,
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

# --- Feishu OAuth Binding APIs ---

@app.get("/api/auth/feishu/url")
def get_feishu_url(current_user: User = Depends(get_current_user)):
    # Use user's username or id as OAuth state to link them
    return {"url": get_feishu_auth_url(state=str(current_user.id))}

@app.get("/api/auth/feishu/callback")
def feishu_callback(code: str, state: str, db: Session = Depends(get_db)):
    """
    Feishu callback handler. Exchanged code for access/refresh token and closes window.
    """
    user_id = int(state)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return HTMLResponse("<h3>授权失败：未找到本地关联用户。</h3>")
        
    try:
        # Exchange code for token
        token_data = exchange_code_for_token(code)
        
        # Get user info
        user_info = get_user_info(token_data["access_token"])
        
        # Check if user already has a token in DB, update or create
        now = datetime.datetime.utcnow()
        expires_at = now + datetime.timedelta(seconds=token_data["expires_in"])
        refresh_expires_at = now + datetime.timedelta(seconds=token_data["refresh_expires_in"])
        
        db_token = db.query(FeishuToken).filter(FeishuToken.user_id == user_id).first()
        if db_token:
            db_token.open_id = token_data.get("open_id", user_info.get("open_id"))
            db_token.name = user_info.get("name")
            db_token.avatar_url = user_info.get("avatar_url")
            db_token.access_token = token_data["access_token"]
            db_token.refresh_token = token_data["refresh_token"]
            db_token.expires_at = expires_at
            db_token.refresh_expires_at = refresh_expires_at
            db_token.updated_at = now
        else:
            db_token = FeishuToken(
                user_id=user_id,
                open_id=token_data.get("open_id", user_info.get("open_id")),
                name=user_info.get("name"),
                avatar_url=user_info.get("avatar_url"),
                access_token=token_data["access_token"],
                refresh_token=token_data["refresh_token"],
                expires_at=expires_at,
                refresh_expires_at=refresh_expires_at
            )
            db.add(db_token)
            
        db.commit()
        
        # Return elegant HTML that notifies frontend SPA and closes popup
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
                    授权异常: {str(e)}
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
        
    safe_title = re.sub(r'[\/:*?"<>|]', '_', task.title or "声记工坊转写记录")
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

# --- Static frontend serving ---

# Ensure directories exist
os.makedirs("static", exist_ok=True)

# Mount the static folder for CSS, HTML, JS
app.mount("/", StaticFiles(directory="static", html=True), name="static")
