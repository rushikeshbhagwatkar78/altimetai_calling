from __future__ import annotations

import hashlib
import logging
import os
import secrets
from contextlib import contextmanager
from typing import Generator, Optional, Tuple

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base, Lead, Property, User

load_dotenv()
logger = logging.getLogger("crm_db")

def hash_password(password: str, salt: Optional[str] = None) -> str:
    """Hash password using PBKDF2 HMAC SHA-256 with salt."""
    if not salt:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return f"{salt}${key.hex()}"

def verify_password(password: str, stored_hash: str) -> bool:
    """Verify plain password against stored salt$hash string."""
    try:
        if "$" not in stored_hash:
            return False
        salt, key_hex = stored_hash.split("$", 1)
        expected_key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
        return secrets.compare_digest(key_hex, expected_key.hex())
    except Exception:
        return False

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///nagpur_estates.db").strip()

# SQLAlchemy 1.4+ and 2.0+ require 'postgresql://' instead of legacy 'postgres://' (common in Render / Heroku)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Detect if running in cloud (Render, Hugging Face, etc.) with an unresolvable localhost database URL
is_cloud = bool(os.getenv("RENDER") or os.getenv("SPACE_ID") or (os.getenv("PORT") and os.getenv("PORT") != "8000"))
if is_cloud and ("localhost" in DATABASE_URL or "127.0.0.1" in DATABASE_URL):
    logger.warning(
        "DATABASE_URL is pointing to 'localhost' inside a cloud container where no local PostgreSQL server runs. "
        "Falling back to built-in SQLite (nagpur_estates.db). To use PostgreSQL, provide a remote database URL."
    )
    DATABASE_URL = "sqlite:///nagpur_estates.db"

def setup_sqlite_pragmas(target_engine):
    @event.listens_for(target_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

# Configure engine
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False, "timeout": 15}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

