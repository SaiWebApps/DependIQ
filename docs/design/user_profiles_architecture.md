# User Profiles Architecture Plan

## Overview
This document outlines the architecture for implementing user authentication and profile management in dependiq, based on the requirements specification.

## Requirements Summary
- **Authentication**: Required for all features (ZIP upload and GitHub access)
- **Database**: PostgreSQL for both development and production
- **Session Management**: Hybrid approach
  - JWT tokens for read operations
  - Server-side sessions for GitHub operations (creating pull requests, etc.)
- **OAuth Providers**: GitHub (complete first), then Google, Microsoft, LinkedIn, Bitbucket (Atlassian)
- **Profile Features**:
  - Email/password authentication
  - OAuth account linking/unlinking
  - Password management
  - Project history tracking
  - User preferences (theme: light/dark, language)

---

## Database Schema Design

### Tables

#### 1. `users`
Core user account information.

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255),  -- NULL if OAuth-only user
    email_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    CONSTRAINT email_format CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$')
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_created_at ON users(created_at);
```

#### 2. `oauth_connections`
Linked OAuth provider accounts.

```sql
CREATE TABLE oauth_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,  -- 'github', 'google', 'microsoft', 'linkedin', 'bitbucket'
    provider_user_id VARCHAR(255) NOT NULL,
    provider_email VARCHAR(255),
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    token_expires_at TIMESTAMP,
    scopes TEXT,
    provider_data JSONB,  -- Store additional provider-specific data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(provider, provider_user_id),
    UNIQUE(user_id, provider)  -- One connection per provider per user
);

CREATE INDEX idx_oauth_user_id ON oauth_connections(user_id);
CREATE INDEX idx_oauth_provider ON oauth_connections(provider);
```

#### 3. `user_preferences`
User-specific settings and preferences.

```sql
CREATE TABLE user_preferences (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    theme VARCHAR(20) DEFAULT 'light',  -- 'light' or 'dark'
    language VARCHAR(10) DEFAULT 'en',  -- ISO language codes
    timezone VARCHAR(50) DEFAULT 'UTC',
    notifications_enabled BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT theme_check CHECK (theme IN ('light', 'dark'))
);
```

#### 4. `project_history`
Track all project uploads and updates.

```sql
CREATE TABLE project_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id VARCHAR(50) UNIQUE NOT NULL,
    project_name VARCHAR(255),
    project_type VARCHAR(50),  -- 'python', 'java', 'scala', etc.
    source_type VARCHAR(20) NOT NULL,  -- 'zip_upload' or 'github'
    github_repo_url VARCHAR(500),
    zip_file_path TEXT,
    status VARCHAR(20) DEFAULT 'processing',  -- 'processing', 'completed', 'failed'
    dependencies_count INTEGER DEFAULT 0,
    updates_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    metadata JSONB,  -- Store additional project-specific data
    CONSTRAINT status_check CHECK (status IN ('processing', 'completed', 'failed')),
    CONSTRAINT source_check CHECK (source_type IN ('zip_upload', 'github'))
);

CREATE INDEX idx_project_user_id ON project_history(user_id);
CREATE INDEX idx_project_created_at ON project_history(created_at DESC);
CREATE INDEX idx_project_status ON project_history(status);
CREATE INDEX idx_project_session_id ON project_history(session_id);
```

#### 5. `user_sessions`
Server-side session storage for GitHub operations.

```sql
CREATE TABLE user_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token VARCHAR(255) UNIQUE NOT NULL,
    oauth_state VARCHAR(255),  -- For OAuth flow validation
    github_access_token TEXT,
    session_data JSONB,  -- Store any additional session data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sessions_user_id ON user_sessions(user_id);
CREATE INDEX idx_sessions_token ON user_sessions(session_token);
CREATE INDEX idx_sessions_expires ON user_sessions(expires_at);
```

#### 6. `email_verification_tokens`
Email verification tokens for new accounts.

```sql
CREATE TABLE email_verification_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP
);

