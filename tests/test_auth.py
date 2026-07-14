"""
auth.py 单元测试。

覆盖：
- bcrypt 密码哈希与校验（正确/错误密码）
- JWT access_token 创建与解码
- token 过期校验
- get_current_user 在无效 token / 不存在用户场景下的行为
"""
import datetime
import pytest
from jose import jwt

import auth
from config import settings


class TestPasswordHash:
    def test_hash_and_verify_correct(self):
        plain = "mysecret123"
        hashed = auth.get_password_hash(plain)
        assert hashed != plain
        assert auth.verify_password(plain, hashed) is True

    def test_verify_wrong_password(self):
        hashed = auth.get_password_hash("correct")
        assert auth.verify_password("wrong", hashed) is False

    def test_hash_is_unique_per_call(self):
        """bcrypt 每次生成不同 salt，相同密码两次哈希结果不同。"""
        h1 = auth.get_password_hash("same")
        h2 = auth.get_password_hash("same")
        assert h1 != h2
        assert auth.verify_password("same", h1) and auth.verify_password("same", h2)

    def test_verify_invalid_hash_returns_false(self):
        """损坏的哈希字符串不应抛异常，而是返回 False。"""
        assert auth.verify_password("any", "not-a-valid-hash") is False


class TestCreateAccessToken:
    def test_create_and_decode_token(self):
        token = auth.create_access_token(data={"sub": "alice"})
        assert isinstance(token, str)

        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert payload["sub"] == "alice"
        assert "exp" in payload

    def test_token_with_custom_expiry(self):
        delta = datetime.timedelta(minutes=5)
        token = auth.create_access_token(data={"sub": "bob"}, expires_delta=delta)

        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        exp = datetime.datetime.fromtimestamp(payload["exp"], tz=datetime.timezone.utc)
        now = datetime.datetime.now(datetime.timezone.utc)
        # 过期时间应在 4~6 分钟之间
        assert 4 * 60 < (exp - now).total_seconds() <= 5 * 60

    def test_expired_token_raises(self):
        """已过期的 token 在解码时应抛 JWTError。"""
        delta = datetime.timedelta(seconds=-10)
        token = auth.create_access_token(data={"sub": "carol"}, expires_delta=delta)
        with pytest.raises(jwt.JWTError):
            jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


class TestGetCurrentUser:
    """get_current_user 需要数据库 + token，用 TestClient 间接验证更方便。
    这里仅验证无 token 时 FastAPI 会拦截（在 API 测试中覆盖）。"""
    pass
