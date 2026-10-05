from __future__ import annotations

import csv
import io
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from db.models import Lead, LeadActivity, LeadNote
from db.session import get_db_session

logger = logging.getLogger("crm_leads")


def mask_phone_number(phone: str) -> str:
    """Mask phone number for safe logging & UI display."""
    cleaned = phone.strip()
    if len(cleaned) <= 6:
        return "****"
    return f"{cleaned[:6]}****{cleaned[-2:]}"


def normalize_phone_e164(phone: str) -> str:
    """Normalize Indian and international phone numbers to E.164 format."""
    cleaned = re.sub(r"[\s\-\(\)]", "", phone.strip())
    if re.match(r"^[6-9]\d{9}$", cleaned):
        cleaned = f"+91{cleaned}"
    elif re.match(r"^0[6-9]\d{9}$", cleaned):
        cleaned = f"+91{cleaned[1:]}"
    elif not cleaned.startswith("+") and re.match(r"^\d{10,14}$", cleaned):
        cleaned = f"+{cleaned}"
    return cleaned


def create_or_update_lead(
    phone_number: str,
    name: str = "Customer",
    preferred_location: Optional[str] = None,
    property_type: Optional[str] = None,
    bhk: Optional[str] = None,
    budget_min: Optional[float] = None,
    budget_max: Optional[float] = None,
    purchase_purpose: Optional[str] = None,
    purchase_timeline: Optional[str] = None,
    lead_temperature: Optional[str] = None,
    stage: Optional[str] = None,
    assigned_agent: str = "Priya",
    notes: Optional[str] = None,
    db: Optional[Session] = None,
) -> Lead:
    """Create a new lead or update an existing lead by phone number."""
    norm_phone = normalize_phone_e164(phone_number)
    masked = mask_phone_number(norm_phone)

    def _execute(session: Session) -> Lead:
        lead = session.query(Lead).filter(Lead.phone_number == norm_phone).first()
        is_new = False
        if not lead:
            is_new = True
            lead = Lead(
                name=name or "Customer",
                phone_number=norm_phone,
                masked_phone=masked,
                assigned_agent=assigned_agent,
            )
            session.add(lead)
            session.flush()

        # Update attributes
        if name and name != "Customer":
            lead.name = name
        if preferred_location:
            lead.preferred_location = preferred_location
        if property_type:
            lead.property_type = property_type
        if bhk:
            lead.bhk = bhk
        if budget_min is not None:
            lead.budget_min = budget_min
        if budget_max is not None:
            lead.budget_max = budget_max
        if purchase_purpose:
            lead.purchase_purpose = purchase_purpose
        if purchase_timeline:
            lead.purchase_timeline = purchase_timeline
        if lead_temperature:
            lead.lead_temperature = lead_temperature.lower()
        if stage:
            lead.stage = stage.lower()
        if notes:
            lead.notes = notes

        # Log activity
        activity_type = "lead_created" if is_new else "lead_updated"
        desc = f"Lead {'created' if is_new else 'updated'} via CRM."
        activity = LeadActivity(
            lead_id=lead.id,
            activity_type=activity_type,
            description=desc,
            metadata_json=json.dumps({"stage": lead.stage, "temperature": lead.lead_temperature}),
        )
        session.add(activity)
        session.commit()
        session.refresh(lead)
        return lead

    if db:
        return _execute(db)
    with get_db_session() as session:
        return _execute(session)


