"""
pytest 全局配置。

关键点：
- 在导入任何项目模块之前设置 DATABASE_URL 为共享内存 SQLite，避免污染真实数据文件。
- Patch sqlalchemy.create_engine 让共享内存 SQLite 使用 StaticPool，
  否则每个连接会创建独立的 :memory: 数据库，数据无法跨连接共享。
- 提供 client / db_session / auth_headers 等通用 fixture。
"""
import os
import sys
from pathlib import Path

# 将项目根目录加入 sys.path，确保 tests 可以 import 项目模块
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ---- 必须在导入 config / database 之前设置环境变量 ----
os.environ['DATABASE_URL'] = 'sqlite:///file:memdb_test?mode=memory&cache=shared&uri=true'
os.environ.setdefault('FEISHU_APP_ID', 'test_app_id')
os.environ.setdefault('FEISHU_APP_SECRET', 'test_app_secret')
os.environ.setdefault('FEISHU_REDIRECT_URI', 'http://127.0.0.1:8000/api/auth/feishu/callback')

# ---- Patch sqlalchemy.create_engine ----
import sqlalchemy
from sqlalchemy.pool import StaticPool

_orig_create_engine = sqlalchemy.create_engine


def _test_create_engine(url, **kwargs):
    if isinstance(url, str) and 'mode=memory' in url:
        kwargs['poolclass'] = StaticPool
        kwargs.setdefault('connect_args', {})
        kwargs['connect_args'].setdefault('check_same_thread', False)
        kwargs['connect_args'].setdefault('uri', True)
    return _orig_create_engine(url, **kwargs)


sqlalchemy.create_engine = _test_create_engine

# ---- 现在安全导入项目模块 ----
import config  # noqa: E402  (确保 settings 已用测试环境变量初始化)
import database  # noqa: E402
from models import Base  # noqa: E402
import main  # noqa: E402
from main import app  # noqa: E402

from fastapi.testclient import TestClient
import pytest


def _reset_db():
    """清空并重建所有表，确保测试之间数据隔离。"""
    Base.metadata.drop_all(bind=database.engine)
    Base.metadata.create_all(bind=database.engine)


@pytest.fixture
def db_session():
    """提供独立的 SQLAlchemy session，测试前后清空数据库。"""
    _reset_db()
    session = database.SessionLocal()
    try:
        yield session
    finally:
        session.close()
        _reset_db()


@pytest.fixture
def client(db_session):
    """FastAPI TestClient，覆盖 get_db 依赖以使用测试 session。"""
    from database import get_db

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth_token(client):
    """注册并登录测试用户，返回 JWT access_token。"""
    client.post('/api/auth/register', json={'username': 'testuser', 'password': 'testpass123'})
    resp = client.post(
        '/api/auth/login',
        data={'username': 'testuser', 'password': 'testpass123'},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()['access_token']


@pytest.fixture
def auth_headers(auth_token):
    return {'Authorization': f'Bearer {auth_token}'}
