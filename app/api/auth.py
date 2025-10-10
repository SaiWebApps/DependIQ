"""
Authentication API routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..middleware import get_current_user
from ..models import User
from ..services.auth_service import AuthService
from ..services.token_service import create_access_token, create_refresh_token

router = APIRouter(prefix="/auth", tags=["authentication"])


# Request/Response Models
class RegisterRequest(BaseModel):
    """User registration request"""

    email: EmailStr
    password: str
    confirm_password: str


class LoginRequest(BaseModel):
    """User login request"""

    email: EmailStr
    password: str


class RefreshTokenRequest(BaseModel):
    """Token refresh request"""

    refresh_token: str


class VerifyEmailRequest(BaseModel):
    """Email verification request"""

    token: str


class ForgotPasswordRequest(BaseModel):
    """Forgot password request"""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Password reset request"""

    token: str
    new_password: str
    confirm_password: str


class ChangePasswordRequest(BaseModel):
    """Change password request"""

    current_password: str
    new_password: str
    confirm_password: str


class AuthResponse(BaseModel):
    """Authentication response"""

    message: str
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str | None = None
    expires_in: int | None = None
    user: dict | None = None


class MessageResponse(BaseModel):
    """Generic message response"""

    message: str


class CheckEmailRequest(BaseModel):
    """Check email request"""

    email: EmailStr


class SendMagicLinkRequest(BaseModel):
    """Send registration link request"""

    email: EmailStr


class CompleteMagicLinkRequest(BaseModel):
    """Complete registration link request"""

    token: str
    temp_password: str
    new_password: str
    confirm_password: str
    use_passkey: bool = False


# Routes


@router.post(
    "/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED
)
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Register a new user with email and password

    - **email**: User email address
    - **password**: User password (min 8 chars, must include uppercase, lowercase, number, special char)
    - **confirm_password**: Password confirmation
    """
    auth_service = AuthService(db)

    user, error = await auth_service.register_user(
        email=request.email,
        password=request.password,
        confirm_password=request.confirm_password,
    )

    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return AuthResponse(
        message="Registration successful. Please check your email to verify your account.",
        user={"id": str(user.id), "email": user.email},
    )


@router.post("/check-email", response_model=dict)
async def check_email(request: CheckEmailRequest, db: AsyncSession = Depends(get_db)):
    """
    Check if email exists in the system

    - **email**: Email address to check

    Returns whether the email exists and needs password or is new
    """
    auth_service = AuthService(db)

    exists, error = await auth_service.check_email_exists(email=request.email)

    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return {"exists": exists, "requires_password": exists}


@router.post("/send-magic-link", response_model=MessageResponse)
async def send_magic_link(
    request: SendMagicLinkRequest, db: AsyncSession = Depends(get_db)
):
    """
    Send registration link to new user

    - **email**: User email address

    Sends an email with a registration link and temporary password
    """
    auth_service = AuthService(db)

    token, error = await auth_service.send_magic_link(email=request.email)

    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    # In production, this should send an email
    # For now, return success message
    return MessageResponse(
        message="Registration link sent! Please check your email for the registration link and temporary password."
    )


@router.post(
    "/complete-magic-link-registration",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
async def complete_magic_link_registration(
    request: CompleteMagicLinkRequest, db: AsyncSession = Depends(get_db)
):
    """
    Complete registration using registration link

    - **token**: Registration link token from email URL
    - **temp_password**: Temporary password from email
    - **new_password**: User's desired new password
    - **confirm_password**: Password confirmation
    - **use_passkey**: Whether to use passkey instead of password
    """
    auth_service = AuthService(db)

    user, error = await auth_service.complete_magic_link_registration(
        token=request.token,
        temp_password=request.temp_password,
        new_password=request.new_password,
        confirm_password=request.confirm_password,
        use_passkey=request.use_passkey,
    )

    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    # Generate tokens for auto-login
    access_token = create_access_token(str(user.id), user.email)
    refresh_token = create_refresh_token(str(user.id))

    return AuthResponse(
        message="Registration completed successfully!",
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=900,
        user=user.to_dict(),
    )


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Login with email and password

    - **email**: User email address
    - **password**: User password

    Returns JWT access token (15 min expiry) and refresh token (7 days expiry)
    """
    auth_service = AuthService(db)

    tokens, error = await auth_service.login_user(
        email=request.email, password=request.password
    )

    if error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error,
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthResponse(message="Login successful", **tokens)


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(
    request: RefreshTokenRequest, db: AsyncSession = Depends(get_db)
):
    """
    Refresh access token using refresh token

    - **refresh_token**: JWT refresh token

    Returns new access token (15 min expiry)
    """
    auth_service = AuthService(db)

    access_token, error = await auth_service.refresh_access_token(
        refresh_token=request.refresh_token
    )

    if error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error,
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthResponse(
        message="Token refreshed successfully",
        access_token=access_token,
        token_type="bearer",
        expires_in=900,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(current_user: User = Depends(get_current_user)):
    """
    Logout current user

    Note: Client should discard tokens. Server-side token blacklisting can be added later.
    """
    return MessageResponse(message="Logged out successfully")


@router.get("/verify-email", response_model=MessageResponse)
async def verify_email_get(token: str, db: AsyncSession = Depends(get_db)):
    """
    Verify email address with token (from email link)

    - **token**: Email verification token from email URL
    """
    from fastapi.responses import RedirectResponse

    auth_service = AuthService(db)
    success, error = await auth_service.verify_email(token=token)

    if error:
        # Redirect to login with error message
        return RedirectResponse(url=f"/login?error=verification_failed&message={error}")

    # Redirect to login with success message
    return RedirectResponse(url="/login?verified=true")


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email_post(
    request: VerifyEmailRequest, db: AsyncSession = Depends(get_db)
):
    """
    Verify email address with token (API call)

    - **token**: Email verification token from email
    """
    auth_service = AuthService(db)

    success, error = await auth_service.verify_email(token=request.token)

    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return MessageResponse(message="Email verified successfully. You can now log in.")


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    request: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)
):
    """
    Request password reset email

    - **email**: User email address

    Note: Always returns success to prevent email enumeration
    """
    auth_service = AuthService(db)

    token, error = await auth_service.request_password_reset(email=request.email)

    # Always return success message to prevent email enumeration
    return MessageResponse(
        message="If an account exists with this email, you will receive password reset instructions."
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    request: ResetPasswordRequest, db: AsyncSession = Depends(get_db)
):
    """
    Reset password with token

    - **token**: Password reset token from email
    - **new_password**: New password
    - **confirm_password**: Password confirmation
    """
    auth_service = AuthService(db)

    success, error = await auth_service.reset_password(
        token=request.token,
        new_password=request.new_password,
        confirm_password=request.confirm_password,
    )

    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return MessageResponse(message="Password reset successfully. You can now log in.")


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Change password for authenticated user

    - **current_password**: Current password
    - **new_password**: New password
    - **confirm_password**: Password confirmation
    """
    auth_service = AuthService(db)

    success, error = await auth_service.change_password(
        user_id=str(current_user.id),
        current_password=request.current_password,
        new_password=request.new_password,
        confirm_password=request.confirm_password,
    )

    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    return MessageResponse(message="Password changed successfully")


@router.get("/me", response_model=dict)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    Get current authenticated user information
    """
    return current_user.to_dict()


