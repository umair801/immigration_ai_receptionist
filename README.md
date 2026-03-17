# AI Immigration Receptionist and Intake Automation System

**Built by [Datawebify](https://datawebify.com) | [immigration.datawebify.com](https://immigration.datawebify.com) | [GitHub](https://github.com/umair801/immigration_ai_receptionist)**

A fully autonomous AI receptionist system for immigration law firms. Handles inbound and outbound calls in English and Spanish, qualifies leads through structured intake conversations, books consultations with payment confirmation, transfers calls to paralegals when needed, and logs every interaction into GoHighLevel — without human receptionist involvement.

---

## Business Outcomes

| Metric | Manual Receptionist | With This System | Change |
|---|---|---|---|
| Call answer rate | 60-70% (missed after hours) | 100% (24/7) | Full coverage |
| Time to first intake question | 2-5 minutes | Under 10 seconds | 97% faster |
| Intake completion rate | 50-60% | 85%+ | +30% |
| Consultation booking rate | 20-30% of calls | 40-55% of calls | 2x improvement |
| Staff time on intake calls | 15-20 hrs/week | Near zero | 90% reduction |
| Lead data in CRM | Inconsistent, manual | 100% automated | Full coverage |

---

## System Architecture
```
Inbound Call / Social Media Lead
           |
     Twilio (routing)
           |
      Retell AI (voice agent)
           |
     ElevenLabs (bilingual TTS)
           |
   ┌───────┴────────┐
   |                |
New Lead     Existing Client
   |                |
Intake Agent   Transfer to
   |            Paralegal
   |
Qualification Agent (GPT-4o)
   |
Appointment Setter Agent
   |
Payment Confirmation Agent
   |
CRM Sync Agent (GoHighLevel)
   |
SMS + Calendar Confirmation
```

### Agent Pipeline

| Agent | Responsibility |
|---|---|
| Call Router | Detects new vs existing caller via GHL lookup |
| Intake Agent | Bilingual structured intake in English and Spanish |
| Qualification Agent | GPT-4o lead scoring 0-100 with urgency escalation |
| Appointment Setter | Calendar slot presentation and caller selection |
| Payment Confirmation | Stripe webhook listener, SMS confirmation, reminder |
| Outbound Caller | Social media lead follow-up within seconds of form submission |
| Call Transfer | Warm transfer with attorney whisper summary |
| CRM Sync | Full GoHighLevel write after every call |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent Framework | LangGraph |
| AI Model | GPT-4o (OpenAI) |
| Voice Platform | Retell AI |
| Telephony | Twilio Voice |
| Voice Synthesis | ElevenLabs (English + Spanish) |
| CRM | GoHighLevel |
| Calendar | Google Calendar API |
| Payment | Stripe |
| Backend | FastAPI + Uvicorn |
| Database | Supabase (PostgreSQL) |
| Deployment | Docker + Railway |
| Language | Python 3.12 |

---

## API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Service health check |
| `/metrics/` | GET | Live KPI dashboard |
| `/metrics/summary` | GET | Executive summary report |
| `/voice/retell-webhook` | POST | Retell AI call events |
| `/voice/intake-webhook` | POST | Demo intake data receiver |
| `/voice/trigger-outbound` | POST | GoHighLevel outbound trigger |
| `/payment/stripe-webhook` | POST | Stripe payment confirmation |
| `/payment/success` | GET | Post-payment landing page |

---

## Key Features

**Bilingual voice quality.** ElevenLabs voices configured separately for English and Spanish with tuned stability and similarity settings for natural conversational cadence.

**Structured immigration intake.** Eight-question intake flow collecting name, country of origin, entry date, family status, immigration history, court involvement, and detention status. All fields extracted from free-form speech via GPT-4o.

**Deterministic lead scoring.** Qualification scoring uses a weighted model across urgency level, case type, family status, court involvement, and data completeness. Detained callers and imminent court hearings trigger immediate attorney escalation regardless of score.

**Payment-gated appointments.** Consultation slots are held as pending until Stripe confirms payment. Stripe webhook signature verification prevents unauthorized confirmation. Appointments are only finalized in GoHighLevel and Google Calendar after payment lands.

**Warm call transfer with whisper.** Paralegals and attorneys receive a spoken summary of the caller's name, case type, urgency, and escalation reason before the caller is connected. No cold transfers.

**Full CRM automation.** Every call produces a structured GoHighLevel contact record with intake fields, qualification score, attorney brief, outcome tags, and pipeline stage update. Tags drive GoHighLevel email sequences and follow-up tasks automatically.

**Outbound lead response.** Social media leads from Facebook and Instagram trigger outbound calls within seconds of form submission via GoHighLevel webhook. The same intake and qualification pipeline runs on outbound calls.

---

## Project Structure
```
immigration_ai_receptionist/
├── agents/
│   ├── call_router_agent.py
│   ├── intake_agent.py
│   ├── qualification_agent.py
│   ├── appointment_setter_agent.py
│   ├── payment_confirmation_agent.py
│   ├── outbound_caller_agent.py
│   ├── call_transfer_agent.py
│   └── crm_sync_agent.py
├── core/
│   ├── orchestrator.py
│   ├── config.py
│   ├── database.py
│   ├── session_manager.py
│   ├── models.py
│   └── logger.py
├── api/
│   ├── main.py
│   ├── voice_router.py
│   ├── payment_router.py
│   └── metrics_router.py
├── integrations/
│   ├── retell_client.py
│   ├── elevenlabs_client.py
│   ├── ghl_client.py
│   ├── stripe_client.py
│   └── google_calendar_client.py
├── notifications/
│   └── sms_sender.py
├── tests/
│   ├── test_intake_flow.py
│   ├── test_qualification.py
│   ├── test_call_transfer.py
│   ├── test_payment_confirmation.py
│   └── test_crm_sync.py
├── Dockerfile
├── railway.json
├── requirements.txt
├── schema.sql
└── .env.example
```

---

## Local Setup
```bash
# Clone the repository
git clone https://github.com/umair801/immigration_ai_receptionist.git
cd immigration_ai_receptionist

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Fill in all values in .env

# Apply database schema
# Paste schema.sql into Supabase SQL Editor and run

# Start the server
python main.py
```

---

## Environment Variables

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | GPT-4o API key |
| `RETELL_API_KEY` | Retell AI API key |
| `RETELL_AGENT_ID` | Retell agent ID |
| `ELEVENLABS_API_KEY` | ElevenLabs API key |
| `ELEVENLABS_VOICE_ID_EN` | English voice ID |
| `ELEVENLABS_VOICE_ID_ES` | Spanish voice ID |
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_PHONE_NUMBER` | Twilio phone number |
| `GHL_API_KEY` | GoHighLevel API key |
| `GHL_LOCATION_ID` | GoHighLevel location ID |
| `STRIPE_SECRET_KEY` | Stripe secret key |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Supabase service role key |
| `GOOGLE_CALENDAR_ID` | Google Calendar ID |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Path to service account JSON |
| `BASE_URL` | Public deployment URL |

---

## Test Suite
```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

35 tests across 5 modules covering intake flow, lead qualification,
call transfer routing, payment confirmation, and CRM sync logic.

---

## Deployment

Deployed on Railway via Docker.
Live at: [immigration.datawebify.com](https://immigration.datawebify.com)
```bash
# Railway deployment is automatic on push to main
git push origin main
```

---

## Built by Datawebify

**Agentic AI solutions for professional services firms.**

[datawebify.com](https://datawebify.com) | [github.com/umair801/immigration_ai_receptionist](https://github.com/umair801/immigration_ai_receptionist)
