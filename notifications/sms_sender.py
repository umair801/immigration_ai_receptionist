import structlog
from twilio.rest import Client
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


class SMSSender:
    def __init__(self) -> None:
        self.client = Client(
            settings.twilio_account_sid,
            settings.twilio_auth_token,
        )
        self.from_number: str = settings.twilio_phone_number

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
    )
    async def send(self, to_number: str, body: str) -> dict:
        """Send an SMS message via Twilio."""
        try:
            message = self.client.messages.create(
                body=body,
                from_=self.from_number,
                to=to_number,
            )
            logger.info(
                "sms_sent",
                to=to_number,
                sid=message.sid,
                status=message.status,
            )
            return {"sid": message.sid, "status": message.status}
        except Exception as e:
            logger.error(
                "sms_send_failed",
                to=to_number,
                error=str(e),
            )
            raise


sms_sender = SMSSender()