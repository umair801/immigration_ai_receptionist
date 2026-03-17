import structlog
from typing import Optional
from datetime import datetime

from core.config import get_settings
from core.enums import Language, CallerType, CallStatus
from core.models import Lead, CallSession

logger = structlog.get_logger()
settings = get_settings()

# ------------------------------------------------------------------
# Outbound call scripts
# ------------------------------------------------------------------

OPENING_SCRIPTS = {
    Language.ENGLISH: (
        "Hello, may I speak with {name}? "
        "This is Sofia calling from {firm_name}. "
        "You recently submitted a request for information about immigration services "
        "and I am calling to follow up. "
        "Do you have just a couple of minutes to answer a few quick questions "
        "so we can connect you with the right attorney?"
    ),
    Language.SPANISH: (
        "Hola, puedo hablar con {name}? "
        "Le llama Sofia de {firm_name}. "
        "Usted envio recientemente una solicitud de informacion sobre servicios "
        "de inmigracion y le llamo para dar seguimiento. "
        "Tiene un par de minutos para responder algunas preguntas rapidas "
        "para conectarle con el abogado correcto?"
    ),
}

VOICEMAIL_SCRIPTS = {
    Language.ENGLISH: (
        "Hello {name}, this is Sofia from {firm_name}. "
        "We received your request for immigration assistance and would love to help. "
        "Please call us back at {phone} at your earliest convenience. "
        "We look forward to speaking with you. Thank you."
    ),
    Language.SPANISH: (
        "Hola {name}, le llama Sofia de {firm_name}. "
        "Recibimos su solicitud de asistencia en inmigracion y nos gustaria ayudarle. "
        "Por favor llamenos al {phone} a la brevedad posible. "
        "Esperamos hablar con usted. Gracias."
    ),
}

NO_ANSWER_SCRIPTS = {
    Language.ENGLISH: (
        "We were unable to reach {name} at {phone}. "
        "A follow-up SMS has been sent with our contact information."
    ),
    Language.SPANISH: (
        "No fue posible comunicarse con {name} al {phone}. "
        "Se ha enviado un SMS de seguimiento con nuestra informacion de contacto."
    ),
}

FOLLOW_UP_SMS = {
    Language.ENGLISH: (
        "Hi {name}, this is {firm_name}. We tried to reach you about your "
        "immigration inquiry. Call us at {phone} or reply to this message. "
        "We are here to help."
    ),
    Language.SPANISH: (
        "Hola {name}, somos {firm_name}. Intentamos comunicarnos sobre su "
        "consulta de inmigracion. Llamenos al {phone} o responda este mensaje. "
        "Estamos aqui para ayudarle."
    ),
}

FIRM_NAME = "Immigration Law Office"


