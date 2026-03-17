import structlog
from datetime import datetime, timedelta
from typing import Optional

from core.config import get_settings
from core.enums import AppointmentStatus, PaymentStatus, PipelineStage
from core.models import AppointmentSlot, PaymentRecord, IntakeRecord

logger = structlog.get_logger()
settings = get_settings()

FIRM_TIMEZONE = "America/New_York"

# ------------------------------------------------------------------
# SMS message templates
# ------------------------------------------------------------------

CONFIRMATION_SMS = {
    "en": (
        "Your immigration consultation is confirmed for {slot_display}. "
        "Our office will call you at this number to prepare. "
        "Reply STOP to opt out. - {firm_name}"
    ),
    "es": (
        "Su consulta de inmigracion esta confirmada para {slot_display}. "
        "Nuestra oficina le llamara a este numero para prepararse. "
        "Responda STOP para cancelar. - {firm_name}"
    ),
}

REMINDER_SMS = {
    "en": (
        "Reminder: Your immigration consultation is tomorrow at {time}. "
        "Please have your documents ready. Questions? Call {firm_phone}. "
        "- {firm_name}"
    ),
    "es": (
        "Recordatorio: Su consulta de inmigracion es manana a las {time}. "
        "Por favor tenga sus documentos listos. Preguntas? Llame a {firm_phone}. "
        "- {firm_name}"
    ),
}

FIRM_NAME = "Immigration Law Office"
FIRM_PHONE = settings.twilio_phone_number


