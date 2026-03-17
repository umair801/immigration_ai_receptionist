import hmac
import hashlib
import httpx
import structlog
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

RETELL_BASE_URL = "https://api.retellai.com"


class RetellClient:
    def __init__(self) -> None:
        self.api_key: str = settings.retell_api_key
        self.agent_id: str = settings.retell_agent_id
        self.headers: dict = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Webhook signature verification
    # ------------------------------------------------------------------

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        signature_header: str,
    ) -> bool:
        """
        Verify that an incoming webhook request is genuinely from Retell AI.
        Retell signs each request using HMAC-SHA256 with your API key.
        """
        try:
            expected = hmac.new(
                self.api_key.encode("utf-8"),
                raw_body,
                hashlib.sha256,
            ).hexdigest()

            is_valid = hmac.compare_digest(expected, signature_header)

            logger.info(
                "retell_webhook_signature_check",
                is_valid=is_valid,
            )
            return is_valid

        except Exception as e:
            logger.error("retell_signature_verification_failed", error=str(e))
            return False

    # ------------------------------------------------------------------
    # Agent management
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_agent(self, agent_id: Optional[str] = None) -> dict:
        """Fetch agent configuration from Retell."""
        target_id = agent_id or self.agent_id
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{RETELL_BASE_URL}/get-agent/{target_id}",
                headers=self.headers,
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            logger.info("retell_agent_fetched", agent_id=target_id)
            return data

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def update_agent_webhook(self, webhook_url: str) -> dict:
        """
        Update the Retell agent's webhook URL.
        Call this once during deployment to point Retell at your server.
        """
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{RETELL_BASE_URL}/update-agent/{self.agent_id}",
                headers=self.headers,
                json={"webhook_url": webhook_url},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            logger.info(
                "retell_agent_webhook_updated",
                agent_id=self.agent_id,
                webhook_url=webhook_url,
            )
            return data

    # ------------------------------------------------------------------
    # Call management
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def create_phone_call(
        self,
        to_number: str,
        from_number: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        Initiate an outbound call via Retell AI.
        Used by the Outbound Caller Agent in Step 12.
        """
        payload: dict = {
            "agent_id": self.agent_id,
            "to_number": to_number,
            "from_number": from_number or settings.twilio_phone_number,
        }
        if metadata:
            payload["metadata"] = metadata

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{RETELL_BASE_URL}/create-phone-call",
                headers=self.headers,
                json=payload,
                timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()
            logger.info(
                "retell_outbound_call_created",
                to_number=to_number,
                call_id=data.get("call_id"),
            )
            return data

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_call(self, call_id: str) -> dict:
        """Fetch call details including transcript from Retell."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{RETELL_BASE_URL}/get-call/{call_id}",
                headers=self.headers,
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            logger.info("retell_call_fetched", call_id=call_id)
            return data

    # ------------------------------------------------------------------
    # Phone number management
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def list_phone_numbers(self) -> list:
        """List all Twilio numbers registered with this Retell account."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{RETELL_BASE_URL}/list-phone-numbers",
                headers=self.headers,
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            logger.info("retell_phone_numbers_listed", count=len(data))
            return data

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def import_twilio_number(
        self,
        phone_number: str,
        twilio_account_sid: str,
        twilio_auth_token: str,
    ) -> dict:
        """
        Import a Twilio number into Retell so inbound calls
        are routed to this agent automatically.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{RETELL_BASE_URL}/import-phone-number",
                headers=self.headers,
                json={
                    "phone_number": phone_number,
                    "twilio_account_sid": twilio_account_sid,
                    "twilio_auth_token": twilio_auth_token,
                },
                timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()
            logger.info(
                "retell_twilio_number_imported",
                phone_number=phone_number,
            )
            return data

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def assign_agent_to_number(
        self,
        phone_number: str,
        agent_id: Optional[str] = None,
    ) -> dict:
        """Assign this agent to a Twilio number for inbound call handling."""
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{RETELL_BASE_URL}/update-phone-number/{phone_number}",
                headers=self.headers,
                json={"agent_id": agent_id or self.agent_id},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            logger.info(
                "retell_agent_assigned_to_number",
                phone_number=phone_number,
                agent_id=agent_id or self.agent_id,
            )
            return data


# Singleton instance
retell_client = RetellClient()