CREATE INDEX idx_verify_token ON email_verification_tokens(token);
CREATE INDEX idx_verify_user ON email_verification_tokens(user_id);
```

#### 7. `password_reset_tokens`
Password reset tokens for "forgot password" flow.

```sql
CREATE TABLE password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP
);

CREATE INDEX idx_reset_token ON password_reset_tokens(token);
CREATE INDEX idx_reset_user ON password_reset_tokens(user_id);
```

---

## Authentication Architecture

### Hybrid Authentication Strategy

```mermaid
graph TB
    User[User Request] --> CheckAuth{Authentication Required?}
    CheckAuth -->|Read Operation| JWT[Validate JWT Token]
    CheckAuth -->|GitHub Operation| Session[Validate Server Session]

    JWT --> JWTValid{Valid?}
    JWTValid -->|Yes| ReadDB[(Read from Database)]
    JWTValid -->|No| Return401[Return 401 Unauthorized]

    Session --> SessionValid{Valid?}
    SessionValid -->|Yes| GitHubOp[Perform GitHub Operation]
    SessionValid -->|No| Return401

    ReadDB --> Response[Return Response]
    GitHubOp --> Response
```

### JWT Token Structure

**Access Token** (Short-lived: 15 minutes)
```json
{
  "sub": "user_id",
  "email": "user@example.com",
  "exp": 1234567890,
  "iat": 1234567800,
  "type": "access"
}
```

**Refresh Token** (Long-lived: 7 days)
```json
{
  "sub": "user_id",
  "exp": 1234567890,
  "iat": 1234567800,
  "type": "refresh"
}
```

### Authentication Flows

#### 1. Email/Password Registration Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant API
    participant Database
    participant Email

    User->>Frontend: Fill registration form
    Frontend->>API: POST /auth/register
    API->>Database: Check if email exists
    Database-->>API: Email available
    API->>API: Hash password (bcrypt)
    API->>Database: Create user record
    API->>Database: Create verification token
    API->>Email: Send verification email
    API-->>Frontend: Registration successful
    Frontend-->>User: Check your email

    User->>Email: Click verification link
    Email->>Frontend: Redirect with token
    Frontend->>API: POST /auth/verify-email
    API->>Database: Validate and mark verified
    API-->>Frontend: Email verified
    Frontend-->>User: Login now available
```

#### 2. Email/Password Login Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant API
    participant Database

    User->>Frontend: Enter credentials
    Frontend->>API: POST /auth/login
    API->>Database: Find user by email
    Database-->>API: User record
    API->>API: Verify password hash
    API->>API: Generate JWT tokens
    API->>Database: Update last_login_at
    API-->>Frontend: Access + Refresh tokens
    Frontend->>Frontend: Store tokens
    Frontend-->>User: Redirect to dashboard
```

#### 3. GitHub OAuth Flow (Complete)

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant API
    participant Session DB
    participant GitHub
    participant User DB

    User->>Frontend: Click "Sign in with GitHub"
    Frontend->>API: GET /auth/github/authorize
    API->>API: Generate state token
    API->>Session DB: Store state + session
    API-->>Frontend: Redirect URL
    Frontend->>GitHub: Redirect to GitHub OAuth
    GitHub-->>User: Login to GitHub
    User->>GitHub: Authorize app
    GitHub->>Frontend: Redirect with code + state
    Frontend->>API: GET /auth/github/callback?code=...&state=...
    API->>Session DB: Validate state token
    API->>GitHub: Exchange code for access token
    GitHub-->>API: Access token + user info
    API->>User DB: Find or create user by GitHub ID
    API->>User DB: Store/update OAuth connection
    API->>API: Generate JWT tokens
    API->>Session DB: Create user session
    API-->>Frontend: Access + Refresh tokens + Session cookie
    Frontend-->>User: Redirect to dashboard
```