class PaymentConfirmationAgent:
    """
    Handles everything that happens after Stripe confirms payment:
    1. Parse the Stripe webhook event
    2. Extract lead and appointment IDs from metadata
    3. Update the PaymentRecord status
    4. Finalize the AppointmentSlot
    5. Send confirmation SMS
    6. Schedule reminder SMS
    7. Update GoHighLevel pipeline stage
    """

    def parse_stripe_event(self, event: dict) -> Optional[dict]:
        """
        Extract the relevant payment data from a verified Stripe event.
        Handles both payment_intent.succeeded and checkout.session.completed.
        Returns a normalized payment info dict or None if not a payment event.
        """
        event_type = event.get("type")
        data_object = event.get("data", {}).get("object", {})

        if event_type == "payment_intent.succeeded":
            metadata = data_object.get("metadata", {})
            return {
                "event_type": event_type,
                "stripe_payment_intent_id": data_object.get("id"),
                "amount_cents": data_object.get("amount_received", 0),
                "currency": data_object.get("currency", "usd"),
                "lead_id": metadata.get("lead_id"),
                "appointment_id": metadata.get("appointment_id"),
                "call_session_id": metadata.get("call_session_id"),
                "contact_name": metadata.get("contact_name"),
                "contact_phone": metadata.get("contact_phone"),
            }

        if event_type == "checkout.session.completed":
            metadata = data_object.get("metadata", {})
            return {
                "event_type": event_type,
                "stripe_session_id": data_object.get("id"),
                "stripe_payment_intent_id": data_object.get("payment_intent"),
                "amount_cents": data_object.get("amount_total", 0),
                "currency": data_object.get("currency", "usd"),
                "lead_id": metadata.get("lead_id"),
                "appointment_id": metadata.get("appointment_id"),
                "call_session_id": metadata.get("call_session_id"),
                "contact_name": metadata.get("contact_name"),
                "contact_phone": metadata.get("contact_phone"),
            }

        logger.info(
            "stripe_event_ignored",
            event_type=event_type,
        )
        return None

    def build_payment_record(
        self,
        payment_info: dict,
        appointment: AppointmentSlot,
    ) -> PaymentRecord:
        """Build a confirmed PaymentRecord from parsed Stripe event data."""
        return PaymentRecord(
            lead_id=payment_info["lead_id"],
            appointment_id=appointment.id,
            stripe_payment_intent_id=payment_info.get("stripe_payment_intent_id"),
            stripe_session_id=payment_info.get("stripe_session_id"),
            amount=payment_info["amount_cents"] / 100,
            currency=payment_info.get("currency", "usd"),
            status=PaymentStatus.COMPLETED,
            paid_at=datetime.utcnow(),
        )

    def finalize_appointment(
        self,
        appointment: AppointmentSlot,
    ) -> AppointmentSlot:
        """Mark the appointment as confirmed after payment."""
        appointment.status = AppointmentStatus.CONFIRMED
        logger.info(
            "appointment_finalized",
            appointment_id=appointment.id,
            lead_id=appointment.lead_id,
        )
        return appointment

    def build_confirmation_sms(
        self,
        phone: str,
        slot_display: str,
        language: str = "en",
    ) -> str:
        """Build the post-payment confirmation SMS body."""
        lang = "es" if language == "es" else "en"
        return CONFIRMATION_SMS[lang].format(
            slot_display=slot_display,
            firm_name=FIRM_NAME,
        )

    def build_reminder_sms(
        self,
        appointment: AppointmentSlot,
        language: str = "en",
    ) -> str:
        """Build the 24-hour reminder SMS body."""
        lang = "es" if language == "es" else "en"
        time_display = appointment.start_time.strftime("%I:%M %p")
        return REMINDER_SMS[lang].format(
            time=time_display,
            firm_phone=FIRM_PHONE,
            firm_name=FIRM_NAME,
        )

    async def send_confirmation_sms(
        self,
        phone: str,
        slot_display: str,
        language: str = "en",
    ) -> dict:
        """Send the post-payment confirmation SMS."""
        from notifications.sms_sender import sms_sender

        body = self.build_confirmation_sms(phone, slot_display, language)
        result = await sms_sender.send(to_number=phone, body=body)
        logger.info(
            "confirmation_sms_sent",
            phone=phone,
            language=language,
        )
        return result

    async def sync_to_ghl(
        self,
        contact_id: str,
        payment_record: PaymentRecord,
        appointment: AppointmentSlot,
    ) -> None:
        """
        Update GoHighLevel after payment confirmation:
        - Add payment confirmed note
        - Add payment-confirmed tag
        """
        from integrations.ghl_client import ghl_client

        note = (
            f"Payment Confirmed\n"
            f"{'=' * 30}\n"
            f"Amount: ${payment_record.amount:.2f} {payment_record.currency.upper()}\n"
            f"Stripe ID: {payment_record.stripe_payment_intent_id}\n"
            f"Appointment: {appointment.start_time.strftime('%B %d, %Y at %I:%M %p')}\n"
            f"Status: CONFIRMED\n"
            f"Paid at: {payment_record.paid_at.strftime('%Y-%m-%d %H:%M UTC')}"
        )

        await ghl_client.add_note(contact_id, note)
        await ghl_client.add_tags(contact_id, ["payment-confirmed", "consultation-scheduled"])

        logger.info(
            "payment_confirmation_ghl_synced",
            contact_id=contact_id,
            appointment_id=appointment.id,
        )

    async def process_payment_event(
        self,
        event: dict,
        appointment: AppointmentSlot,
        language: str = "en",
        ghl_contact_id: Optional[str] = None,
    ) -> Optional[PaymentRecord]:
        """
        Full payment confirmation flow triggered by a Stripe webhook.
        Returns the finalized PaymentRecord or None if the event is not
        a payment event.
        """
        payment_info = self.parse_stripe_event(event)

        if not payment_info:
            return None

        payment_record = self.build_payment_record(payment_info, appointment)
        self.finalize_appointment(appointment)

        phone = payment_info.get("contact_phone", "")
        slot_display = appointment.start_time.strftime("%B %d at %I:%M %p")

        if phone:
            try:
                await self.send_confirmation_sms(phone, slot_display, language)
            except Exception as e:
                logger.error(
                    "confirmation_sms_failed",
                    phone=phone,
                    error=str(e),
                )

        if ghl_contact_id:
            try:
                await self.sync_to_ghl(ghl_contact_id, payment_record, appointment)
            except Exception as e:
                logger.error(
                    "payment_ghl_sync_failed",
                    contact_id=ghl_contact_id,
                    error=str(e),
                )

        logger.info(
            "payment_confirmation_complete",
            lead_id=payment_info.get("lead_id"),
            appointment_id=appointment.id,
            amount=payment_record.amount,
        )

        return payment_record


# Singleton instance
payment_confirmation_agent = PaymentConfirmationAgent()