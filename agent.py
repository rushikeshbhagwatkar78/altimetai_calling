from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import sys
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

# Prioritize IPv4 DNS resolution to prevent Windows/ISP IPv6 WebSocket handshake timeouts
_orig_getaddrinfo = socket.getaddrinfo
def _getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _getaddrinfo_ipv4

import numpy as np
from dotenv import load_dotenv
from google.genai import types as genai_types
import livekit.api as lapi
from livekit import rtc
from livekit.agents import (
    JobContext,
    WorkerOptions,
    cli,
    llm,
)
from livekit.agents import voice
from livekit.plugins import google

from db.models import Lead, Property
from db.session import get_db_session, init_db
from services.booking_service import book_site_visit, schedule_callback as schedule_crm_callback
from services.call_service import add_call_turn_record, update_live_call_state
from services.lead_service import create_or_update_lead, mask_phone_number
from services.rag_service import search_properties_hybrid

# Load environment variables
load_dotenv()

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("gemini_live_agent")

COMPANY_NAME = os.getenv("COMPANY_NAME", "Nagpur Estates")
AGENT_DISPLAY_NAME = os.getenv("AGENT_DISPLAY_NAME", "Priya")
BENCHMARK_MODE = os.getenv("BENCHMARK_MODE", "true").lower() in ("true", "1")
MAX_CALL_DURATION_SECONDS = int(os.getenv("MAX_CALL_DURATION_SECONDS", "600"))


def calculate_percentile(data: List[float], pct: float) -> Optional[float]:
    """Calculate percentile from numeric list. Returns None if insufficient data."""
    if not data:
        return None
    sd = sorted(data)
    k = (len(sd) - 1) * (pct / 100.0)
    f = int(k)
    c = f + 1
    return sd[f] + (k - f) * (sd[c] - sd[f]) if c < len(sd) else sd[f]


# ---------------------------------------------------------------------------
# Call State Machine
# ---------------------------------------------------------------------------
class CallState(Enum):
    INITIALIZING = "initializing"
    ROOM_CONNECTED = "room_connected"
    WAITING_FOR_CUSTOMER = "waiting_for_customer"
    CUSTOMER_CONNECTED = "customer_connected"
    GREETING_STARTED = "greeting_started"
    CONVERSATION_ACTIVE = "conversation_active"
    CALL_ENDING = "call_ending"
    CALL_ENDED = "call_ended"


# ---------------------------------------------------------------------------
# Structured Lead State & Domain Representation
# ---------------------------------------------------------------------------
@dataclass
class LeadState:
    lead_id: Optional[str] = None
    customer_name: str = "Customer"
    phone_number: str = ""
    preferred_location: Optional[str] = None
    property_type: Optional[str] = None
    bhk: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    purchase_purpose: Optional[str] = None
    purchase_timeline: Optional[str] = None
    loan_required: Optional[bool] = None
    site_visit_interested: bool = False
    site_visit_datetime: Optional[str] = None
    callback_required: bool = False
    callback_datetime: Optional[str] = None
    whatsapp_followup: bool = False
    dnd_requested: bool = False
    lead_temperature: Optional[str] = "warm"
    next_action: Optional[str] = "qualify"
    matched_properties: Optional[List[Dict[str, Any]]] = None


