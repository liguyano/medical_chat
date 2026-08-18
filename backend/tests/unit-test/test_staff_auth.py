"""医护账号认证与演示种子单元测试。"""

import pytest

from app.errors.codes import ErrorCode
from app.errors.handlers import AppError
from app.managers.patient_seeder import _PATIENT_SEEDS
from app.managers.staff_seeder import StaffSeeder
from app.models.staff_account import StaffAccount
from app.schemas.staff import StaffLoginRequest
from app.services import staff_service
from app.utils.password import hash_password, verify_password


class _FakeDb:
    """只实现医护登录服务所需 scalar 的假数据库会话。"""

    def __init__(self, staff: StaffAccount | None) -> None:
        self.staff = staff

    def scalar(self, _statement):
        return self.staff


class _FakeRedis:
    """记录会话写入的假 Redis。"""

    def __init__(self) -> None:
        self.saved: dict[str, object] | None = None

    def set(self, key: str, value: dict, *, ex: int) -> bool:
        self.saved = {"key": key, "value": value, "ex": ex}
        return True


class _FakeSeederSession:
    """模拟种子导入会话，首个查询返回已逻辑删除的 N001。"""

    def __init__(self, existing: StaffAccount) -> None:
        self.existing = existing
        self.scalar_calls = 0
        self.added: list[StaffAccount] = []

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        return False

    def scalar(self, _statement):
        self.scalar_calls += 1
        return self.existing if self.scalar_calls == 1 else None

    def add(self, staff: StaffAccount) -> None:
        self.added.append(staff)

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


def test_password_hash_is_not_plaintext() -> None:
    """医护密码应保存为 bcrypt 哈希并支持正确校验。"""
    password_hash = hash_password("123456")

    assert password_hash != "123456"
    assert password_hash.startswith("$2")
    assert verify_password("123456", password_hash)
    assert not verify_password("654321", password_hash)


def test_staff_login_creates_session_without_exposing_hash(monkeypatch) -> None:
    """医护登录成功时应返回公开账号信息并写入 Redis 会话。"""
    staff = StaffAccount(
        id=7,
        staff_no="N007",
        staff_name="测试护士",
        role_code="nurse",
        department_name="测试病区",
        password_hash=hash_password("123456"),
        account_status="启用",
    )
    redis = _FakeRedis()
    monkeypatch.setattr(staff_service, "get_redis", lambda: redis)

    result, token = staff_service.login_staff(
        _FakeDb(staff),
        StaffLoginRequest(staff_no=" n007 ", password="123456"),
    )

    assert token
    assert result.staff.staff_no == "N007"
    assert result.staff.id == 7
    assert not hasattr(result.staff, "password_hash")
    assert redis.saved is not None
    assert redis.saved["value"] == {"staff_id": 7, "staff_no": "N007"}


def test_staff_login_rejects_wrong_password(monkeypatch) -> None:
    """密码错误时不得创建会话。"""
    staff = StaffAccount(
        id=8,
        staff_no="N008",
        staff_name="测试护士",
        role_code="nurse",
        department_name="测试病区",
        password_hash=hash_password("123456"),
        account_status="启用",
    )
    redis = _FakeRedis()
    monkeypatch.setattr(staff_service, "get_redis", lambda: redis)

    with pytest.raises(AppError) as exc_info:
        staff_service.login_staff(
            _FakeDb(staff),
            StaffLoginRequest(staff_no="N008", password="wrong"),
        )

    assert exc_info.value.code == ErrorCode.ERR_STAFF_001
    assert redis.saved is None


def test_staff_seeder_restores_logically_deleted_demo_account() -> None:
    """重复执行种子时应恢复被逻辑删除的演示账号。"""
    existing = StaffAccount(
        id=1,
        staff_no="N001",
        staff_name="历史姓名",
        role_code="nurse",
        department_name="历史科室",
        password_hash=hash_password("123456"),
        account_status="停用",
        deleted=1,
    )
    session = _FakeSeederSession(existing)

    result = StaffSeeder(session_factory=lambda: session).seed()

    assert result == {"created": 4, "updated": 1, "total": 5}
    assert existing.staff_name == "李护士"
    assert existing.account_status == "启用"
    assert existing.deleted == 0


def test_patient_demo_seeds_have_unique_identity_credentials() -> None:
    """每位患者演示数据都应包含唯一身份证号和手机号，供登录联调。"""
    id_cards = [seed["id_card_no"] for seed in _PATIENT_SEEDS]
    phones = [seed["phone"] for seed in _PATIENT_SEEDS]

    assert len(_PATIENT_SEEDS) == 10
    assert len(set(id_cards)) == len(id_cards)
    assert len(set(phones)) == len(phones)
    assert all(len(card) == 18 for card in id_cards)
