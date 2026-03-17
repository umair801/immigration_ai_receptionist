from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    # OpenAI
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")

    # Retell AI
    retell_api_key: str = Field(..., env="RETELL_API_KEY")
    retell_agent_id: str = Field(..., env="RETELL_AGENT_ID")

    # ElevenLabs
    elevenlabs_api_key: str = Field(..., env="ELEVENLABS_API_KEY")
    elevenlabs_voice_id_en: str = Field(..., env="ELEVENLABS_VOICE_ID_EN")
    elevenlabs_voice_id_es: str = Field(..., env="ELEVENLABS_VOICE_ID_ES")

    # Twilio
    twilio_account_sid: str = Field(..., env="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(..., env="TWILIO_AUTH_TOKEN")
    twilio_phone_number: str = Field(..., env="TWILIO_PHONE_NUMBER")

    # GoHighLevel
    ghl_api_key: str = Field(..., env="GHL_API_KEY")
    ghl_location_id: str = Field(..., env="GHL_LOCATION_ID")

    # Stripe
    stripe_secret_key: str = Field(..., env="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str = Field(..., env="STRIPE_WEBHOOK_SECRET")

    # Supabase
    supabase_url: str = Field(..., env="SUPABASE_URL")
    supabase_service_key: str = Field(..., env="SUPABASE_SERVICE_KEY")

    # Google Calendar
    google_calendar_id: str = Field(..., env="GOOGLE_CALENDAR_ID")
    google_service_account_json: str = Field(..., env="GOOGLE_SERVICE_ACCOUNT_JSON")

    # App
    app_env: str = Field(default="development", env="APP_ENV")
    app_port: int = Field(default=8000, env="APP_PORT")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    base_url: str = Field(..., env="BASE_URL")

    model_config = {"env_file": ".env", "case_sensitive": False}


@lru_cache()
def get_settings() -> Settings:
    return Settings()