# GitHub OAuth Routes


@router.get("/github")
async def github_oauth_login(db: AsyncSession = Depends(get_db)):
    """
    Initiate GitHub OAuth flow

    Redirects user to GitHub authorization page
    """
    import secrets

    from fastapi.responses import RedirectResponse

    from ..services.github_oauth_service import GitHubOAuthService

    github_service = GitHubOAuthService(db)

    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)

    # Store state in session/cache for validation (simplified for now)
    # In production, store in Redis or database

    auth_url = github_service.get_authorization_url(state)
    return RedirectResponse(url=auth_url)


@router.get("/github/callback")
async def github_oauth_callback(
    code: str, state: str, db: AsyncSession = Depends(get_db)
):
    """
    Handle GitHub OAuth callback

    - **code**: Authorization code from GitHub
    - **state**: CSRF protection state
    """
    from fastapi.responses import RedirectResponse

    from ..services.github_oauth_service import GitHubOAuthService
    from ..services.token_service import create_access_token, create_refresh_token

    github_service = GitHubOAuthService(db)

    # Exchange code for token
    token_data = await github_service.exchange_code_for_token(code)
    if not token_data:
        return RedirectResponse(url="/login?error=github_auth_failed")

    access_token = token_data.get("access_token")

    # Get GitHub user info
    github_user = await github_service.get_github_user_info(access_token)
    if not github_user:
        return RedirectResponse(url="/login?error=github_user_fetch_failed")

    # Check if user exists with GitHub email
    from sqlalchemy import select

    result = await db.execute(
        select(User).where(User.email == github_user["email"].lower())
    )
    user = result.scalar_one_or_none()

    if not user:
        # Create new user with GitHub OAuth
        user = User(
            email=github_user["email"].lower(),
            email_verified=True,  # GitHub emails are verified
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    # Link GitHub account
    await github_service.link_github_account(
        user=user,
        access_token=access_token,
        github_user_data=github_user,
        refresh_token=token_data.get("refresh_token"),
    )

    # Create session
    await github_service.create_user_session(user=user, access_token=access_token)

    # Generate JWT tokens
    jwt_access_token = create_access_token({"user_id": str(user.id)})
    # Note: Refresh token intentionally not returned via cookie for security
    _jwt_refresh_token = create_refresh_token({"user_id": str(user.id)})

    # Create redirect response to profile page
    response = RedirectResponse(url="/profile?github_connected=true", status_code=303)

    # Set tokens in cookies
    response.set_cookie(
        key="access_token",
        value=jwt_access_token,
        max_age=900,  # 15 minutes
        httponly=False,  # Allow JavaScript access for API calls
        samesite="lax",
    )

    return response


@router.post("/github/link")
async def link_github_account(
    code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Link GitHub account to existing user

    - **code**: Authorization code from GitHub
    """
    from ..services.github_oauth_service import GitHubOAuthService

    github_service = GitHubOAuthService(db)

    # Exchange code for token
    token_data = await github_service.exchange_code_for_token(code)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to exchange GitHub authorization code",
        )

    access_token = token_data.get("access_token")

    # Get GitHub user info
    github_user = await github_service.get_github_user_info(access_token)
    if not github_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to fetch GitHub user information",
        )

    # Link GitHub account
    await github_service.link_github_account(
        user=current_user,
        access_token=access_token,
        github_user_data=github_user,
        refresh_token=token_data.get("refresh_token"),
    )

    # Create session
    await github_service.create_user_session(
        user=current_user, access_token=access_token
    )

    return {
        "message": "GitHub account linked successfully",
        "github_user": github_user["login"],
        "github_email": github_user["email"],
    }
