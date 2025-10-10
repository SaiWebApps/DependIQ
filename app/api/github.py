"""
GitHub integration API routes for OAuth and repository management
"""

import secrets
import time

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

from ..config import Config
from ..services.github_api import GitHubAPIService
from ..services.github_oauth import GitHubOAuthService
from ..services.progress_service import analysis_status

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# In-memory session storage for GitHub OAuth states and tokens
# In production, this should use a proper session store like Redis
github_sessions = {}


@router.get("/auth/github")
def github_oauth_initiate(request: Request):
    """Initiate GitHub OAuth flow"""
    try:
        oauth_service = GitHubOAuthService()
        state = oauth_service.generate_state()

        # Store state in session for validation
        github_sessions[state] = {"created_at": time.time(), "status": "pending"}

        authorization_url = oauth_service.get_authorization_url(state)

        return RedirectResponse(url=authorization_url)

    except ValueError as e:
        # OAuth credentials not configured
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"GitHub OAuth not configured: {e!s}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate OAuth: {e!s}",
        )


@router.get("/auth/github/callback")
def github_oauth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    error: str = Query(None),
):
    """Handle GitHub OAuth callback"""
    try:
        # Check for OAuth errors
        if error:
            return templates.TemplateResponse(
                "github_error.html",
                {
                    "request": request,
                    "error": "GitHub OAuth cancelled",
                    "error_description": f"OAuth error: {error}",
                },
            )

        # Validate state parameter
        if state not in github_sessions:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OAuth state",
            )

        # Check if state is too old (15 minutes max)
        session_data = github_sessions[state]
        if time.time() - session_data["created_at"] > 900:  # 15 minutes
            del github_sessions[state]
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST, detail="OAuth state expired"
            )

        # Exchange code for token
        oauth_service = GitHubOAuthService()
        token_data = oauth_service.exchange_code_for_token(code, state)

        # Get user information
        access_token = token_data["access_token"]
        user_info = oauth_service.get_user_info(access_token)

        # Store session data
        session_id = secrets.token_urlsafe(32)
        github_sessions[session_id] = {
            "access_token": access_token,
            "user_info": user_info,
            "created_at": time.time(),
            "status": "authenticated",
        }

        # Clean up OAuth state
        del github_sessions[state]

        # Redirect to repository selection page
        return RedirectResponse(url=f"/github/repositories?session={session_id}")

    except Exception as e:
        return templates.TemplateResponse(
            "github_error.html",
            {
                "request": request,
                "error": "Authentication failed",
                "error_description": str(e),
            },
        )


@router.get("/github/repositories")
def github_repositories_page(request: Request, session: str = Query(...)):
    """Display GitHub repositories selection page"""
    try:
        # Validate session
        if session not in github_sessions:
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED, detail="Invalid or expired session"
            )

        session_data = github_sessions[session]

        # Check if session is too old (1 hour max)
        if time.time() - session_data["created_at"] > 3600:
            del github_sessions[session]
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED, detail="Session expired"
            )

        user_info = session_data["user_info"]

        return templates.TemplateResponse(
            "github_repositories.html",
            {"request": request, "session_id": session, "user_info": user_info},
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load repositories page: {e!s}",
        )


