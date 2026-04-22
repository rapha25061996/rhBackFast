"""
FastAPI RH Management System - Main Application
"""
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings, validate_configuration
from app.core.startup import run_startup_tasks
from app.core.audit_middleware import AuditMiddleware
from app.user_app.routes import get_user_app_router
from app.paie_app.routes import get_paie_app_router
from app.audit_app.routes import router as audit_router
from app.reset_password_app import router as password_reset_router
from app.conge_app.routes import router as conge_router
from app.presence_app.routes import router as presence_router

# Validate configuration at startup
validate_configuration()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Runs startup tasks when the app starts and cleanup when it shuts down.
    """
    # Startup
    print(f"\n🚀 Starting {settings.APP_NAME} v{settings.APP_VERSION}...")
    await run_startup_tasks()
    print("✓ Application ready\n")

    yield

    # Shutdown
    print("\n👋 Shutting down application...")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add audit middleware (if enabled)
if getattr(settings, "AUDIT_ENABLED", True):
    app.add_middleware(AuditMiddleware)

# Include routers
app.include_router(get_user_app_router(), prefix="/api")
app.include_router(get_paie_app_router(), prefix="/api/paie")
app.include_router(audit_router, prefix="/api")
app.include_router(password_reset_router)
app.include_router(conge_router)
app.include_router(presence_router)

# Mount the uploads directory so saved files are served at /uploads/*
uploads_dir = Path("uploads")
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to RH Management System API",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
