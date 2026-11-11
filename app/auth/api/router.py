from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import OAuth2PasswordRequestForm

from app.auth.repos.revoked_token import RevokedTokenRepo
from app.auth.repos.user import UserRepo
from app.auth.schemas.token import (
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.auth.schemas.user import UserRead
from app.auth.services.auth import AuthService
from app.auth.use_cases.login import LoginUseCase
from app.auth.use_cases.logout import LogoutUseCase
from app.auth.use_cases.refresh_token import RefreshTokenUseCase
from app.auth.use_cases.register import RegisterUseCase
from app.core.config import settings
from app.core.exceptions.schemas import CONFLICT, RATE_LIMITED, UNAUTHENTICATED
from app.core.ratelimit import limiter
from app.deps.auth import CurrentUser, oauth2_scheme
from app.deps.repository import get_repo

router = APIRouter(prefix="/auth", tags=["Auth"], responses={**RATE_LIMITED})


def _auth_service(
    user_repo: Annotated[UserRepo, Depends(get_repo(UserRepo))],
    revoked_token_repo: Annotated[RevokedTokenRepo, Depends(get_repo(RevokedTokenRepo))],
) -> AuthService:
    return AuthService(user_repo, revoked_token_repo)


AuthServiceDep = Annotated[AuthService, Depends(_auth_service)]


def _never_cache(response: Response) -> None:
    # RFC 6749, 5.1: a response that carries tokens must not be stored by any cache.
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


@router.post("/login", response_model=TokenResponse, responses={**UNAUTHENTICATED})
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def login(
    request: Request,
    response: Response,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    service: AuthServiceDep,
):
    """Exchange credentials for an access token and a refresh token.

    OAuth2 password form, not JSON. `username` takes the email or the username. A wrong
    password and an unknown account answer the same 401.
    """
    _never_cache(response)
    uc = LoginUseCase(service)
    return await uc.execute(form.username, form.password)


@router.post("/register", response_model=UserRead, status_code=201, responses={**CONFLICT})
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def register(request: Request, body: RegisterRequest, service: AuthServiceDep):
    """Create an account. It gets the `user` role; 409 if the email or username is taken."""
    uc = RegisterUseCase(service)
    user = await uc.execute(body.email, body.username, body.password, body.full_name)
    return UserRead.model_validate(user)


@router.post("/refresh", response_model=TokenResponse, responses={**UNAUTHENTICATED})
@limiter.limit(settings.RATE_LIMIT_STRICT)
async def refresh(
    request: Request, response: Response, body: RefreshRequest, service: AuthServiceDep
):
    """Exchange a refresh token for a new pair. The token presented stops working.

    Presenting a refresh token a second time answers 401 with code `refresh_token_reused`
    and ends every session of the account.
    """
    _never_cache(response)
    uc = RefreshTokenUseCase(service)
    return await uc.execute(body.refresh_token)


@router.post("/logout", status_code=204, responses={**UNAUTHENTICATED})
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def logout(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
    service: AuthServiceDep,
    body: LogoutRequest | None = None,
):
    """Revoke the access token of the request and, if sent, the refresh token."""
    uc = LogoutUseCase(service)
    await uc.execute(token, body.refresh_token if body else None)


@router.get("/me", response_model=UserRead, responses={**UNAUTHENTICATED})
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def me(request: Request, user: CurrentUser):
    """The authenticated user, with its roles."""
    return UserRead.model_validate(user)
