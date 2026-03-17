import structlog
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage

from core.config import get_settings
from core.enums import Language, AppointmentStatus
from core.models import AppointmentSlot, QualificationResult, IntakeRecord

logger = structlog.get_logger()
settings = get_settings()

FIRM_TIMEZONE = "America/New_York"

llm = ChatOpenAI(
    model="gpt-4o",
    api_key=settings.openai_api_key,
    temperature=0.0,
)

# ------------------------------------------------------------------
# Slot presentation scripts
# ------------------------------------------------------------------

SLOT_PRESENTATION = {
    Language.ENGLISH: (
        "I have checked our attorney's calendar and I have {count} available "
        "times for your consultation. {slots} Which of these works best for you?"
    ),
    Language.SPANISH: (
        "He revisado el calendario de nuestro abogado y tengo {count} horarios "
        "disponibles para su consulta. {slots} Cual de estos le viene mejor?"
    ),
}

SLOT_FORMAT = {
    Language.ENGLISH: "Option {n}: {display}.",
    Language.SPANISH: "Opcion {n}: {display}.",
}

CONFIRMATION_MESSAGE = {
    Language.ENGLISH: (
        "Perfect {name}. I have reserved {slot} for your consultation. "
        "I am sending a secure payment link to {phone} right now to confirm "
        "your appointment. The consultation fee is ${amount}. "
        "Once payment is received your appointment will be fully confirmed "
        "and you will receive a reminder the day before."
    ),
    Language.SPANISH: (
        "Perfecto {name}. He reservado {slot} para su consulta. "
        "Le estoy enviando un enlace de pago seguro a {phone} en este momento "
        "para confirmar su cita. El costo de la consulta es ${amount}. "
        "Una vez recibido el pago su cita quedara completamente confirmada "
        "y recibira un recordatorio el dia anterior."
    ),
}

NO_SLOTS_MESSAGE = {
    Language.ENGLISH: (
        "I apologize, but I am not seeing any available times in the next "
        "few days. I am flagging your case for our team and someone will "
        "call you back within one business hour to schedule your consultation."
    ),
    Language.SPANISH: (
        "Le pido disculpas, pero no veo horarios disponibles en los proximos "
        "dias. Estoy marcando su caso para nuestro equipo y alguien le llamara "
        "en el transcurso de una hora laboral para programar su consulta."
    ),
}

CONSULTATION_FEE = 150.00


# ------------------------------------------------------------------
# Slot selection parser
# ------------------------------------------------------------------

async def parse_slot_selection(
    caller_message: str,
    available_slots: list[dict],
    language: Language,
) -> Optional[int]:
    """
    Use GPT-4o to determine which slot index (0-based) the caller selected.
    Returns None if the selection is unclear.
    """
    slots_text = "\n".join(
        f"Option {i+1}: {s['display']}"
        for i, s in enumerate(available_slots)
    )

    lang_label = "Spanish" if language == Language.SPANISH else "English"

    system_prompt = (
        f"The caller is speaking {lang_label}. They were offered these appointment slots:\n"
        f"{slots_text}\n\n"
        f"Based on the caller's response, which option did they choose? "
        f"Return only the number 1, 2, or 3. "
        f"If unclear or no preference stated, return 0."
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Caller said: {caller_message}"),
    ]

    response = await llm.ainvoke(messages)
    try:
        choice = int(response.content.strip())
        if 1 <= choice <= len(available_slots):
            return choice - 1
        return None
    except ValueError:
        return None


# ------------------------------------------------------------------
# Slot presentation builder
# ------------------------------------------------------------------

def build_slot_presentation(
    slots: list[dict],
    language: Language,
) -> str:
    """Build the natural language slot options string for the caller."""
    slot_strings = " ".join(
        SLOT_FORMAT[language].format(n=i + 1, display=s["display"])
        for i, s in enumerate(slots)
    )
    return SLOT_PRESENTATION[language].format(
        count=len(slots),
        slots=slot_strings,
    )