#### 4. OAuth Account Linking Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant API
    participant OAuth DB
    participant Provider

    User->>Frontend: Click "Link GitHub Account"
    Frontend->>API: GET /auth/github/link (with JWT)
    API->>API: Validate JWT, get user_id
    API->>API: Generate state token
    API-->>Frontend: Redirect URL
    Frontend->>Provider: Redirect to OAuth provider
    Provider-->>User: Authorize app
    User->>Provider: Grant permission
    Provider->>Frontend: Redirect with code
    Frontend->>API: GET /auth/github/link/callback
    API->>Provider: Exchange code for token
    Provider-->>API: Access token + provider user ID
    API->>OAuth DB: Check if already linked
    API->>OAuth DB: Create OAuth connection
    API-->>Frontend: Account linked successfully
    Frontend-->>User: Show success message
```

---

## API Endpoints Specification

### Authentication Endpoints

#### POST `/auth/register`
Create a new user account with email/password.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!",
  "confirm_password": "SecurePassword123!"
}
```

**Response (201 Created):**
```json
{
  "message": "Registration successful. Please check your email to verify your account.",
  "user_id": "uuid-here",
  "email": "user@example.com"
}
```

**Validation:**
- Email format validation
- Password strength (min 8 chars, uppercase, lowercase, number, special char)
- Passwords match
- Email not already registered

---

#### POST `/auth/login`
Login with email and password.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!"
}
```

**Response (200 OK):**
```json
{
  "access_token": "jwt-access-token",
  "refresh_token": "jwt-refresh-token",
  "token_type": "Bearer",
  "expires_in": 900,
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "email_verified": true
  }
}
```

**Response (401 Unauthorized):**
```json
{
  "error": "Invalid email or password"
}
```

---

#### POST `/auth/refresh`
Refresh access token using refresh token.

**Request Body:**
```json
{
  "refresh_token": "jwt-refresh-token"
}
```

**Response (200 OK):**
```json
{
  "access_token": "new-jwt-access-token",
  "token_type": "Bearer",
  "expires_in": 900
}
```

---

#### POST `/auth/logout`
Logout and invalidate tokens.

**Headers:**
```
Authorization: Bearer <access-token>
```

**Response (200 OK):**
```json
{
  "message": "Logged out successfully"
}
```

---

#### POST `/auth/verify-email`
Verify email address with token.

**Request Body:**
```json
{
  "token": "verification-token-from-email"
}
```

**Response (200 OK):**
```json
{
  "message": "Email verified successfully. You can now log in."
}
```

---

#### POST `/auth/forgot-password`
Request password reset email.

**Request Body:**
```json
{
  "email": "user@example.com"
}
```

**Response (200 OK):**
```json
{
  "message": "If an account exists with this email, you will receive password reset instructions."
}
```

---

#### POST `/auth/reset-password`
Reset password with token.

**Request Body:**
```json
{
  "token": "reset-token-from-email",
  "new_password": "NewSecurePassword123!",
  "confirm_password": "NewSecurePassword123!"
}
```

**Response (200 OK):**
```json
{
  "message": "Password reset successfully. You can now log in."
}
```

---

### GitHub OAuth Endpoints

#### GET `/auth/github/authorize`
Initiate GitHub OAuth flow.

**Response (302 Redirect):**
Redirects to GitHub OAuth authorization URL.

---

#### GET `/auth/github/callback`
GitHub OAuth callback.

**Query Parameters:**
- `code`: Authorization code from GitHub
- `state`: State token for validation

**Response (302 Redirect):**
Redirects to frontend with tokens in URL or cookies.

---

#### GET `/auth/github/link`
Link GitHub account to existing user (requires authentication).

**Headers:**
```
Authorization: Bearer <access-token>
```

**Response (302 Redirect):**
Redirects to GitHub OAuth with link intent.

---

#### POST `/auth/github/unlink`
Unlink GitHub account (requires authentication).

**Headers:**
```
Authorization: Bearer <access-token>
```

**Response (200 OK):**
```json
{
  "message": "GitHub account unlinked successfully"
}
```

---

### User Profile Endpoints

#### GET `/api/user/profile`
Get current user profile.

**Headers:**
```
Authorization: Bearer <access-token>
```

**Response (200 OK):**
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "email_verified": true,
  "created_at": "2024-01-01T00:00:00Z",
  "last_login_at": "2024-01-15T12:30:00Z",
  "oauth_connections": [
    {
      "provider": "github",
      "provider_email": "user@example.com",
      "connected_at": "2024-01-10T10:00:00Z"
    }
  ],
  "preferences": {
    "theme": "dark",
    "language": "en",
    "timezone": "America/New_York"
  }
}
```

