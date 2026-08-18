"""医护账号密码工具。
作用：统一使用 bcrypt 哈希保存和校验医护端登录密码，禁止业务层直接处理明文哈希细节。
"""

import bcrypt

MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    """生成密码 bcrypt 哈希。"""
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError("密码长度不能超过 72 个字节")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """校验密码与已保存哈希是否匹配。"""
    try:
        encoded = password.encode("utf-8")
        if len(encoded) > MAX_PASSWORD_BYTES:
            return False
        return bcrypt.checkpw(encoded, password_hash.encode("ascii"))
    except (ValueError, TypeError, UnicodeError):
        # 数据库中存在损坏或历史未知格式哈希时按登录失败处理。
        return False
