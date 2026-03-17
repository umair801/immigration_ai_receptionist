import structlog
from typing import Optional

from core.config import get_settings
from core.enums import Language, UrgencyLevel
from core.models import IntakeRecord, QualificationResult, CallSession

logger = structlog.get_logger()
settings = get_settings()

FIRM_NAME = "Immigration Law Office"

# ------------------------------------------------------------------
# Whisper scripts (heard only by the receiving staff member)
# ------------------------------------------------------------------

WHISPER_TEMPLATE = (
    "Incoming transfer. Caller name: {name}. "
    "Case type: {case_type}. "
    "Urgency: {urgency}. "
    "Language: {language}. "
    "{escalation_note}"
    "Summary: {summary}"
)

ESCALATION_NOTE = "URGENT: {reason}. "

# ------------------------------------------------------------------
# Hold messages (heard by the caller while being transferred)
# ------------------------------------------------------------------

HOLD_MESSAGES = {
    Language.ENGLISH: (
        "Please hold for just a moment while I connect you with one of our "
        "attorneys who can assist you right away."
    ),
    Language.SPANISH: (
        "Por favor espere un momento mientras le conecto con uno de nuestros "
        "abogados que puede ayudarle de inmediato."
    ),
}

TRANSFER_FAILED_MESSAGES = {
    Language.ENGLISH: (
        "I apologize, I was unable to reach the attorney directly. "
        "I have marked your case as urgent and someone will call you back "
        "within 15 minutes. Thank you for your patience."
    ),
    Language.SPANISH: (
        "Le pido disculpas, no pude comunicarme directamente con el abogado. "
        "He marcado su caso como urgente y alguien le llamara en 15 minutos. "
        "Gracias por su paciencia."
    ),
}


# ------------------------------------------------------------------
# Paralegal and attorney routing table
# ------------------------------------------------------------------

# In production this comes from GoHighLevel or a config file.
# These are placeholders replaced with real numbers at deployment.
TRANSFER_TARGETS = {
    "default_paralegal": {
        "name": "Paralegal Team",
        "phone": "+10000000001",
        "languages": [Language.ENGLISH, Language.SPANISH],
    },
    "senior_attorney": {
        "name": "Senior Attorney",
        "phone": "+10000000002",
        "languages": [Language.ENGLISH, Language.SPANISH],
    },
    "spanish_paralegal": {
        "name": "Spanish Paralegal",
        "phone": "+10000000003",
        "languages": [Language.SPANISH],
    },
}


class CallTransferAgent:
    """
    Handles warm call transfers from the AI receptionist to live staff.
    Uses Twilio conference-based transfer with a whisper message to the
    receiving staff member before the caller is connected.
    """

    def select_transfer_target(
        self,
        qualification: QualificationResult,
        language: Language,
        requires_escalation: bool = False,
    ) -> dict:
        """
        Choose the right staff member to receive the transfer.
        Escalated or critical cases go to the senior attorney.
        Spanish-preferred callers route to Spanish-speaking staff.
        """
        if requires_escalation or qualification.urgency_level == UrgencyLevel.CRITICAL:
            target = TRANSFER_TARGETS["senior_attorney"]
            logger.info(
                "transfer_target_selected",
                target=target["name"],
                reason="escalation_or_critical",
            )
            return target

        if language == Language.SPANISH:
            target = TRANSFER_TARGETS["spanish_paralegal"]
            logger.info(
                "transfer_target_selected",
                target=target["name"],
                reason="spanish_language",
            )
            return target

        target = TRANSFER_TARGETS["default_paralegal"]
        logger.info(
            "transfer_target_selected",
            target=target["name"],
            reason="default",
        )
        return target

    def build_whisper_message(
        self,
        intake: IntakeRecord,
        qualification: QualificationResult,
    ) -> str:
        """
        Build the whisper message heard only by the receiving staff member.
        Delivered before the caller is connected so staff are prepared.
        """
        escalation_note = ""
        if qualification.requires_escalation and qualification.escalation_reason:
            escalation_note = ESCALATION_NOTE.format(
                reason=qualification.escalation_reason
            )

        return WHISPER_TEMPLATE.format(
            name=intake.name,
            case_type=intake.case_type.value.replace("_", " ").title(),
            urgency=intake.urgency_level.value.upper(),
            language=intake.language.value.upper(),
            escalation_note=escalation_note,
            summary=qualification.summary[:200],
        )

    def build_hold_message(self, language: Language) -> str:
        """Return the hold message played to the caller during transfer."""
        return HOLD_MESSAGES.get(language, HOLD_MESSAGES[Language.ENGLISH])

    def build_transfer_failed_message(self, language: Language) -> str:
        """Return the failure message if the transfer cannot be completed."""
        return TRANSFER_FAILED_MESSAGES.get(
            language, TRANSFER_FAILED_MESSAGES[Language.ENGLISH]
        )

    async def execute_transfer(
        self,
        call_session: CallSession,
        intake: IntakeRecord,
        qualification: QualificationResult,
        target_override: Optional[str] = None,
    ) -> dict:
        """
        Execute the warm call transfer via Twilio.
        Steps:
        1. Select the transfer target
        2. Build the whisper message
        3. Initiate Twilio conference with whisper
        4. Return transfer result for CRM logging
        """
        from twilio.rest import Client

        client = Client(
            settings.twilio_account_sid,
            settings.twilio_auth_token,
        )

        target = (
            TRANSFER_TARGETS.get(target_override)
            or self.select_transfer_target(
                qualification,
                intake.language,
                qualification.requires_escalation,
            )
        )

        whisper = self.build_whisper_message(intake, qualification)
        conference_name = f"transfer-{call_session.id[:8]}"

        logger.info(
            "call_transfer_initiated",
            session_id=call_session.id,
            target=target["name"],
            target_phone=target["phone"],
            conference=conference_name,
            urgency=qualification.urgency_level,
        )

        try:
            # Add the staff member to the conference with the whisper
            staff_call = client.calls.create(
                to=target["phone"],
                from_=settings.twilio_phone_number,
                twiml=(
                    f"<Response>"
                    f"<Say>{whisper}</Say>"
                    f"<Dial>"
                    f"<Conference>{conference_name}</Conference>"
                    f"</Dial>"
                    f"</Response>"
                ),
            )

            logger.info(
                "call_transfer_staff_leg_created",
                staff_call_sid=staff_call.sid,
                target_phone=target["phone"],
            )

            return {
                "status": "transfer_initiated",
                "conference_name": conference_name,
                "target_name": target["name"],
                "target_phone": target["phone"],
                "staff_call_sid": staff_call.sid,
                "whisper_delivered": True,
                "session_id": call_session.id,
            }

        except Exception as e:
            logger.error(
                "call_transfer_failed",
                session_id=call_session.id,
                target=target["name"],
                error=str(e),
            )
            return {
                "status": "transfer_failed",
                "error": str(e),
                "session_id": call_session.id,
                "failure_message": self.build_transfer_failed_message(
                    intake.language
                ),
            }


# Singleton instance
call_transfer_agent = CallTransferAgent()