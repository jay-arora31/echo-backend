from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logfire

from app.config import settings
from app.database import init_db, close_db
from app.api import api_router

# Initialize Logfire - auto-instruments FastAPI, httpx, asyncio, OpenAI
if settings.logfire_token:
    logfire.configure(
        token=settings.logfire_token,
        service_name="superbryn-voice-agent",
        environment=settings.app_env,
        console=False,  # Disable console logging (too verbose)
    )
    # Instrument common libraries
    logfire.instrument_httpx()  # All HTTP calls (tool API calls)
    # Note: Removed asyncpg instrumentation - too verbose with BEGIN/COMMIT logs
    print("✅ Logfire initialized")
else:
    print("⚠️ Logfire token not set - observability disabled")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    print("🚀 Starting SuperBryn Voice Agent API...")
    await init_db()
    print("✅ Database initialized")

    yield

    # Shutdown
    print("👋 Shutting down...")
    await close_db()
    print("✅ Database connections closed")


app = FastAPI(
    title=settings.app_name,
    description="AI Voice Agent for Appointment Booking",
    version="1.0.0",
    lifespan=lifespan,
)

# Instrument FastAPI with Logfire
if settings.logfire_token:
    logfire.instrument_fastapi(app)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api")


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": "1.0.0",
    }


@app.get("/health")
async def health_check():
    """Detailed health check."""
    return {
        "status": "healthy",
        "database": "connected",
        "livekit": "configured" if settings.livekit_api_key else "not_configured",
    }