---

#### PUT `/api/user/profile`
Update user profile information.

**Headers:**
```
Authorization: Bearer <access-token>
```

**Request Body:**
```json
{
  "email": "newemail@example.com"
}
```

**Response (200 OK):**
```json
{
  "message": "Profile updated successfully",
  "user": { /* updated user object */ }
}
```

---

#### POST `/api/user/change-password`
Change user password.

**Headers:**
```
Authorization: Bearer <access-token>
```

**Request Body:**
```json
{
  "current_password": "CurrentPassword123!",
  "new_password": "NewPassword123!",
  "confirm_password": "NewPassword123!"
}
```

**Response (200 OK):**
```json
{
  "message": "Password changed successfully"
}
```

---

### User Preferences Endpoints

#### GET `/api/user/preferences`
Get user preferences.

**Headers:**
```
Authorization: Bearer <access-token>
```

**Response (200 OK):**
```json
{
  "theme": "dark",
  "language": "en",
  "timezone": "America/New_York",
  "notifications_enabled": true
}
```

---

#### PUT `/api/user/preferences`
Update user preferences.

**Headers:**
```
Authorization: Bearer <access-token>
```

**Request Body:**
```json
{
  "theme": "light",
  "language": "es"
}
```

**Response (200 OK):**
```json
{
  "message": "Preferences updated successfully",
  "preferences": { /* updated preferences */ }
}
```

---

### Project History Endpoints

#### GET `/api/user/projects`
Get user's project history.

**Headers:**
```
Authorization: Bearer <access-token>
```

**Query Parameters:**
- `page` (optional): Page number (default: 1)
- `limit` (optional): Items per page (default: 20)
- `status` (optional): Filter by status
- `source_type` (optional): Filter by source type

**Response (200 OK):**
```json
{
  "projects": [
    {
      "id": "uuid",
      "session_id": "session-123",
      "project_name": "my-app",
      "project_type": "python",
      "source_type": "zip_upload",
      "status": "completed",
      "dependencies_count": 25,
      "updates_count": 8,
      "created_at": "2024-01-15T10:00:00Z",
      "completed_at": "2024-01-15T10:15:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 45,
    "pages": 3
  }
}
```

---

#### GET `/api/user/projects/{session_id}`
Get detailed project information.

**Headers:**
```
Authorization: Bearer <access-token>
```

**Response (200 OK):**
```json
{
  "id": "uuid",
  "session_id": "session-123",
  "project_name": "my-app",
  "project_type": "python",
  "source_type": "zip_upload",
  "github_repo_url": null,
  "status": "completed",
  "dependencies_count": 25,
  "updates_count": 8,
  "created_at": "2024-01-15T10:00:00Z",
  "completed_at": "2024-01-15T10:15:00Z",
  "metadata": {
    "original_dependencies": [...],
    "updated_dependencies": [...]
  }
}
```

---

## File Structure

