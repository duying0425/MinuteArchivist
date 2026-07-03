import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SECRET_KEY: str = "voicenote_forge_secret_key_change_me_in_prod"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 1 day

    DATABASE_URL: str = "sqlite:///./data/db.sqlite3"

    # Feishu App settings (can be overridden via environment variables or .env file)
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""
    FEISHU_REDIRECT_URI: str = "http://127.0.0.1:8000/api/auth/feishu/callback"

    UPLOAD_DIR: str = "./data/uploads"
    OUTPUT_DIR: str = "./data/outputs"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# Create directories if they do not exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.OUTPUT_DIR, exist_ok=True)

db_path = settings.DATABASE_URL.replace("sqlite:///", "")
if db_path and not db_path.startswith(":memory:"):
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
