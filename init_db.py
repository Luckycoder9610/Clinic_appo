import os
import sys
from datetime import datetime, date, time, timedelta
import pymysql
from config import Config
from app import create_app
from models import db, Doctor, Patient, Appointment, ClinicSetting


def init_mysql_database():
    """Connects to MySQL server directly and creates the target database if missing."""
    print(f"Connecting to MySQL server at {Config.DB_HOST}:{Config.DB_PORT} as '{Config.DB_USER}'...")
    try:
        connection = pymysql.connect(
            host=Config.DB_HOST,
            port=int(Config.DB_PORT),
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            charset="utf8mb4",
            connect_timeout=5,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{Config.DB_NAME}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            )
        connection.commit()
        connection.close()
        print(f"[Success] Database '{Config.DB_NAME}' created or verified on MySQL.")
        return True
    except pymysql.MySQLError as err:
        print(f"[Notice] MySQL connection error: {err}")
        print("[Notice] If root requires a password, please specify DB_PASSWORD in your .env file.")
        return False


def seed_data(app):
    """Seeds doctors, initial patients, settings, and sample appointments."""
    with app.app_context():
        db.create_all()

        # Seed Clinic Settings
        ClinicSetting.set_val(
            "cancellation_cutoff_hours",
            Config.DEFAULT_CUTOFF_HOURS,
            "Hours prior to appointment where cancellation is considered late",
        )
        ClinicSetting.set_val(
            "late_cancellation_fee",
            Config.DEFAULT_LATE_FEE,
            "Fee charged for late cancellations",
        )

        # Check if doctors already exist
        if Doctor.query.count() > 0:
            print("[Notice] Database already contains records. Skipping seed.")
            return

        print("Seeding Doctors roster...")
        doc1 = Doctor(
            name="Dr. Sarah Chen",
            specialty="General Practice & Family Medicine",
            email="dr.chen@clinicapp.internal",
            phone="(555) 201-1001",
            shift_start=time(9, 0),
            shift_end=time(17, 0),
            slot_duration_mins=30,
            is_active=True,
        )
        doc2 = Doctor(
            name="Dr. Marcus Patel",
            specialty="Pediatrics",
            email="dr.patel@clinicapp.internal",
            phone="(555) 201-1002",
            shift_start=time(9, 0),
            shift_end=time(16, 30),
            slot_duration_mins=30,
            is_active=True,
        )
        doc3 = Doctor(
            name="Dr. Elena Rostova",
            specialty="Cardiology & Internal Medicine",
            email="dr.rostova@clinicapp.internal",
            phone="(555) 201-1003",
            shift_start=time(10, 0),
            shift_end=time(18, 0),
            slot_duration_mins=45,
            is_active=True,
        )
        db.session.add_all([doc1, doc2, doc3])
        db.session.flush()

        print("Seeding Patients...")
        pat1 = Patient(
            name="John Doe",
            phone="(555) 123-4567",
            email="john.doe@example.com",
            date_of_birth=date(1985, 4, 12),
        )
        pat2 = Patient(
            name="Maria Garcia",
            phone="(555) 987-6543",
            email="maria.garcia@example.com",
            date_of_birth=date(1992, 8, 24),
        )
        pat3 = Patient(
            name="Robert Smith",
            phone="(555) 456-7890",
            email="robert.smith@example.com",
            date_of_birth=date(1978, 11, 3),
        )
        pat4 = Patient(
            name="Emily Johnson",
            phone="(555) 321-0987",
            email="emily.j@example.com",
            date_of_birth=date(2001, 2, 19),
        )
        db.session.add_all([pat1, pat2, pat3, pat4])
        db.session.flush()

        print("Seeding Sample Appointments...")
        now = datetime.now()
        today = now.date()
        tomorrow = today + timedelta(days=1)

        # 1. Appointment for Dr. Chen today at 09:30 - 10:00 (Active)
        apt1 = Appointment(
            doctor_id=doc1.id,
            patient_id=pat1.id,
            start_time=datetime.combine(today, time(9, 30)),
            end_time=datetime.combine(today, time(10, 0)),
            status="BOOKED",
            notes="Annual physical check-up",
        )

        # 2. Appointment for Dr. Chen today at 11:00 - 11:30 (Active)
        apt2 = Appointment(
            doctor_id=doc1.id,
            patient_id=pat2.id,
            start_time=datetime.combine(today, time(11, 0)),
            end_time=datetime.combine(today, time(11, 30)),
            status="BOOKED",
            notes="Routine blood pressure check",
        )

        # 3. Appointment for Dr. Patel tomorrow at 10:00 - 10:30 (Ample notice for free cancellation demo)
        apt3 = Appointment(
            doctor_id=doc2.id,
            patient_id=pat3.id,
            start_time=datetime.combine(tomorrow, time(10, 0)),
            end_time=datetime.combine(tomorrow, time(10, 30)),
            status="BOOKED",
            notes="Pediatric wellness visit for child",
        )

        # 4. A previously cancelled appointment showing late fee applied
        apt4 = Appointment(
            doctor_id=doc1.id,
            patient_id=pat4.id,
            start_time=datetime.combine(today, time(14, 0)),
            end_time=datetime.combine(today, time(14, 30)),
            status="CANCELLED",
            cancellation_fee=25.00,
            is_late_cancellation=True,
            cancellation_reason="Patient caught in traffic; cancelled 45 minutes before slot.",
            cancelled_at=datetime.combine(today, time(13, 15)),
            notes="Migraine follow-up",
        )

        db.session.add_all([apt1, apt2, apt3, apt4])
        db.session.commit()
        print("[Success] Clinic database initialized with seed doctors, patients, and schedule!")


if __name__ == "__main__":
    mysql_ready = False
    if Config.DB_TYPE == "mysql":
        mysql_ready = init_mysql_database()

    if not mysql_ready and Config.DB_TYPE == "mysql":
        print("\n[Notice] MySQL credentials not yet verified. Initializing local database so you can test right away...")
        os.environ["DB_TYPE"] = "sqlite"
        Config.DB_TYPE = "sqlite"
        Config.SQLALCHEMY_DATABASE_URI = Config.get_database_uri(force_sqlite=True)

    app = create_app()
    seed_data(app)
    print("\nInitialization complete! To connect to MySQL, add DB_PASSWORD=your_password in .env and run init_db.py again.")
