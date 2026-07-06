from pydantic import BaseModel, Field
from typing import Optional, Dict
from datetime import datetime

# User schemas
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    created_at: datetime

    class Config:
        from_attributes = True

# Token schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# Feishu schema
class FeishuBindRequest(BaseModel):
    code: str

# Task schemas
class TaskCreateFeishu(BaseModel):
    minute_url_or_token: str
    title: Optional[str] = None

class TaskUpdateSpeakerMap(BaseModel):
    speaker_map: Dict[str, str]

class TaskResponse(BaseModel):
    id: str
    task_type: str
    status: str
    title: Optional[str] = None
    filename: Optional[str] = None
    file_size: Optional[int] = None
    minute_token: Optional[str] = None
    duration: Optional[float] = None
    progress: int
    speaker_map: Optional[Dict[str, str]] = None
    result_markdown: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        # Resolve SQLAlchemy relation to return dictionary speaker_map
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }
