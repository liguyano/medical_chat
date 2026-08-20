"""患者身份凭据工具
作用：使用配置密钥对身份证号进行可逆加密，供患者登录时校验；
      不向 API 响应返回身份证号或其加密内容。
"""

from __future__ import annotations

import base64
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken


def normalize_id_card(value: str) -> str:
    """标准化身份证号。"""
    return "".join(value.split()).upper()


def normalize_phone(value: str) -> str:
    """标准化手机号。"""
    return "".join(value.split())


def _fernet(secret: str) -> Fernet:
    """根据应用密钥构造确定性的 Fernet 实例。"""
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_id_card(id_card: str, secret: str) -> str:
    """加密身份证号。"""
    normalized = normalize_id_card(id_card)
    return _fernet(secret).encrypt(normalized.encode("utf-8")).decode("ascii")


def decrypt_id_card(ciphertext: str | None, secret: str) -> str | None:
    """解密身份证号
    作用：仅供服务端校验和生成脱敏展示值，不得直接通过 API 返回。
    """
    if not ciphertext:
        return None
    try:
        return _fernet(secret).decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError):
        return None


def mask_id_card(ciphertext: str | None, secret: str) -> str | None:
    """返回身份证号脱敏值。"""
    value = decrypt_id_card(ciphertext, secret)
    if not value:
        return None
    if len(value) <= 8:
        return f"{value[:2]}***{value[-2:]}"
    return f"{value[:4]}**********{value[-4:]}"


def verify_id_card(id_card: str, ciphertext: str | None, secret: str) -> bool:
    """校验身份证号与已保存密文是否匹配。"""
    if not ciphertext:
        return False
    decrypted = decrypt_id_card(ciphertext, secret)
    if decrypted is None:
        return False
    return hmac.compare_digest(normalize_id_card(id_card), decrypted)
