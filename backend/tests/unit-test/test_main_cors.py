from fastapi.testclient import TestClient

from app.main import create_app


def test_lan_frontend_origin_can_pass_cors_preflight():
    client = TestClient(create_app())

    response = client.options(
        "/api/auth/staff/login",
        headers={
            "Origin": "http://192.168.144.1:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://192.168.144.1:3000"
    assert response.headers["access-control-allow-credentials"] == "true"
