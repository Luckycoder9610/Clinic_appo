import pytest
from datetime import datetime, date, time, timedelta
from app import create_app
from config import TestConfig
from models import db, Doctor, Patient, Appointment, ClinicSetting
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


def test_conflict_free_booking_exact_overlap(app):
    """Test that two patients cannot book the exact same slot for the same doctor."""
    with app.app_context():
        doc = Doctor.query.filter_by(name="Dr. Sarah Chen").first()
        target_day = date(2026, 10, 1)

        start1 = datetime.combine(target_day, time(10, 0))
        end1 = datetime.combine(target_day, time(10, 30))

        # First booking succeeds
        res1 = BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=start1,
            end_time=end1,
            patient_name="Alice Smith",
            patient_phone="555-0101",
        )
        assert res1["success"] is True
        assert res1["appointment"]["status"] == "BOOKED"

        # Second booking for same doctor & same time is BLOCKED
        res2 = BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=start1,
            end_time=end1,
            patient_name="Bob Jones",
            patient_phone="555-0102",
        )
        assert res2["success"] is False
        assert res2.get("conflict") is True
        assert "Slot conflict" in res2["error"]


def test_conflict_free_booking_partial_and_enclosing_overlaps(app):
    """Test partial overlaps (left overlap, right overlap, enclosing, sub-interval)."""
    with app.app_context():
        doc = Doctor.query.filter_by(name="Dr. Sarah Chen").first()
        target_day = date(2026, 10, 2)

        # Baseline: 10:00 - 11:00
        base_start = datetime.combine(target_day, time(10, 0))
        base_end = datetime.combine(target_day, time(11, 0))
        res_base = BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=base_start,
            end_time=base_end,
            patient_name="Existing Patient",
            patient_phone="555-1111",
        )
        assert res_base["success"] is True

        # Case A: Partial overlap left (09:30 - 10:30)
        res_a = BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=datetime.combine(target_day, time(9, 30)),
            end_time=datetime.combine(target_day, time(10, 30)),
            patient_name="Overlap Left",
            patient_phone="555-2222",
        )
        assert res_a["success"] is False
        assert res_a.get("conflict") is True

        # Case B: Partial overlap right (10:30 - 11:30)
        res_b = BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=datetime.combine(target_day, time(10, 30)),
            end_time=datetime.combine(target_day, time(11, 30)),
            patient_name="Overlap Right",
            patient_phone="555-3333",
        )
        assert res_b["success"] is False
        assert res_b.get("conflict") is True

        # Case C: Enclosing interval (09:30 - 11:30)
        res_c = BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=datetime.combine(target_day, time(9, 30)),
            end_time=datetime.combine(target_day, time(11, 30)),
            patient_name="Enclosing Overlap",
            patient_phone="555-4444",
        )
        assert res_c["success"] is False
        assert res_c.get("conflict") is True

        # Case D: Sub-interval (10:15 - 10:45)
        res_d = BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=datetime.combine(target_day, time(10, 15)),
            end_time=datetime.combine(target_day, time(10, 45)),
            patient_name="Inside Overlap",
            patient_phone="555-5555",
        )
        assert res_d["success"] is False
        assert res_d.get("conflict") is True


def test_adjacent_slots_and_different_doctors_allowed(app):
    """Adjacent time slots are allowed; two different doctors can book at identical times."""
    with app.app_context():
        doc1 = Doctor.query.filter_by(name="Dr. Sarah Chen").first()
        doc2 = Doctor.query.filter_by(name="Dr. Marcus Patel").first()
        target_day = date(2026, 10, 3)

        # Slot 1: 09:00 - 09:30 for Dr. Chen
        res1 = BookingService.book_appointment(
            doctor_id=doc1.id,
            start_time=datetime.combine(target_day, time(9, 0)),
            end_time=datetime.combine(target_day, time(9, 30)),
            patient_name="Patient 1",
            patient_phone="555-1001",
        )
        assert res1["success"] is True

        # Adjacent Slot 2: 09:30 - 10:00 for Dr. Chen (immediately follows Slot 1) -> Allowed!
        res2 = BookingService.book_appointment(
            doctor_id=doc1.id,
            start_time=datetime.combine(target_day, time(9, 30)),
            end_time=datetime.combine(target_day, time(10, 0)),
            patient_name="Patient 2",
            patient_phone="555-1002",
        )
        assert res2["success"] is True

        # Doctor 2 at same 09:00 - 09:30 as Dr. Chen -> Allowed! Doctors have independent schedules.
        res3 = BookingService.book_appointment(
            doctor_id=doc2.id,
            start_time=datetime.combine(target_day, time(9, 0)),
            end_time=datetime.combine(target_day, time(9, 30)),
            patient_name="Patient 3",
            patient_phone="555-1003",
        )
        assert res3["success"] is True