def get_leads_filtered(
    search: Optional[str] = None,
    stage: Optional[str] = None,
    temperature: Optional[str] = None,
    location: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """Retrieve filtered and paginated lead records."""
    with get_db_session() as db:
        q = db.query(Lead)

        if search:
            s = f"%{search.strip()}%"
            q = q.filter(or_(Lead.name.ilike(s), Lead.phone_number.ilike(s), Lead.preferred_location.ilike(s)))

        if stage and stage.lower() != "all":
            q = q.filter(Lead.stage == stage.lower())

        if temperature and temperature.lower() != "all":
            q = q.filter(Lead.lead_temperature == temperature.lower())

        if location and location.lower() != "all":
            q = q.filter(Lead.preferred_location.ilike(f"%{location.strip()}%"))

        total = q.count()
        leads = q.order_by(Lead.updated_at.desc()).offset(offset).limit(limit).all()

        lead_list = []
        for l in leads:
            lead_list.append({
                "id": l.id,
                "name": l.name,
                "phone_number": l.phone_number,
                "masked_phone": l.masked_phone,
                "preferred_location": l.preferred_location,
                "property_type": l.property_type,
                "bhk": l.bhk,
                "budget_min": l.budget_min,
                "budget_max": l.budget_max,
                "budget_display": f"₹{l.budget_max/100000:.0f} L" if l.budget_max else "N/A",
                "purchase_purpose": l.purchase_purpose,
                "purchase_timeline": l.purchase_timeline,
                "lead_temperature": l.lead_temperature,
                "stage": l.stage,
                "assigned_agent": l.assigned_agent,
                "site_visit_interested": l.site_visit_interested,
                "callback_required": l.callback_required,
                "dnd_requested": l.dnd_requested,
                "notes": l.notes,
                "created_at": l.created_at.isoformat() if l.created_at else None,
                "updated_at": l.updated_at.isoformat() if l.updated_at else None,
            })

        return {"total": total, "leads": lead_list}


def get_lead_detail(lead_id: str) -> Optional[Dict[str, Any]]:
    """Get full lead profile with notes, activities, calls, and site visits."""
    with get_db_session() as db:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return None

        notes = [
            {
                "id": n.id,
                "author": n.author_name,
                "note": n.note,
                "created_at": n.created_at.isoformat(),
            }
            for n in lead.lead_notes
        ]

        activities = [
            {
                "id": a.id,
                "type": a.activity_type,
                "description": a.description,
                "metadata": json.loads(a.metadata_json or "{}"),
                "created_at": a.created_at.isoformat(),
            }
            for a in lead.activities
        ]

        calls = [
            {
                "id": c.id,
                "call_id": c.call_id,
                "status": c.status,
                "duration_seconds": c.duration_seconds,
                "greeting_latency_ms": c.greeting_latency_ms,
                "avg_response_latency_ms": c.avg_response_latency_ms,
                "turns_count": c.turns_count,
                "outcome": c.outcome,
                "summary": c.summary,
                "created_at": c.created_at.isoformat(),
            }
            for c in lead.calls
        ]

        site_visits = [
            {
                "id": sv.id,
                "location": sv.location,
                "visit_datetime": sv.visit_datetime,
                "status": sv.status,
                "salesperson": sv.assigned_salesperson,
                "notes": sv.notes,
                "created_at": sv.created_at.isoformat(),
            }
            for sv in lead.site_visits
        ]

        return {
            "id": lead.id,
            "name": lead.name,
            "phone_number": lead.phone_number,
            "masked_phone": lead.masked_phone,
            "preferred_location": lead.preferred_location,
            "property_type": lead.property_type,
            "bhk": lead.bhk,
            "budget_min": lead.budget_min,
            "budget_max": lead.budget_max,
            "budget_display": f"₹{lead.budget_max/100000:.0f} L" if lead.budget_max else "N/A",
            "purchase_purpose": lead.purchase_purpose,
            "purchase_timeline": lead.purchase_timeline,
            "loan_required": lead.loan_required,
            "lead_temperature": lead.lead_temperature,
            "stage": lead.stage,
            "assigned_agent": lead.assigned_agent,
            "site_visit_interested": lead.site_visit_interested,
            "callback_required": lead.callback_required,
            "dnd_requested": lead.dnd_requested,
            "notes": lead.notes,
            "created_at": lead.created_at.isoformat(),
            "updated_at": lead.updated_at.isoformat(),
            "lead_notes": notes,
            "activities": activities,
            "calls": calls,
            "site_visits": site_visits,
        }


def add_lead_note(lead_id: str, note_text: str, author_name: str = "Agent") -> LeadNote:
    """Add a CRM note to a lead record."""
    with get_db_session() as db:
        note = LeadNote(
            lead_id=lead_id,
            author_name=author_name,
            note=note_text.strip(),
        )
        db.add(note)
        activity = LeadActivity(
            lead_id=lead_id,
            activity_type="note_added",
            description=f"Note added by {author_name}: {note_text[:40]}...",
        )
        db.add(activity)
        db.commit()
        db.refresh(note)
        return note


def import_leads_from_csv(csv_content: str) -> Dict[str, Any]:
    """Import leads from CSV text with deduplication."""
    reader = csv.DictReader(io.StringIO(csv_content))
    imported = 0
    skipped = 0
    errors = []

    with get_db_session() as db:
        for idx, row in enumerate(reader):
            try:
                phone = row.get("phone") or row.get("phone_number") or row.get("mobile")
                if not phone:
                    skipped += 1
                    continue
                name = row.get("name") or row.get("customer_name") or "Customer"
                loc = row.get("location") or row.get("preferred_location")
                ptype = row.get("property_type") or row.get("type")
                bhk = row.get("bhk")
                budget = float(row.get("budget") or row.get("budget_max") or 0) or None
                notes = row.get("notes")

                create_or_update_lead(
                    phone_number=phone,
                    name=name,
                    preferred_location=loc,
                    property_type=ptype,
                    bhk=bhk,
                    budget_max=budget,
                    notes=notes,
                    db=db,
                )
                imported += 1
            except Exception as e:
                skipped += 1
                errors.append(f"Row {idx+1}: {e}")

    return {"imported": imported, "skipped": skipped, "errors": errors}
