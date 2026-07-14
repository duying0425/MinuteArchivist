"""
杂项 API 测试：ASR 状态、静态首页、版本注入。
"""
import pytest

import main
from asr import HAS_WHISPER


class TestAsrStatus:
    def test_asr_status_returns_whisper_flag(self, client):
        resp = client.get('/api/asr/status')
        assert resp.status_code == 200
        data = resp.json()
        assert data['has_whisper'] == HAS_WHISPER
        assert 'device' in data


class TestStaticIndex:
    def test_root_returns_html(self, client):
        resp = client.get('/')
        assert resp.status_code == 200
        assert 'text/html' in resp.headers.get('content-type', '')
        # __APP_VERSION__ 占位符应已被替换为实际版本号
        assert '__APP_VERSION__' not in resp.text

    def test_index_no_store_cache_headers(self, client):
        """首页应禁用缓存（避免 CDN 命中旧版前端）。"""
        resp = client.get('/')
        cc = resp.headers.get('cache-control', '')
        assert 'no-store' in cc

    def test_index_html_alias(self, client):
        """/index.html 应同样返回注入版本号的首页。"""
        resp = client.get('/index.html')
        assert resp.status_code == 200
        assert '__APP_VERSION__' not in resp.text

    def test_app_js_served_with_no_store(self, client):
        """静态 JS 资源也应带 no-store 头。"""
        resp = client.get('/app.js')
        assert resp.status_code == 200
        cc = resp.headers.get('cache-control', '')
        assert 'no-store' in cc

    def test_app_js_has_version_query(self, client):
        """index.html 中的 app.js 引用应带 ?v=<version> 查询参数。"""
        resp = client.get('/')
        assert 'app.js?v=' in resp.text
        assert 'style.css?v=' in resp.text


class TestAppVersion:
    def test_app_version_not_placeholder(self):
        """模块加载时 APP_VERSION 应被设置为非占位符值。"""
        assert main.APP_VERSION
        assert main.APP_VERSION != '__APP_VERSION__'

    def test_render_index_html_replaces_placeholder(self):
        html = main._render_index_html()
        assert '__APP_VERSION__' not in html
        assert f'?v={main.APP_VERSION}' in html