# ---------------------------------------------------------------------------
# Consultative Sales System Prompt for Gemini 3.1 Live
# ---------------------------------------------------------------------------
def build_system_prompt(customer_name: str) -> str:
    cust_display = customer_name if customer_name and customer_name.lower() != "customer" else ""
    name_clause = f"The customer's name is {cust_display}." if cust_display else ""
    cust_ji = f"{cust_display} ji" if cust_display else "ji"

    return f"""You are {AGENT_DISPLAY_NAME}, a warm, confident, and professional virtual real-estate sales advisor calling from {COMPANY_NAME}, Nagpur's premier property advisory firm. {name_clause}

CRITICAL FIRST GREETING INSTRUCTION:
- Your very first spoken words to the customer MUST ALWAYS be your formal opening greeting:
  "Namaste {cust_ji}, main {AGENT_DISPLAY_NAME} bol rahi hoon {COMPANY_NAME} se. Aapne property enquiry ki thi. Kya abhi do minute baat ho sakti hai?"
- Whenever the call connects or the customer says "Hello", "Haan", "Kaun", "Boliye", or stays silent, your immediate first response MUST be this exact opening greeting with natural Indian enthusiasm and warmth.

Conversational Philosophy — Speak Less, Sell Consultatively:
- Keep your answers short, crisp, and conversational (usually 8–20 words, 1–2 short sentences).
- Ask strictly ONE question at a time. Never barrage the customer with multiple questions.
- Support Hindi, English, Marathi, and Hinglish with natural code-switching.
- Mirror the customer's language immediately (if Hindi, speak Hindi; if Marathi, speak warm Marathi/Hinglish; if English, speak English).
- Format Indian currency phonetically (e.g. "55 Lakhs", "60 se 70 Lakh", "1.5 Crore"). Never output numeric symbols like ₹5500000.

Sales Strategy — Follow the 6-Step Conversion Funnel:
1. DISCOVER: Briefly understand requirement (Area: Besa / Manish Nagar / Wardha Road / Sonegaon / MIHAN, BHK, Budget).
2. MATCH: Search inventory using `search_properties`.
3. VALUE: Present 1 matching project highlighting 1 key benefit (e.g. "Besa mein Greenwood Meadows mein ready 2 BHK hai 55 Lakhs mein clubhouse ke sath.").
4. CONVINCE: Address questions honestly using trusted data. Never hallucinate facts, discounts, or RERA details.
5. SITE VISIT: Propose a free site visit ("Ek baar site visit dekhna convenient rahega? Saturday ya Sunday?").
6. BOOK & CLOSE: Confirm the day & time, execute `schedule_site_visit()`, thank the customer warmly ("Perfect {cust_ji}, Saturday 11 baje site visit confirm hai. Thank you!"), then immediately execute `end_call(reason='site_visit_booked')`.

Guardrails & Call Ending:
- If customer asks if you are AI/bot: "Ji, main {COMPANY_NAME} ki virtual advisor hoon."
- If customer is busy: Offer a callback, call `create_callback()`, and call `end_call(reason='callback_scheduled')`.
- If customer is not interested / DND: Call `mark_dnd()`, say a polite goodbye, and call `end_call(reason='not_interested')`.
- Never invent property details. If unknown, say: "Main apne property specialist ko aapki requirement forward kar deti hoon."
"""


