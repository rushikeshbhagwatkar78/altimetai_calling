from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from db.models import Callback, Lead, LeadActivity, Property, SiteVisit
from db.session import get_db_session

logger = logging.getLogger("crm_booking")


def book_site_visit(
    lead_id: str,
    location: str,
    visit_datetime: str,
    property_id: Optional[str] = None,
    customer_name: Optional[str] = None,
    phone_number: Optional[str] = None,
    salesperson: str = "Priya",
    notes: Optional[str] = None,
    db: Optional[Session] = None,
) -> SiteVisit:
    """
    Idempotent site visit booking:
    1. Validates lead.
    2. Creates SiteVisit record.
    3. Updates Lead state (stage='site_visit', site_visit_interested=True, temperature='hot').
    4. Logs activity in CRM timeline.
    """
    def _execute(session: Session) -> SiteVisit:
        lead = session.query(Lead).filter(Lead.id == lead_id).first()
        cust_name = customer_name or (lead.name if lead else "Customer")
        phone = phone_number or (lead.phone_number if lead else "+910000000000")

        # Prevent duplicate identical bookings within the same hour
        existing = (
            session.query(SiteVisit)
            .filter(
                SiteVisit.lead_id == lead_id,
                SiteVisit.location == location,
                SiteVisit.visit_datetime == visit_datetime,
                SiteVisit.status.in_(["requested", "confirmed"]),
            )
            .first()
        )
        if existing:
            logger.info(f"SITE_VISIT_EXISTS | lead_id={lead_id} | id={existing.id}")
            return existing

        visit = SiteVisit(
            lead_id=lead_id,
            property_id=property_id,
            customer_name=cust_name,
            phone_number=phone,
            location=location,
            visit_datetime=visit_datetime,
            status="confirmed",
            assigned_salesperson=salesperson,
            notes=notes,
        )
        session.add(visit)

        if lead:
            lead.stage = "site_visit"
            lead.site_visit_interested = True
            lead.lead_temperature = "hot"

            activity = LeadActivity(
                lead_id=lead.id,
                activity_type="site_visit_booked",
                description=f"Site visit confirmed for {location} on {visit_datetime}.",
                metadata_json=json.dumps({"location": location, "datetime": visit_datetime, "salesperson": salesperson}),
            )
            session.add(activity)

        session.commit()
        session.refresh(visit)
        logger.info(f"SITE_VISIT_BOOKED | id={visit.id} | lead_id={lead_id} | dt={visit_datetime}")
        return visit

    if db:
        return _execute(db)
    with get_db_session() as session:
        return _execute(session)


def schedule_callback(
    lead_id: str,
    scheduled_at: str,
    reason: str = "Customer requested callback",
    call_id: Optional[str] = None,
    customer_name: Optional[str] = None,
    phone_number: Optional[str] = None,
    assigned_to: str = "Priya",
    db: Optional[Session] = None,
) -> Callback:
    """Schedule a callback in the CRM."""
    def _execute(session: Session) -> Callback:
        lead = session.query(Lead).filter(Lead.id == lead_id).first()
        cust_name = customer_name or (lead.name if lead else "Customer")
        phone = phone_number or (lead.phone_number if lead else "+910000000000")

        cb = Callback(
            lead_id=lead_id,
            call_id=call_id,
            customer_name=cust_name,
            phone_number=phone,
            scheduled_at=scheduled_at,
            reason=reason,
            status="pending",
            assigned_to=assigned_to,
        )
        session.add(cb)

        if lead:
            lead.callback_required = True
            activity = LeadActivity(
                lead_id=lead.id,
                activity_type="callback_scheduled",
                description=f"Callback scheduled for {scheduled_at}. Reason: {reason}",
                metadata_json=json.dumps({"scheduled_at": scheduled_at, "reason": reason}),
            )
            session.add(activity)

        session.commit()
        session.refresh(cb)
        logger.info(f"CALLBACK_SCHEDULED | id={cb.id} | lead_id={lead_id} | time={scheduled_at}")
        return cb

    if db:
        return _execute(db)
    with get_db_session() as session:
        return _execute(session)


def get_site_visits_list() -> List[Dict[str, Any]]:
    """Retrieve all site visits for CRM calendar & list views."""
    with get_db_session() as db:
        visits = db.query(SiteVisit).order_by(SiteVisit.created_at.desc()).all()
        return [
            {
                "id": v.id,
                "lead_id": v.lead_id,
                "customer_name": v.customer_name,
                "phone_number": v.phone_number,
                "location": v.location,
                "visit_datetime": v.visit_datetime,
                "status": v.status,
                "salesperson": v.assigned_salesperson,
                "notes": v.notes,
                "created_at": v.created_at.isoformat(),
            }
            for v in visits
        ]


def get_callbacks_list(status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve callbacks list for CRM follow-ups view."""
    with get_db_session() as db:
        q = db.query(Callback)
        if status_filter and status_filter.lower() != "all":
            q = q.filter(Callback.status == status_filter.lower())
        cbs = q.order_by(Callback.created_at.desc()).all()
        return [
            {
                "id": cb.id,
                "lead_id": cb.lead_id,
                "call_id": cb.call_id,
                "customer_name": cb.customer_name,
                "phone_number": cb.phone_number,
                "scheduled_at": cb.scheduled_at,
                "reason": cb.reason,
                "status": cb.status,
                "assigned_to": cb.assigned_to,
                "created_at": cb.created_at.isoformat(),
            }
            for cb in cbs
        ]
