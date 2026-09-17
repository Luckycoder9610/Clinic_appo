import pytest
from datetime import datetime, date, time, timedelta
from app import create_app
from config import TestConfig
from models import db, Doctor, Patient, Appointment, NotificationOutbox, ClinicSetting
from services.booking_service import BookingService


@pytest.fixture
def app():
    app = create_app(config_class=TestConfig)
    with app.app_context():
        db.create_all()
        # Seed settings
        ClinicSetting.set_val("cancellation_cutoff_hours", 24.0)
        ClinicSetting.set_val("late_cancellation_fee", 25.00)

        # Seed doctors
        doc1 = Doctor(
            name="Dr. Sarah Chen",
            specialty="General Practice",
            shift_start=time(9, 0),
            shift_end=time(17, 0),
            slot_duration_mins=30,
            is_active=True,
        )
        doc2 = Doctor(
            name="Dr. Marcus Patel",
            specialty="Pediatrics",
            shift_start=time(9, 0),
            shift_end=time(17, 0),
            slot_duration_mins=30,
            is_active=True,
        )
        db.session.add_all([doc1, doc2])
        db.session.commit()

        yield app

        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


# =============================================================================
# LEVEL 1 — T6 (LIFECYCLE): RESCHEDULE AN APPOINTMENT
# =============================================================================
def test_reschedule_preserves_doctor_and_patient(app, client):
    """Rescheduling keeps the exact same patient and doctor."""
    with app.app_context():
        doc = Doctor.query.filter_by(name="Dr. Sarah Chen").first()
        res_book = BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=datetime(2026, 11, 1, 10, 0),
            end_time=datetime(2026, 11, 1, 10, 30),
            patient_name="Jessica Alba",
            patient_phone="555-4321",
        )
        apt_id = res_book["appointment"]["id"]
        original_doc_id = res_book["appointment"]["doctor_id"]
        original_patient_id = res_book["appointment"]["patient_id"]

        # Reschedule to 14:00 on the same day
        res = client.post(
            f"/appointments/{apt_id}/reschedule",
            json={"start_time": "2026-11-01 14:00", "duration_mins": 30},
        )
        assert res.status_code == 200
        data = res.json["appointment"]
        assert data["doctor_id"] == original_doc_id
        assert data["patient_id"] == original_patient_id
        assert data["patient_name"] == "Jessica Alba"
        assert data["start_time"] == "2026-11-01 14:00"
        assert data["end_time"] == "2026-11-01 14:30"
        assert data["status"] == "BOOKED"


def test_reschedule_rejects_overlapping_slot(app, client):
    """Rescheduling to a time slot that is already booked must be rejected."""
    with app.app_context():
        doc = Doctor.query.filter_by(name="Dr. Sarah Chen").first()
        
        # Appointment 1: 10:00 - 10:30
        apt1 = BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=datetime(2026, 11, 2, 10, 0),
            end_time=datetime(2026, 11, 2, 10, 30),
            patient_name="Patient One",
            patient_phone="555-0001",
        )["appointment"]

        # Appointment 2: 11:00 - 11:30
        apt2 = BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=datetime(2026, 11, 2, 11, 0),
            end_time=datetime(2026, 11, 2, 11, 30),
            patient_name="Patient Two",
            patient_phone="555-0002",
        )["appointment"]

        # Try to reschedule Appointment 2 to 10:15 (overlaps with Appointment 1) -> 409 Conflict
        res = client.post(
            f"/appointments/{apt2['id']}/reschedule",
            json={"start_time": "2026-11-02 10:15", "duration_mins": 30},
        )
        assert res.status_code == 409
        assert "Slot conflict" in res.json["error"]
        assert res.json.get("conflict") is True


def test_reschedule_excludes_self_from_conflict(app, client):
    """Shifting an appointment by 15 minutes within its own window does not self-conflict."""
    with app.app_context():
        doc = Doctor.query.filter_by(name="Dr. Sarah Chen").first()
        apt = BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=datetime(2026, 11, 3, 10, 0),
            end_time=datetime(2026, 11, 3, 11, 0),
            patient_name="Self Shifter",
            patient_phone="555-0003",
        )["appointment"]

        # Shift to 10:15 - 11:15 (partially overlaps its own previous 10:00 - 11:00 slot)
        res = client.post(
            f"/appointments/{apt['id']}/reschedule",
            json={"start_time": "2026-11-03 10:15", "duration_mins": 60},
        )
        assert res.status_code == 200
        assert res.json["appointment"]["start_time"] == "2026-11-03 10:15"
        assert res.json["appointment"]["end_time"] == "2026-11-03 11:15"


