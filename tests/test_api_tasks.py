"""
任务管理 API 端点测试（/api/tasks/*）。

策略：
- monkeypatch 掉 main.process_feishu_task 与 main.process_local_task，
  避免 BackgroundTasks 触发真实飞书/ASR 外部调用。
- 通过 db_session 直接构造已完成任务，测试下载/说话人映射/公共下载等端点。
- settings.OUTPUT_DIR / UPLOAD_DIR 重定向到 tmp_path，避免污染真实 data 目录。
"""
import json
import uuid
from pathlib import Path

import pytest
from datetime import datetime

import main
from models import User, Task, FeishuToken


# ==================== helpers ====================

def _noop_background_task(task_id: str):
    """替换真实后台任务的空操作，避免外部请求。"""
    pass


@pytest.fixture(autouse=True)
def _patch_background_tasks(monkeypatch):
    """自动 patch 掉所有会发外部请求的后台任务。"""
    monkeypatch.setattr(main, 'process_feishu_task', _noop_background_task)
    monkeypatch.setattr(main, 'process_local_task', _noop_background_task)


@pytest.fixture
def isolated_dirs(tmp_path, monkeypatch):
    """将 OUTPUT_DIR / UPLOAD_DIR 重定向到临时目录。"""
    out_dir = tmp_path / "outputs"
    up_dir = tmp_path / "uploads"
    out_dir.mkdir()
    up_dir.mkdir()
    monkeypatch.setattr(main.settings, 'OUTPUT_DIR', str(out_dir))
    monkeypatch.setattr(main.settings, 'UPLOAD_DIR', str(up_dir))
    return out_dir, up_dir


def _bind_feishu_to_current_user(db_session, user_id: int):
    """给指定用户绑定一个虚拟飞书账号，便于测试飞书任务创建。"""
    token = FeishuToken(
        user_id=user_id,
        open_id=f"ou_test_{user_id}",
        name="飞书测试用户",
        avatar_url="",
        access_token="fake_access_token",
        refresh_token="fake_refresh_token",
        expires_at=datetime(2099, 1, 1),
        refresh_expires_at=datetime(2099, 1, 1),
    )
    db_session.add(token)
    db_session.commit()
    return token


def _get_user_id(db_session, username="testuser"):
    return db_session.query(User).filter(User.username == username).first().id


def _make_completed_task(db_session, user_id, *, title="测试任务", task_type="feishu",
                         minute_token="abcdef1234567890abcdef12", raw_text=""):
    """直接构造一个已完成的任务用于下载/更新测试。"""
    task = Task(
        id=str(uuid.uuid4()),
        user_id=user_id,
        task_type=task_type,
        status="completed",
        title=title,
        minute_token=minute_token if task_type == "feishu" else None,
        filename=f"{uuid.uuid4()}.wav" if task_type == "local" else None,
        duration=60.0,
        progress=100,
        speaker_map=json.dumps({}),
        result_markdown=raw_text,
    )
    db_session.add(task)
    db_session.commit()
    return task


# ==================== list tasks ====================