```
dependiq/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── database.py              # New: Database connection and session management
│   ├── api/
│   │   ├── __init__.py
│   │   ├── analysis.py
│   │   ├── files.py
│   │   ├── github.py
│   │   ├── progress.py
│   │   ├── updates.py
│   │   ├── auth.py              # New: Authentication routes
│   │   └── user.py              # New: User profile routes
│   ├── models/
│   │   ├── __init__.py
│   │   ├── dependency.py
│   │   ├── exclusions.py
│   │   ├── project.py
│   │   ├── user.py              # New: User model
│   │   ├── oauth_connection.py # New: OAuth connection model
│   │   ├── user_preference.py  # New: User preferences model
│   │   └── project_history.py  # New: Project history model
│   ├── services/
│   │   ├── __init__.py
│   │   ├── ai_service.py
│   │   ├── github_api.py
│   │   ├── github_oauth.py
│   │   ├── progress_service.py
│   │   ├── session_storage.py
│   │   ├── auth_service.py      # New: Authentication service
│   │   ├── user_service.py      # New: User management service
│   │   ├── email_service.py     # New: Email sending service
│   │   └── token_service.py     # New: JWT token service
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── auth_middleware.py   # New: JWT authentication middleware
│   └── utils/
│       ├── __init__.py
│       ├── file_utils.py
│       ├── json_parser.py
│       ├── project_utils.py
│       ├── password_utils.py     # New: Password hashing utilities
│       └── validators.py         # New: Input validation utilities
├── alembic/                      # New: Database migrations
│   ├── versions/
│   └── env.py
├── templates/
│   ├── index.html
│   ├── analysis.html
│   ├── file_viewer.html
│   ├── github_error.html
│   ├── github_repositories.html
│   ├── progress.html
│   ├── results.html
│   ├── login.html                # New: Login page
│   ├── register.html             # New: Registration page
│   ├── profile.html              # New: User profile page
│   └── email/                    # New: Email templates
│       ├── verification.html
│       └── password_reset.html
├── static/
│   ├── css/
│   │   └── main.css
│   └── js/
│       ├── main.js
│       ├── progress.js
│       ├── auth.js               # New: Authentication JS
│       └── profile.js            # New: Profile management JS
├── alembic.ini                   # New: Alembic configuration
├── .env
├── requirements.txt
└── main.py
```

---

## Security Considerations

### Password Security
- Use `bcrypt` for password hashing (cost factor: 12)
- Enforce strong password policy:
  - Minimum 8 characters
  - At least one uppercase letter
  - At least one lowercase letter
  - At least one number
  - At least one special character
- Never store passwords in plain text

### JWT Security
- Short-lived access tokens (15 minutes)
- Longer-lived refresh tokens (7 days)
- Secure token storage:
  - Access tokens: Memory only (never localStorage)
  - Refresh tokens: HttpOnly cookies
- Token rotation on refresh

### OAuth Security
- Use state parameter to prevent CSRF
- Validate state on callback
- Store OAuth tokens encrypted
- Implement token refresh before expiration

### Session Security
- Use secure, HttpOnly cookies for session tokens
- Implement session expiration
- Clean up expired sessions regularly
- Use HTTPS only in production

### Database Security
- Use parameterized queries (SQLAlchemy ORM)
- Implement row-level security where needed
- Regular backups
- Encrypted connections

### API Security
- Rate limiting on authentication endpoints
- CORS configuration for frontend
- Input validation and sanitization
- Error messages that don't leak information

---

## Implementation Phases

### Phase 1: Database Setup (Priority: High)
**Estimated Time: 2-3 days**

1. Set up PostgreSQL connection
2. Configure SQLAlchemy ORM
3. Create database models:
   - [`User`](app/models/user.py)
   - [`OAuthConnection`](app/models/oauth_connection.py)
   - [`UserPreference`](app/models/user_preference.py)
   - [`ProjectHistory`](app/models/project_history.py)
   - [`UserSession`](app/models/user_session.py)
4. Set up Alembic for migrations
5. Create initial migration scripts
6. Test database connectivity

**Deliverables:**
- Working PostgreSQL connection
- All models defined
- Migration system in place

---

### Phase 2: Core Authentication (Priority: High)
**Estimated Time: 3-4 days**

1. Implement password hashing utilities
2. Create JWT token service
3. Build authentication service:
   - User registration
   - User login
   - Token refresh
   - Password reset
