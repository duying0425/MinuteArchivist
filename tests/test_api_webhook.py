"""
飞书 Webhook 事件端点测试（/api/feishu/events）。

覆盖：
- URL Verification challenge 握手
- vc.meeting.recording_ready_v1 事件：无绑定用户忽略、缺少字段忽略
- minutes.minute.generated_v1 事件：无绑定用户忽略、缺少字段忽略、有绑定触发后台任务
- 未知事件类型忽略
"""
import uuid
import pytest

import main
from models import User, FeishuToken
from datetime import datetime


@pytest.fixture
def captured_background_calls(monkeypatch):
    """捕获 background_tasks.add_task 的调用，避免真实执行。"""
    calls = []

    def fake_add_task(self, func, *args, **kwargs):
        calls.append({"func": func.__name__, "args": args, "kwargs": kwargs})

    monkeypatch.setattr("fastapi.BackgroundTasks.add_task", fake_add_task)
    return calls


class TestUrlVerification:
    def test_challenge_handshake(self, client):
        """飞书配置 webhook 时的 challenge 验证。"""
        resp = client.post('/api/feishu/events', json={
            "type": "url_verification",
            "challenge": "ajls384kdjx98XX",
        })
        assert resp.status_code == 200
        assert resp.json() == {"challenge": "ajls384kdjx98XX"}


class TestRecordingReadyEvent:
    def test_missing_fields_ignored(self, client):
        resp = client.post('/api/feishu/events', json={
            "header": {"event_type": "vc.meeting.recording_ready_v1"},
            "event": {"meeting_id": "m1"},  # 缺少 operator.open_id
        })
        assert resp.json()["status"] == "ignored"

    def test_no_bound_user_ignored(self, client):
        """open_id 没有对应本地用户时应忽略。"""
        resp = client.post('/api/feishu/events', json={
            "header": {"event_type": "vc.meeting.recording_ready_v1"},
            "event": {
                "meeting_id": "meeting_abc",
                "operator": {"id": {"open_id": "ou_nobody"}},
            },
        })
        assert resp.json()["status"] == "ignored"
        assert 'No bound' in resp.json()["reason"]

    def test_bound_user_triggers_background_task(self, client, db_session, captured_background_calls):
        uid = _ensure_user_with_feishu(db_session, open_id="ou_recording_user")
        resp = client.post('/api/feishu/events', json={
            "header": {"event_type": "vc.meeting.recording_ready_v1"},
            "event": {
                "meeting_id": "meeting_xyz",
                "operator": {"id": {"open_id": "ou_recording_user"}},
            },
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "processing"
        assert len(captured_background_calls) == 1
        assert captured_background_calls[0]["func"] == "process_webhook_recording_event"


class TestMinutesGeneratedEvent:
    def test_missing_fields_ignored(self, client):
        resp = client.post('/api/feishu/events', json={
            "header": {"event_type": "minutes.minute.generated_v1"},
            "event": {},  # 缺少 minute_token 和 open_id
        })
        assert resp.json()["status"] == "ignored"

    def test_no_bound_user_ignored(self, client):
        resp = client.post('/api/feishu/events', json={
            "header": {"event_type": "minutes.minute.generated_v1"},
            "event": {
                "minute_token": "mt1234567890",
                "owner_id": {"open_id": "ou_nobody"},
            },
        })
        assert resp.json()["status"] == "ignored"

    def test_owner_id_form_triggers(self, client, db_session, captured_background_calls):
        uid = _ensure_user_with_feishu(db_session, open_id="ou_minute_owner")
        resp = client.post('/api/feishu/events', json={
            "header": {"event_type": "minutes.minute.generated_v1"},
            "event": {
                "minute_token": "mt_owner_1234567890",
                "owner_id": {"open_id": "ou_minute_owner"},
            },
        })
        assert resp.json()["status"] == "processing"
        assert captured_background_calls[0]["func"] == "process_webhook_minute_event"

    def test_user_id_form_triggers(self, client, db_session, captured_background_calls):
        _ensure_user_with_feishu(db_session, open_id="ou_minute_userid")
        resp = client.post('/api/feishu/events', json={
            "header": {"event_type": "minutes.minute.generated_v1"},
            "event": {
                "minute_token": "mt_userid_123456789",
                "user_id": {"open_id": "ou_minute_userid"},
            },
        })
        assert resp.json()["status"] == "processing"

    def test_operator_form_triggers(self, client, db_session, captured_background_calls):
        _ensure_user_with_feishu(db_session, open_id="ou_minute_operator")
        resp = client.post('/api/feishu/events', json={
            "header": {"event_type": "minutes.minute.generated_v1"},
            "event": {
                "minute_token": "mt_op_1234567890",
                "operator": {"id": {"open_id": "ou_minute_operator"}},
            },
        })
        assert resp.json()["status"] == "processing"


class TestUnknownEvent:
    def test_unknown_event_type_ignored(self, client):
        resp = client.post('/api/feishu/events', json={
            "header": {"event_type": "some.unknown.event_v1"},
            "event": {},
        })
        assert resp.json()["status"] == "ignored"
        assert 'not handled' in resp.json()["reason"]

    def test_missing_header(self, client):
        resp = client.post('/api/feishu/events', json={})
        assert resp.json()["status"] == "ignored"


# ===== helper =====

def _ensure_user_with_feishu(db_session, *, open_id: str, username: str = None) -> int:
    """创建一个带飞书绑定的用户，返回 user.id。"""
    username = username or f"u_{open_id[-6:]}"
    user = User(username=username, hashed_password="x")
    db_session.add(user)
    db_session.commit()
    token = FeishuToken(
        user_id=user.id,
        open_id=open_id,
        name=username,
        avatar_url="",
        access_token="fake",
        refresh_token="fake",
        expires_at=datetime(2099, 1, 1),
        refresh_expires_at=datetime(2099, 1, 1),
    )
    db_session.add(token)
    db_session.commit()
    return user.id
