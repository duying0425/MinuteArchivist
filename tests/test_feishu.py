"""
feishu.py 单元测试（不发外部请求的部分）。

覆盖：
- extract_minute_token：URL / 纯 token / 带 query / 异常输入
- get_feishu_auth_url：scope 必含妙记导出权限、state 透传
- send_feishu_card_notification 的时长格式化逻辑（通过 monkeypatch requests 验证 payload）
"""
import json
import pytest

import feishu
from config import settings


class TestExtractMinuteToken:
    def test_from_full_url(self):
        url = "https://sample.feishu.cn/minutes/obcnq3b9jl72l83w4f14xxxx"
        assert feishu.extract_minute_token(url) == "obcnq3b9jl72l83w4f14xxxx"

    def test_from_url_with_query(self):
        url = "https://sample.feishu.cn/minutes/abcdef123456?foo=bar&baz=1"
        assert feishu.extract_minute_token(url) == "abcdef123456"

    def test_raw_token_passthrough(self):
        token = "rawtoken123456"
        assert feishu.extract_minute_token(token) == token

    def test_strip_whitespace(self):
        assert feishu.extract_minute_token("  abc123  ") == "abc123"

    def test_short_segment_still_extracted(self):
        """正则要求 token 长度 >=10，短 segment 不匹配则整体返回。"""
        url = "https://x.feishu.cn/minutes/short"
        # 'short' 长度 < 10，不匹配，整体返回（去掉首尾空格）
        assert feishu.extract_minute_token(url) == url.strip()

    def test_token_with_dashes_and_underscores(self):
        url = "https://x.feishu.cn/minutes/abc_def-123456"
        assert feishu.extract_minute_token(url) == "abc_def-123456"


class TestGetFeishuAuthUrl:
    def test_url_contains_required_scopes(self):
        url = feishu.get_feishu_auth_url(state="login")
        # 关键约束（见 project_memory）：scope 必须包含这三个
        assert "minutes:minutes.transcript:export" in url
        assert "minutes:minutes.basic:read" in url
        assert "offline_access" in url

    def test_url_contains_app_id_and_redirect(self):
        url = feishu.get_feishu_auth_url(state="login")
        assert f"app_id={settings.FEISHU_APP_ID}" in url
        assert settings.FEISHU_REDIRECT_URI in url

    def test_state_passthrough(self):
        url = feishu.get_feishu_auth_url(state="12345")
        assert "state=12345" in url

    def test_state_login(self):
        url = feishu.get_feishu_auth_url(state="login")
        assert "state=login" in url


class TestSendFeishuCardNotification:
    """通过 monkeypatch requests.post 验证卡片消息 payload 的构造逻辑，
    不发送真实网络请求。"""

    def test_card_payload_contains_title_and_duration(self, monkeypatch):
        captured = {}

        class FakeResp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"code": 0, "msg": "ok"}

        def fake_post(url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResp()

        # 拦截 get_tenant_access_token 与 send 中的 requests.post
        monkeypatch.setattr(feishu.requests, "post", fake_post)
        monkeypatch.setattr(feishu, "get_tenant_access_token", lambda: "fake_tenant_token")

        feishu.send_feishu_card_notification(
            open_id="ou_test",
            task_title="周会",
            duration_seconds=125.0,
            download_url="https://example.com/dl",
        )

        payload = captured["json"]
        assert payload["receive_id"] == "ou_test"
        assert payload["msg_type"] == "interactive"
        card = json.loads(payload["content"])
        assert "周会" in card["elements"][0]["text"]["content"]
        assert "2分5秒" in card["elements"][0]["text"]["content"]
        assert card["elements"][2]["actions"][0]["url"] == "https://example.com/dl"
        assert captured["headers"]["Authorization"] == "Bearer fake_tenant_token"

    def test_card_unknown_duration(self, monkeypatch):
        class FakeResp:
            def raise_for_status(self): pass
            def json(self): return {"code": 0}

        monkeypatch.setattr(feishu.requests, "post", lambda *a, **kw: FakeResp())
        monkeypatch.setattr(feishu, "get_tenant_access_token", lambda: "t")

        # 用捕获的方式验证 duration_str
        captured = {}
        original_post = feishu.requests.post

        def capturing_post(url, json=None, headers=None):
            captured["json"] = json
            return FakeResp()

        monkeypatch.setattr(feishu.requests, "post", capturing_post)
        feishu.send_feishu_card_notification(
            open_id="ou", task_title="t", duration_seconds=0.0, download_url="u"
        )
        card = json.loads(captured["json"]["content"])
        assert "未知" in card["elements"][0]["text"]["content"]