# ---------------------------------------------------------------------------
# Call Metrics Tracker (Monotonic time.perf_counter)
# ---------------------------------------------------------------------------
class CallMetricsTracker:
    """Tracks latency metrics for Gemini Live Native Audio sessions using monotonic time."""

    def __init__(self, call_id: str, room_name: str, masked_phone: str):
        self.call_id = call_id
        self.room_name = room_name
        self.masked_phone = masked_phone

        # Monotonic timestamps
        self.pc_job_received = time.perf_counter()
        self.pc_room_connected: Optional[float] = None
        self.pc_customer_connected: Optional[float] = None
        self.pc_gemini_session_started: Optional[float] = None
        self.pc_greeting_first_audio: Optional[float] = None
        self.pc_call_ended: Optional[float] = None

        self.wall_started = time.time()
        self.wall_ended: Optional[float] = None

        self.turn_count = 0
        self.interruption_count = 0
        self.turn_latencies: List[float] = []

        self.current_user_speech_end: Optional[float] = None
        self._greeting_audio_recorded = False
        self._greeting_finished = False
        self._finalized = False

    def mark_room_connected(self):
        self.pc_room_connected = time.perf_counter()
        elapsed = (self.pc_room_connected - self.pc_job_received) * 1000
        logger.info(f"ROOM_CONNECTED | call_id={self.call_id} | JOB_TO_ROOM={elapsed:.0f}ms")

    def mark_gemini_session_started(self):
        self.pc_gemini_session_started = time.perf_counter()
        elapsed = (self.pc_gemini_session_started - self.pc_job_received) * 1000
        logger.info(f"GEMINI_SESSION_STARTED | call_id={self.call_id} | t={elapsed:.0f}ms")

    def mark_customer_connected(self):
        self.pc_customer_connected = time.perf_counter()
        if self.pc_room_connected:
            elapsed = (self.pc_customer_connected - self.pc_room_connected) * 1000
            logger.info(f"CUSTOMER_CONNECTED | call_id={self.call_id} | ROOM_TO_CUSTOMER={elapsed:.0f}ms")
        else:
            logger.info(f"CUSTOMER_CONNECTED | call_id={self.call_id}")

    def mark_greeting_requested(self):
        now = time.perf_counter()
        if self.pc_customer_connected:
            latency = (now - self.pc_customer_connected) * 1000
            logger.info(f"GREETING_REQUESTED | call_id={self.call_id} | since_cust_conn={latency:.0f}ms")
        else:
            logger.info(f"GREETING_REQUESTED | call_id={self.call_id}")

    def mark_agent_speech_started(self):
        """Called when assistant audio begins playout."""
        now = time.perf_counter()

        if not self._greeting_audio_recorded and not self._greeting_finished:
            self._greeting_audio_recorded = True
            self.pc_greeting_first_audio = now
            if self.pc_customer_connected:
                latency = (now - self.pc_customer_connected) * 1000
                job_to_greeting = (now - self.pc_job_received) * 1000
                logger.info(
                    f"\n========================================\n"
                    f"GREETING FIRST AUDIO DELIVERED\n"
                    f"Customer → First Audio:  {latency:.0f}ms\n"
                    f"Total Job → First Audio: {job_to_greeting:.0f}ms\n"
                    f"========================================"
                )
            return

        if self._greeting_finished and self.current_user_speech_end:
            latency = (now - self.current_user_speech_end) * 1000
            self.turn_latencies.append(latency)
            self.turn_count += 1
            self.current_user_speech_end = None
            logger.info(f"ASSISTANT_FIRST_AUDIO | call_id={self.call_id} | turn={self.turn_count} | latency_ms={latency:.0f}")

    def mark_greeting_finished(self):
        self._greeting_finished = True

    def mark_user_speech_started(self):
        logger.info(f"USER_SPEECH_STARTED | call_id={self.call_id}")

    def mark_user_speech_ended(self):
        self.current_user_speech_end = time.perf_counter()
        logger.info(f"USER_SPEECH_ENDED | call_id={self.call_id}")

    def mark_interruption(self):
        self.interruption_count += 1
        logger.info(f"INTERRUPTION | call_id={self.call_id} | total={self.interruption_count}")

    def generate_final_report(self, lead: LeadState, call_status: str = "completed") -> Dict[str, Any]:
        """Generate and persist final call report. Guaranteed to run exactly once."""
        if self._finalized:
            return {}
        self._finalized = True

        self.pc_call_ended = time.perf_counter()
        self.wall_ended = time.time()
        duration_sec = int(self.pc_call_ended - self.pc_job_received)
        mm, ss = divmod(duration_sec, 60)

        greeting_ms: Optional[float] = None
        if self.pc_greeting_first_audio and self.pc_customer_connected:
            greeting_ms = round((self.pc_greeting_first_audio - self.pc_customer_connected) * 1000)

        avg_lat = round(sum(self.turn_latencies) / len(self.turn_latencies)) if self.turn_latencies else None
        p50 = round(calculate_percentile(self.turn_latencies, 50)) if self.turn_latencies else None
        p90 = round(calculate_percentile(self.turn_latencies, 90)) if self.turn_latencies else None
        p95 = round(calculate_percentile(self.turn_latencies, 95)) if self.turn_latencies else None
        p99 = round(calculate_percentile(self.turn_latencies, 99)) if self.turn_latencies else None

        # Build AI call summary
        loc = lead.preferred_location or "Nagpur"
        bhk_val = lead.bhk or "Property"
        budget_val = f"within ₹{lead.budget_max/100000:.0f} Lakhs" if lead.budget_max else "Budget discussed"
        summary_text = (
            f"Customer {lead.customer_name} inquired about {bhk_val} in {loc} ({budget_val}). "
            f"Lead temperature: {lead.lead_temperature}. Next action: {lead.next_action}. Outcome: {lead.next_action}."
        )

        report = {
            "call_id": self.call_id,
            "room_name": self.room_name,
            "customer_name": lead.customer_name,
            "phone_number_masked": self.masked_phone,
            "status": call_status,
            "started_at": self.wall_started,
            "ended_at": self.wall_ended,
            "duration_seconds": duration_sec,
            "greeting_latency_ms": greeting_ms,
            "avg_response_latency_ms": avg_lat,
            "p50_latency_ms": p50,
            "p90_latency_ms": p90,
            "p95_latency_ms": p95,
            "p99_latency_ms": p99,
            "turns_count": self.turn_count,
            "interruptions_count": self.interruption_count,
            "lead_temperature": lead.lead_temperature,
            "next_action": lead.next_action,
            "outcome": lead.next_action or "completed",
            "summary": summary_text,
        }

        # Persist report to Call Service & DB
        update_live_call_state(self.call_id, report)

        # Update Lead record in CRM
        if lead.phone_number:
            create_or_update_lead(
                phone_number=lead.phone_number,
                name=lead.customer_name,
                preferred_location=lead.preferred_location,
                property_type=lead.property_type,
                bhk=lead.bhk,
                budget_max=lead.budget_max,
                purchase_purpose=lead.purchase_purpose,
                purchase_timeline=lead.purchase_timeline,
                lead_temperature=lead.lead_temperature,
                stage="site_visit" if lead.site_visit_interested else ("qualified" if lead.preferred_location else "contacted"),
            )

        if BENCHMARK_MODE:
            logger.info(
                f"\n====================================================\n"
                f"NAGPUR ESTATES GEMINI LIVE BENCHMARK\n"
                f"Call ID:                       {self.call_id}\n"
                f"Duration:                      {mm:02d}:{ss:02d}\n"
                f"Greeting first audio:          {greeting_ms or 'N/A'} ms\n"
                f"Avg Turn Latency:              {avg_lat or 'N/A'} ms\n"
                f"P50 / P90:                     {p50 or 'N/A'} ms / {p90 or 'N/A'} ms\n"
                f"Lead Outcome:                  {lead.next_action}\n"
                f"===================================================="
            )

        return report