@router.get("/api/github/repositories")
def get_github_repositories_api(request: Request):
    """API endpoint to fetch GitHub repositories (requires session parameter)"""
    try:
        # Extract parameters from query string
        session = request.query_params.get("session")
        page = int(request.query_params.get("page", 1))
        per_page = int(request.query_params.get("per_page", 20))
        search = request.query_params.get("search")
        check_dependencies = (
            request.query_params.get("check_dependencies", "false").lower() == "true"
        )

        # Validate session
        if not session or session not in github_sessions:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail="GitHub session required. Please connect via OAuth first.",
            )

        # Validate pagination parameters
        if page < 1:
            page = 1
        if per_page < 1 or per_page > 100:
            per_page = 20

        session_data = github_sessions[session]
        access_token = session_data["access_token"]

        # Create GitHub API service
        github_api = GitHubAPIService(access_token)

        if search:
            # Search repositories
            repositories = github_api.search_repositories(search, per_page)
            has_more = len(repositories) >= per_page
        else:
            # Get user repositories
            repositories, has_more = github_api.get_user_repositories(per_page, page)

        # Only check dependencies if explicitly requested
        if check_dependencies:
            for repo in repositories:
                try:
                    owner = repo["owner"]["login"]
                    name = repo["name"]
                    dep_info = github_api.check_dependency_files(owner, name)
                    repo.update(dep_info)
                except Exception as e:
                    print(
                        f"Warning: Failed to check dependencies for {repo['full_name']}: {e}"
                    )
                    repo["dependency_files"] = []
                    repo["has_dependencies"] = False
                    repo["project_type"] = "unknown"
        else:
            # Set default values when not checking
            for repo in repositories:
                repo["dependency_files"] = []
                repo["has_dependencies"] = None  # Unknown
                repo["project_type"] = "unknown"

        return JSONResponse(
            {
                "repositories": repositories,
                "has_more": has_more,
                "page": page,
                "per_page": per_page,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch repositories: {e!s}",
        )


@router.post("/github/analyze/{owner}/{repo}")
async def analyze_github_repository(
    request: Request,
    owner: str,
    repo: str,
    session: str = Query(...),
    ref: str = Query("main"),
    user_instructions: str = Form(""),
):
    """Start analysis of selected GitHub repository"""
    try:
        # Validate session
        if session not in github_sessions:
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED, detail="Invalid or expired session"
            )

        session_data = github_sessions[session]
        access_token = session_data["access_token"]

        # Create GitHub API service
        github_api = GitHubAPIService(access_token)

        # Download repository
        print(f"🔄 Downloading repository {owner}/{repo} (ref: {ref})")
        zip_content = github_api.download_repository(owner, repo, ref)

        # Create session ID for analysis tracking
        analysis_session_id = str(int(time.time() * 1000))

        # Save ZIP content to temporary file
        temp_file_path = Config.get_temp_file_path(analysis_session_id)
        with open(temp_file_path, "wb") as f:
            f.write(zip_content)

        # Store file info for the analysis process
        analysis_status[analysis_session_id] = {
            "temp_file_path": temp_file_path,
            "filename": f"{owner}-{repo}-{ref}.zip",
            "status": "queued",
            "source": "github",
            "github_info": {
                "owner": owner,
                "repo": repo,
                "ref": ref,
                "full_name": f"{owner}/{repo}",
            },
            "user_instructions": user_instructions.strip() if user_instructions else "",
        }

        print(
            f"🚀 Created analysis session {analysis_session_id} for GitHub repo {owner}/{repo}"
        )
        if user_instructions:
            print(f"📝 USER INSTRUCTIONS: {user_instructions[:100]}...")

        # Redirect to analysis page
        return RedirectResponse(url=f"/analysis/{analysis_session_id}", status_code=302)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start repository analysis: {e!s}",
        )


@router.get("/api/github/repository/{owner}/{repo}")
def get_repository_details(owner: str, repo: str, session: str = Query(...)):
    """Get detailed information about a specific repository"""
    try:
        # Validate session
        if session not in github_sessions:
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED, detail="Invalid or expired session"
            )

        session_data = github_sessions[session]
        access_token = session_data["access_token"]

        # Create GitHub API service
        github_api = GitHubAPIService(access_token)

        # Get repository info
        repo_info = github_api.get_repository_info(owner, repo)

        # Get dependency files
        dep_info = github_api.check_dependency_files(owner, repo)

        # Get branches and tags
        branches = github_api.get_repository_branches(owner, repo)
        tags = github_api.get_repository_tags(owner, repo)

        return JSONResponse(
            {
                "repository": repo_info,
                "dependency_info": dep_info,
                "branches": branches,
                "tags": tags,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get repository details: {e!s}",
        )


@router.post("/github/disconnect")
def disconnect_github(session: str = Query(...)):
    """Disconnect GitHub session"""
    try:
        github_sessions.pop(session, None)

        return JSONResponse({"message": "Disconnected successfully"})

    except Exception as e:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disconnect: {e!s}",
        )


# Cleanup function for expired sessions
def cleanup_expired_github_sessions():
    """Clean up expired GitHub sessions"""
    current_time = time.time()
    expired_sessions = []

    for session_id, session_data in github_sessions.items():
        # Remove sessions older than 1 hour
        if current_time - session_data["created_at"] > 3600:
            expired_sessions.append(session_id)

    for session_id in expired_sessions:
        del github_sessions[session_id]

    print(f"🧹 Cleaned up {len(expired_sessions)} expired GitHub sessions")
