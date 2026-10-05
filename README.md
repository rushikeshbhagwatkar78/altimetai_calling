---
title: Nagpur Estates AI Voice CRM
emoji: 🏢
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Gemini Live Native Audio Outbound Calling Agent

Production-grade real-time AI voice outbound calling agent powered by **Google Gemini Live Native Audio**, **LiveKit Cloud**, **LiveKit SIP**, and **Vobiz**.

---

## 1. Architecture

```text
                         CUSTOMER
                            │
                            │ PSTN (Mobile / Landline)
                            ▼
                         VOBIZ
                   Number + SIP Trunk
                            │
                            │ SIP Signaling & G.711 RTP Audio
                            ▼
                    LIVEKIT SIP
                            │
                            │ WebRTC Realtime Audio
                            ▼
              LIVEKIT AGENT WORKER (agent.py)
                            │
                            ▼
              GEMINI LIVE NATIVE AUDIO (gemini-3.1-flash-live-preview)
                            │
                 ┌──────────┴──────────┐
                 │                     │
              Audio In              Audio Out
                 │                     │
                 └──────────┬──────────┘
                            ▼
                       LIVEKIT SIP
                            │
                            ▼
                          VOBIZ
                            │
                            ▼
                        CUSTOMER
```

---

## 2. Key Features

- **Gemini Live Native Audio**: Direct speech-to-speech multimodal streaming. Eliminates cascaded STT → text LLM → TTS delays.
- **Natural Multilingual Mirroring**: Seamlessly conversations in Hindi, English, and Hinglish with natural Indian conversational nuances.
- **Domain-Grounded Real Estate Persona (Priya)**: Tailored for Nagpur Estates covering localities (Wardha Road, Besa, Manish Nagar, Zingabai Takli, Koradi Road, MIHAN, Dharampeth).
- **Tool Calling & Structured Lead State**: Built-in function tools for property searches, site visit bookings, callbacks, WhatsApp follow-ups, and DND compliance.
- **Instant Greeting (<400ms)**: Native audio greeting delivered immediately upon customer pickup without waiting for customer speech or text generation.
- **Fast Telephony Turn Endpointing & Barge-In**: Silero VAD tuned for phone audio (350ms–850ms silence detection) with instant interruption cutoff.
- **Call-Control FastAPI Server**: `/call` with `Idempotency-Key` deduplication, phone normalization (`9876543210` → `+919876543210`), `/health`, `/ready`, `/calls`, and `/calls/{call_id}/hangup`.
- **Telemetry & Latency Profiling**: Real-time logging of P50, P90, P95, and P99 response latencies alongside masked phone numbers (`+919876****10`).

---

## 3. Installation & Setup

### Prerequisites
- Python 3.10+
- LiveKit Cloud project with configured SIP Outbound Trunk
- Vobiz SIP Trunk credentials configured in LiveKit
- Google Gemini API Key

### Virtual Environment Setup
```bash
python -m venv .venv
```

**Windows (PowerShell):**
```powershell
.venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
source .venv/bin/activate
```

### Install Dependencies
```bash
pip install -r requirements.txt
```

---

## 4. Configuration (`.env`)

Copy `.env.example` to `.env` and fill in your credentials:

```env
# LiveKit Cloud
LIVEKIT_URL=wss://YOUR_PROJECT.livekit.cloud
LIVEKIT_API_KEY=YOUR_LIVEKIT_API_KEY
LIVEKIT_API_SECRET=YOUR_LIVEKIT_API_SECRET
LIVEKIT_SIP_OUTBOUND_TRUNK_ID=YOUR_OUTBOUND_TRUNK_ID
AGENT_NAME=ai-calling-agent

# Google Gemini Live
GOOGLE_API_KEY=YOUR_GOOGLE_API_KEY
GEMINI_LIVE_MODEL=gemini-3.1-flash-live-preview
GEMINI_VOICE=Aoede

# Application Settings
COMPANY_NAME=Nagpur Estates
AGENT_DISPLAY_NAME=Priya
API_HOST=0.0.0.0
API_PORT=8000
DEV_MODE=true
BENCHMARK_MODE=true
```

---

## 5. Running the Application

### Step 1: Start the Agent Worker
```bash
lk agent dev
```
*(Or for production: `python agent.py start`)*

### Step 2: Start the FastAPI Call Control Server
In a separate terminal:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 6. Initiating Outbound Calls

### API Request (PowerShell)
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/call" -Method Post -ContentType "application/json" -Body '{"phone_number": "+919876543210", "customer_name": "Rahul"}'
```

### API Request (cURL)
```bash
curl -X POST http://localhost:8000/call \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: call-req-001" \
  -d '{"phone_number": "+919876543210", "customer_name": "Rahul"}'
```

---

## 7. Telemetry & Benchmark Logging

Upon call termination, the agent worker logs structured call analytics and lead qualification data:

```text
====================================================
GEMINI LIVE CALL BENCHMARK
====================================================

Call ID:                       call-dcd4f016
Duration:                      01:45
Greeting first audio:          380 ms

Response latency:
  Average:                     420 ms
  P50:                         395 ms
  P90:                         510 ms
  P95:                         620 ms
  P99:                         750 ms

Interruptions:                 2
Turns:                         8

Outcome:                       site_visit
Lead Temperature:              hot
====================================================
```
