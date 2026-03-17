import unittest
from core.enums import Language, UrgencyLevel, CaseType, LeadScore
from core.models import IntakeRecord, QualificationResult
from agents.qualification_agent import label_from_score, URGENCY_SCORES, CASE_TYPE_SCORES, QUALIFICATION_THRESHOLD


def make_intake(
    urgency=UrgencyLevel.MEDIUM,
    case_type=CaseType.VISA_APPLICATION,
    is_detained=False,
    court=False,
    language=Language.SPANISH,
) -> IntakeRecord:
    return IntakeRecord(
        lead_id="lead-test-001",
        call_session_id="session-test-001",
        name="Test Caller",
        phone_number="+13051234567",
        country_of_origin="Mexico",
        entry_date="2019",
        family_status="Spouse is US citizen",
        immigration_history="Test reason",
        court_involvement=court,
        is_detained=is_detained,
        urgency_level=urgency,
        case_type=case_type,
        language=language,
    )


class TestQualification(unittest.TestCase):

    def test_label_from_score(self):
        self.assertEqual(label_from_score(80), LeadScore.HOT)
        self.assertEqual(label_from_score(60), LeadScore.WARM)
        self.assertEqual(label_from_score(30), LeadScore.COLD)
        self.assertEqual(label_from_score(10), LeadScore.UNQUALIFIED)
        self.assertEqual(label_from_score(75), LeadScore.HOT)
        self.assertEqual(label_from_score(50), LeadScore.WARM)
        self.assertEqual(label_from_score(25), LeadScore.COLD)
        self.assertEqual(label_from_score(0), LeadScore.UNQUALIFIED)

    def test_urgency_scores_defined(self):
        self.assertIn(UrgencyLevel.CRITICAL, URGENCY_SCORES)
        self.assertIn(UrgencyLevel.HIGH, URGENCY_SCORES)
        self.assertIn(UrgencyLevel.MEDIUM, URGENCY_SCORES)
        self.assertIn(UrgencyLevel.LOW, URGENCY_SCORES)
        self.assertGreater(
            URGENCY_SCORES[UrgencyLevel.CRITICAL],
            URGENCY_SCORES[UrgencyLevel.HIGH],
        )
        self.assertGreater(
            URGENCY_SCORES[UrgencyLevel.HIGH],
            URGENCY_SCORES[UrgencyLevel.MEDIUM],
        )

    def test_case_type_scores_defined(self):
        self.assertIn(CaseType.DETENTION, CASE_TYPE_SCORES)
        self.assertIn(CaseType.VISA_APPLICATION, CASE_TYPE_SCORES)
        self.assertGreater(
            CASE_TYPE_SCORES[CaseType.DETENTION],
            CASE_TYPE_SCORES[CaseType.VISA_APPLICATION],
        )

    def test_detained_score_reaches_hot(self):
        urgency_score = URGENCY_SCORES[UrgencyLevel.CRITICAL]
        case_score = CASE_TYPE_SCORES[CaseType.DETENTION]
        raw = urgency_score + case_score
        score = min(raw, 100)
        label = label_from_score(score)
        self.assertEqual(label, LeadScore.HOT)

    def test_standard_visa_score_above_zero(self):
        urgency_score = URGENCY_SCORES[UrgencyLevel.MEDIUM]
        case_score = CASE_TYPE_SCORES[CaseType.VISA_APPLICATION]
        bonus = 10 + 5 + 5
        score = min(urgency_score + case_score + bonus, 100)
        self.assertGreater(score, 0)
        self.assertLessEqual(score, 100)

    def test_high_urgency_court_score_above_threshold(self):
        urgency_score = URGENCY_SCORES[UrgencyLevel.HIGH]
        case_score = CASE_TYPE_SCORES[CaseType.REMOVAL_DEFENSE]
        bonus = 10
        score = min(urgency_score + case_score + bonus, 100)
        self.assertGreater(score, QUALIFICATION_THRESHOLD)

    def test_qualification_threshold_is_reasonable(self):
        self.assertGreaterEqual(QUALIFICATION_THRESHOLD, 30)
        self.assertLessEqual(QUALIFICATION_THRESHOLD, 60)

    def test_score_always_bounded(self):
        for urgency in UrgencyLevel:
            for case_type in CaseType:
                u = URGENCY_SCORES.get(urgency, 5)
                c = CASE_TYPE_SCORES.get(case_type, 0)
                score = min(u + c + 30, 100)
                self.assertGreaterEqual(score, 0)
                self.assertLessEqual(score, 100)


if __name__ == "__main__":
    unittest.main()