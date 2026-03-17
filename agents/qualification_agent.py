import structlog
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage

from core.config import get_settings
from core.enums import (
    UrgencyLevel,
    CaseType,
    LeadScore,
)
from core.models import IntakeRecord, QualificationResult

logger = structlog.get_logger()
settings = get_settings()

llm = ChatOpenAI(
    model="gpt-4o",
    api_key=settings.openai_api_key,
    temperature=0.0,
)

# ------------------------------------------------------------------
# Scoring weights
# ------------------------------------------------------------------

URGENCY_SCORES = {
    UrgencyLevel.CRITICAL: 40,
    UrgencyLevel.HIGH: 30,
    UrgencyLevel.MEDIUM: 15,
    UrgencyLevel.LOW: 5,
}

CASE_TYPE_SCORES = {
    CaseType.DETENTION: 35,
    CaseType.REMOVAL_DEFENSE: 30,
    CaseType.ASYLUM: 28,
    CaseType.FAMILY_PETITION: 22,
    CaseType.GREEN_CARD: 20,
    CaseType.DACA: 18,
    CaseType.VISA_APPLICATION: 16,
    CaseType.WORK_PERMIT: 14,
    CaseType.NATURALIZATION: 12,
    CaseType.OTHER: 8,
    CaseType.UNKNOWN: 0,
}

QUALIFICATION_THRESHOLD = 40


def label_from_score(score: int) -> LeadScore:
    if score >= 75:
        return LeadScore.HOT
    if score >= 50:
        return LeadScore.WARM
    if score >= 25:
        return LeadScore.COLD
    return LeadScore.UNQUALIFIED


# ------------------------------------------------------------------
# GPT-4o summary generator
# ------------------------------------------------------------------

async def generate_qualification_summary(
    intake: IntakeRecord,
    score: int,
    label: LeadScore,
) -> str:
    """
    Use GPT-4o to write a one-paragraph attorney briefing
    summarizing the lead and recommended next action.
    """
    system_prompt = (
        "You are a senior immigration paralegal writing a brief lead summary "
        "for an attorney. Write exactly two sentences. "
        "Sentence one: summarize the caller's situation and case type. "
        "Sentence two: state the recommended next action based on urgency. "
        "Be direct and professional. No bullet points. No headers."
    )

    intake_summary = (
        f"Name: {intake.name}\n"
        f"Country: {intake.country_of_origin}\n"
        f"Entry date: {intake.entry_date}\n"
        f"Reason: {intake.immigration_history}\n"
        f"Case type: {intake.case_type}\n"
        f"Court involvement: {intake.court_involvement}\n"
        f"Detained: {intake.is_detained}\n"
        f"Family status: {intake.family_status}\n"
        f"Urgency: {intake.urgency_level}\n"
        f"Lead score: {score} ({label})\n"
        f"Language: {intake.language}"
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=intake_summary),
    ]

    response = await llm.ainvoke(messages)
    return response.content.strip()


# ------------------------------------------------------------------
# Main qualification function
# ------------------------------------------------------------------

async def qualify_lead(intake: IntakeRecord) -> QualificationResult:
    """
    Score and qualify a completed intake record.
    Returns a QualificationResult with score, label, escalation flag,
    and a GPT-4o generated attorney summary.
    """
    logger.info(
        "qualification_started",
        lead_id=intake.lead_id,
        case_type=intake.case_type,
        urgency=intake.urgency_level,
    )

    # Base score from urgency and case type
    urgency_score = URGENCY_SCORES.get(intake.urgency_level, 5)
    case_score = CASE_TYPE_SCORES.get(intake.case_type, 8)

    # Bonus points for additional qualifying factors
    bonus = 0

    if intake.family_status and intake.family_status.lower() not in [
        "unknown", "none", "no", "ninguno"
    ]:
        bonus += 10

    if intake.court_involvement:
        bonus += 10

    if intake.country_of_origin and intake.country_of_origin.lower() not in [
        "unknown", ""
    ]:
        bonus += 5

    if intake.entry_date and intake.entry_date.lower() not in [
        "unknown", ""
    ]:
        bonus += 5

    raw_score = urgency_score + case_score + bonus
    score = min(raw_score, 100)
    label = label_from_score(score)

    # Escalation check
    requires_escalation = False
    escalation_reason = None

    if intake.is_detained:
        requires_escalation = True
        escalation_reason = "Caller or family member is currently detained"

    elif intake.urgency_level == UrgencyLevel.CRITICAL:
        requires_escalation = True
        escalation_reason = "Critical urgency level detected"

    elif intake.court_involvement and intake.urgency_level == UrgencyLevel.HIGH:
        requires_escalation = True
        escalation_reason = "Active court involvement with high urgency"

    # GPT-4o attorney summary
    summary = await generate_qualification_summary(intake, score, label)

    result = QualificationResult(
        lead_id=intake.lead_id,
        intake_id=intake.id,
        score=score,
        label=label,
        case_type=intake.case_type,
        urgency_level=intake.urgency_level,
        requires_escalation=requires_escalation,
        escalation_reason=escalation_reason,
        summary=summary,
    )

    logger.info(
        "qualification_complete",
        lead_id=intake.lead_id,
        score=score,
        label=label,
        requires_escalation=requires_escalation,
    )

    return result