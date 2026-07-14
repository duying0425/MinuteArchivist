"""
鉴权相关 API 端点测试（/api/auth/*）。

覆盖：
- 注册：成功、用户名重复、用户名过短、密码过短
- 登录：成功、密码错误、用户不存在
- /me：无 token 401、有 token 返回当前用户信息、飞书绑定状态
- 飞书登录 URL生成
- 解绑飞书（未绑定时 400）
"""
import pytest


class TestRegister:
    def test_register_success(self, client):
        resp = client.post('/api/auth/register', json={'username': 'alice', 'password': 'pass123456'})
        assert resp.status_code == 200
        data = resp.json()
        assert data['username'] == 'alice'
        assert 'id' in data
        assert 'created_at' in data
        # 密码不应出现在响应中
        assert 'hashed_password' not in data
        assert 'password' not in data

    def test_register_duplicate(self, client):
        client.post('/api/auth/register', json={'username': 'alice', 'password': 'pass123456'})
        resp = client.post('/api/auth/register', json={'username': 'alice', 'password': 'pass123456'})
        assert resp.status_code == 400
        assert '已被注册' in resp.json()['detail']

    def test_register_username_too_short(self, client):
        resp = client.post('/api/auth/register', json={'username': 'ab', 'password': 'pass123456'})
        assert resp.status_code == 422  # Pydantic 校验失败

    def test_register_password_too_short(self, client):
        resp = client.post('/api/auth/register', json={'username': 'alice', 'password': '123'})
        assert resp.status_code == 422


class TestLogin:
    def test_login_success(self, client):
        client.post('/api/auth/register', json={'username': 'alice', 'password': 'pass123456'})
        resp = client.post(
            '/api/auth/login',
            data={'username': 'alice', 'password': 'pass123456'},
        )
        assert resp.status_code == 200
        token = resp.json()
        assert token['token_type'] == 'bearer'
        assert token['access_token']

    def test_login_wrong_password(self, client):
        client.post('/api/auth/register', json={'username': 'alice', 'password': 'pass123456'})
        resp = client.post(
            '/api/auth/login',
            data={'username': 'alice', 'password': 'wrongpass'},
        )
        assert resp.status_code == 401
        assert '用户名或密码错误' in resp.json()['detail']

    def test_login_nonexistent_user(self, client):
        resp = client.post(
            '/api/auth/login',
            data={'username': 'ghost', 'password': 'whatever'},
        )
        assert resp.status_code == 401


class TestGetMe:
    def test_me_without_token(self, client):
        resp = client.get('/api/auth/me')
        assert resp.status_code == 401

    def test_me_with_valid_token(self, client, auth_headers):
        resp = client.get('/api/auth/me', headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data['username'] == 'testuser'
        assert data['feishu_bound'] is False
        assert data['feishu_info'] is None

    def test_me_with_invalid_token(self, client):
        resp = client.get('/api/auth/me', headers={'Authorization': 'Bearer invalidtoken'})
        assert resp.status_code == 401


class TestFeishuAuthUrls:
    def test_feishu_login_url(self, client):
        resp = client.get('/api/auth/feishu/login_url')
        assert resp.status_code == 200
        url = resp.json()['url']
        assert url.startswith('https://open.feishu.cn/open-apis/authen/v1/index')
        assert 'state=login' in url

    def test_feishu_binding_url_requires_auth(self, client):
        resp = client.get('/api/auth/feishu/url')
        assert resp.status_code == 401

    def test_feishu_binding_url_with_auth(self, client, auth_headers):
        resp = client.get('/api/auth/feishu/url', headers=auth_headers)
        assert resp.status_code == 200
        # state 应为用户 id（字符串形式）
        url = resp.json()['url']
        assert 'state=' in url


class TestFeishuUnbind:
    def test_unbind_without_binding(self, client, auth_headers):
        """未绑定飞书时解绑应返回 400。"""
        resp = client.post('/api/auth/feishu/unbind', headers=auth_headers)
        assert resp.status_code == 400
        assert '未绑定' in resp.json()['detail']

    def test_unbind_requires_auth(self, client):
        resp = client.post('/api/auth/feishu/unbind')
        assert resp.status_code == 401
