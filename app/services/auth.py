import uuid
from typing import Optional, Dict, Any
from fastapi import Depends, Request
from fastapi_users import BaseUserManager, UUIDIDMixin, FastAPIUsers
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.jwt import generate_jwt
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.repositories.models import User
from app.infra.database import get_db_session
from app.infra.vault import VaultClient
from app.domain.exceptions import PermissionDenied

logger = structlog.get_logger()

# 1. Database adapter dependency
async def get_user_db(session: AsyncSession = Depends(get_db_session)):
    yield SQLAlchemyUserDatabase(session, User)

# 2. UserManager with disabled email/SMTP flow
class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    async def on_after_register(self, user: User, request: Optional[Request] = None):
        logger.info("User registered successfully", user_id=str(user.id), email=user.email, role=user.role)

    async def on_after_forgot_password(self, user: User, token: str, request: Optional[Request] = None):
        logger.info("User requested password reset (Email Flow Disabled)", user_id=str(user.id), token=token)

    async def on_after_request_verify(self, user: User, token: str, request: Optional[Request] = None):
        logger.info("User verification requested (Email Flow Disabled)", user_id=str(user.id), token=token)

# 3. Dynamic User Manager provider retrieving secrets from Vault
async def get_user_manager(user_db=Depends(get_user_db), request: Request = None):
    # Resolve secret key from Vault Client
    vault = getattr(request.app.state, "vault", None) if request else None
    if not vault:
        vault = VaultClient()
        
    try:
        secrets = await vault.get_secret("secret/data/app")
        jwt_secret = secrets.get("jwt_secret")
    except Exception:
        jwt_secret = None

    if not jwt_secret:
        try:
            secrets = await vault.get_secret("secret/app")
            jwt_secret = secrets.get("jwt_secret", "dev-secret-change-me")
        except Exception:
            jwt_secret = "dev-secret-change-me"

    user_manager = UserManager(user_db)
    user_manager.reset_password_token_secret = jwt_secret
    user_manager.verification_token_secret = jwt_secret
    return user_manager

# 4. Custom JWT Strategy to encode Role into JWT claim payload
class RoleJWTStrategy(JWTStrategy):
    async def write_token(self, user: User) -> str:
        data = {
            "sub": str(user.id),
            "aud": self.token_audience,
            "role": user.role
        }
        return generate_jwt(data, self.encode_key, self.lifetime_seconds, algorithm=self.algorithm)

# 5. Dynamic Strategy provider retrieving secret from Vault
async def get_jwt_strategy(request: Request) -> RoleJWTStrategy:
    vault = getattr(request.app.state, "vault", None) if request else None
    if not vault:
        vault = VaultClient()
        
    try:
        secrets = await vault.get_secret("secret/data/app")
        jwt_secret = secrets.get("jwt_secret")
    except Exception:
        jwt_secret = None

    if not jwt_secret:
        try:
            secrets = await vault.get_secret("secret/app")
            jwt_secret = secrets.get("jwt_secret", "dev-secret-change-me")
        except Exception:
            jwt_secret = "dev-secret-change-me"

    return RoleJWTStrategy(secret=jwt_secret, lifetime_seconds=3600)

# 6. Transport & Backend declaration
bearer_transport = BearerTransport(tokenUrl="auth/login")

auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

# 7. FastAPIUsers client initialization
fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [auth_backend],
)

# 8. Standard active user dependency
current_active_user = fastapi_users.current_user(active=True)

# 9. Role-check guard dependency wrapper
def require_role(role: str):
    async def dep(user: User = Depends(current_active_user)):
        if user.role != role:
            raise PermissionDenied("Insufficient permissions.")
        return user
    return dep