4. Create authentication middleware
5. Build authentication API endpoints
6. Write unit tests for auth flow

**Deliverables:**
- Working registration and login
- JWT token generation and validation
- Password reset functionality

---

### Phase 3: GitHub OAuth Integration (Priority: High)
**Estimated Time: 2-3 days**

1. Complete GitHub OAuth service
2. Implement OAuth callback handling
3. Create session management for GitHub operations
4. Build OAuth linking/unlinking endpoints
5. Update existing GitHub integration to use new auth
6. Test OAuth flow end-to-end

**Deliverables:**
- Complete GitHub OAuth flow
- OAuth account linking
- Hybrid auth (JWT + session)

---

### Phase 4: User Profile Management (Priority: Medium)
**Estimated Time: 2-3 days**

1. Create user profile endpoints
2. Implement password change functionality
3. Build preferences management
4. Create OAuth management endpoints
5. Write tests for profile operations

**Deliverables:**
- User can view/edit profile
- Password change working
- Preferences CRUD operations

---

### Phase 5: Project History Tracking (Priority: Medium)
**Estimated Time: 2-3 days**

1. Update existing upload flow to track history
2. Create project history endpoints
3. Implement pagination
4. Add filters and search
5. Test history tracking

**Deliverables:**
- Project uploads tracked
- History API working
- Pagination implemented

---

### Phase 6: Frontend Implementation (Priority: High)
**Estimated Time: 4-5 days**

1. Create login page UI
2. Create registration page UI
3. Build user profile page
4. Implement password change form
5. Build OAuth management UI
6. Create project history view
7. Build preferences settings UI
8. Add authentication to all existing pages
9. Implement theme switching (light/dark)
10. Add language switching

**Deliverables:**
- Complete UI for all auth flows
- Protected routes
- Theme and language switching

---

### Phase 7: Integration & Testing (Priority: High)
**Estimated Time: 3-4 days**

1. Update all existing routes with auth middleware
2. Add user context to project operations
3. Test end-to-end flows
4. Fix integration issues
5. Performance testing
6. Security audit

**Deliverables:**
- All features protected by auth
- E2E tests passing
- Performance benchmarks met

---

### Phase 8: Email & Additional Features (Priority: Low)
**Estimated Time: 2-3 days**

1. Set up email service (SendGrid/AWS SES)
2. Create email templates
3. Implement email verification
4. Add "forgot password" emails
5. Test email delivery

**Deliverables:**
- Email verification working
- Password reset emails sent
- Email templates responsive

---

## Migration Strategy

### Update Existing Features

#### 1. ZIP Upload Flow
**Before:** Anonymous upload
**After:** Requires authentication

```python
# app/api/analysis.py
@router.post("/analyze/")
async def analyze_project(
    file: UploadFile,
    current_user: User = Depends(get_current_user)  # New dependency
):
    # Track in project history
    project = await create_project_history(
        user_id=current_user.id,
        source_type="zip_upload",
        ...
    )
    # Rest of existing logic
```

#### 2. GitHub Repository Selection
**Before:** OAuth without user accounts
**After:** OAuth linked to user account

```python
# app/api/github.py
@router.get("/auth/github/callback")
async def github_callback(
    code: str,
    state: str,
    current_user: User = Depends(get_current_user_optional)  # Optional for first-time
):
    # If user logged in: link to account
    # If not: create new account with GitHub
```

#### 3. Project Sessions
**Before:** In-memory dictionary
**After:** Database-backed with user association

```python
# app/api/updates.py
async def complete_update(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    # Store in project_history table
    await update_project_history(
        session_id=session_id,
        user_id=current_user.id,
        status="completed",
        ...
    )
```

---

## Configuration Updates

### Environment Variables

