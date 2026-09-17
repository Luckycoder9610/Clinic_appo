from datetime import datetime, date, time, timedelta
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy import and_, or_
from models import db, Doctor, Patient, Appointment, NotificationOutbox, ClinicSetting
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
            try:
                query = query.with_for_update()
            except Exception:
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
        """Atomically books an appointment for a doctor and patient."""
        if start_time >= end_time:
            return {"success": False, "error": "Start time must be before end time."}

        doctor = db.session.get(Doctor, doctor_id)
        if not doctor:
            return {"success": False, "error": "Doctor not found."}
        doc_name = doctor.name if doctor.name.startswith("Dr.") else f"Dr. {doctor.name}"
        if not doctor.is_active:
            return {"success": False, "error": f"{doc_name} is currently inactive."}

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
            if patient_name and patient.name != patient_name.strip():
                patient.name = patient_name.strip()
            if patient_email and patient.email != patient_email.strip():
                patient.email = patient_email.strip()

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

    # =========================================================================
    # LEVEL 1 — T6 (LIFECYCLE): RESCHEDULING AN APPOINTMENT
    # =========================================================================
    @staticmethod
    def reschedule_appointment(
        appointment_id: int,
        new_start_time: datetime,
        new_end_time: Optional[datetime] = None,
        duration_mins: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Reschedules an appointment to a new time.
        Invariants:
        1. Keeps the EXACT same patient and doctor.
        2. Must stay conflict-free (re-checks overlap excluding this appointment).
        3. Enforces doctor shift working hours.
        """
        appointment = db.session.get(Appointment, appointment_id)
        if not appointment:
            return {"success": False, "error": "Appointment not found."}

        if appointment.status != "BOOKED":
            return {
                "success": False,
                "error": f"Only booked appointments can be rescheduled. Current status: {appointment.status}.",
            }

        doctor = db.session.get(Doctor, appointment.doctor_id)
        if not doctor:
            return {"success": False, "error": "Doctor not found."}
        doc_name = doctor.name if doctor.name.startswith("Dr.") else f"Dr. {doctor.name}"

        # Calculate new_end_time
        if new_end_time is None:
            if duration_mins:
                new_end_time = new_start_time + timedelta(minutes=int(duration_mins))
            else:
                original_duration = appointment.end_time - appointment.start_time
                new_end_time = new_start_time + original_duration

        if new_start_time >= new_end_time:
            return {"success": False, "error": "New start time must be before new end time."}

        # Validate doctor working hours
        shift_start_time = doctor.shift_start or time(9, 0)
        shift_end_time = doctor.shift_end or time(17, 0)
        slot_start_time = new_start_time.time()
        slot_end_time = new_end_time.time()

        if slot_start_time < shift_start_time or slot_end_time > shift_end_time:
            return {
                "success": False,
                "error": f"Rescheduled time ({new_start_time.strftime('%H:%M')} - {new_end_time.strftime('%H:%M')}) "
                f"falls outside {doc_name}'s working hours ({shift_start_time.strftime('%H:%M')} - {shift_end_time.strftime('%H:%M')}).",
            }

        # Concurrency-safe overlap check excluding this appointment
        conflict = BookingService.check_conflict(
            doctor_id=appointment.doctor_id,
            start_time=new_start_time,
            end_time=new_end_time,
            exclude_appointment_id=appointment.id,
            lock_for_update=True,
        )

        if conflict:
            conflicting_patient = conflict.patient.name if conflict.patient else "Another patient"
            return {
                "success": False,
                "conflict": True,
                "error": f"Slot conflict! Cannot reschedule: {doc_name} already has an appointment booked from "
                f"{conflict.start_time.strftime('%H:%M')} to {conflict.end_time.strftime('%H:%M')} "
                f"(Patient: {conflicting_patient}).",
                "conflicting_appointment_id": conflict.id,
            }

        # If date changes, reset reminder_sent so patient can receive reminder for new date
        if new_start_time.date() != appointment.start_time.date():
            appointment.reminder_sent = False
            appointment.reminder_sent_at = None

        appointment.start_time = new_start_time
        appointment.end_time = new_end_time
        db.session.commit()

        return {
            "success": True,
            "message": f"Appointment successfully rescheduled to {new_start_time.strftime('%Y-%m-%d %H:%M')}.",
            "appointment": appointment.to_dict(),
        }

    # =========================================================================
    # COMPLETION
    # =========================================================================
    @staticmethod
    def mark_completed(appointment_id: int) -> Dict[str, Any]:
        """Marks an appointment as COMPLETED when the patient attends the visit."""
        appointment = db.session.get(Appointment, appointment_id)
        if not appointment:
            return {"success": False, "error": "Appointment not found."}

        if appointment.status != "BOOKED":
            return {
                "success": False,
                "error": f"Cannot mark appointment as completed. Current status: {appointment.status}.",
            }

        appointment.status = "COMPLETED"
        appointment.completed_at = datetime.now()
        db.session.commit()

        return {
            "success": True,
            "message": "Appointment marked as completed.",
            "appointment": appointment.to_dict(),
        }

    # =========================================================================
    # LEVEL 2 & 3: CLOCK, MORNING REMINDERS & AUTO NO-SHOWS
    # =========================================================================
    @staticmethod
    def get_simulated_clock() -> datetime:
        """Returns the current simulated clock time, or now() if not set."""
        val = ClinicSetting.get_val("simulated_clock")
        if val:
            try:
                return datetime.fromisoformat(val)
            except Exception:
                pass
        return datetime.now()

    @staticmethod
    def set_simulated_clock(clock_time: datetime) -> Dict[str, Any]:
        """
        Sets the clinic clock and executes automated morning reminders & no-show detection.
        """
        ClinicSetting.set_val("simulated_clock", clock_time.isoformat(), "Simulated clock timestamp")

        # Level 2 (T1): Trigger morning reminders for today's appointments
        reminders_count = BookingService.trigger_morning_reminders(clock_time)

        # Level 3 (T2): Trigger auto-marking no-shows (30 min after start)
        no_shows_count = BookingService.trigger_auto_no_shows(clock_time)

        return {
            "success": True,
            "clock": clock_time.isoformat(),
            "clock_formatted": clock_time.strftime("%Y-%m-%d %H:%M:%S"),
            "reminders_sent": reminders_count,
            "no_shows_marked": no_shows_count,
        }

    @staticmethod
    def trigger_morning_reminders(current_time: datetime) -> int:
        """
        Level 2 — T1: Each morning, remind patients of today's appointments via Notification Service outbox.
        """
        target_date = current_time.date()
        day_start = datetime.combine(target_date, time(0, 0, 0))
        day_end = datetime.combine(target_date, time(23, 59, 59))

        # Find all active appointments today that have NOT yet received a reminder
        todays_appointments = (
            Appointment.query.filter(
                Appointment.status == "BOOKED",
                Appointment.start_time >= day_start,
                Appointment.start_time <= day_end,
                Appointment.reminder_sent == False,
            )
            .all()
        )

        sent_count = 0
        for apt in todays_appointments:
            doctor = apt.doctor
            doc_name = doctor.name if doctor and doctor.name.startswith("Dr.") else f"Dr. {doctor.name if doctor else 'Physician'}"
            patient = apt.patient
            pat_name = patient.name if patient else "Patient"
            recipient = patient.phone if (patient and patient.phone) else (patient.email if patient else "Patient")

            msg_text = (
                f"Reminder: Hello {pat_name}, you have an appointment today at "
                f"{apt.start_time.strftime('%H:%M')} with {doc_name}."
            )

            outbox_entry = NotificationOutbox(
                appointment_id=apt.id,
                patient_id=apt.patient_id,
                patient_name=pat_name,
                recipient=recipient,
                message=msg_text,
                notification_type="REMINDER",
                sent_at=current_time,
            )
            db.session.add(outbox_entry)
            apt.reminder_sent = True
            apt.reminder_sent_at = current_time
            sent_count += 1

        if sent_count > 0:
            db.session.commit()

        return sent_count

    @staticmethod
    def trigger_auto_no_shows(current_time: datetime) -> int:
        """
        Level 3 — T2: Auto-mark appointments as no-show 30 min after their start if not completed.
        """
        # Threshold: start_time + 30m <= current_time => start_time <= current_time - 30m
        threshold_time = current_time - timedelta(minutes=30)

        unattended = (
            Appointment.query.filter(
                Appointment.status == "BOOKED",
                Appointment.start_time <= threshold_time,
            )
            .all()
        )

        marked_count = 0
        for apt in unattended:
            apt.status = "NO_SHOW"
            apt.no_show_at = current_time
            marked_count += 1

        if marked_count > 0:
            db.session.commit()

        return marked_count

    @staticmethod
    def get_outbox() -> List[Dict[str, Any]]:
        """Retrieves all notifications in the notification outbox."""
        entries = NotificationOutbox.query.order_by(NotificationOutbox.id.asc()).all()
        return [e.to_dict() for e in entries]

    @staticmethod
    def clear_outbox() -> int:
        """Clears all outbox entries (useful for testing)."""
        count = NotificationOutbox.query.delete()
        db.session.commit()
        return count

    # =========================================================================
    # CANCELLATION & PREVIEW
    # =========================================================================
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
        cancel_dt = cancellation_time or BookingService.get_simulated_clock()

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
        """Cancels an appointment, enforces late fee policy, and frees slot."""
        appointment = db.session.get(Appointment, appointment_id)
        if not appointment:
            return {"success": False, "error": "Appointment not found."}

        if appointment.status != "BOOKED":
            return {
                "success": False,
                "error": f"Appointment cannot be cancelled because it is {appointment.status.lower()}.",
            }

        cancel_dt = cancellation_time or BookingService.get_simulated_clock()
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
        """Returns full breakdown of the doctor's day."""
        doctor = db.session.get(Doctor, doctor_id)
        if not doctor:
            return {"success": False, "error": "Doctor not found."}

        day_start = datetime.combine(target_date, doctor.shift_start or time(9, 0))
        day_end = datetime.combine(target_date, doctor.shift_end or time(17, 0))
        slot_duration = timedelta(minutes=doctor.slot_duration_mins or 30)

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

        booked_appointments = [a for a in all_appointments if a.status in ("BOOKED", "COMPLETED", "NO_SHOW")]
        cancelled_appointments = [a for a in all_appointments if a.status == "CANCELLED"]

        timeline = []
        curr_time = day_start
        while curr_time + slot_duration <= day_end:
            slot_end = curr_time + slot_duration

            matched_booking = None
            for apt in booked_appointments:
                if apt.start_time < slot_end and apt.end_time > curr_time:
                    matched_booking = apt
                    break

            if matched_booking:
                timeline.append({
                    "type": matched_booking.status,
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
            "booked_count": sum(1 for a in booked_appointments if a.status == "BOOKED"),
            "completed_count": sum(1 for a in booked_appointments if a.status == "COMPLETED"),
            "noshow_count": sum(1 for a in booked_appointments if a.status == "NO_SHOW"),
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
