import logging
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers.webhook import router as webhook_router
from app.routers.reviews import router as reviews_router
from app.routers.frontend import router as frontend_router
from app.routers.pages import router as pages_router

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("crop_doctor")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown lifecycle management.
    """
    settings = get_settings()
    logger.info("Initializing Crop Doctor on WhatsApp Backend...")
    # Ensure media directories exist
    settings.storage_path
    logger.info(f"Media storage initialized at: {settings.storage_path.resolve()}")
    yield
    logger.info("Shutting down Crop Doctor backend...")


# Initialize FastAPI instance
app = FastAPI(
    title="Crop Doctor on WhatsApp API",
    description="Backend microservice for farmer pest/disease diagnosis via WhatsApp Cloud API, Prisma STT, Vision, and Evon LLM.",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for student web dashboard and testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(webhook_router)
app.include_router(reviews_router)
app.include_router(frontend_router)
app.include_router(pages_router)

# Mount local media and storage directory for review dashboard and local inspection
settings = get_settings()
storage_path = settings.storage_path
app.mount("/media", StaticFiles(directory=str(storage_path)), name="media")
app.mount("/storage", StaticFiles(directory="storage"), name="storage")


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Detailed health check inspecting storage and service status.
    """
    settings = get_settings()
    return {
        "status": "healthy",
        "environment": settings.APP_ENV,
        "whatsapp_configured": bool(settings.WHATSAPP_PHONE_NUMBER_ID and not settings.WHATSAPP_PHONE_NUMBER_ID.startswith("mock")),
        "supabase_configured": bool(settings.SUPABASE_URL and "your-project-id" not in settings.SUPABASE_URL),
        "prisma_key_present": bool(settings.effective_prisma_key),
        "prisma_url_configured": bool(settings.PRISMA_STT_API_URL),
        "storage_ready": settings.storage_path.exists()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=(settings.APP_ENV == "development")
    )

