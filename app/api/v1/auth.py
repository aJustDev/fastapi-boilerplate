import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm

from app.core.config import settings
from app.core.ratelimit import limiter
from app.deps.auth import CurrentUser
from app.deps.repository import get_repo
from app.repos.auth.user import UserRepo
from app.schemas.auth.token import RefreshRequest, RegisterRequest, TokenResponse
from app.schemas.auth.user import UserRead
from app.services.auth import AuthService
from app.use_cases.auth.login import LoginUseCase
from app.use_cases.auth.refresh_token import RefreshTokenUseCase
from app.use_cases.auth.register import RegisterUseCase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


def _auth_service(
    user_repo: Annotated[UserRepo, Depends(get_repo(UserRepo))],
) -> AuthService:
    return AuthService(user_repo)


AuthServiceDep = Annotated[AuthService, Depends(_auth_service)]


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    service: AuthServiceDep,
):
    uc = LoginUseCase(service)
    logger.info(f"Attempting login for user: {form.username}")
    return await uc.execute(form.username, form.password)


@router.post("/register", response_model=UserRead, status_code=201)
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def register(request: Request, body: RegisterRequest, service: AuthServiceDep):
    uc = RegisterUseCase(service)
    user = await uc.execute(body.email, body.username, body.password, body.full_name)
    return UserRead.model_validate(user)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def refresh(request: Request, body: RefreshRequest, service: AuthServiceDep):
    uc = RefreshTokenUseCase(service)
    return await uc.execute(body.refresh_token)


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser):
    return UserRead.model_validate(user)
