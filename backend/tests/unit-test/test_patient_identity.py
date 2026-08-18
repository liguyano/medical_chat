"""患者身份凭据工具单元测试。"""

from app.utils.patient_identity import (
    encrypt_id_card,
    normalize_id_card,
    normalize_phone,
    verify_id_card,
)


def test_patient_identity_encrypts_and_verifies() -> None:
    """身份证号应加密保存并支持正确校验。"""
    secret = "unit-test-secret"
    ciphertext = encrypt_id_card("110101196801180043", secret)

    assert "110101196801180043" not in ciphertext
    assert verify_id_card("110101196801180043", ciphertext, secret)
    assert not verify_id_card("110101196801180044", ciphertext, secret)
    assert not verify_id_card("110101196801180043", ciphertext, "wrong-secret")


def test_patient_identity_normalization() -> None:
    """身份证号与手机号应去除空白并统一身份证末位大小写。"""
    assert normalize_id_card("110101 19680118 004x") == "11010119680118004X"
    assert normalize_phone("138 0000 0004") == "13800000004"