def test_working_hours_validation(app):
    """Appointments outside doctor's shift are rejected."""
    with app.app_context():
        doc = Doctor.query.filter_by(name="Dr. Sarah Chen").first()
        target_day = date(2026, 10, 4)

        # Before shift start (08:00 - 08:30, shift starts at 09:00)
        res_early = BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=datetime.combine(target_day, time(8, 0)),
            end_time=datetime.combine(target_day, time(8, 30)),
            patient_name="Early Bird",
            patient_phone="555-0800",
        )
        assert res_early["success"] is False
        assert "working hours" in res_early["error"]

        # After shift end (17:00 - 17:30, shift ends at 17:00)
        res_late = BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=datetime.combine(target_day, time(17, 0)),
            end_time=datetime.combine(target_day, time(17, 30)),
            patient_name="Late Bird",
            patient_phone="555-1700",
        )
        assert res_late["success"] is False
        assert "working hours" in res_late["error"]


def test_fair_cancellation_in_good_time_is_free(app):
    """If a patient cancels >= 24 hours in advance, fee is $0.00."""
    with app.app_context():
        doc = Doctor.query.filter_by(name="Dr. Sarah Chen").first()
        apt_start = datetime(2026, 10, 10, 14, 0)
        apt_end = datetime(2026, 10, 10, 14, 30)

        book_res = BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=apt_start,
            end_time=apt_end,
            patient_name="Timely Patient",
            patient_phone="555-2401",
        )
        apt_id = book_res["appointment"]["id"]

        # Cancel 48 hours prior (well above 24-hour cutoff)
        cancel_time = datetime(2026, 10, 8, 14, 0)
        cancel_res = BookingService.cancel_appointment(
            appointment_id=apt_id,
            cancellation_time=cancel_time,
            reason="Work meeting rescheduled",
        )

        assert cancel_res["success"] is True
        assert cancel_res["fee"] == 0.0
        assert cancel_res["is_late"] is False
        assert cancel_res["appointment"]["status"] == "CANCELLED"
        assert cancel_res["appointment"]["cancellation_fee"] == 0.0


def test_fair_cancellation_late_carries_fee(app):
    """If a patient cancels < 24 hours in advance, a late fee of $25 is charged."""
    with app.app_context():
        doc = Doctor.query.filter_by(name="Dr. Sarah Chen").first()
        apt_start = datetime(2026, 10, 10, 14, 0)
        apt_end = datetime(2026, 10, 10, 14, 30)

        book_res = BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=apt_start,
            end_time=apt_end,
            patient_name="Late Canceller",
            patient_phone="555-2402",
        )
        apt_id = book_res["appointment"]["id"]

        # Cancel 3 hours prior
        cancel_time = datetime(2026, 10, 10, 11, 0)
        cancel_res = BookingService.cancel_appointment(
            appointment_id=apt_id,
            cancellation_time=cancel_time,
            reason="Woke up sick",
        )

        assert cancel_res["success"] is True
        assert cancel_res["fee"] == 25.0
        assert cancel_res["is_late"] is True
        assert cancel_res["appointment"]["status"] == "CANCELLED"
        assert cancel_res["appointment"]["cancellation_fee"] == 25.0


def test_late_cancellation_waiver(app):
    """Front desk can waive fee in case of genuine emergency."""
    with app.app_context():
        doc = Doctor.query.filter_by(name="Dr. Sarah Chen").first()
        apt_start = datetime(2026, 10, 10, 14, 0)
        apt_end = datetime(2026, 10, 10, 14, 30)

        book_res = BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=apt_start,
            end_time=apt_end,
            patient_name="Waived Patient",
            patient_phone="555-2403",
        )
        apt_id = book_res["appointment"]["id"]

        # Cancel 2 hours before with waiver
        cancel_time = datetime(2026, 10, 10, 12, 0)
        cancel_res = BookingService.cancel_appointment(
            appointment_id=apt_id,
            cancellation_time=cancel_time,
            waive_fee=True,
            waiver_reason="Emergency room admission",
        )

        assert cancel_res["success"] is True
        assert cancel_res["fee"] == 0.0
        assert cancel_res["fee_waived"] is True
        assert cancel_res["appointment"]["status"] == "CANCELLED"