# =============================================================================
# LEVEL 2 — T1 (INTEGRATE): MORNING PATIENT REMINDERS VIA /outbox & POST /clock
# =============================================================================
def test_morning_reminders_sent_to_outbox(app, client):
    """Advancing clock to morning triggers reminders in /outbox for today's appointments."""
    with app.app_context():
        doc = Doctor.query.filter_by(name="Dr. Sarah Chen").first()
        target_date = date(2026, 11, 10)

        # Appointment 1 today at 09:30
        BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=datetime.combine(target_date, time(9, 30)),
            end_time=datetime.combine(target_date, time(10, 0)),
            patient_name="Alice Reminder",
            patient_phone="555-1111",
        )

        # Appointment 2 today at 14:00
        BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=datetime.combine(target_date, time(14, 0)),
            end_time=datetime.combine(target_date, time(14, 30)),
            patient_name="Bob Reminder",
            patient_phone="555-2222",
        )

        # Appointment tomorrow (should NOT receive reminder today)
        BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=datetime.combine(target_date + timedelta(days=1), time(10, 0)),
            end_time=datetime.combine(target_date + timedelta(days=1), time(10, 30)),
            patient_name="Tomorrow Patient",
            patient_phone="555-3333",
        )

        # 1. Advance clock to 08:00 on target_date
        clock_res = client.post("/clock", json={"timestamp": "2026-11-10T08:00:00"})
        assert clock_res.status_code == 200
        assert clock_res.json["reminders_sent"] == 2

        # 2. Check /outbox
        outbox_res = client.get("/outbox")
        assert outbox_res.status_code == 200
        outbox = outbox_res.json
        assert len(outbox) == 2

        recipients = [m["recipient"] for m in outbox]
        assert "555-1111" in recipients
        assert "555-2222" in recipients
        assert "555-3333" not in recipients

        # Verify message contents
        assert "Alice Reminder" in outbox[0]["message"]
        assert "09:30" in outbox[0]["message"]
        assert "Dr. Sarah Chen" in outbox[0]["message"]


def test_morning_reminders_idempotency(app, client):
    """Calling POST /clock multiple times on the same day does not duplicate reminders."""
    with app.app_context():
        doc = Doctor.query.filter_by(name="Dr. Sarah Chen").first()
        target_date = date(2026, 11, 11)

        BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=datetime.combine(target_date, time(10, 0)),
            end_time=datetime.combine(target_date, time(10, 30)),
            patient_name="Single Reminder",
            patient_phone="555-9999",
        )

        # First clock call at 08:00
        client.post("/clock", json={"timestamp": "2026-11-11T08:00:00"})
        assert len(client.get("/outbox").json) == 1

        # Second clock call at 08:30
        res2 = client.post("/clock", json={"timestamp": "2026-11-11T08:30:00"})
        assert res2.json["reminders_sent"] == 0
        assert len(client.get("/outbox").json) == 1


# =============================================================================
# LEVEL 3 — T2 (AUTOMATION): AUTO-MARK NO-SHOW 30 MIN AFTER START
# =============================================================================
def test_auto_mark_noshow_30_min_after_start(app, client):
    """An appointment is automatically marked NO_SHOW 30 minutes after start if not completed."""
    with app.app_context():
        doc = Doctor.query.filter_by(name="Dr. Sarah Chen").first()
        target_date = date(2026, 11, 15)

        # Appointment starts at 10:00
        apt_res = BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=datetime.combine(target_date, time(10, 0)),
            end_time=datetime.combine(target_date, time(10, 30)),
            patient_name="No Show Patient",
            patient_phone="555-0099",
        )
        apt_id = apt_res["appointment"]["id"]

        # Step A: Clock at 10:20 (20 min after start) -> Still BOOKED
        client.post("/clock", json={"timestamp": "2026-11-15T10:20:00"})
        apt_data = client.get(f"/appointments/{apt_id}").json["appointment"]
        assert apt_data["status"] == "BOOKED"

        # Step B: Clock at 10:29 (29 min after start) -> Still BOOKED
        client.post("/clock", json={"timestamp": "2026-11-15T10:29:00"})
        apt_data = client.get(f"/appointments/{apt_id}").json["appointment"]
        assert apt_data["status"] == "BOOKED"

        # Step C: Clock at 10:30 (30 min after start) -> Automatically becomes NO_SHOW!
        res_noshow = client.post("/clock", json={"timestamp": "2026-11-15T10:30:00"})
        assert res_noshow.json["no_shows_marked"] == 1
        apt_data = client.get(f"/appointments/{apt_id}").json["appointment"]
        assert apt_data["status"] == "NO_SHOW"
        assert apt_data["no_show_at"] is not None


def test_completed_appointment_not_marked_noshow(app, client):
    """If patient arrives and is marked completed, it is never marked as NO_SHOW."""
    with app.app_context():
        doc = Doctor.query.filter_by(name="Dr. Sarah Chen").first()
        target_date = date(2026, 11, 16)

        # Appointment starts at 10:00
        apt_res = BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=datetime.combine(target_date, time(10, 0)),
            end_time=datetime.combine(target_date, time(10, 30)),
            patient_name="Attended Patient",
            patient_phone="555-0088",
        )
        apt_id = apt_res["appointment"]["id"]

        # Patient arrives at 10:05 and is marked COMPLETED
        comp_res = client.post(f"/appointments/{apt_id}/complete")
        assert comp_res.status_code == 200
        assert comp_res.json["appointment"]["status"] == "COMPLETED"

        # Advance clock to 10:45 (45 min after start)
        client.post("/clock", json={"timestamp": "2026-11-16T10:45:00"})
        apt_data = client.get(f"/appointments/{apt_id}").json["appointment"]
        # Must still be COMPLETED, not NO_SHOW!
        assert apt_data["status"] == "COMPLETED"
