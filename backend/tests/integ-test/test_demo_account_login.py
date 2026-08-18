"""演示医护与患者账号真实登录集成测试。

前置条件：按 deploy/Install.md 启动 PostgreSQL、Redis，并执行 seed_demo。
"""

from fastapi.testclient import TestClient

from app.main import app

STAFF_NOS = ["N001", "N002", "N003", "N004", "N005"]
PATIENT_CREDENTIALS = [
    ("110101194803120010", "13800000001", "张桂芳"),
    ("110101195507250026", "13800000002", "李国强"),
    ("110101194011020038", "13800000003", "王秀兰"),
    ("110101196801180043", "13800000004", "陈建军"),
    ("110101198509300051", "13800000005", "赵敏"),
    ("110101197206150028", "13800000006", "周海燕"),
    ("110101196212080035", "13800000007", "孙志伟"),
    ("110101197904220026", "13800000008", "杨秀梅"),
    ("110101195010090019", "13800000009", "黄建国"),
    ("11010119920214002X", "13800000010", "林晓莉"),
]


def test_all_seeded_staff_accounts_can_login() -> None:
    """5 个医护演示账号均应通过数据库密码哈希和 Redis 会话登录。"""
    with TestClient(app) as client:
        for staff_no in STAFF_NOS:
            response = client.post(
                "/api/auth/staff/login",
                json={"staff_no": staff_no, "password": "123456"},
            )
            assert response.status_code == 200, response.text
            data = response.json()["data"]["staff"]
            assert data["staff_no"] == staff_no
            assert "password_hash" not in data

            current = client.get("/api/auth/staff/me")
            assert current.status_code == 200
            assert current.json()["data"]["staff"]["staff_no"] == staff_no
            assert client.post("/api/auth/staff/logout").status_code == 200


def test_all_seeded_patients_can_login() -> None:
    """10 位患者均应通过身份证号、手机号和在院记录登录。"""
    with TestClient(app) as client:
        for id_card_no, phone, patient_name in PATIENT_CREDENTIALS:
            response = client.post(
                "/api/patients/login",
                json={"id_card_no": id_card_no, "phone": phone},
            )
            assert response.status_code == 200, response.text
            data = response.json()["data"]
            assert data["patient"]["patient_name"] == patient_name
            assert "id_card_no" not in data["patient"]
            assert "id_card_ciphertext" not in data["patient"]
            assert client.post("/api/patients/logout").status_code == 200


def test_staff_session_protects_nurse_patient_list() -> None:
    """在院患者列表应拒绝匿名请求并接受有效医护会话。"""
    with TestClient(app) as client:
        anonymous = client.get("/api/patients/in-hospital")
        assert anonymous.status_code == 401
        assert anonymous.json()["code"] == "ERR_STAFF_002"

        assert (
            client.post(
                "/api/auth/staff/login",
                json={"staff_no": "N001", "password": "123456"},
            ).status_code
            == 200
        )
        authorized = client.get("/api/patients/in-hospital")
        assert authorized.status_code == 200
        assert len(authorized.json()["data"]) >= 10