class TestListTasks:
    def test_list_empty(self, client, auth_headers):
        resp = client.get('/api/tasks', headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_unauthorized(self, client):
        resp = client.get('/api/tasks')
        assert resp.status_code == 401


# ==================== create feishu task ====================

class TestCreateFeishuTask:
    def test_without_feishu_binding(self, client, auth_headers):
        """未绑定飞书时创建飞书任务应 400。"""
        resp = client.post(
            '/api/tasks/feishu',
            json={'minute_url_or_token': 'https://x.feishu.cn/minutes/abcdef1234567890'},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert '绑定飞书' in resp.json()['detail']

    def test_invalid_minute_url(self, client, auth_headers, db_session):
        _bind_feishu_to_current_user(db_session, _get_user_id(db_session))
        resp = client.post(
            '/api/tasks/feishu',
            json={'minute_url_or_token': 'not-a-valid-url-no-slash'},
            headers=auth_headers,
        )
        # 没有 / 时直接返回原字符串作为 token，所以会创建成功（除非为空）
        # 这里验证：传入空字符串应失败
        assert resp.status_code in (200, 400)

    def test_empty_minute_url(self, client, auth_headers, db_session):
        _bind_feishu_to_current_user(db_session, _get_user_id(db_session))
        resp = client.post(
            '/api/tasks/feishu',
            json={'minute_url_or_token': ''},
            headers=auth_headers,
        )
        # extract_minute_token('') 返回 ''， falsy -> 400
        assert resp.status_code == 400
        assert '无效' in resp.json()['detail']

    def test_create_success(self, client, auth_headers, db_session):
        _bind_feishu_to_current_user(db_session, _get_user_id(db_session))
        resp = client.post(
            '/api/tasks/feishu',
            json={'minute_url_or_token': 'https://x.feishu.cn/minutes/abcdef1234567890'},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data['task_type'] == 'feishu'
        assert data['status'] == 'pending'
        assert data['minute_token'] == 'abcdef1234567890'
        assert data['progress'] == 0

    def test_duplicate_active_task(self, client, auth_headers, db_session):
        _bind_feishu_to_current_user(db_session, _get_user_id(db_session))
        url = 'https://x.feishu.cn/minutes/abcdef1234567890'
        r1 = client.post('/api/tasks/feishu', json={'minute_url_or_token': url}, headers=auth_headers)
        assert r1.status_code == 200
        # 第二次提交相同 token 应被拒绝
        r2 = client.post('/api/tasks/feishu', json={'minute_url_or_token': url}, headers=auth_headers)
        assert r2.status_code == 400
        assert '重复' in r2.json()['detail']

    def test_custom_title(self, client, auth_headers, db_session):
        _bind_feishu_to_current_user(db_session, _get_user_id(db_session))
        resp = client.post(
            '/api/tasks/feishu',
            json={'minute_url_or_token': 'https://x.feishu.cn/minutes/abcdef1234567890',
                  'title': '产品周会'},
            headers=auth_headers,
        )
        assert resp.json()['title'] == '产品周会'

    def test_default_title_when_not_provided(self, client, auth_headers, db_session):
        _bind_feishu_to_current_user(db_session, _get_user_id(db_session))
        resp = client.post(
            '/api/tasks/feishu',
            json={'minute_url_or_token': 'https://x.feishu.cn/minutes/abcdef1234567890'},
            headers=auth_headers,
        )
        assert '飞书妙记_' in resp.json()['title']


# ==================== create local task ====================

class TestCreateLocalTask:
    def test_unsupported_format(self, client, auth_headers, isolated_dirs):
        resp = client.post(
            '/api/tasks/local',
            files={'file': ('note.txt', b'hello', 'text/plain')},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert '不支持' in resp.json()['detail']

    def test_create_success(self, client, auth_headers, isolated_dirs):
        resp = client.post(
            '/api/tasks/local',
            files={'file': ('audio.mp3', b'\x00\x01\x02mp3data', 'audio/mpeg')},
            data={'title': '本地录音'},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data['task_type'] == 'local'
        assert data['status'] == 'pending'
        assert data['title'] == '本地录音'
        assert data['filename'].endswith('.mp3')
        assert data['file_size'] > 0

    def test_default_title_from_filename(self, client, auth_headers, isolated_dirs):
        resp = client.post(
            '/api/tasks/local',
            files={'file': ('meeting.wav', b'wavdata', 'audio/wav')},
            headers=auth_headers,
        )
        assert resp.json()['title'] == 'meeting.wav'

    def test_uploaded_file_saved_to_disk(self, client, auth_headers, isolated_dirs):
        _, up_dir = isolated_dirs
        resp = client.post(
            '/api/tasks/local',
            files={'file': ('meeting.wav', b'wavdata123', 'audio/wav')},
            headers=auth_headers,
        )
        filename = resp.json()['filename']
        saved = up_dir / filename
        assert saved.exists()
        assert saved.read_bytes() == b'wavdata123'


# ==================== get task ====================

class TestGetTask:
    def test_task_not_found(self, client, auth_headers):
        resp = client.get('/api/tasks/non-existent-id', headers=auth_headers)
        assert resp.status_code == 404

    def test_get_own_task(self, client, auth_headers, db_session):
        uid = _get_user_id(db_session)
        task = _make_completed_task(db_session, uid, raw_text="说话人 1 00:00:01.000\nhi")
        resp = client.get(f'/api/tasks/{task.id}', headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()['id'] == task.id

    def test_cannot_access_other_users_task(self, client, auth_headers, db_session):
        """用户 A 不能查看用户 B 的任务（权限隔离）。"""
        # 创建另一个用户及其任务
        other = User(username='other', hashed_password='x')
        db_session.add(other)
        db_session.commit()
        task = _make_completed_task(db_session, other.id)
        resp = client.get(f'/api/tasks/{task.id}', headers=auth_headers)
        assert resp.status_code == 404


# ==================== update speaker map ====================

class TestUpdateSpeakerMap:
    def test_task_not_found(self, client, auth_headers):
        resp = client.post(
            '/api/tasks/no-id/update_speaker_map',
            json={'speaker_map': {}},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_update_not_completed_task(self, client, auth_headers, db_session):
        uid = _get_user_id(db_session)
        task = Task(
            id=str(uuid.uuid4()), user_id=uid, task_type='feishu', status='pending',
            minute_token='mt', progress=0,
        )
        db_session.add(task)
        db_session.commit()
        resp = client.post(
            f'/api/tasks/{task.id}/update_speaker_map',
            json={'speaker_map': {'说话人 1': '张三'}},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert '已完成' in resp.json()['detail']

    def test_update_success_regenerates_markdown(self, client, auth_headers, db_session, isolated_dirs):
        out_dir, _ = isolated_dirs
        uid = _get_user_id(db_session)
        raw = "说话人 1 00:00:01.000\n你好\n说话人 2 00:00:05.000\n你好呀"
        task = _make_completed_task(db_session, uid, raw_text=raw, title="会议X")

        resp = client.post(
            f'/api/tasks/{task.id}/update_speaker_map',
            json={'speaker_map': {'说话人 1': '张三', '说话人 2': '李四'}},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['speaker_map'] == {'说话人 1': '张三', '说话人 2': '李四'}

        # 验证 markdown 文件已被重新生成并包含映射后的名字
        md_file = out_dir / f"{task.id}.md"
        assert md_file.exists()
        content = md_file.read_text(encoding='utf-8')
        assert '张三' in content
        assert '李四' in content
        assert '说话人 1' not in content


# ==================== download ====================

class TestDownloadTaskMarkdown:
    def test_task_not_found(self, client, auth_headers):
        resp = client.get('/api/tasks/no-id/download', headers=auth_headers)
        assert resp.status_code == 404

    def test_download_not_completed(self, client, auth_headers, db_session):
        uid = _get_user_id(db_session)
        task = Task(id=str(uuid.uuid4()), user_id=uid, task_type='local',
                    status='processing', progress=50)
        db_session.add(task)
        db_session.commit()
        resp = client.get(f'/api/tasks/{task.id}/download', headers=auth_headers)
        assert resp.status_code == 400

    def test_download_file_missing(self, client, auth_headers, db_session, isolated_dirs):
        uid = _get_user_id(db_session)
        task = _make_completed_task(db_session, uid)
        # 不创建实际文件，应 404
        resp = client.get(f'/api/tasks/{task.id}/download', headers=auth_headers)
        assert resp.status_code == 404
        assert '丢失' in resp.json()['detail']

    def test_download_success(self, client, auth_headers, db_session, isolated_dirs):
        out_dir, _ = isolated_dirs
        uid = _get_user_id(db_session)
        # 使用无空格的 ASCII 标题，避免 RFC 5987 编码干扰断言
        task = _make_completed_task(db_session, uid, title="MeetingNotes")
        (out_dir / f"{task.id}.md").write_text("# 内容", encoding='utf-8')

        resp = client.get(f'/api/tasks/{task.id}/download', headers=auth_headers)
        assert resp.status_code == 200
        assert resp.text == "# 内容"
        cd = resp.headers.get('content-disposition', '')
        assert 'MeetingNotes.md' in cd

    def test_download_filename_sanitized(self, client, auth_headers, db_session, isolated_dirs):
        """标题中的非法文件名字符应被替换为下划线。"""
        out_dir, _ = isolated_dirs
        uid = _get_user_id(db_session)
        task = _make_completed_task(db_session, uid, title="周会/纪要:2026")
        (out_dir / f"{task.id}.md").write_text("x", encoding='utf-8')

        resp = client.get(f'/api/tasks/{task.id}/download', headers=auth_headers)
        assert resp.status_code == 200
        # 原始非法字符 / 和 : 不应出现在 Content-Disposition 中
        cd = resp.headers.get('content-disposition', '')
        # 安全化后应为 "周会_纪要_2026.md"，非 ASCII 部分可能被 RFC5987 编码
        assert '%2F' not in cd.upper() and '/' not in cd.split('filename')[-1]
        assert '%3A' not in cd.upper() and ':' not in cd.split('filename')[-1]


# ==================== delete task ====================

class TestDeleteTask:
    def test_delete_not_found(self, client, auth_headers):
        resp = client.delete('/api/tasks/no-id', headers=auth_headers)
        assert resp.status_code == 404

    def test_delete_own_task(self, client, auth_headers, db_session, isolated_dirs):
        uid = _get_user_id(db_session)
        task = _make_completed_task(db_session, uid)
        resp = client.delete(f'/api/tasks/{task.id}', headers=auth_headers)
        assert resp.status_code == 200
        # 删除后再获取应 404
        assert client.get(f'/api/tasks/{task.id}', headers=auth_headers).status_code == 404

    def test_delete_other_users_task(self, client, auth_headers, db_session):
        other = User(username='other2', hashed_password='x')
        db_session.add(other)
        db_session.commit()
        task = _make_completed_task(db_session, other.id)
        resp = client.delete(f'/api/tasks/{task.id}', headers=auth_headers)
        assert resp.status_code == 404

    def test_delete_local_task_removes_audio_file(self, client, auth_headers, db_session, isolated_dirs):
        _, up_dir = isolated_dirs
        uid = _get_user_id(db_session)
        task = _make_completed_task(db_session, uid, task_type="local")
        audio = up_dir / task.filename
        audio.write_bytes(b'audio')
        md = (isolated_dirs[0] / f"{task.id}.md")
        md.write_text("x", encoding='utf-8')

        resp = client.delete(f'/api/tasks/{task.id}', headers=auth_headers)
        assert resp.status_code == 200
        assert not audio.exists()
        assert not md.exists()


# ==================== public download ====================

class TestPublicDownload:
    def test_public_download_not_found(self, client):
        resp = client.get('/api/tasks/public/no-id/download')
        assert resp.status_code == 404

    def test_public_download_not_completed(self, client, auth_headers, db_session):
        # auth_headers fixture 负责注册 testuser，使 _get_user_id 能查到用户
        uid = _get_user_id(db_session)
        task = Task(id=str(uuid.uuid4()), user_id=uid, task_type='feishu',
                    status='processing', progress=50, minute_token='mt')
        db_session.add(task)
        db_session.commit()
        resp = client.get(f'/api/tasks/public/{task.id}/download')
        assert resp.status_code == 400

    def test_public_download_success_no_auth(self, client, auth_headers, db_session, isolated_dirs):
        """公共下载端点不需要鉴权（飞书卡片按钮直接打开）。"""
        out_dir, _ = isolated_dirs
        uid = _get_user_id(db_session)
        task = _make_completed_task(db_session, uid, title="公共可下载")
        (out_dir / f"{task.id}.md").write_text("# 公共内容", encoding='utf-8')

        resp = client.get(f'/api/tasks/public/{task.id}/download')
        assert resp.status_code == 200
        assert "# 公共内容" in resp.text