# ------------------------------------------------------------------
# Appointment slot builder
# ------------------------------------------------------------------

def build_appointment_slot(
    selected_slot: dict,
    lead_id: str,
    stripe_payment_link: Optional[str] = None,
) -> AppointmentSlot:
    """Convert a raw calendar slot dict into an AppointmentSlot model."""
    return AppointmentSlot(
        lead_id=lead_id,
        start_time=datetime.fromisoformat(selected_slot["start"]),
        end_time=datetime.fromisoformat(selected_slot["end"]),
        status=AppointmentStatus.PENDING_PAYMENT,
        stripe_payment_link=stripe_payment_link,
    )


# ------------------------------------------------------------------
# Confirmation message builder
# ------------------------------------------------------------------

def build_confirmation_message(
    name: str,
    phone: str,
    slot: dict,
    language: Language,
    amount: float = CONSULTATION_FEE,
) -> str:
    """Build the post-selection confirmation message for the caller."""
    return CONFIRMATION_MESSAGE[language].format(
        name=name,
        slot=slot["display"],
        phone=phone,
        amount=int(amount),
    )


# ------------------------------------------------------------------
# Main appointment setter flow
# ------------------------------------------------------------------

class AppointmentSetterAgent:
    """
    Orchestrates the full appointment booking conversation:
    1. Fetch available slots
    2. Present options to caller
    3. Parse caller selection
    4. Build pending appointment
    5. Return confirmation message and slot for payment link delivery
    """

    async def get_slots_message(
        self,
        language: Language,
        days_ahead: int = 5,
    ) -> tuple[str, list[dict]]:
        """
        Fetch available slots and return the presentation message
        plus the raw slot list for later selection parsing.
        """
        from integrations.google_calendar_client import google_calendar_client

        slots = await google_calendar_client.get_available_slots(
            days_ahead=days_ahead,
            slots_to_return=3,
        )

        if not slots:
            logger.warning("appointment_setter_no_slots_available")
            return NO_SLOTS_MESSAGE[language], []

        message = build_slot_presentation(slots, language)
        logger.info(
            "appointment_setter_slots_presented",
            slot_count=len(slots),
            language=language,
        )
        return message, slots

    async def process_selection(
        self,
        caller_message: str,
        available_slots: list[dict],
        intake: IntakeRecord,
        qualification: QualificationResult,
    ) -> tuple[Optional[AppointmentSlot], str]:
        """
        Parse the caller's slot selection, build the appointment,
        and return the slot model plus confirmation message.
        Returns (None, no_slots_message) if selection fails.
        """
        language = intake.language

        selected_index = await parse_slot_selection(
            caller_message, available_slots, language
        )

        if selected_index is None:
            logger.warning(
                "appointment_setter_selection_unclear",
                lead_id=intake.lead_id,
                caller_message=caller_message,
            )
            # Re-present slots if selection was unclear
            message = build_slot_presentation(available_slots, language)
            return None, message

        selected_slot = available_slots[selected_index]
        appointment = build_appointment_slot(
            selected_slot=selected_slot,
            lead_id=intake.lead_id,
        )

        confirmation = build_confirmation_message(
            name=intake.name,
            phone=intake.phone_number,
            slot=selected_slot,
            language=language,
        )

        logger.info(
            "appointment_setter_slot_selected",
            lead_id=intake.lead_id,
            slot=selected_slot["display"],
            appointment_id=appointment.id,
        )

        return appointment, confirmation

    async def attach_payment_link(
        self,
        appointment: AppointmentSlot,
        payment_link: str,
    ) -> AppointmentSlot:
        """Attach a Stripe payment link to a pending appointment slot."""
        appointment.stripe_payment_link = payment_link
        logger.info(
            "appointment_setter_payment_link_attached",
            appointment_id=appointment.id,
            lead_id=appointment.lead_id,
        )
        return appointment


# Singleton instance
appointment_setter_agent = AppointmentSetterAgent()