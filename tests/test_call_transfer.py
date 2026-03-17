import unittest
from core.enums import Language, UrgencyLevel, CaseType, LeadScore
from core.models import IntakeRecord, QualificationResult
from agents.call_transfer_agent import CallTransferAgent


class TestCallTransfer(unittest.TestCase):

    def setUp(self):
        self.agent = CallTransferAgent()
        self.intake = IntakeRecord(
            lead_id="lead-001",
            call_session_id="session-001",
            name="Maria Gonzalez",
            phone_number="+13051234567",
            country_of_origin="Honduras",
            entry_date="2023",
            family_status="None",
            immigration_history="Husband detained",
            court_involvement=True,
            is_detained=True,
            urgency_level=UrgencyLevel.CRITICAL,
            case_type=CaseType.DETENTION,
            language=Language.SPANISH,
        )
        self.qual_critical = QualificationResult(
            lead_id="lead-001",
            intake_id=self.intake.id,
            score=95,
            label=LeadScore.HOT,
            case_type=CaseType.DETENTION,
            urgency_level=UrgencyLevel.CRITICAL,
            requires_escalation=True,
            escalation_reason="Detained",
            summary="Immediate intervention required.",
        )
        self.qual_standard = QualificationResult(
            lead_id="lead-002",
            intake_id=self.intake.id,
            score=51,
            label=LeadScore.WARM,
            case_type=CaseType.VISA_APPLICATION,
            urgency_level=UrgencyLevel.MEDIUM,
            requires_escalation=False,
            summary="Work visa consultation needed.",
        )

    def test_critical_routes_to_attorney(self):
        target = self.agent.select_transfer_target(
            self.qual_critical, Language.SPANISH, True
        )
        self.assertEqual(target["name"], "Senior Attorney")

    def test_spanish_standard_routes_to_spanish_paralegal(self):
        target = self.agent.select_transfer_target(
            self.qual_standard, Language.SPANISH, False
        )
        self.assertEqual(target["name"], "Spanish Paralegal")

    def test_english_standard_routes_to_default_paralegal(self):
        target = self.agent.select_transfer_target(
            self.qual_standard, Language.ENGLISH, False
        )
        self.assertEqual(target["name"], "Paralegal Team")

    def test_whisper_contains_key_fields(self):
        whisper = self.agent.build_whisper_message(self.intake, self.qual_critical)
        self.assertIn("Maria Gonzalez", whisper)
        self.assertIn("CRITICAL", whisper)
        self.assertIn("URGENT", whisper)

    def test_hold_message_spanish(self):
        msg = self.agent.build_hold_message(Language.SPANISH)
        self.assertIn("espere", msg.lower())

    def test_hold_message_english(self):
        msg = self.agent.build_hold_message(Language.ENGLISH)
        self.assertIn("hold", msg.lower())

    def test_transfer_failed_message_contains_timeframe(self):
        msg = self.agent.build_transfer_failed_message(Language.SPANISH)
        self.assertIn("15 minutos", msg)


if __name__ == "__main__":
    unittest.main()