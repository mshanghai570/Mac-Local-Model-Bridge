from fastapi.testclient import TestClient

from local_ai_gateway.server import create_app


def test_bridge_model_routes_are_mounted_and_require_explicit_pairing():
    app = create_app()
    client = TestClient(app)

    response = client.get("/bridge/v1/models")

    assert response.status_code == 401
    assert "paired-device token" in response.json()["detail"]
