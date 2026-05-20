import pytest
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.repositories.models import User
from app.services.auth import get_user_db
from app.infra.vault import VaultClient

try:
    from jose import jwt
except ImportError:
    import jwt

@pytest.mark.asyncio
async def test_auth_and_role_based_permissions_flow(caplog):
    # 1. Generate unique emails to avoid database conflicts
    unique_id = uuid.uuid4().hex[:6]
    user_email = f"user_{unique_id}@example.com"
    admin_email = f"admin_{unique_id}@example.com"
    password = "SecurePassword123!"

    # 2. Trigger startup/lifespan context manager correctly to initialize Database and Vault engines
    with TestClient(app, raise_server_exceptions=False) as client:
        # 3. Register Regular User
        reg_response = client.post(
            "/auth/register",
            json={
                "email": user_email,
                "password": password,
                "role": "user"
            }
        )
        assert reg_response.status_code == 201
        reg_data = reg_response.json()
        assert reg_data["email"] == user_email
        assert reg_data["role"] == "user"
        assert "id" in reg_data

        # 4. Register Admin User
        admin_reg_response = client.post(
            "/auth/register",
            json={
                "email": admin_email,
                "password": password,
                "role": "admin"
            }
        )
        assert admin_reg_response.status_code == 201
        assert admin_reg_response.json()["role"] == "admin"

        # 5. Log in Regular User and Retrieve JWT
        login_response = client.post(
            "/auth/login",
            data={
                "username": user_email,
                "password": password
            }
        )
        assert login_response.status_code == 200
        login_data = login_response.json()
        assert "access_token" in login_data
        assert login_data["token_type"] == "bearer"
        user_token = login_data["access_token"]

        # 6. Log in Admin User and Retrieve JWT
        admin_login_response = client.post(
            "/auth/login",
            data={
                "username": admin_email,
                "password": password
            }
        )
        assert admin_login_response.status_code == 200
        admin_token = admin_login_response.json()["access_token"]

        # 7. Static JWT Claim Verification
        # Fetch signing key from Vault to decode and verify token payload statically
        vault = VaultClient()
        try:
            secrets = await vault.get_secret("secret/data/app")
            jwt_secret = secrets.get("jwt_secret")
        except Exception:
            jwt_secret = None

        if not jwt_secret:
            secrets = await vault.get_secret("secret/app")
            jwt_secret = secrets.get("jwt_secret", "dev-secret-change-me")

        # Decode and verify regular user payload
        user_payload = jwt.decode(
            user_token,
            jwt_secret,
            algorithms=["HS256"],
            audience="fastapi-users:auth"
        )
        assert user_payload["role"] == "user"
        assert "sub" in user_payload

        # Decode and verify admin payload
        admin_payload = jwt.decode(
            admin_token,
            jwt_secret,
            algorithms=["HS256"],
            audience="fastapi-users:auth"
        )
        assert admin_payload["role"] == "admin"

        # 8. Access /users/me using Bearer Authentication
        me_response = client.get(
            "/users/me",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert me_response.status_code == 200
        assert me_response.json()["email"] == user_email
        assert me_response.json()["role"] == "user"

        # 9. Hit Admin Endpoint with Regular User (Assert 403 Forbidden)
        admin_restricted_response = client.get(
            "/admin/dashboard",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert admin_restricted_response.status_code == 403
        assert admin_restricted_response.json()["error"] == "PERMISSION_DENIED"

        # 10. Hit Admin Endpoint with Admin User (Assert 200 OK)
        admin_ok_response = client.get(
            "/admin/dashboard",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert admin_ok_response.status_code == 200
        assert admin_ok_response.json()["status"] == "success"
        assert "Welcome to the admin dashboard" in admin_ok_response.json()["message"]
        assert admin_ok_response.json()["role"] == "admin"
