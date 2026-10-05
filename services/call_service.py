from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

import livekit.api as lapi
from livekit.protocol import sip as sip_proto
from sqlalchemy.orm import Session

from db.models import CallEvent, CallRecord, CallTurn, Lead, LeadActivity
from db.session import get_db_session
from services.lead_service import mask_phone_number, normalize_phone_e164

logger = logging.getLogger("crm_calls")

# In-memory real-time state for live calls: call_id -> dict
LIVE_CALL_REGISTRY: Dict[str, Dict[str, Any]] = {}
IDEMPOTENCY_CACHE: Dict[str, Dict[str, Any]] = {}


async def initiate_outbound_call(
    phone_number: str,
    customer_name: str = "Customer",
    lead_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Initiate Outbound Call via LiveKit Cloud SIP Trunk:
    1. Validates and normalizes phone number to E.164 format.
    2. Prevents simultaneous duplicate active calls.
    3. Persists initial CallRecord in database.
    4. Creates LiveKit room, dispatches Agent Worker, and triggers SIP outbound participant.
    """
    norm_phone = normalize_phone_e164(phone_number)
    masked_phone = mask_phone_number(norm_phone)

    # Check idempotency
    if idempotency_key and idempotency_key in IDEMPOTENCY_CACHE:
        logger.info(f"IDEMPOTENT_CALL_SERVED | key={idempotency_key}")
        return IDEMPOTENCY_CACHE[idempotency_key]

    # Prevent simultaneous active calls to same number
    for cid, cinfo in LIVE_CALL_REGISTRY.items():
        if cinfo.get("phone_number") == norm_phone and cinfo.get("status") in ("initiating", "ringing", "in_progress"):
            raise RuntimeError(f"An active call to {masked_phone} is already in progress (Call ID: {cid}).")

    room_name = f"call-{uuid.uuid4().hex[:8]}"
    call_id = room_name

    trunk_id = os.getenv("LIVEKIT_SIP_OUTBOUND_TRUNK_ID") or os.getenv("LIVEKIT_SIP_TRUNK_ID")
    agent_name = os.getenv("AGENT_NAME", "ai-calling-agent")
    livekit_url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not trunk_id or not livekit_url or not api_key:
        raise RuntimeError("LiveKit credentials or SIP trunk ID is not configured.")

    # 1. Look up or auto-link Lead ID
    with get_db_session() as db:
        lead = None
        if lead_id:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            lead = db.query(Lead).filter(Lead.phone_number == norm_phone).first()
        if not lead:
            lead = Lead(
                name=customer_name or "Customer",
                phone_number=norm_phone,
                masked_phone=masked_phone,
                assigned_agent="Priya",
                stage="contacted",
            )
            db.add(lead)
            db.flush()

        actual_lead_id = lead.id

        # 2. Persist CallRecord in database
        call_rec = CallRecord(
            call_id=call_id,
            room_name=room_name,
            lead_id=actual_lead_id,
            customer_name=customer_name or lead.name,
            phone_number_masked=masked_phone,
            status="initiating",
            started_at=time.time(),
        )
        db.add(call_rec)

        # Log lead activity
        act = LeadActivity(
            lead_id=actual_lead_id,
            activity_type="call_started",
            description=f"Outbound AI call initiated to {masked_phone} (Call ID: {call_id}).",
            metadata_json=json.dumps({"call_id": call_id, "room": room_name}),
        )
        db.add(act)
        db.commit()

    # 3. Create LiveKit API Client
    lk_api = lapi.LiveKitAPI(url=livekit_url, api_key=api_key, api_secret=api_secret)

    try:
        # Step A: Dispatch Agent worker
        metadata_payload = json.dumps({
            "call_id": call_id,
            "customer_name": customer_name,
            "phone_number": norm_phone,
            "room_name": room_name,
            "lead_id": actual_lead_id,
        })

        dispatch_req = lapi.CreateAgentDispatchRequest(
            agent_name=agent_name,
            room=room_name,
            metadata=metadata_payload,
        )
        dispatch_info = await lk_api.agent_dispatch.create_dispatch(dispatch_req)
        dispatch_id = getattr(dispatch_info, "id", None)
        logger.info(f"AGENT_DISPATCHED | room={room_name} | dispatch_id={dispatch_id}")

        # Step B: Create Outbound SIP Participant
        sip_req = sip_proto.CreateSIPParticipantRequest(
            sip_trunk_id=trunk_id,
            sip_call_to=norm_phone,
            room_name=room_name,
            participant_identity=f"sip-{norm_phone}",
            participant_name=customer_name,
            participant_attributes={
                "customer_name": customer_name,
                "phone_number": norm_phone,
                "call_id": call_id,
                "lead_id": actual_lead_id,
            },
        )
        sip_info = await lk_api.sip.create_sip_participant(sip_req)
        sip_call_id = getattr(sip_info, "sip_call_id", None) or getattr(sip_info, "participant_id", None)
        logger.info(f"SIP_PARTICIPANT_CREATED | room={room_name} | trunk={trunk_id} | sip_id={sip_call_id}")

        # Record in live registry
        live_record = {
            "call_id": call_id,
            "room_name": room_name,
            "lead_id": actual_lead_id,
            "phone_number": norm_phone,
            "phone_number_masked": masked_phone,
            "customer_name": customer_name,
            "dispatch_id": dispatch_id,
            "sip_call_id": sip_call_id,
            "status": "initiating",
            "stage": "connecting",
            "duration_seconds": 0,
            "turns": [],
            "started_at": time.time(),
            "lead_temperature": "warm",
            "matched_properties": [],
            "site_visit_status": None,
        }
        LIVE_CALL_REGISTRY[call_id] = live_record

        # Update DB record with dispatch and SIP IDs
        with get_db_session() as db:
            c = db.query(CallRecord).filter(CallRecord.call_id == call_id).first()
            if c:
                c.dispatch_id = dispatch_id
                c.sip_call_id = sip_call_id
                db.commit()

        if idempotency_key:
            IDEMPOTENCY_CACHE[idempotency_key] = live_record

        return live_record

    except Exception as e:
        logger.error(f"CALL_INITIATION_ERROR | room={room_name} | error={e}", exc_info=True)
        with get_db_session() as db:
            c = db.query(CallRecord).filter(CallRecord.call_id == call_id).first()
            if c:
                c.status = "failed"
                c.outcome = f"Error: {str(e)}"
                db.commit()
        raise
    finally:
        await lk_api.aclose()


def update_live_call_state(call_id: str, updates: Dict[str, Any]):
    """Update live in-memory and database state for an active call."""
    if call_id in LIVE_CALL_REGISTRY:
        LIVE_CALL_REGISTRY[call_id].update(updates)

    # Sync critical state to DB
    with get_db_session() as db:
        c = db.query(CallRecord).filter(CallRecord.call_id == call_id).first()
        if c:
            if "status" in updates:
                c.status = updates["status"]
            if "duration_seconds" in updates:
                c.duration_seconds = updates["duration_seconds"]
            if "outcome" in updates:
                c.outcome = updates["outcome"]
            if "summary" in updates:
                c.summary = updates["summary"]
            if "greeting_latency_ms" in updates:
                c.greeting_latency_ms = updates["greeting_latency_ms"]
            if "avg_response_latency_ms" in updates:
                c.avg_response_latency_ms = updates["avg_response_latency_ms"]
            if "p50_latency_ms" in updates:
                c.p50_latency_ms = updates["p50_latency_ms"]
            if "p90_latency_ms" in updates:
                c.p90_latency_ms = updates["p90_latency_ms"]
            if "turns_count" in updates:
                c.turns_count = updates["turns_count"]
            if "lead_temperature" in updates:
                c.lead_temperature = updates["lead_temperature"]
            if "next_action" in updates:
                c.next_action = updates["next_action"]
            db.commit()


def add_call_turn_record(
    call_id: str,
    turn_number: int,
    speaker: str,
    text: str,
    latency_ms: Optional[float] = None,
    interrupted: bool = False,
):
    """Add a speaker turn to live registry and database."""
    turn_data = {
        "turn_number": turn_number,
        "speaker": speaker,
        "text": text,
        "latency_ms": latency_ms,
        "interrupted": interrupted,
        "timestamp": time.time(),
    }

    if call_id in LIVE_CALL_REGISTRY:
        LIVE_CALL_REGISTRY[call_id]["turns"].append(turn_data)

    with get_db_session() as db:
        t = CallTurn(
            call_id=call_id,
            turn_number=turn_number,
            speaker=speaker,
            text=text,
            latency_ms=latency_ms,
            interrupted=interrupted,
            timestamp=time.time(),
        )
        db.add(t)
        db.commit()


def get_live_call_status(call_id: str) -> Dict[str, Any]:
    """Retrieve real-time call status and turns from database across processes."""
    with get_db_session() as db:
        c = db.query(CallRecord).filter(CallRecord.call_id == call_id).first()
        if not c:
            if call_id in LIVE_CALL_REGISTRY:
                return LIVE_CALL_REGISTRY[call_id]
            raise KeyError(f"Call ID {call_id} not found.")

        turns = [
            {
                "turn_number": t.turn_number,
                "speaker": t.speaker,
                "text": t.text,
                "latency_ms": t.latency_ms,
                "interrupted": t.interrupted,
                "timestamp": t.timestamp,
            }
            for t in c.turns
        ]

        duration = c.duration_seconds
        if c.status in ("initiating", "in_progress", "conversation_active", "customer_connected") and c.started_at:
            duration = int(time.time() - c.started_at)

        stage = "Active"
        if c.outcome:
            stage = c.outcome
        elif c.status == "customer_connected":
            stage = "Greeting"

        return {
            "call_id": c.call_id,
            "room_name": c.room_name,
            "lead_id": c.lead_id,
            "phone_number_masked": c.phone_number_masked,
            "customer_name": c.customer_name,
            "status": c.status,
            "stage": stage,
            "duration_seconds": duration,
            "greeting_latency_ms": c.greeting_latency_ms,
            "avg_response_latency_ms": c.avg_response_latency_ms,
            "turns": turns,
            "lead_temperature": c.lead_temperature or "warm",
            "next_action": c.next_action,
            "outcome": c.outcome,
            "summary": c.summary,
        }


async def terminate_call(call_id: str) -> Dict[str, Any]:
    """Terminate an active call room in LiveKit."""
    livekit_url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    room_name = call_id
    if call_id in LIVE_CALL_REGISTRY:
        room_name = LIVE_CALL_REGISTRY[call_id].get("room_name", call_id)
        LIVE_CALL_REGISTRY[call_id]["status"] = "cancelled"

    lk_api = lapi.LiveKitAPI(url=livekit_url, api_key=api_key, api_secret=api_secret)
    try:
        await lk_api.room.delete_room(lapi.DeleteRoomRequest(room=room_name))
        logger.info(f"CALL_TERMINATED | call_id={call_id} | room={room_name}")
        with get_db_session() as db:
            c = db.query(CallRecord).filter(CallRecord.call_id == call_id).first()
            if c:
                c.status = "cancelled"
                db.commit()
        return {"status": "terminated", "call_id": call_id}
    except Exception as e:
        logger.warning(f"Error terminating call {call_id}: {e}")
        return {"status": "already_closed", "call_id": call_id}
    finally:
        await lk_api.aclose()
