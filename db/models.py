from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    Enum,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True, default=lambda: f"usr_{uuid.uuid4().hex[:10]}")
    email = Column(String(128), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    role = Column(String(32), default="sales_agent", nullable=False)  # admin, sales_manager, sales_agent
    password_hash = Column(String(256), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Lead(Base):
    __tablename__ = "leads"

    id = Column(String(64), primary_key=True, default=lambda: f"lead_{uuid.uuid4().hex[:10]}")
    name = Column(String(128), default="Customer", nullable=False, index=True)
    phone_number = Column(String(32), nullable=False, index=True)
    masked_phone = Column(String(32), nullable=False)
    
    # Requirements
    preferred_location = Column(String(128), nullable=True, index=True)  # Besa, Manish Nagar, Wardha Road, etc.
    property_type = Column(String(64), nullable=True, index=True)  # Flat, Plot, Bungalow, Commercial
    bhk = Column(String(16), nullable=True)  # 1, 2, 3, 4
    budget_min = Column(Float, nullable=True)
    budget_max = Column(Float, nullable=True, index=True)
    purchase_purpose = Column(String(64), nullable=True)  # Self-use, Investment
    purchase_timeline = Column(String(64), nullable=True)  # Immediate, 1-3 months, Diwali, Next year
    loan_required = Column(Boolean, nullable=True)
    
    # Qualification & Pipeline State
    lead_temperature = Column(String(32), default="warm", index=True)  # hot, warm, cold, not_interested
    stage = Column(String(64), default="new", index=True)  # new, contacted, qualified, property_matched, site_visit, won, lost, dnd
    assigned_agent = Column(String(128), default="Priya", nullable=False)
    
    # Operational flags
    site_visit_interested = Column(Boolean, default=False)
    callback_required = Column(Boolean, default=False)
    dnd_requested = Column(Boolean, default=False, index=True)
    whatsapp_followup = Column(Boolean, default=False)
    
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    lead_notes = relationship("LeadNote", back_populates="lead", cascade="all, delete-orphan", order_by="desc(LeadNote.created_at)")
    activities = relationship("LeadActivity", back_populates="lead", cascade="all, delete-orphan", order_by="desc(LeadActivity.created_at)")
    calls = relationship("CallRecord", back_populates="lead", cascade="all, delete-orphan", order_by="desc(CallRecord.created_at)")
    site_visits = relationship("SiteVisit", back_populates="lead", cascade="all, delete-orphan", order_by="desc(SiteVisit.created_at)")
    callbacks = relationship("Callback", back_populates="lead", cascade="all, delete-orphan", order_by="desc(Callback.created_at)")


class LeadNote(Base):
    __tablename__ = "lead_notes"

    id = Column(String(64), primary_key=True, default=lambda: f"note_{uuid.uuid4().hex[:10]}")
    lead_id = Column(String(64), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(64), nullable=True)
    author_name = Column(String(128), default="Agent", nullable=False)
    note = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    lead = relationship("Lead", back_populates="lead_notes")


class LeadActivity(Base):
    __tablename__ = "lead_activities"

    id = Column(String(64), primary_key=True, default=lambda: f"act_{uuid.uuid4().hex[:10]}")
    lead_id = Column(String(64), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_type = Column(String(64), nullable=False)  # lead_created, call_completed, site_visit_booked, note_added, stage_changed, etc.
    description = Column(String(256), nullable=False)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    lead = relationship("Lead", back_populates="activities")


class Property(Base):
    __tablename__ = "properties"

    id = Column(String(64), primary_key=True, default=lambda: f"prop_{uuid.uuid4().hex[:10]}")
    project_name = Column(String(128), nullable=False, index=True)
    location = Column(String(128), nullable=False, index=True)  # Besa, Manish Nagar, Wardha Road, Sonegaon, MIHAN, Civil Lines, etc.
    property_type = Column(String(64), nullable=False, index=True)  # Flat, Plot, Luxury Apartment, Bungalow, Commercial
    bhk = Column(String(16), nullable=True, index=True)  # 1 BHK, 2 BHK, 3 BHK, 4 BHK, Plot
    price_min = Column(Float, nullable=False, index=True)
    price_max = Column(Float, nullable=False, index=True)
    price_display = Column(String(64), nullable=False)  # e.g. "₹55 L - ₹65 L"
    carpet_area = Column(String(64), nullable=True)  # e.g. "1050 - 1350 sq.ft."
    possession_status = Column(String(64), default="Ready to Move", nullable=False)  # Ready to Move, Under Construction (Diwali 2026)
    rera_id = Column(String(64), nullable=True)
    builder_name = Column(String(128), default="Nagpur Estates Partner", nullable=False)
    description = Column(Text, nullable=False)
    amenities = Column(Text, nullable=True)  # Comma-separated or JSON string
    available_units = Column(Integer, default=5, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(String(64), primary_key=True, default=lambda: f"doc_{uuid.uuid4().hex[:10]}")
    filename = Column(String(256), nullable=False)
    document_type = Column(String(32), nullable=False)  # pdf, docx, txt, md, csv
    status = Column(String(32), default="uploaded", nullable=False)  # uploaded, indexing, indexed, failed
    chunk_count = Column(Integer, default=0, nullable=False)
    vector_count = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    chunks = relationship("KnowledgeChunk", back_populates="document", cascade="all, delete-orphan")


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id = Column(String(64), primary_key=True, default=lambda: f"chk_{uuid.uuid4().hex[:10]}")
    document_id = Column(String(64), ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=True)
    # Stored as JSON string or text for vector values (compatible across SQLite and PostgreSQL)
    embedding_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    document = relationship("KnowledgeDocument", back_populates="chunks")


class CallRecord(Base):
    __tablename__ = "calls"

    id = Column(String(64), primary_key=True, default=lambda: f"call_{uuid.uuid4().hex[:10]}")
    call_id = Column(String(64), unique=True, nullable=False, index=True)
    room_name = Column(String(64), nullable=False, index=True)
    lead_id = Column(String(64), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_name = Column(String(128), default="Customer", nullable=False)
    phone_number_masked = Column(String(32), nullable=False)
    dispatch_id = Column(String(64), nullable=True)
    sip_call_id = Column(String(64), nullable=True)
    status = Column(String(32), default="initiated", nullable=False)  # initiating, ringing, in_progress, completed, failed, cancelled, busy, no_answer
    
    duration_seconds = Column(Integer, default=0, nullable=False)
    greeting_latency_ms = Column(Float, nullable=True)
    avg_response_latency_ms = Column(Float, nullable=True)
    p50_latency_ms = Column(Float, nullable=True)
    p90_latency_ms = Column(Float, nullable=True)
    p95_latency_ms = Column(Float, nullable=True)
    p99_latency_ms = Column(Float, nullable=True)
    
    turns_count = Column(Integer, default=0, nullable=False)
    interruptions_count = Column(Integer, default=0, nullable=False)
    lead_temperature = Column(String(32), nullable=True)
    next_action = Column(String(64), nullable=True)
    outcome = Column(String(64), nullable=True)  # site_visit_booked, callback_required, property_shared, not_interested, dnd, wrong_number, completed
    summary = Column(Text, nullable=True)
    
    started_at = Column(Float, nullable=True)
    ended_at = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    lead = relationship("Lead", back_populates="calls")
    turns = relationship("CallTurn", back_populates="call", cascade="all, delete-orphan", order_by="CallTurn.turn_number")
    events = relationship("CallEvent", back_populates="call", cascade="all, delete-orphan", order_by="CallEvent.timestamp")


class CallTurn(Base):
    __tablename__ = "call_turns"

    id = Column(String(64), primary_key=True, default=lambda: f"turn_{uuid.uuid4().hex[:10]}")
    call_id = Column(String(64), ForeignKey("calls.call_id", ondelete="CASCADE"), nullable=False, index=True)
    turn_number = Column(Integer, nullable=False)
    speaker = Column(String(16), nullable=False)  # assistant, customer
    text = Column(Text, nullable=False)
    latency_ms = Column(Float, nullable=True)
    interrupted = Column(Boolean, default=False, nullable=False)
    timestamp = Column(Float, default=time.time, nullable=False)

    call = relationship("CallRecord", back_populates="turns")


class CallEvent(Base):
    __tablename__ = "call_events"

    id = Column(String(64), primary_key=True, default=lambda: f"ev_{uuid.uuid4().hex[:10]}")
    call_id = Column(String(64), ForeignKey("calls.call_id", ondelete="CASCADE"), nullable=False, index=True)
    event_name = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=True)
    timestamp = Column(Float, default=time.time, nullable=False)

    call = relationship("CallRecord", back_populates="events")


class SiteVisit(Base):
    __tablename__ = "site_visits"

    id = Column(String(64), primary_key=True, default=lambda: f"sv_{uuid.uuid4().hex[:10]}")
    lead_id = Column(String(64), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    property_id = Column(String(64), ForeignKey("properties.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_name = Column(String(128), nullable=False)
    phone_number = Column(String(32), nullable=False)
    location = Column(String(128), nullable=False)
    visit_datetime = Column(String(128), nullable=False)  # e.g. "Saturday 11:00 AM" or ISO
    status = Column(String(32), default="requested", nullable=False)  # requested, confirmed, completed, cancelled, rescheduled, no_show
    assigned_salesperson = Column(String(128), default="Priya", nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    lead = relationship("Lead", back_populates="site_visits")
    property = relationship("Property")


class Callback(Base):
    __tablename__ = "callbacks"

    id = Column(String(64), primary_key=True, default=lambda: f"cb_{uuid.uuid4().hex[:10]}")
    lead_id = Column(String(64), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    call_id = Column(String(64), nullable=True)
    customer_name = Column(String(128), nullable=False)
    phone_number = Column(String(32), nullable=False)
    scheduled_at = Column(String(128), nullable=False)  # e.g. "Tomorrow 10:00 AM" or ISO
    reason = Column(String(256), default="Customer requested later call", nullable=False)
    status = Column(String(32), default="pending", nullable=False)  # pending, completed, missed, cancelled
    assigned_to = Column(String(128), default="Priya", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    lead = relationship("Lead", back_populates="callbacks")
