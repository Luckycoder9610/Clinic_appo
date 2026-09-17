from datetime import datetime, date, time, timedelta
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy import and_, or_
from models import db, Doctor, Patient, Appointment, ClinicSetting
from config import Config


class BookingService:
    @staticmethod
    def get_cancellation_policy() -> Tuple[float, float]:
        """Returns (cutoff_hours, late_fee) from settings or config defaults."""
        cutoff = ClinicSetting.get_val("cancellation_cutoff_hours")
        fee = ClinicSetting.get_val("late_cancellation_fee")
        cutoff_hours = float(cutoff) if cutoff is not None else Config.DEFAULT_CUTOFF_HOURS
        late_fee = float(fee) if fee is not None else Config.DEFAULT_LATE_FEE
        return cutoff_hours, late_fee

    @staticmethod
    def check_conflict(
        doctor_id: int,
        start_time: datetime,
        end_time: datetime,
        exclude_appointment_id: Optional[int] = None,
        lock_for_update: bool = False,
    ) -> Optional[Appointment]:
        """
        Checks if the requested time slot [start_time, end_time) conflicts
        with any existing active ('BOOKED') appointment for this doctor.

        Overlap rule: A.start_time < end_time AND A.end_time > start_time.
        """
        query = Appointment.query.filter(
            Appointment.doctor_id == doctor_id,
            Appointment.status == "BOOKED",
            Appointment.start_time < end_time,
            Appointment.end_time > start_time,
        )

        if exclude_appointment_id:
            query = query.filter(Appointment.id != exclude_appointment_id)

        if lock_for_update:
            # Prevent race conditions during concurrent bookings
            try:
                query = query.with_for_update()
            except Exception:
                # Some dialects (like SQLite in certain modes) do not support with_for_update
                pass

        return query.first()

    @staticmethod
    def book_appointment(
        doctor_id: int,
        start_time: datetime,
        end_time: datetime,
        patient_name: str,
        patient_phone: str,
        patient_email: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Atomically books an appointment for a doctor and patient.
        Ensures strict conflict-free validation.
        """
        if start_time >= end_time:
            return {"success": False, "error": "Start time must be before end time."}

        # Check doctor existence & active status
        doctor = db.session.get(Doctor, doctor_id)
        if not doctor:
            return {"success": False, "error": "Doctor not found."}
        doc_name = doctor.name if doctor.name.startswith("Dr.") else f"Dr. {doctor.name}"
        if not doctor.is_active:
            return {"success": False, "error": f"{doc_name} is currently inactive."}

        # Check doctor working hours
        shift_start_time = doctor.shift_start or time(9, 0)
        shift_end_time = doctor.shift_end or time(17, 0)
        slot_start_time = start_time.time()
        slot_end_time = end_time.time()

        if slot_start_time < shift_start_time or slot_end_time > shift_end_time:
            return {
                "success": False,
                "error": f"Appointment ({start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}) "
                f"falls outside {doc_name}'s working hours ({shift_start_time.strftime('%H:%M')} - {shift_end_time.strftime('%H:%M')}).",
            }

        # Concurrency-safe overlap check
        conflict = BookingService.check_conflict(
            doctor_id=doctor_id,
            start_time=start_time,
            end_time=end_time,
            lock_for_update=True,
        )

        if conflict:
            conflicting_patient = conflict.patient.name if conflict.patient else "Another patient"
            return {
                "success": False,
                "conflict": True,
                "error": f"Slot conflict! {doc_name} already has an appointment booked from "
                f"{conflict.start_time.strftime('%H:%M')} to {conflict.end_time.strftime('%H:%M')} "
                f"(Patient: {conflicting_patient}).",
                "conflicting_appointment_id": conflict.id,
            }

        # Find or create patient
        patient = Patient.query.filter_by(phone=patient_phone.strip()).first()
        if not patient:
            patient = Patient(
                name=patient_name.strip(),
                phone=patient_phone.strip(),
                email=patient_email.strip() if patient_email else None,
            )
            db.session.add(patient)
            db.session.flush()
        else:
            # Update name/email if provided
            if patient_name and patient.name != patient_name.strip():
                patient.name = patient_name.strip()
            if patient_email and patient.email != patient_email.strip():
                patient.email = patient_email.strip()

        # Create appointment
        appointment = Appointment(
            doctor_id=doctor_id,
            patient_id=patient.id,
            start_time=start_time,
            end_time=end_time,
            status="BOOKED",
            notes=notes.strip() if notes else None,
        )
        db.session.add(appointment)
        db.session.commit()

        return {
            "success": True,
            "message": "Appointment successfully booked.",
            "appointment": appointment.to_dict(),
        }

    @staticmethod
    def preview_cancellation(
        appointment_id: int,
        cancellation_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Calculates fee details for cancelling without modifying the database."""
        appointment = db.session.get(Appointment, appointment_id)
        if not appointment:
            return {"success": False, "error": "Appointment not found."}

        if appointment.status != "BOOKED":
            return {
                "success": False,
                "error": f"Appointment is already {appointment.status.lower()}.",
            }

        cutoff_hours, late_fee = BookingService.get_cancellation_policy()
        cancel_dt = cancellation_time or datetime.now()

        # Calculate difference in hours between cancellation request and appointment start
        delta = appointment.start_time - cancel_dt
        hours_notice = delta.total_seconds() / 3600.0

        is_late = hours_notice < cutoff_hours
        fee = late_fee if is_late else 0.0

        return {
            "success": True,
            "appointment_id": appointment.id,
            "patient_name": appointment.patient.name if appointment.patient else "Unknown",
            "doctor_name": appointment.doctor.name if appointment.doctor else "Unknown",
            "start_time": appointment.start_time.strftime("%Y-%m-%d %H:%M"),
            "cancellation_time": cancel_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "hours_notice": round(hours_notice, 1),
            "cutoff_hours": cutoff_hours,
            "is_late": is_late,
            "fee": fee,
            "policy_summary": (
                f"Late cancellation fee (${late_fee:.2f}) applies because cancellation is within "
                f"{cutoff_hours:.0f} hours of the appointment ({round(hours_notice, 1)}h notice)."
                if is_late
                else f"Free cancellation! Ample notice provided ({round(hours_notice, 1)}h notice, policy is {cutoff_hours:.0f}h)."
            ),
        }

    @staticmethod
    def cancel_appointment(
        appointment_id: int,
        cancellation_time: Optional[datetime] = None,
        waive_fee: bool = False,
        waiver_reason: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Cancels an appointment, enforces late fee policy, and immediately frees the time slot.
        """
        appointment = db.session.get(Appointment, appointment_id)
        if not appointment:
            return {"success": False, "error": "Appointment not found."}

        if appointment.status != "BOOKED":
            return {
                "success": False,
                "error": f"Appointment cannot be cancelled because it is {appointment.status.lower()}.",
            }

        cancel_dt = cancellation_time or datetime.now()
        preview = BookingService.preview_cancellation(appointment_id, cancellation_time=cancel_dt)
        if not preview["success"]:
            return preview

        is_late = preview["is_late"]
        fee = preview["fee"]

        if waive_fee:
            fee = 0.0
            appointment.fee_waived = True
            appointment.waiver_reason = waiver_reason or "Waived by front desk staff."

        appointment.status = "CANCELLED"
        appointment.cancelled_at = cancel_dt
        appointment.cancellation_fee = fee
        appointment.is_late_cancellation = is_late
        appointment.cancellation_reason = reason or "Patient requested cancellation."

        db.session.commit()

        return {
            "success": True,
            "message": (
                f"Appointment cancelled. Late fee of ${fee:.2f} applied."
                if (is_late and not waive_fee)
                else "Appointment cancelled in good time. No fee charged."
            ),
            "fee": fee,
            "is_late": is_late,
            "fee_waived": waive_fee,
            "appointment": appointment.to_dict(),
        }

    @staticmethod
    def get_doctor_day_schedule(doctor_id: int, target_date: date) -> Dict[str, Any]:
        """
        Returns full breakdown of the doctor's day:
        - All regular time slots (marked as available or booked)
        - Confirmed booked appointments
        - Cancelled appointments (for audit visibility)
        """
        doctor = db.session.get(Doctor, doctor_id)
        if not doctor:
            return {"success": False, "error": "Doctor not found."}

        day_start = datetime.combine(target_date, doctor.shift_start or time(9, 0))
        day_end = datetime.combine(target_date, doctor.shift_end or time(17, 0))
        slot_duration = timedelta(minutes=doctor.slot_duration_mins or 30)

        # Retrieve all appointments for that day
        day_beginning = datetime.combine(target_date, time(0, 0, 0))
        day_ending = datetime.combine(target_date, time(23, 59, 59))

        all_appointments = (
            Appointment.query.filter(
                Appointment.doctor_id == doctor_id,
                Appointment.start_time >= day_beginning,
                Appointment.start_time <= day_ending,
            )
            .order_by(Appointment.start_time)
            .all()
        )

        booked_appointments = [a for a in all_appointments if a.status == "BOOKED"]
        cancelled_appointments = [a for a in all_appointments if a.status == "CANCELLED"]

        # Generate timeline slots from shift_start to shift_end
        timeline = []
        curr_time = day_start
        while curr_time + slot_duration <= day_end:
            slot_end = curr_time + slot_duration

            # Find matching booked appointment if any
            matched_booking = None
            for apt in booked_appointments:
                # If slot overlaps with booked appointment
                if apt.start_time < slot_end and apt.end_time > curr_time:
                    matched_booking = apt
                    break

            if matched_booking:
                timeline.append({
                    "type": "BOOKED",
                    "slot_start": curr_time.strftime("%H:%M"),
                    "slot_end": slot_end.strftime("%H:%M"),
                    "appointment": matched_booking.to_dict(),
                })
            else:
                timeline.append({
                    "type": "AVAILABLE",
                    "slot_start": curr_time.strftime("%H:%M"),
                    "slot_end": slot_end.strftime("%H:%M"),
                    "start_iso": curr_time.strftime("%Y-%m-%d %H:%M"),
                    "end_iso": slot_end.strftime("%Y-%m-%d %H:%M"),
                })

            curr_time += slot_duration

        return {
            "success": True,
            "doctor": doctor.to_dict(),
            "date": target_date.strftime("%Y-%m-%d"),
            "working_hours": f"{doctor.shift_start.strftime('%H:%M')} - {doctor.shift_end.strftime('%H:%M')}",
            "slot_duration_mins": doctor.slot_duration_mins,
            "timeline": timeline,
            "booked_count": len(booked_appointments),
            "cancelled_count": len(cancelled_appointments),
            "cancelled_appointments": [a.to_dict() for a in cancelled_appointments],
        }

    @staticmethod
    def search_patient_appointments(query_str: str) -> List[Dict[str, Any]]:
        """Searches patient by name or phone and returns all their appointments."""
        query_str = query_str.strip()
        if not query_str:
            return []

        search_filter = or_(
            Patient.name.ilike(f"%{query_str}%"),
            Patient.phone.like(f"%{query_str}%"),
        )
        patients = Patient.query.filter(search_filter).limit(20).all()

        results = []
        for p in patients:
            apts = (
                Appointment.query.filter_by(patient_id=p.id)
                .order_by(Appointment.start_time.desc())
                .all()
            )
            results.append({
                "patient": p.to_dict(),
                "appointments": [a.to_dict() for a in apts],
                "active_count": sum(1 for a in apts if a.status == "BOOKED"),
                "total_cancellation_fees": sum(float(a.cancellation_fee or 0) for a in apts),
            })

        return results
