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

def _reduce_audio_noise(audio_path: str, progress_callback) -> str:
    """
    Apply spectral noise reduction using noisereduce.
    Returns path to denoised temp wav file, or original path on failure
    (graceful degradation so transcription still proceeds).
    """
    try:
        import numpy as np  # noqa: F401
        import soundfile as sf
        import noisereduce as nr
    except ImportError:
        progress_callback(10, "降噪库未安装，跳过降噪...")
        return audio_path

    progress_callback(6, "正在读取音频以降噪...")
    try:
        # soundfile 读取为 float32 numpy 数组
        audio, sr = sf.read(audio_path, dtype="float32", always_2d=False)
        # 多声道转单声道
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        if len(audio) == 0:
            return audio_path

        progress_callback(9, "正在执行降噪处理...")
        # noisereduce 频谱减法，默认参数对稳态噪音（空调、线路底噪）有效
        reduced = nr.reduce_noise(y=audio, sr=sr)

        # 写到临时 wav 文件，转写完后清理
        temp_path = os.path.splitext(audio_path)[0] + ".denoised.wav"
        sf.write(temp_path, reduced, sr, subtype="PCM_16")
        return temp_path
    except Exception as e:
        # soundfile 不支持的格式（如 m4a）或降噪失败时降级
        progress_callback(10, f"降噪跳过，使用原音频: {e}")
        return audio_path


def run_real_asr(audio_path: str, progress_callback) -> Tuple[str, float]:
    """
    Run actual transcription using faster-whisper model.
    Returns (transcript_text, duration_seconds).
    """
    # 降噪预处理（失败则降级用原音频）
    denoised_path = _reduce_audio_noise(audio_path, progress_callback)

    try:
        # Initialize Whisper model (using base on CPU as default)
        # Note: In production, device="cuda" should be used if GPU is available
        progress_callback(15, "正在加载 ASR 模型...")
        model = WhisperModel("base", device="cpu", compute_type="int8")

        progress_callback(18, "正在加载音频并进行初始化...")
        segments, info = model.transcribe(denoised_path, beam_size=5)

        duration = info.duration or 0.0

        # Process segments — iterate the generator directly so progress updates
        # incrementally as transcription proceeds (list(segments) would block until
        # the entire audio is transcribed, freezing the progress bar).
        transcript_lines = []
        seg_count = 0
        for segment in segments:
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

            seg_count += 1
            # Estimate progress by processed audio duration when available,
            # otherwise fall back to a per-segment heuristic.
            if duration > 0:
                ratio = min(segment.end / duration, 1.0)
            else:
                ratio = min(seg_count / max(seg_count + 8, 16), 1.0)
            current_progress = int(18 + ratio * 77)
            progress_callback(min(current_progress, 95), f"已转写 {seg_count} 个片段（{timestamp}）...")

        return "\n".join(transcript_lines), duration
    finally:
        # 清理临时降噪文件
        if denoised_path != audio_path and os.path.exists(denoised_path):
            try:
                os.remove(denoised_path)
            except OSError:
                pass

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
