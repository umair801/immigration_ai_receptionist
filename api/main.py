import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

from core.config import get_settings
from core.logger import logger
from api.voice_router import router as voice_router
from api.payment_router import router as payment_router
from api.metrics_router import router as metrics_router

settings = get_settings()


# ------------------------------------------------------------------
# Startup and shutdown lifecycle
# ------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "app_starting",
        env=settings.app_env,
        port=settings.app_port,
    )

    # Verify database connectivity
    try:
        from core.database import supabase
        supabase.table("call_sessions").select("id").limit(1).execute()
        logger.info("startup_database_connected")
    except Exception as e:
        logger.error("startup_database_failed", error=str(e))

    # Verify ElevenLabs voice configuration
    try:
        from integrations.elevenlabs_client import elevenlabs_client
        from core.enums import Language
        en_config = elevenlabs_client.build_retell_voice_config(Language.ENGLISH)
        es_config = elevenlabs_client.build_retell_voice_config(Language.SPANISH)
        logger.info(
            "startup_voices_configured",
            english_voice=en_config["voice_id"][:8],
            spanish_voice=es_config["voice_id"][:8],
        )
    except Exception as e:
        logger.error("startup_voices_failed", error=str(e))

    logger.info("app_ready", base_url=settings.base_url)

    yield

    logger.info("app_shutting_down")


# ------------------------------------------------------------------
# FastAPI application
# ------------------------------------------------------------------

app = FastAPI(
    title="AI Immigration Receptionist",
    description=(
        "Autonomous AI receptionist system for immigration law firms. "
        "Handles inbound and outbound calls in English and Spanish, "
        "qualifies leads, books consultations, confirms payments, "
        "and logs every interaction into GoHighLevel."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
)


# ------------------------------------------------------------------
# CORS middleware
# ------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.base_url,
        "https://app.retellai.com",
        "https://dashboard.stripe.com",
        "https://app.gohighlevel.com",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------
# Mount routers
# ------------------------------------------------------------------

app.include_router(voice_router)
app.include_router(payment_router)
app.include_router(metrics_router)


# ------------------------------------------------------------------
# Root and health endpoints
# ------------------------------------------------------------------

@app.get("/")
async def root():
    return {
        "service": "AI Immigration Receptionist",
        "version": "1.0.0",
        "status": "live",
        "timestamp": datetime.utcnow().isoformat(),
        "endpoints": {
            "voice_webhook": "/voice/retell-webhook",
            "intake_webhook": "/voice/intake-webhook",
            "outbound_trigger": "/voice/trigger-outbound",
            "stripe_webhook": "/payment/stripe-webhook",
            "metrics": "/metrics/",
            "health": "/metrics/health",
            "docs": "/docs",
        },
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
    }