class OutboundCallerAgent:
    """
    Handles the full outbound call lifecycle for social media leads:
    1. Validate lead data from GHL webhook payload
    2. Detect preferred language
    3. Initiate call via Retell AI
    4. Track call session state
    5. Handle no-answer with SMS follow-up
    6. Trigger intake flow on answer
    """

    def build_lead_from_webhook(self, payload: dict) -> Lead:
        """
        Parse a GoHighLevel webhook payload into a Lead model.
        GHL sends contact data when a new lead enters a pipeline stage.
        """
        phone = (
            payload.get("phone")
            or payload.get("Phone")
            or payload.get("contact", {}).get("phone", "")
        )
        name = (
            payload.get("full_name")
            or payload.get("name")
            or f"{payload.get('first_name', '')} {payload.get('last_name', '')}".strip()
            or "Unknown"
        )
        email = payload.get("email") or payload.get("Email")

        language = self.detect_language(payload)

        lead = Lead(
            phone_number=phone,
            name=name,
            email=email,
            language=language,
            caller_type=CallerType.NEW_LEAD,
        )

        logger.info(
            "outbound_lead_built",
            lead_id=lead.id,
            phone=phone,
            language=language,
        )
        return lead

    def detect_language(self, payload: dict) -> Language:
        """
        Detect preferred language from GHL payload.
        Checks tags, custom fields, and name heuristics.
        Defaults to Spanish for Miami-market leads.
        """
        tags = payload.get("tags", [])
        if isinstance(tags, list):
            if "english" in [t.lower() for t in tags]:
                return Language.ENGLISH
            if "spanish" in [t.lower() for t in tags]:
                return Language.SPANISH

        custom_fields = payload.get("customFields", [])
        for field in custom_fields:
            if field.get("key") == "preferred_language":
                val = field.get("value", "").lower()
                if "english" in val:
                    return Language.ENGLISH
                if "spanish" in val:
                    return Language.SPANISH

        # Default to Spanish for Miami immigration market
        return Language.SPANISH

    def build_opening_script(
        self,
        lead: Lead,
        language: Language,
    ) -> str:
        """Build the outbound call opening script for this lead."""
        return OPENING_SCRIPTS[language].format(
            name=lead.name or "there",
            firm_name=FIRM_NAME,
        )

    def build_voicemail_script(
        self,
        lead: Lead,
        language: Language,
    ) -> str:
        """Build the voicemail script if the call is not answered."""
        return VOICEMAIL_SCRIPTS[language].format(
            name=lead.name or "there",
            firm_name=FIRM_NAME,
            phone=settings.twilio_phone_number,
        )

    def build_follow_up_sms(
        self,
        lead: Lead,
        language: Language,
    ) -> str:
        """Build the follow-up SMS body for unanswered calls."""
        return FOLLOW_UP_SMS[language].format(
            name=lead.name or "there",
            firm_name=FIRM_NAME,
            phone=settings.twilio_phone_number,
        )

    def create_call_session(
        self,
        lead: Lead,
        call_id: str,
    ) -> CallSession:
        """Create a CallSession record for tracking the outbound call."""
        session = CallSession(
            call_id=call_id,
            phone_number=lead.phone_number,
            lead_id=lead.id,
            caller_type=CallerType.NEW_LEAD,
            language=lead.language,
            status=CallStatus.INITIATED,
        )
        logger.info(
            "outbound_call_session_created",
            session_id=session.id,
            lead_id=lead.id,
            call_id=call_id,
        )
        return session

    async def initiate_call(
        self,
        lead: Lead,
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        Trigger an outbound call via Retell AI.
        Returns the Retell call object with call_id.
        """
        from integrations.retell_client import retell_client

        call_metadata = {
            "lead_id": lead.id,
            "lead_name": lead.name,
            "language": lead.language.value,
            "caller_type": CallerType.NEW_LEAD.value,
            **(metadata or {}),
        }

        call = await retell_client.create_phone_call(
            to_number=lead.phone_number,
            metadata=call_metadata,
        )

        logger.info(
            "outbound_call_initiated",
            lead_id=lead.id,
            call_id=call.get("call_id"),
            to_number=lead.phone_number,
        )
        return call

    async def handle_no_answer(
        self,
        lead: Lead,
        max_attempts: int = 2,
    ) -> dict:
        """
        Send a follow-up SMS when a call goes unanswered.
        Returns the SMS result.
        """
        from notifications.sms_sender import sms_sender

        sms_body = self.build_follow_up_sms(lead, lead.language)

        try:
            result = await sms_sender.send(
                to_number=lead.phone_number,
                body=sms_body,
            )
            logger.info(
                "outbound_no_answer_sms_sent",
                lead_id=lead.id,
                phone=lead.phone_number,
            )
            return result
        except Exception as e:
            logger.error(
                "outbound_no_answer_sms_failed",
                lead_id=lead.id,
                error=str(e),
            )
            raise

    async def process_ghl_webhook(
        self,
        payload: dict,
    ) -> tuple[Lead, CallSession]:
        """
        Full outbound trigger flow from a GoHighLevel webhook.
        Called when a new lead enters the pipeline.
        Returns the Lead and CallSession created.
        """
        lead = self.build_lead_from_webhook(payload)

        if not lead.phone_number:
            logger.error(
                "outbound_no_phone_number",
                payload_keys=list(payload.keys()),
            )
            raise ValueError("Lead has no phone number in GHL webhook payload")

        call = await self.initiate_call(lead)
        call_id = call.get("call_id", f"mock-{lead.id[:8]}")
        session = self.create_call_session(lead, call_id)

        logger.info(
            "outbound_webhook_processed",
            lead_id=lead.id,
            session_id=session.id,
            language=lead.language,
        )
        return lead, session


# Singleton instance
outbound_caller_agent = OutboundCallerAgent()