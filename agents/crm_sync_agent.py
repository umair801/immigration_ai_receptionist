import structlog
from typing import Optional
from datetime import datetime

from core.config import get_settings
from core.enums import (
    CallStatus,
    PipelineStage,
    UrgencyLevel,
    LeadScore,
)
from core.models import (
    CallSession,
    IntakeRecord,
    QualificationResult,
    AppointmentSlot,
    PaymentRecord,
)

logger = structlog.get_logger()
settings = get_settings()


def build_outcome_tags(
    intake: IntakeRecord,
    qualification: QualificationResult,
    appointment: Optional[AppointmentSlot] = None,
    payment: Optional[PaymentRecord] = None,
    call_status: CallStatus = CallStatus.COMPLETED,
) -> list[str]:
    """
    Build the complete list of outcome tags to apply to the GHL contact.
    Tags drive GoHighLevel automations like email sequences and tasks.
    """
    tags = [
        f"ai-receptionist",
        f"case-type:{intake.case_type.value}",
        f"urgency:{intake.urgency_level.value}",
        f"language:{intake.language.value}",
        f"lead-score:{qualification.label.value}",
    ]

    if intake.is_detained:
        tags.append("detained")

    if intake.court_involvement:
        tags.append("court-involvement")

    if qualification.requires_escalation:
        tags.append("escalation-required")

    if appointment:
        tags.append("consultation-scheduled")
        if payment:
            tags.append("payment-received")

    if call_status == CallStatus.TRANSFERRED:
        tags.append("transferred-to-staff")

    if call_status == CallStatus.ABANDONED:
        tags.append("call-abandoned")

    if qualification.label == LeadScore.HOT:
        tags.append("hot-lead")

    if qualification.urgency_level == UrgencyLevel.CRITICAL:
        tags.append("critical-urgency")

    return tags


def determine_pipeline_stage(
    qualification: QualificationResult,
    appointment: Optional[AppointmentSlot],
    payment: Optional[PaymentRecord],
    call_status: CallStatus,
) -> PipelineStage:
    """
    Determine the correct GoHighLevel pipeline stage based on call outcome.
    """
    if call_status == CallStatus.ESCALATED:
        return PipelineStage.ESCALATED

    if payment and payment.status.value == "completed":
        return PipelineStage.PAYMENT_RECEIVED

    if appointment:
        return PipelineStage.CONSULTATION_SCHEDULED

    if qualification.score >= 40:
        return PipelineStage.QUALIFIED

    if qualification.score > 0:
        return PipelineStage.INTAKE_COMPLETE

    return PipelineStage.NEW_LEAD


def build_call_note(
    session: CallSession,
    intake: IntakeRecord,
    qualification: QualificationResult,
    appointment: Optional[AppointmentSlot] = None,
    payment: Optional[PaymentRecord] = None,
) -> str:
    """
    Build the complete call note written to the GHL contact record.
    This is what the attorney and paralegal read when they open the contact.
    """
    duration = ""
    if session.ended_at and session.started_at:
        secs = int((session.ended_at - session.started_at).total_seconds())
        duration = f"{secs // 60}m {secs % 60}s"

    lines = [
        "AI Receptionist Call Log",
        "=" * 45,
        f"Date: {session.started_at.strftime('%B %d, %Y at %I:%M %p UTC')}",
        f"Duration: {duration or 'N/A'}",
        f"Call ID: {session.call_id}",
        f"Language: {intake.language.value.upper()}",
        f"Caller Type: {session.caller_type.value.replace('_', ' ').title()}",
        "",
        "INTAKE SUMMARY",
        "-" * 30,
        f"Name: {intake.name}",
        f"Phone: {intake.phone_number}",
        f"Country of Origin: {intake.country_of_origin or 'Not provided'}",
        f"Entry Date: {intake.entry_date or 'Not provided'}",
        f"Family Status: {intake.family_status or 'Not provided'}",
        f"Case Type: {intake.case_type.value.replace('_', ' ').title()}",
        f"Court Involvement: {'Yes' if intake.court_involvement else 'No'}",
        f"Detained: {'YES - URGENT' if intake.is_detained else 'No'}",
        f"Urgency Level: {intake.urgency_level.value.upper()}",
        "",
        "QUALIFICATION",
        "-" * 30,
        f"Score: {qualification.score}/100 ({qualification.label.value.upper()})",
        f"Escalation Required: {'YES' if qualification.requires_escalation else 'No'}",
    ]

    if qualification.escalation_reason:
        lines.append(f"Escalation Reason: {qualification.escalation_reason}")

    lines += [
        "",
        "ATTORNEY BRIEF",
        "-" * 30,
        qualification.summary,
    ]

    if appointment:
        lines += [
            "",
            "APPOINTMENT",
            "-" * 30,
            f"Scheduled: {appointment.start_time.strftime('%B %d, %Y at %I:%M %p')}",
            f"Status: {appointment.status.value.replace('_', ' ').title()}",
        ]
        if appointment.stripe_payment_link:
            lines.append(f"Payment Link: {appointment.stripe_payment_link}")

    if payment:
        lines += [
            "",
            "PAYMENT",
            "-" * 30,
            f"Amount: ${payment.amount:.2f} {payment.currency.upper()}",
            f"Status: {payment.status.value.upper()}",
            f"Stripe ID: {payment.stripe_payment_intent_id or 'N/A'}",
        ]
        if payment.paid_at:
            lines.append(
                f"Paid At: {payment.paid_at.strftime('%Y-%m-%d %H:%M UTC')}"
            )

    if session.call_summary:
        lines += [
            "",
            "CALL SUMMARY",
            "-" * 30,
            session.call_summary,
        ]

    if session.transcript:
        lines += [
            "",
            "TRANSCRIPT (excerpt)",
            "-" * 30,
            session.transcript[:500] + ("..." if len(session.transcript) > 500 else ""),
        ]

    return "\n".join(lines)


