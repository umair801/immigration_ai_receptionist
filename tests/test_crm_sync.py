import unittest
from datetime import datetime
from core.enums import (
    Language, UrgencyLevel, CaseType, CallStatus,
    AppointmentStatus, PaymentStatus, LeadScore, PipelineStage,
)
from core.models import (
    IntakeRecord, QualificationResult, CallSession,
    AppointmentSlot, PaymentRecord,
)
from agents.crm_sync_agent import (
    build_outcome_tags,
    build_call_note,
    determine_pipeline_stage,
)


class TestCRMSync(unittest.TestCase):

    def setUp(self):
        self.intake = IntakeRecord(
            lead_id="lead-001",
            call_session_id="session-001",
            name="Carlos Mendoza",
            phone_number="+13051234567",
            country_of_origin="Mexico",
            entry_date="2019",
            family_status="Spouse is US citizen",
            immigration_history="Work visa",
            court_involvement=False,
            is_detained=False,
            urgency_level=UrgencyLevel.MEDIUM,
            case_type=CaseType.VISA_APPLICATION,
            language=Language.SPANISH,
        )
        self.qualification = QualificationResult(
            lead_id="lead-001",
            intake_id=self.intake.id,
            score=51,
            label=LeadScore.WARM,
            case_type=CaseType.VISA_APPLICATION,
            urgency_level=UrgencyLevel.MEDIUM,
            requires_escalation=False,
            summary="Carlos is a qualified lead for a work visa consultation.",
        )
        self.session = CallSession(
            call_id="call-001",
            phone_number="+13051234567",
            lead_id="lead-001",
            language=Language.SPANISH,
            status=CallStatus.COMPLETED,
            started_at=datetime(2026, 3, 17, 14, 0, 0),
            ended_at=datetime(2026, 3, 17, 14, 8, 30),
        )
        self.appointment = AppointmentSlot(
            lead_id="lead-001",
            start_time=datetime(2026, 3, 18, 9, 0),
            end_time=datetime(2026, 3, 18, 9, 30),
            status=AppointmentStatus.CONFIRMED,
        )
        self.payment = PaymentRecord(
            lead_id="lead-001",
            appointment_id=self.appointment.id,
            stripe_payment_intent_id="pi_test_123",
            amount=150.0,
            currency="usd",
            status=PaymentStatus.COMPLETED,
            paid_at=datetime(2026, 3, 17, 14, 5, 0),
        )

    def test_tags_include_required_fields(self):
        tags = build_outcome_tags(
            self.intake, self.qualification,
            self.appointment, self.payment,
            CallStatus.COMPLETED,
        )
        self.assertIn("ai-receptionist", tags)
        self.assertIn("language:es", tags)
        self.assertIn("consultation-scheduled", tags)
        self.assertIn("payment-received", tags)

    def test_detained_adds_escalation_tags(self):
        detained_intake = IntakeRecord(
            lead_id="lead-002",
            call_session_id="session-002",
            name="Maria",
            phone_number="+13059876543",
            country_of_origin="Honduras",
            entry_date="2023",
            family_status="None",
            immigration_history="Detained",
            court_involvement=True,
            is_detained=True,
            urgency_level=UrgencyLevel.CRITICAL,
            case_type=CaseType.DETENTION,
            language=Language.SPANISH,
        )
        qual = QualificationResult(
            lead_id="lead-002",
            intake_id=detained_intake.id,
            score=95,
            label=LeadScore.HOT,
            case_type=CaseType.DETENTION,
            urgency_level=UrgencyLevel.CRITICAL,
            requires_escalation=True,
            escalation_reason="Detained",
            summary="Immediate intervention needed.",
        )
        tags = build_outcome_tags(
            detained_intake, qual, None, None, CallStatus.ESCALATED
        )
        self.assertIn("detained", tags)
        self.assertIn("escalation-required", tags)
        self.assertIn("hot-lead", tags)
        self.assertIn("critical-urgency", tags)

    def test_pipeline_stage_with_payment(self):
        stage = determine_pipeline_stage(
            self.qualification, self.appointment,
            self.payment, CallStatus.COMPLETED
        )
        self.assertEqual(stage, PipelineStage.PAYMENT_RECEIVED)

    def test_pipeline_stage_no_payment(self):
        stage = determine_pipeline_stage(
            self.qualification, self.appointment,
            None, CallStatus.COMPLETED
        )
        self.assertEqual(stage, PipelineStage.CONSULTATION_SCHEDULED)

    def test_pipeline_stage_qualified_only(self):
        stage = determine_pipeline_stage(
            self.qualification, None, None, CallStatus.COMPLETED
        )
        self.assertEqual(stage, PipelineStage.QUALIFIED)

    def test_call_note_contains_required_sections(self):
        note = build_call_note(
            self.session, self.intake,
            self.qualification, self.appointment, self.payment
        )
        self.assertIn("Carlos Mendoza", note)
        self.assertIn("ATTORNEY BRIEF", note)
        self.assertIn("APPOINTMENT", note)
        self.assertIn("PAYMENT", note)
        self.assertIn("$150.00", note)
        self.assertIn("8m 30s", note)

    def test_call_note_without_payment(self):
        note = build_call_note(
            self.session, self.intake, self.qualification
        )
        self.assertIn("Carlos Mendoza", note)
        self.assertNotIn("PAYMENT", note)


if __name__ == "__main__":
    unittest.main()