Add to `.env`:
```bash
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/dependiq

# JWT
JWT_SECRET_KEY=your-super-secret-jwt-key-change-in-production
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Email (for verification/reset)
EMAIL_SERVICE=sendgrid  # or 'ses' for AWS SES
SENDGRID_API_KEY=your-sendgrid-api-key
EMAIL_FROM=noreply@dependiq.com
EMAIL_FROM_NAME=dependiq

# Security
SESSION_SECRET=your-session-secret-key
SECURE_COOKIES=true  # Set to false in development

# OAuth (existing)
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret
GITHUB_REDIRECT_URI=http://localhost:8000/auth/github/callback
```

### Update `requirements.txt`

```txt
# Existing dependencies
fastapi==0.111.0
uvicorn[standard]==0.27.1
openai==1.30.1
python-multipart==0.0.9
httpx==0.24.1
aiohttp==3.9.1
jinja2==3.1.4
authlib==1.2.1
requests==2.31.0
python-jose[cryptography]==3.3.0

# New dependencies for user authentication
sqlalchemy==2.0.23
asyncpg==0.29.0  # PostgreSQL driver
alembic==1.13.1  # Database migrations
bcrypt==4.1.2  # Password hashing
passlib[bcrypt]==1.7.4  # Password utilities
python-multipart==0.0.9
email-validator==2.1.0
pydantic[email]==2.5.0
pyjwt==2.8.0

# Email service
sendgrid==6.11.0  # or boto3 for AWS SES

# Development
pytest-asyncio==0.23.2
httpx==0.24.1
```

---

## Testing Strategy

### Unit Tests
- Password hashing and validation
- JWT token generation and validation
- User model operations
- OAuth connection management
- Preferences CRUD

### Integration Tests
- Complete registration flow
- Complete login flow
- OAuth linking flow
- Password reset flow
- Email verification flow

### E2E Tests
- User registers → verifies email → logs in
- User logs in → uploads project → views history
- User connects GitHub → selects repo → updates dependencies
- User changes theme → refreshes page → theme persists

---

## Security Checklist

- [ ] Passwords hashed with bcrypt (cost 12+)
- [ ] JWT tokens properly signed and validated
- [ ] Refresh token rotation implemented
- [ ] HTTPS enforced in production
- [ ] CORS properly configured
- [ ] Rate limiting on auth endpoints
- [ ] Input validation on all endpoints
- [ ] SQL injection prevented (ORM)
- [ ] XSS prevention (template escaping)
- [ ] CSRF protection for OAuth
- [ ] Secure cookie attributes (HttpOnly, Secure, SameSite)
- [ ] Email verification required
- [ ] Account lockout after failed attempts
- [ ] Password reset tokens expire
- [ ] OAuth tokens stored encrypted
- [ ] Error messages don't leak info
- [ ] Logging doesn't expose sensitive data
- [ ] Database connections encrypted
- [ ] Environment variables secured
- [ ] Dependencies regularly updated

---

## Monitoring & Logging

### Metrics to Track
- Registration rate
- Login success/failure rate
- Active users (DAU/MAU)
- OAuth connection success rate
- Password reset requests
- Email verification rate
- API response times
- Database query performance

### Logging Events
- User registration
- Login attempts (success/failure)
- Password changes
- OAuth connections/disconnections
- Project uploads
- Failed authentication attempts
- Token refresh operations
- Email sending (success/failure)

---

## Future Enhancements

### Additional OAuth Providers
1. Google OAuth
2. Microsoft OAuth
3. LinkedIn OAuth
4. Bitbucket OAuth (Atlassian)

### Advanced Features
- Two-factor authentication (2FA)
- API key generation for programmatic access
- Team/organization accounts
- Role-based access control (RBAC)
- Audit logs for compliance
- Data export functionality
- Account deletion with data cleanup
- Session management (view/revoke sessions)
- Activity timeline

---

## Documentation Updates Needed

1. **API Documentation**: Update OpenAPI/Swagger with new endpoints
2. **User Guide**: Add authentication instructions
3. **Developer Guide**: Database setup instructions
4. **Deployment Guide**: Environment variables and database setup
5. **Security Guide**: Best practices for production deployment