class CRMSyncAgent:
    """
    Writes the complete call record to GoHighLevel after every call.
    Handles contact creation or update, tags, pipeline stage,
    and the full structured call note.
    """

    async def sync_call(
        self,
        session: CallSession,
        intake: IntakeRecord,
        qualification: QualificationResult,
        appointment: Optional[AppointmentSlot] = None,
        payment: Optional[PaymentRecord] = None,
        ghl_contact_id: Optional[str] = None,
    ) -> dict:
        """
        Full CRM sync after a call ends.
        Creates or updates the GHL contact, adds tags,
        writes the call note, and updates the pipeline stage.
        Returns a dict with the contact_id and sync status.
        """
        from integrations.ghl_client import ghl_client

        logger.info(
            "crm_sync_started",
            session_id=session.id,
            lead_id=intake.lead_id,
        )

        # Step 1: Get or create contact
        if ghl_contact_id:
            contact_id = ghl_contact_id
        else:
            contact = await ghl_client.get_or_create_contact(
                phone_number=intake.phone_number,
                name=intake.name,
            )
            contact_id = contact.get("id")

        if not contact_id:
            logger.error(
                "crm_sync_no_contact_id",
                phone=intake.phone_number,
            )
            raise ValueError(
                f"Could not resolve GHL contact for {intake.phone_number}"
            )

        # Step 2: Build and apply tags
        tags = build_outcome_tags(
            intake, qualification, appointment, payment, session.status
        )
        await ghl_client.add_tags(contact_id, tags)

        # Step 3: Write the call note
        note = build_call_note(
            session, intake, qualification, appointment, payment
        )
        await ghl_client.add_note(contact_id, note)

        # Step 4: Determine and log pipeline stage
        stage = determine_pipeline_stage(
            qualification, appointment, payment, session.status
        )

        logger.info(
            "crm_sync_complete",
            session_id=session.id,
            contact_id=contact_id,
            pipeline_stage=stage,
            tags_applied=len(tags),
            score=qualification.score,
        )

        return {
            "contact_id": contact_id,
            "pipeline_stage": stage.value,
            "tags_applied": tags,
            "note_length": len(note),
            "sync_status": "complete",
        }

    async def sync_minimal(
        self,
        phone_number: str,
        name: str,
        reason: str,
        language: str,
    ) -> dict:
        """
        Lightweight sync for the demo webhook endpoint.
        Creates a GHL contact with minimal intake data.
        Used by the /voice/intake-webhook route in the demo.
        """
        from integrations.ghl_client import ghl_client

        contact = await ghl_client.get_or_create_contact(
            phone_number=phone_number,
            name=name,
        )
        contact_id = contact.get("id")

        await ghl_client.add_tags(
            contact_id,
            [
                "ai-receptionist",
                f"language:{language}",
                "demo-intake",
            ],
        )

        note = (
            f"Demo Intake\n"
            f"{'=' * 30}\n"
            f"Name: {name}\n"
            f"Phone: {phone_number}\n"
            f"Reason: {reason}\n"
            f"Language: {language.upper()}\n"
            f"Captured via: AI Receptionist Demo"
        )
        await ghl_client.add_note(contact_id, note)

        logger.info(
            "crm_minimal_sync_complete",
            contact_id=contact_id,
            phone=phone_number,
        )

        return {"contact_id": contact_id, "sync_status": "complete"}


# Singleton instance
crm_sync_agent = CRMSyncAgent()