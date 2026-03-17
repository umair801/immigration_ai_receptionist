from enum import Enum


class Language(str, Enum):
    ENGLISH = "en"
    SPANISH = "es"


class CallerType(str, Enum):
    NEW_LEAD = "new_lead"
    EXISTING_CLIENT = "existing_client"
    UNKNOWN = "unknown"


class CallStatus(str, Enum):
    INITIATED = "initiated"
    IN_PROGRESS = "in_progress"
    INTAKE_COMPLETE = "intake_complete"
    QUALIFIED = "qualified"
    APPOINTMENT_SET = "appointment_set"
    PAYMENT_PENDING = "payment_pending"
    PAYMENT_CONFIRMED = "payment_confirmed"
    TRANSFERRED = "transferred"
    ESCALATED = "escalated"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


class UrgencyLevel(str, Enum):
    CRITICAL = "critical"      # Detained or court hearing within 48 hours
    HIGH = "high"              # Court hearing within 30 days
    MEDIUM = "medium"          # Active case, no immediate deadline
    LOW = "low"                # Exploratory inquiry


class CaseType(str, Enum):
    ASYLUM = "asylum"
    REMOVAL_DEFENSE = "removal_defense"
    FAMILY_PETITION = "family_petition"
    NATURALIZATION = "naturalization"
    DACA = "daca"
    VISA_APPLICATION = "visa_application"
    WORK_PERMIT = "work_permit"
    GREEN_CARD = "green_card"
    DETENTION = "detention"
    OTHER = "other"
    UNKNOWN = "unknown"


class LeadScore(str, Enum):
    HOT = "hot"          # Score 75-100
    WARM = "warm"        # Score 50-74
    COLD = "cold"        # Score 25-49
    UNQUALIFIED = "unqualified"  # Score 0-24


class PipelineStage(str, Enum):
    NEW_LEAD = "new_lead"
    INTAKE_COMPLETE = "intake_complete"
    QUALIFIED = "qualified"
    CONSULTATION_SCHEDULED = "consultation_scheduled"
    PAYMENT_RECEIVED = "payment_received"
    ACTIVE_CLIENT = "active_client"
    NOT_QUALIFIED = "not_qualified"
    ESCALATED = "escalated"


class AppointmentStatus(str, Enum):
    PENDING_PAYMENT = "pending_payment"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"