def test_immediate_slot_recovery_after_cancellation(app):
    """When an appointment is cancelled, the slot is immediately liberated for other patients."""
    with app.app_context():
        doc = Doctor.query.filter_by(name="Dr. Sarah Chen").first()
        apt_start = datetime(2026, 10, 12, 11, 0)
        apt_end = datetime(2026, 10, 12, 11, 30)

        # 1. Patient A books slot
        res1 = BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=apt_start,
            end_time=apt_end,
            patient_name="Patient A",
            patient_phone="555-9001",
        )
        assert res1["success"] is True
        apt1_id = res1["appointment"]["id"]

        # 2. Patient B tries to book the same slot -> BLOCKED
        res2 = BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=apt_start,
            end_time=apt_end,
            patient_name="Patient B",
            patient_phone="555-9002",
        )
        assert res2["success"] is False
        assert res2.get("conflict") is True

        # 3. Patient A cancels
        cancel_res = BookingService.cancel_appointment(
            appointment_id=apt1_id,
            reason="Change of plans",
        )
        assert cancel_res["success"] is True

        # 4. Patient B tries again -> SUCCEEDS immediately!
        res3 = BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=apt_start,
            end_time=apt_end,
            patient_name="Patient B",
            patient_phone="555-9002",
        )
        assert res3["success"] is True
        assert res3["appointment"]["patient_name"] == "Patient B"


def test_doctor_day_schedule_generation(app):
    """Test generating a doctor's full day schedule with booked and open slots."""
    with app.app_context():
        doc = Doctor.query.filter_by(name="Dr. Sarah Chen").first()
        target_day = date(2026, 10, 15)

        # Book one slot at 10:00 - 10:30
        BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=datetime.combine(target_day, time(10, 0)),
            end_time=datetime.combine(target_day, time(10, 30)),
            patient_name="Schedule Tester",
            patient_phone="555-7777",
        )

        schedule = BookingService.get_doctor_day_schedule(doc.id, target_day)
        assert schedule["success"] is True
        assert schedule["booked_count"] == 1

        timeline = schedule["timeline"]
        # Shift is 09:00 - 17:00 (8 hours = 16 30-min slots)
        assert len(timeline) == 16

        # Check that 10:00 is BOOKED and others are AVAILABLE
        slot_10 = [s for s in timeline if s["slot_start"] == "10:00"][0]
        assert slot_10["type"] == "BOOKED"
        assert slot_10["appointment"]["patient_name"] == "Schedule Tester"

        slot_09 = [s for s in timeline if s["slot_start"] == "09:00"][0]
        assert slot_09["type"] == "AVAILABLE"


def test_patient_search_and_appointment_history(app):
    """Test looking up patient appointments by name or phone."""
    with app.app_context():
        doc = Doctor.query.filter_by(name="Dr. Sarah Chen").first()
        target_day = date(2026, 10, 16)

        # Book an appointment for Eleanor Rigby
        BookingService.book_appointment(
            doctor_id=doc.id,
            start_time=datetime.combine(target_day, time(14, 0)),
            end_time=datetime.combine(target_day, time(14, 30)),
            patient_name="Eleanor Rigby",
            patient_phone="555-8888",
            notes="Follow up visit",
        )

        # Search by partial name "Eleanor"
        search_res = BookingService.search_patient_appointments("Eleanor")
        assert len(search_res) == 1
        assert search_res[0]["patient"]["name"] == "Eleanor Rigby"
        assert len(search_res[0]["appointments"]) == 1
        assert search_res[0]["active_count"] == 1

        # Search by phone "8888"
        search_phone = BookingService.search_patient_appointments("8888")
        assert len(search_phone) == 1
        assert search_phone[0]["patient"]["name"] == "Eleanor Rigby"
