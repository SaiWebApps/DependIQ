"""
DependIQ - AI-powered dependency management tool
Main application entry point using modular architecture
"""

from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import create_router
from app.config import Config
from app.database import get_db
from app.middleware import register_error_handlers
from app.services.workos_auth import SESSION_COOKIE_NAME, get_current_user_from_cookie

# Create FastAPI application
app = FastAPI(
    title="DependIQ",
    description="AI-powered dependency management and code update tool",
    version="1.0.0",
)

# Register error handlers for better user feedback
register_error_handlers(app)


@app.middleware("http")
async def refresh_session_middleware(request: Request, call_next):
    """Propagate refreshed session cookie to the response."""
    request.state.refreshed_session = None
    response = await call_next(request)
    new_cookie = request.state.refreshed_session
    if new_cookie:
        is_production = Config.ENVIRONMENT != "development"
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=new_cookie,
            max_age=400 * 24 * 60 * 60,
            httponly=True,
            secure=is_production,
            samesite="lax",
            path="/",
        )
    return response


# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/images", StaticFiles(directory="images"), name="images")
templates = Jinja2Templates(directory="templates")

# Include API routes with /api prefix
api_router = create_router()
app.include_router(api_router, prefix="/api")


@app.get("/")
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    """Main landing page - requires authentication"""
    user = await get_current_user_from_cookie(request, db)

    if not user:
        return RedirectResponse(url="/login", status_code=303)

    return templates.TemplateResponse("index.html", {"request": request, "user": user})


@app.get("/login")
def login_page(request: Request):
    """Login page — redirects to WorkOS AuthKit"""
    return templates.TemplateResponse("sign_in.html", {"request": request})


@app.get("/profile")
async def profile_page(request: Request, db: AsyncSession = Depends(get_db)):
    """User profile page - requires authentication"""
    user = await get_current_user_from_cookie(request, db)

    if not user:
        return RedirectResponse(url="/login?return_to=/profile", status_code=303)

    return templates.TemplateResponse(
        "profile.html", {"request": request, "user": user}
    )


@app.get("/projects")
async def projects_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Project library page - requires authentication"""
    user = await get_current_user_from_cookie(request, db)

    if not user:
        return RedirectResponse(url="/login?return_to=/projects", status_code=303)

    return templates.TemplateResponse(
        "projects.html", {"request": request, "user": user}
    )


@app.get("/jobs")
async def jobs_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Job history page - requires authentication"""
    user = await get_current_user_from_cookie(request, db)

    if not user:
        return RedirectResponse(url="/login?return_to=/jobs", status_code=303)

    return templates.TemplateResponse("jobs.html", {"request": request, "user": user})


@app.get("/history")
async def history_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Project history page - requires authentication (legacy route)"""
    user = await get_current_user_from_cookie(request, db)

    if not user:
        return RedirectResponse(url="/login?return_to=/history", status_code=303)

    return templates.TemplateResponse(
        "history.html", {"request": request, "user": user}
    )


@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check endpoint for Render monitoring"""
    try:
        # Test database connection
        await db.execute("SELECT 1")
        return {
            "status": "healthy",
            "service": "dependiq",
            "environment": Config.ENVIRONMENT
            if hasattr(Config, "ENVIRONMENT")
            else "unknown",
            "version": "1.0.0",
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


# Optional: Add startup event for cleanup
@app.on_event("startup")
async def startup_event():
    """Application startup tasks"""
    print("🚀 DependIQ application starting up...")
    print(f"📡 Max SSE iterations: {Config.MAX_SSE_ITERATIONS}")
    print("🤖 AI: litellm agent layer (Anthropic/OpenAI/Ollama)")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown tasks"""
    print("🛑 DependIQ application shutting down...")
    # Clean up any remaining sessions, temp files, etc.
    from app.services.progress_service import cleanup_old_sessions

    cleanup_old_sessions(max_age=0)  # Clean all sessions on shutdown


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
