from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import uuid4

from core.enums import (
    Language,
    CallerType,
    CallStatus,
    UrgencyLevel,
    CaseType,
    LeadScore,
    PipelineStage,
    AppointmentStatus,
    PaymentStatus,
)


class Lead(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    phone_number: str
    name: Optional[str] = None
    email: Optional[str] = None
    language: Language = Language.ENGLISH
    caller_type: CallerType = CallerType.UNKNOWN
    ghl_contact_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class IntakeRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    lead_id: str
    call_session_id: str
    name: str
    phone_number: str
    country_of_origin: Optional[str] = None
    entry_date: Optional[str] = None
    family_status: Optional[str] = None
    immigration_history: Optional[str] = None
    court_involvement: bool = False
    is_detained: bool = False
    urgency_level: UrgencyLevel = UrgencyLevel.LOW
    case_type: CaseType = CaseType.UNKNOWN
    language: Language = Language.ENGLISH
    additional_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class QualificationResult(BaseModel):
    lead_id: str
    intake_id: str
    score: int = Field(ge=0, le=100)
    label: LeadScore
    case_type: CaseType
    urgency_level: UrgencyLevel
    requires_escalation: bool = False
    escalation_reason: Optional[str] = None
    summary: str
    scored_at: datetime = Field(default_factory=datetime.utcnow)


class AppointmentSlot(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    lead_id: str
    start_time: datetime
    end_time: datetime
    attorney_name: Optional[str] = None
    ghl_calendar_id: Optional[str] = None
    google_event_id: Optional[str] = None
    status: AppointmentStatus = AppointmentStatus.PENDING_PAYMENT
    stripe_payment_link: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PaymentRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    lead_id: str
    appointment_id: str
    stripe_payment_intent_id: Optional[str] = None
    stripe_session_id: Optional[str] = None
    amount: float
    currency: str = "usd"
    status: PaymentStatus = PaymentStatus.PENDING
    paid_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CallSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    call_id: str
    phone_number: str
    lead_id: Optional[str] = None
    caller_type: CallerType = CallerType.UNKNOWN
    language: Language = Language.ENGLISH
    status: CallStatus = CallStatus.INITIATED
    intake_id: Optional[str] = None
    qualification_id: Optional[str] = None
    appointment_id: Optional[str] = None
    payment_id: Optional[str] = None
    transcript: Optional[str] = None
    call_summary: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None


class WebhookIntakePayload(BaseModel):
    call_id: str
    phone_number: str
    name: str
    reason_for_calling: str
    language: Language
    timestamp: datetime = Field(default_factory=datetime.utcnow)