# ---------------------------------------------------------------------------
# Function Tools for Gemini 3.1 Live
# ---------------------------------------------------------------------------
def create_tools(lead_state: LeadState, call_id: str, trigger_hangup_cb: Any) -> list:
    """Create asynchronous function tools for Gemini 3.1 Live."""

    @llm.function_tool(description="Search available Nagpur Estates residential inventory using location, BHK, property type, and budget.")
    async def search_properties(
        location: str,
        property_type: str = "Flat",
        bhk: Optional[str] = None,
        budget_max: Optional[float] = None,
        query: Optional[str] = None,
    ) -> str:
        """Execute hybrid SQL + semantic RAG search across properties."""
        lead_state.preferred_location = location
        lead_state.property_type = property_type
        if bhk:
            lead_state.bhk = bhk
        if budget_max:
            lead_state.budget_max = budget_max
        lead_state.lead_temperature = "warm"
        lead_state.next_action = "property_recommendation"

        logger.info(f"TOOL_EXECUTED | search_properties | call_id={call_id} | loc={location} | bhk={bhk} | budget={budget_max}")

        rag_res = search_properties_hybrid(
            location=location,
            property_type=property_type,
            bhk=bhk,
            budget_max=budget_max,
            query_text=query or f"{bhk} in {location}",
            call_id=call_id,
            top_k=2,
        )

        matches = rag_res.get("matches", [])
        if not matches:
            return f"Currently checking inventory in {location}. Specialist will share customized layout options."

        lead_state.matched_properties = matches
        update_live_call_state(call_id, {"matched_properties": matches, "stage": "property_matched"})

        # Format concise output for Gemini
        top = matches[0]
        amenity_summary = top["amenities"].split(",")[0] if top["amenities"] else "Prime amenities"
        return (
            f"Found {top['project_name']} in {top['location']}: {top['bhk']} {top['property_type']} "
            f"priced at {top['price_display']}, {top['possession_status']}, with {amenity_summary}."
        )

    @llm.function_tool(description="Get complete trusted details for a specific property project.")
    async def get_property_details(property_id: str) -> str:
        """Retrieve verified property details from database."""
        with get_db_session() as db:
            prop = db.query(Property).filter(Property.id == property_id).first()
            if not prop:
                return "Property details currently unavailable."
            return (
                f"{prop.project_name} by {prop.builder_name} in {prop.location}. "
                f"Configuration: {prop.bhk} ({prop.carpet_area}). Price: {prop.price_display}. "
                f"RERA ID: {prop.rera_id or 'Verified'}. Amenities: {prop.amenities}."
            )

    @llm.function_tool(description="Schedule a free property site visit for interested buyers.")
    async def schedule_site_visit(
        location: str,
        preferred_datetime: str,
        property_id: Optional[str] = None,
    ) -> str:
        """Book a site visit in CRM."""
        lead_state.site_visit_interested = True
        lead_state.site_visit_datetime = preferred_datetime
        lead_state.preferred_location = location
        lead_state.lead_temperature = "hot"
        lead_state.next_action = "site_visit_booked"

        logger.info(f"TOOL_EXECUTED | schedule_site_visit | call_id={call_id} | loc={location} | dt={preferred_datetime}")

        # Persist to database
        if lead_state.lead_id:
            book_site_visit(
                lead_id=lead_state.lead_id,
                location=location,
                visit_datetime=preferred_datetime,
                property_id=property_id,
                customer_name=lead_state.customer_name,
                phone_number=lead_state.phone_number,
                salesperson=AGENT_DISPLAY_NAME,
            )

        update_live_call_state(call_id, {
            "site_visit_status": "confirmed",
            "stage": "site_visit_booked",
            "lead_temperature": "hot",
            "next_action": "site_visit_booked",
        })

        return f"Site visit successfully confirmed for {location} on {preferred_datetime}."

    @llm.function_tool(description="Schedule a callback when the customer is busy or requests to speak later.")
    async def create_callback(
        preferred_time: str,
        reason: str = "Customer requested later call",
    ) -> str:
        """Schedule a callback in CRM."""
        lead_state.callback_required = True
        lead_state.callback_datetime = preferred_time
        lead_state.next_action = "callback_scheduled"
        lead_state.lead_temperature = "warm"

        logger.info(f"TOOL_EXECUTED | create_callback | call_id={call_id} | time={preferred_time}")

        if lead_state.lead_id:
            schedule_crm_callback(
                lead_id=lead_state.lead_id,
                scheduled_at=preferred_time,
                reason=reason,
                call_id=call_id,
                customer_name=lead_state.customer_name,
                phone_number=lead_state.phone_number,
            )

        update_live_call_state(call_id, {
            "stage": "callback_scheduled",
            "next_action": "callback_scheduled",
        })

        return f"Callback successfully scheduled for {preferred_time}."

    @llm.function_tool(description="Update lead qualification state (location, budget, purpose, timeline, temperature).")
    async def update_lead(
        preferred_location: Optional[str] = None,
        property_type: Optional[str] = None,
        bhk: Optional[str] = None,
        budget_max: Optional[float] = None,
        purchase_purpose: Optional[str] = None,
        purchase_timeline: Optional[str] = None,
        lead_temperature: Optional[str] = None,
    ) -> str:
        """Update qualification criteria."""
        if preferred_location:
            lead_state.preferred_location = preferred_location
        if property_type:
            lead_state.property_type = property_type
        if bhk:
            lead_state.bhk = bhk
        if budget_max:
            lead_state.budget_max = budget_max
        if purchase_purpose:
            lead_state.purchase_purpose = purchase_purpose
        if purchase_timeline:
            lead_state.purchase_timeline = purchase_timeline
        if lead_temperature:
            lead_state.lead_temperature = lead_temperature.lower()

        logger.info(f"TOOL_EXECUTED | update_lead | call_id={call_id} | loc={preferred_location} | temp={lead_temperature}")
        return "Lead qualification updated."

    @llm.function_tool(description="Mark contact as Do Not Disturb (DND) or Not Interested when requested.")
    async def mark_dnd(
        reason: str = "Customer requested DND / Not interested",
    ) -> str:
        """Mark contact as DND."""
        lead_state.dnd_requested = True
        lead_state.lead_temperature = "not_interested"
        lead_state.next_action = "dnd"

        logger.info(f"TOOL_EXECUTED | mark_dnd | call_id={call_id} | reason={reason}")
        update_live_call_state(call_id, {
            "lead_temperature": "not_interested",
            "next_action": "dnd",
            "stage": "dnd",
        })
        return "Customer marked as DND."

    @llm.function_tool(description="Politely end the call once conversation or booking is complete.")
    async def end_call(
        reason: str = "conversation_complete",
    ) -> str:
        """Gracefully request call termination after speaking final words."""
        logger.info(f"TOOL_EXECUTED | end_call | call_id={call_id} | reason={reason}")
        trigger_hangup_cb(reason)
        return "Call ending initiated."

    return [
        search_properties,
        get_property_details,
        schedule_site_visit,
        create_callback,
        update_lead,
        mark_dnd,
        end_call,
    ]