if DATABASE_URL.startswith("sqlite"):
    setup_sqlite_pragmas(engine)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager for thread-safe database sessions."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database session error: {e}", exc_info=True)
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def seed_initial_data(db: Session):
    """Seed initial Nagpur properties and sample CRM leads if tables are empty."""
    # 1. Seed properties
    if db.query(Property).count() == 0:
        logger.info("Seeding initial Nagpur Estates property inventory...")
        seed_properties = [
            Property(
                id="prop_besa_01",
                project_name="Greenwood Meadows",
                location="Besa",
                property_type="Flat",
                bhk="2 BHK",
                price_min=5200000.0,
                price_max=6200000.0,
                price_display="₹52 L - ₹62 L",
                carpet_area="1050 sq.ft.",
                possession_status="Ready to Move",
                rera_id="P50500021489",
                builder_name="Meadows Infratech",
                description="Premium 2 BHK luxury apartment in Besa near Pipla road with clubhouse, swimming pool, and children play area.",
                amenities="Clubhouse, Swimming Pool, Gym, 24/7 Security, Power Backup, Covered Parking, Children Play Area",
                available_units=6,
            ),
            Property(
                id="prop_besa_02",
                project_name="Besa Imperial Towers",
                location="Besa",
                property_type="Flat",
                bhk="3 BHK",
                price_min=6800000.0,
                price_max=7800000.0,
                price_display="₹68 L - ₹78 L",
                carpet_area="1450 sq.ft.",
                possession_status="Ready to Move",
                rera_id="P50500028711",
                builder_name="Imperial Landmarks",
                description="Spacious 3 BHK apartment with modular kitchen, Italian marble flooring, and panoramic sunset views in Besa.",
                amenities="Gym, Rooftop Garden, Solar Water, EV Charging Station, 24/7 Security, Intercom",
                available_units=4,
            ),
            Property(
                id="prop_wardha_01",
                project_name="Royal Palms Enclave",
                location="Wardha Road",
                property_type="Plot",
                bhk="Plot",
                price_min=1800000.0,
                price_max=3500000.0,
                price_display="₹18 L - ₹35 L",
                carpet_area="1200 - 2400 sq.ft.",
                possession_status="Immediate Registration",
                rera_id="P50500019234",
                builder_name="Royal Developers Nagpur",
                description="NMRDA & RERA approved gated layout plots on Wardha Road near MIHAN flyover with cement roads, underground drainage, and streetlights.",
                amenities="Gated Community, Cement Roads, Underground Drainage, 24/7 Water Pipeline, Landscaped Garden, Street Lights",
                available_units=12,
            ),
            Property(
                id="prop_manish_01",
                project_name="Manish Heights",
                location="Manish Nagar",
                property_type="Flat",
                bhk="2 BHK",
                price_min=5800000.0,
                price_max=6600000.0,
                price_display="₹58 L - ₹66 L",
                carpet_area="1120 sq.ft.",
                possession_status="Under Construction (Diwali 2026)",
                rera_id="P50500034102",
                builder_name="Heights Infrastructure",
                description="Ultra-modern 2 BHK flats in the heart of Manish Nagar close to Metro Station, market, and top schools.",
                amenities="Metro Proximity, Automated Lift, Video Door Phone, Gymnasium, Rainwater Harvesting",
                available_units=5,
            ),
            Property(
                id="prop_sonegaon_01",
                project_name="Airport View Residency",
                location="Sonegaon",
                property_type="Flat",
                bhk="3 BHK",
                price_min=7500000.0,
                price_max=8500000.0,
                price_display="₹75 L - ₹85 L",
                carpet_area="1550 sq.ft.",
                possession_status="Ready to Move",
                rera_id="P50500015690",
                builder_name="Nagpur Skyline Developers",
                description="Luxury 3 BHK residence in prestigious Sonegaon near Airport Road with high-speed elevators and 2 car parkings.",
                amenities="Airport Proximity, 2 Covered Parkings, Terrace Lounge, Smart Home Automation, Fire Safety System",
                available_units=3,
            ),
            Property(
                id="prop_mihan_01",
                project_name="Tech City Oasis",
                location="MIHAN",
                property_type="Flat",
                bhk="2 BHK",
                price_min=4200000.0,
                price_max=5000000.0,
                price_display="₹42 L - ₹50 L",
                carpet_area="980 sq.ft.",
                possession_status="Ready to Move",
                rera_id="P50500041289",
                builder_name="Oasis Group",
                description="Ideal for IT professionals working in TCS, Infosys, and HCL in MIHAN SEZ with rental yield potential.",
                amenities="Clubhouse, Shuttle Service to SEZ, Badminton Court, Supermarket inside campus",
                available_units=8,
            ),
            Property(
                id="prop_civil_01",
                project_name="The Grand Heritage",
                location="Civil Lines",
                property_type="Luxury Apartment",
                bhk="4 BHK",
                price_min=18000000.0,
                price_max=24000000.0,
                price_display="₹1.80 Cr - ₹2.40 Cr",
                carpet_area="2800 sq.ft.",
                possession_status="Ready to Move",
                rera_id="P50500055123",
                builder_name="Heritage Luxury Spaces",
                description="Exclusive 4 BHK ultra-luxury apartment in lush green Civil Lines with private foyer and concierge service.",
                amenities="Infinity Pool, Concierge, Private Elevator, Banquet Hall, Spa & Jacuzzi, 3 Parkings",
                available_units=2,
            ),
        ]
        db.add_all(seed_properties)
        db.commit()
        logger.info(f"Seeded {len(seed_properties)} properties successfully.")

    # 2. Seed default users
    if db.query(User).count() == 0:
        logger.info("Seeding default CRM users...")
        admin_user = User(
            id="usr_admin_01",
            email="admin@nagpurestates.com",
            name="Rohit Patil",
            role="admin",
            password_hash="admin123",
        )
        agent_user = User(
            id="usr_agent_01",
            email="priya@nagpurestates.com",
            name="Priya Sharma",
            role="sales_agent",
            password_hash="agent123",
        )
        db.add_all([admin_user, agent_user])
        db.commit()

    # 3. Seed sample leads
    if db.query(Lead).count() == 0:
        logger.info("Seeding initial CRM leads...")
        sample_leads = [
            Lead(
                id="lead_001",
                name="Rahul",
                phone_number="+918600079496",
                masked_phone="+91860****96",
                preferred_location="Besa",
                property_type="Flat",
                bhk="2 BHK",
                budget_min=5000000.0,
                budget_max=6500000.0,
                purchase_purpose="Self-use",
                purchase_timeline="1-2 months",
                lead_temperature="hot",
                stage="qualified",
                assigned_agent="Priya",
                notes="Inquired about 2 BHK flats near Besa. Interested in ready to move properties.",
            ),
            Lead(
                id="lead_002",
                name="Amit Deshmukh",
                phone_number="+919823012345",
                masked_phone="+91982****45",
                preferred_location="Wardha Road",
                property_type="Plot",
                bhk="Plot",
                budget_min=2000000.0,
                budget_max=3000000.0,
                purchase_purpose="Investment",
                purchase_timeline="Immediate",
                lead_temperature="warm",
                stage="property_matched",
                assigned_agent="Priya",
                notes="Looking for NMRDA approved plots near MIHAN SEZ.",
            ),
            Lead(
                id="lead_003",
                name="Sneha Kulkarni",
                phone_number="+919765432100",
                masked_phone="+91976****00",
                preferred_location="Manish Nagar",
                property_type="Flat",
                bhk="2 BHK",
                budget_min=5500000.0,
                budget_max=6500000.0,
                purchase_purpose="Self-use",
                purchase_timeline="Diwali",
                lead_temperature="warm",
                stage="contacted",
                assigned_agent="Priya",
                notes="Wants metro-connected apartment in Manish Nagar.",
            ),
            Lead(
                id="lead_004",
                name="Vikram Joshi",
                phone_number="+919422155890",
                masked_phone="+91942****90",
                preferred_location="Sonegaon",
                property_type="Flat",
                bhk="3 BHK",
                budget_min=7000000.0,
                budget_max=8500000.0,
                purchase_purpose="Self-use",
                purchase_timeline="Immediate",
                lead_temperature="hot",
                stage="site_visit",
                assigned_agent="Priya",
                site_visit_interested=True,
                notes="Site visit scheduled for Airport View Residency.",
            ),
        ]
        db.add_all(sample_leads)
        db.commit()
        logger.info(f"Seeded {len(sample_leads)} CRM leads.")

    # 3. Seed default admin user
    if db.query(User).count() == 0:
        admin_email = os.getenv("ADMIN_EMAIL", "admin@nagpurestates.com").strip().lower()
        admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
        admin_user = User(
            id="usr_admin_01",
            email=admin_email,
            name="Admin Manager",
            role="admin",
            password_hash=hash_password(admin_password),
        )
        db.add(admin_user)
        db.commit()
        logger.info(f"Seeded default CRM admin user: {admin_email}")


def init_db():
    """Create all database tables and seed initial catalog."""
    global engine, SessionLocal, DATABASE_URL
    logger.info(f"Initializing database schema at: {DATABASE_URL}")
    try:
        Base.metadata.create_all(bind=engine)
        with get_db_session() as db:
            seed_initial_data(db)
        logger.info("Database schema initialized successfully.")
    except Exception as e:
        if not DATABASE_URL.startswith("sqlite"):
            logger.error(
                f"Failed to connect to primary database at {DATABASE_URL} ({e}). "
                "Automatically falling back to local SQLite database (nagpur_estates.db)."
            )
            DATABASE_URL = "sqlite:///nagpur_estates.db"
            engine = create_engine(
                DATABASE_URL,
                connect_args={"check_same_thread": False, "timeout": 15},
                pool_pre_ping=True,
            )
            setup_sqlite_pragmas(engine)
            SessionLocal.configure(bind=engine)
            Base.metadata.create_all(bind=engine)
            with get_db_session() as db:
                seed_initial_data(db)
            logger.info("Local SQLite database initialized and seeded successfully.")
        else:
            raise
