import os
from typing import Tuple
from sqlalchemy.orm import Session
from models import Task
from config import settings

# Attempt to import faster-whisper for real local ASR
try:
    from faster_whisper import WhisperModel
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False

def run_real_asr(audio_path: str, progress_callback) -> Tuple[str, float]:
    """
    Run actual transcription using faster-whisper model.
    Returns (transcript_text, duration_seconds).
    """
    # Initialize Whisper model (using base on CPU as default)
    # Note: In production, device="cuda" should be used if GPU is available
    model = WhisperModel("base", device="cpu", compute_type="int8")

    progress_callback(10, "正在加载音频并进行初始化...")
    segments, info = model.transcribe(audio_path, beam_size=5)

    duration = info.duration

    # Process segments
    transcript_lines = []

    # Convert generator to list to track progress
    segments_list = list(segments)
    total_segments = len(segments_list)

    for i, segment in enumerate(segments_list):
        # Format time to [HH:MM:SS]
        start_time = segment.start
        hours = int(start_time // 3600)
        minutes = int((start_time % 3600) // 60)
        seconds = int(start_time % 60)
        timestamp = f"[{hours:02d}:{minutes:02d}:{seconds:02d}]"

        # In a basic faster-whisper without pyannote, we default to "说话人 1"
        # In a full setup, pyannote diarization timestamps would map segments to speakers
        speaker = "说话人 1"

        line = f"{timestamp} {speaker}：{segment.text.strip()}"
        transcript_lines.append(line)

        # Update progress based on segments processed
        current_progress = int(10 + (i + 1) / total_segments * 85)
        progress_callback(min(current_progress, 95), f"已转写 {i+1}/{total_segments} 个音频片段...")

    return "\n".join(transcript_lines), duration

def process_local_asr_task(task_id: str, db: Session):
    """
    Fetch the task, run real ASR, and update task record.
    Fails clearly if faster-whisper is not installed or the audio file is missing.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return

    def update_progress(percent: int, message: str = ""):
        task.progress = percent
        if message:
            task.error_message = message  # Temporarily use this field for status messages
        db.commit()

    try:
        task.status = "processing"
        task.progress = 5
        db.commit()

        if not HAS_WHISPER:
            raise RuntimeError("未安装 faster-whisper，无法进行本地 ASR。请运行: pip install faster-whisper")

        audio_path = os.path.join(settings.UPLOAD_DIR, task.filename)
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {task.filename}")

        transcript, duration = run_real_asr(audio_path, update_progress)

        # Complete task
        task.status = "completed"
        task.progress = 100
        task.result_markdown = transcript
        task.duration = duration
        task.error_message = None  # Clear temporary messages
        db.commit()

    except Exception as e:
        task.status = "failed"
        task.progress = 0
        task.error_message = f"本地 ASR 转写异常: {str(e)}"
        db.commit()