# ---------------------------------------------------------------------------
# Worker Config Validation
# ---------------------------------------------------------------------------
def validate_worker_config():
    """Ensure required LiveKit and Google Gemini API keys are configured."""
    required = ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "GOOGLE_API_KEY"]
    missing = [v for v in required if not os.getenv(v, "").strip() or "your_" in os.getenv(v, "").lower()]
    if missing:
        logger.error(f"CONFIG_VALIDATION_FAILED | Missing: {', '.join(missing)}")
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    model = os.getenv("GEMINI_LIVE_MODEL", "").strip()
    if model != "gemini-3.1-flash-live-preview":
        raise RuntimeError(f"Invalid GEMINI_LIVE_MODEL='{model}'. Must be 'gemini-3.1-flash-live-preview'.")

    logger.info(f"CONFIG_VALIDATED | model={model}")


# ---------------------------------------------------------------------------
# Worker Entrypoint
# ---------------------------------------------------------------------------
async def entrypoint(ctx: JobContext):
    """LiveKit Agents Worker Entrypoint running Gemini 3.1 Live Native Audio."""
    validate_worker_config()
    init_db()

    call_id = ctx.job.id if ctx.job else f"call-{int(time.time())}"
    room_name = ctx.room.name if ctx.room else "unknown"

    customer_name = "Customer"
    raw_phone = "+910000000000"
    lead_id = None

    if ctx.job and ctx.job.metadata:
        try:
            meta = json.loads(ctx.job.metadata)
            customer_name = meta.get("customer_name", "Customer")
            raw_phone = meta.get("phone_number", "+910000000000")
            call_id = meta.get("call_id", call_id)
            lead_id = meta.get("lead_id")
        except Exception as e:
            logger.warning(f"METADATA_PARSE_ERROR | call_id={call_id} | error={e}")

    masked_phone = mask_phone_number(raw_phone)
    logger.info(f"CALL_STARTED | call_id={call_id} | room={room_name} | customer={customer_name} | phone={masked_phone}")

    lead_state = LeadState(lead_id=lead_id, customer_name=customer_name, phone_number=raw_phone)
    metrics = CallMetricsTracker(call_id=call_id, room_name=room_name, masked_phone=masked_phone)
    call_state = CallState.INITIALIZING
    call_status = "initiated"

    def set_state(new_state: CallState):
        nonlocal call_state
        logger.info(f"STATE_CHANGE | call_id={call_id} | {call_state.value} -> {new_state.value}")
        call_state = new_state
        update_live_call_state(call_id, {"status": new_state.value})

    # 1. Connect Room Signaling
    logger.info(f"ROOM_CONNECT_START | room={room_name}")
    await ctx.connect()
    metrics.mark_room_connected()
    set_state(CallState.ROOM_CONNECTED)

    session_closed = asyncio.Event()

    # 2. Configure Gemini Live Native Audio Model
    gemini_live_model = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview").strip()
    gemini_voice = os.getenv("GEMINI_VOICE", "Aoede").strip()
    google_api_key = os.getenv("GOOGLE_API_KEY", "").strip()

    logger.info(f"GEMINI_LIVE_INITIALIZING | model={gemini_live_model} | voice={gemini_voice}")

    # Hangup trigger callback for end_call tool
    hangup_requested = asyncio.Event()

    def request_hangup(reason: str):
        logger.info(f"HANGUP_REQUESTED | call_id={call_id} | reason={reason}")
        hangup_requested.set()

    tools = create_tools(lead_state, call_id, request_hangup)
    system_prompt = build_system_prompt(customer_name)

    realtime_model = google.realtime.RealtimeModel(
        instructions=system_prompt,
        model=gemini_live_model,
        voice=gemini_voice,
        api_key=google_api_key,
        temperature=0.6,
    )
    metrics.mark_gemini_session_started()

    # 3. Customer Connection Detection
    customer_connected = asyncio.Event()

    def is_customer_participant(participant: rtc.RemoteParticipant) -> bool:
        ident = (participant.identity or "").lower()
        if ident.startswith("agent") or ident.startswith("ai-"):
            return False
        return True

    @ctx.room.on("participant_connected")
    def on_participant_connected(participant: rtc.RemoteParticipant):
        identity = participant.identity or ""
        logger.info(f"PARTICIPANT_CONNECTED | call_id={call_id} | identity={identity}")
        if is_customer_participant(participant):
            metrics.mark_customer_connected()
            set_state(CallState.CUSTOMER_CONNECTED)
            customer_connected.set()

    for p in ctx.room.remote_participants.values():
        if is_customer_participant(p):
            logger.info(f"PARTICIPANT_ALREADY_PRESENT | call_id={call_id} | identity={p.identity}")
            metrics.mark_customer_connected()
            set_state(CallState.CUSTOMER_CONNECTED)
            customer_connected.set()
            break

    set_state(CallState.WAITING_FOR_CUSTOMER)

    # 4. Create Agent subclass with on_enter greeting trigger
    greeting_triggered = False

    class NagpurEstatesAgent(voice.Agent):
        async def on_enter(self) -> None:
            """Trigger Gemini 3.1 Live greeting upon customer pickup."""
            nonlocal greeting_triggered
            if greeting_triggered:
                return
            greeting_triggered = True

            logger.info(f"ON_ENTER | call_id={call_id} | Waiting for customer connection...")
            try:
                await asyncio.wait_for(customer_connected.wait(), timeout=25.0)
            except asyncio.TimeoutError:
                logger.warning(f"CUSTOMER_CONNECT_TIMEOUT | call_id={call_id} | Proceeding with greeting anyway")

            # Allow 1.2s for audio stream and Gemini Live WebSocket session to fully stabilize
            await asyncio.sleep(1.2)

            metrics.mark_greeting_requested()
            logger.info(f"INJECTING_GREETING_TRIGGER | call_id={call_id}")

            cust_display = customer_name if customer_name and customer_name.lower() != "customer" else ""
            cust_ji = f"{cust_display} ji" if cust_display else "ji"
            greeting_prompt = f"The call has connected to {cust_ji}. Deliver your opening greeting now: 'Namaste {cust_ji}, main {AGENT_DISPLAY_NAME} bol rahi hoon {COMPANY_NAME} se. Aapne property enquiry ki thi. Kya abhi do minute baat ho sakti hai?'"

            try:
                rt_session = getattr(self, "realtime_llm_session", None)
                if rt_session:
                    if hasattr(rt_session, "_start_new_generation"):
                        rt_session._start_new_generation()
                    if hasattr(rt_session, "_send_client_event"):
                        rt_session._send_client_event(
                            genai_types.LiveClientContent(
                                turns=[
                                    genai_types.Content(
                                        parts=[genai_types.Part(text=greeting_prompt)],
                                        role="user",
                                    )
                                ],
                                turn_complete=True,
                            )
                        )
                        logger.info(f"GREETING_TRIGGER_SENT_VIA_CLIENT_EVENT | call_id={call_id}")
                elif hasattr(self, "session") and self.session:
                    self.session.say(
                        f"Namaste {cust_ji}, main {AGENT_DISPLAY_NAME} bol rahi hoon {COMPANY_NAME} se. Aapne property enquiry ki thi. Kya abhi do minute baat ho sakti hai?",
                        allow_interruptions=True,
                    )
                    logger.info(f"GREETING_TRIGGER_SENT_VIA_SAY | call_id={call_id}")
            except Exception as e:
                logger.error(f"GREETING_TRIGGER_ERROR | call_id={call_id} | {e}", exc_info=True)

    agent = NagpurEstatesAgent(
        instructions=system_prompt,
        llm=realtime_model,
        tools=tools,
        min_endpointing_delay=0.4,
        max_endpointing_delay=2.0,
    )

    session = voice.AgentSession()

    # 5. Wire up Lifecycle & Transcript Events
    turn_counter = 0

    @session.on("close")
    def on_session_close(*args):
        logger.info(f"SESSION_CLOSED | call_id={call_id}")
        session_closed.set()

    @ctx.room.on("disconnected")
    def on_room_disconnected(*args):
        logger.info(f"ROOM_DISCONNECTED | call_id={call_id}")
        session_closed.set()

    @session.on("user_state_changed")
    def on_user_state_changed(ev):
        new_state = str(ev.new_state).lower()
        old_state = str(ev.old_state).lower()
        if "speaking" in new_state:
            metrics.mark_user_speech_started()
            if not metrics._greeting_finished:
                metrics.mark_greeting_finished()
                set_state(CallState.CONVERSATION_ACTIVE)
        elif "speaking" in old_state and "speaking" not in new_state:
            metrics.mark_user_speech_ended()

    @session.on("agent_state_changed")
    def on_agent_state_changed(ev):
        new_state = str(ev.new_state).lower()
        if "speaking" in new_state:
            metrics.mark_agent_speech_started()
            if call_state == CallState.CUSTOMER_CONNECTED:
                set_state(CallState.GREETING_STARTED)

    # Transcript recording handler
    @session.on("conversation_item_added")
    def on_conversation_item_added(ev):
        nonlocal turn_counter
        try:
            item = getattr(ev, "item", ev)
            role = str(getattr(item, "role", "unknown")).lower()
            text = (
                getattr(item, "text_content", None)
                or getattr(item, "raw_text_content", None)
                or getattr(item, "text", None)
                or ""
            )
            if not text and hasattr(item, "content"):
                text = str(item.content)

            if text and text.strip():
                turn_counter += 1
                speaker = "assistant" if ("assistant" in role or "model" in role) else "customer"
                add_call_turn_record(
                    call_id=call_id,
                    turn_number=turn_counter,
                    speaker=speaker,
                    text=text.strip(),
                    latency_ms=metrics.turn_latencies[-1] if metrics.turn_latencies and speaker == "assistant" else None,
                )
                logger.info(f"TRANSCRIPT_RECORDED | turn={turn_counter} | {speaker}: {text.strip()[:60]}")
        except Exception as err:
            logger.warning(f"TRANSCRIPT_CAPTURE_ERROR | call_id={call_id} | {err}", exc_info=True)

    # 6. Start the session and monitor call duration & hangup
    async def duration_and_hangup_watcher():
        start_time = time.time()
        while not session_closed.is_set():
            await asyncio.sleep(1.0)
            elapsed = time.time() - start_time
            update_live_call_state(call_id, {"duration_seconds": int(elapsed)})

            # Auto-hangup after MAX_CALL_DURATION
            if elapsed > MAX_CALL_DURATION_SECONDS:
                logger.info(f"MAX_CALL_DURATION_REACHED | call_id={call_id} | duration={elapsed:.0f}s")
                try:
                    await ctx.room.disconnect()
                except Exception:
                    pass
                break

            # Hangup requested by end_call tool
            if hangup_requested.is_set():
                # Allow 2.5 seconds for final assistant speech audio playout
                logger.info(f"ALLOWING_FINAL_AUDIO_DRAIN | call_id={call_id} | waiting 2.5s")
                await asyncio.sleep(2.5)
                try:
                    await ctx.room.disconnect()
                    logger.info(f"ROOM_DISCONNECTED_AFTER_DRAIN | call_id={call_id}")
                except Exception as e:
                    logger.warning(f"Room disconnect error: {e}")

                try:
                    livekit_url = os.getenv("LIVEKIT_URL")
                    api_key = os.getenv("LIVEKIT_API_KEY")
                    api_secret = os.getenv("LIVEKIT_API_SECRET")
                    lk_api = lapi.LiveKitAPI(url=livekit_url, api_key=api_key, api_secret=api_secret)
                    await lk_api.room.delete_room(lapi.DeleteRoomRequest(room=room_name))
                    await lk_api.aclose()
                    logger.info(f"LIVEKIT_ROOM_DELETED_ON_HANGUP | room={room_name}")
                except Exception as e:
                    logger.warning(f"Room delete error: {e}")
                break

        session_closed.set()

    watcher_task = asyncio.create_task(duration_and_hangup_watcher())

    try:
        call_status = "in_progress"
        set_state(CallState.CONVERSATION_ACTIVE)
        await session.start(agent, room=ctx.room)
        logger.info(f"SESSION_RUNNING | call_id={call_id}")
        await session_closed.wait()
        call_status = "completed"

    except Exception as exc:
        logger.error(f"SESSION_ERROR | call_id={call_id} | error={exc}", exc_info=True)
        call_status = "failed"
    finally:
        watcher_task.cancel()
        set_state(CallState.CALL_ENDING)
        metrics.generate_final_report(lead_state, call_status=call_status)
        set_state(CallState.CALL_ENDED)
        logger.info(f"CALL_ENDED | call_id={call_id} | room={room_name} | status={call_status}")


# ---------------------------------------------------------------------------
# Worker Launcher
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    agent_name = os.getenv("AGENT_NAME", "ai-calling-agent")
    logger.info(f"STARTING_LIVEKIT_AGENT_WORKER | agent_name={agent_name} | engine=Gemini-3.1-Live-Native-Audio")
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name=agent_name,
            load_threshold=1.0,
            num_idle_processes=0,
            port=0,
            host="127.0.0.1",
        )
    )
