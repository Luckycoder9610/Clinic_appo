from datetime import datetime, date, time
from flask import Blueprint, request, jsonify
from models import db, Doctor, Patient, Appointment, ClinicSetting
from services.booking_service import BookingService

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/doctors", methods=["GET"])
def get_doctors():
    """List all active doctors."""
    doctors = Doctor.query.filter_by(is_active=True).all()
    return jsonify({"success": True, "doctors": [d.to_dict() for d in doctors]})


@api_bp.route("/doctors", methods=["POST"])
def add_doctor():
    """Add a new doctor to the clinic roster."""
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    specialty = data.get("specialty", "").strip()
    if not name or not specialty:
        return jsonify({"success": False, "error": "Name and specialty are required."}), 400

    shift_start_str = data.get("shift_start", "09:00")
    shift_end_str = data.get("shift_end", "17:00")
    duration = int(data.get("slot_duration_mins", 30))

    try:
        sh_hour, sh_min = map(int, shift_start_str.split(":"))
        eh_hour, eh_min = map(int, shift_end_str.split(":"))
        sh_time = time(sh_hour, sh_min)
        eh_time = time(eh_hour, eh_min)
    except Exception:
        return jsonify({"success": False, "error": "Invalid time format. Use HH:MM."}), 400

    doctor = Doctor(
        name=name,
        specialty=specialty,
        email=data.get("email"),
        phone=data.get("phone"),
        shift_start=sh_time,
        shift_end=eh_time,
        slot_duration_mins=duration,
        is_active=True,
    )
    db.session.add(doctor)
    db.session.commit()
    return jsonify({"success": True, "doctor": doctor.to_dict()}), 201


@api_bp.route("/doctors/<int:doctor_id>/day", methods=["GET"])
def get_doctor_day(doctor_id):
    """Retrieve full day schedule timeline for a doctor."""
    date_str = request.args.get("date")
    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"success": False, "error": "Invalid date format. Use YYYY-MM-DD."}), 400
    else:
        target_date = date.today()

    result = BookingService.get_doctor_day_schedule(doctor_id, target_date)
    status_code = 200 if result.get("success") else 404
    return jsonify(result), status_code


@api_bp.route("/appointments", methods=["POST"])
def create_appointment():
    """
    Book an appointment.
    Guarantees no double-booking via atomic conflict validation.
    """
    data = request.get_json() or {}
    doctor_id = data.get("doctor_id")
    start_str = data.get("start_time")
    end_str = data.get("end_time")
    duration_mins = data.get("duration_mins")
    patient_name = data.get("patient_name")
    patient_phone = data.get("patient_phone")
    patient_email = data.get("patient_email")
    notes = data.get("notes")

    if not doctor_id or not start_str or not patient_name or not patient_phone:
        return jsonify({
            "success": False,
            "error": "Doctor, start time, patient name, and phone number are required.",
        }), 400

    # Parse start_time
    try:
        if "T" in start_str:
            start_time = datetime.fromisoformat(start_str.replace("Z", ""))
        else:
            start_time = datetime.strptime(start_str, "%Y-%m-%d %H:%M")
    except Exception:
        return jsonify({"success": False, "error": "Invalid start_time format. Use YYYY-MM-DD HH:MM."}), 400

    # Determine end_time
    if end_str:
        try:
            if "T" in end_str:
                end_time = datetime.fromisoformat(end_str.replace("Z", ""))
            else:
                end_time = datetime.strptime(end_str, "%Y-%m-%d %H:%M")
        except Exception:
            return jsonify({"success": False, "error": "Invalid end_time format. Use YYYY-MM-DD HH:MM."}), 400
    elif duration_mins:
        end_time = start_time + __import__("datetime").timedelta(minutes=int(duration_mins))
    else:
        # Fallback to doctor's default slot duration
        doc = db.session.get(Doctor, doctor_id)
        slot_mins = doc.slot_duration_mins if doc else 30
        end_time = start_time + __import__("datetime").timedelta(minutes=slot_mins)

    result = BookingService.book_appointment(
        doctor_id=int(doctor_id),
        start_time=start_time,
        end_time=end_time,
        patient_name=patient_name,
        patient_phone=patient_phone,
        patient_email=patient_email,
        notes=notes,
    )

    if not result.get("success"):
        status_code = 409 if result.get("conflict") else 400
        return jsonify(result), status_code

    return jsonify(result), 201


@api_bp.route("/appointments/<int:appointment_id>/preview-cancel", methods=["GET"])
def preview_cancel(appointment_id):
    """Preview late cancellation fee for an appointment before confirming."""
    sim_time_str = request.args.get("simulated_time")
    sim_dt = None
    if sim_time_str:
        try:
            sim_dt = datetime.strptime(sim_time_str, "%Y-%m-%d %H:%M")
        except Exception:
            pass

    result = BookingService.preview_cancellation(appointment_id, cancellation_time=sim_dt)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@api_bp.route("/appointments/<int:appointment_id>/cancel", methods=["POST"])
def cancel_appointment(appointment_id):
    """
    Cancel an appointment and enforce late cancellation rules.
    Immediately frees the time slot for other patients.
    """
    data = request.get_json() or {}
    reason = data.get("reason")
    waive_fee = bool(data.get("waive_fee", False))
    waiver_reason = data.get("waiver_reason")
    sim_time_str = data.get("simulated_time")

    sim_dt = None
    if sim_time_str:
        try:
            sim_dt = datetime.strptime(sim_time_str, "%Y-%m-%d %H:%M")
        except Exception:
            pass

    result = BookingService.cancel_appointment(
        appointment_id=appointment_id,
        cancellation_time=sim_dt,
        waive_fee=waive_fee,
        waiver_reason=waiver_reason,
        reason=reason,
    )

    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@api_bp.route("/patients/search", methods=["GET"])
def search_patients():
    """Find patient appointments by patient name or phone."""
    query = request.args.get("q", "")
    if not query:
        return jsonify({"success": True, "results": []})

    results = BookingService.search_patient_appointments(query)
    return jsonify({"success": True, "query": query, "results": results})


@api_bp.route("/settings", methods=["GET"])
def get_settings():
    """Retrieve clinic cancellation policy settings."""
    cutoff, fee = BookingService.get_cancellation_policy()
    return jsonify({
        "success": True,
        "cancellation_cutoff_hours": cutoff,
        "late_cancellation_fee": fee,
    })


@api_bp.route("/settings", methods=["PUT"])
def update_settings():
    """Update clinic cancellation cutoff window or late fee."""
    data = request.get_json() or {}
    if "cancellation_cutoff_hours" in data:
        ClinicSetting.set_val(
            "cancellation_cutoff_hours",
            float(data["cancellation_cutoff_hours"]),
            "Hours before appointment start where cancellation incurs a fee",
        )
    if "late_cancellation_fee" in data:
        ClinicSetting.set_val(
            "late_cancellation_fee",
            float(data["late_cancellation_fee"]),
            "Fee charged for late cancellation",
        )

    cutoff, fee = BookingService.get_cancellation_policy()
    return jsonify({
        "success": True,
        "message": "Clinic settings updated successfully.",
        "cancellation_cutoff_hours": cutoff,
        "late_cancellation_fee": fee,
    })
