from datetime import datetime, timezone, time
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utc_now():
    return datetime.now(timezone.utc)


class Doctor(db.Model):
    __tablename__ = "doctors"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    specialty = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    shift_start = db.Column(db.Time, default=time(9, 0), nullable=False)
    shift_end = db.Column(db.Time, default=time(17, 0), nullable=False)
    slot_duration_mins = db.Column(db.Integer, default=30, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    appointments = db.relationship(
        "Appointment",
        backref="doctor",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "specialty": self.specialty,
            "email": self.email,
            "phone": self.phone,
            "shift_start": self.shift_start.strftime("%H:%M") if self.shift_start else "09:00",
            "shift_end": self.shift_end.strftime("%H:%M") if self.shift_end else "17:00",
            "slot_duration_mins": self.slot_duration_mins,
            "is_active": self.is_active,
        }


class Patient(db.Model):
    __tablename__ = "patients"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    phone = db.Column(db.String(30), nullable=False, index=True)
    email = db.Column(db.String(120), nullable=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    appointments = db.relationship(
        "Appointment",
        backref="patient",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "date_of_birth": self.date_of_birth.strftime("%Y-%m-%d") if self.date_of_birth else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Appointment(db.Model):
    __tablename__ = "appointments"

    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False, index=True)
    start_time = db.Column(db.DateTime, nullable=False, index=True)
    end_time = db.Column(db.DateTime, nullable=False, index=True)
    status = db.Column(
        db.String(20),
        default="BOOKED",
        nullable=False,
        index=True,
    )  # BOOKED, CANCELLED, COMPLETED, NO_SHOW
    cancellation_fee = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    is_late_cancellation = db.Column(db.Boolean, default=False, nullable=False)
    cancellation_reason = db.Column(db.Text, nullable=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    fee_waived = db.Column(db.Boolean, default=False, nullable=False)
    waiver_reason = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    
    # Twists support: reminders, completion, no-shows
    reminder_sent = db.Column(db.Boolean, default=False, nullable=False)
    reminder_sent_at = db.Column(db.DateTime, nullable=True)
    no_show_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        db.Index("idx_doctor_schedule", "doctor_id", "start_time", "end_time", "status"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "doctor_id": self.doctor_id,
            "doctor_name": self.doctor.name if self.doctor else None,
            "doctor_specialty": self.doctor.specialty if self.doctor else None,
            "patient_id": self.patient_id,
            "patient_name": self.patient.name if self.patient else None,
            "patient_phone": self.patient.phone if self.patient else None,
            "start_time": self.start_time.strftime("%Y-%m-%d %H:%M"),
            "end_time": self.end_time.strftime("%Y-%m-%d %H:%M"),
            "status": self.status,
            "cancellation_fee": float(self.cancellation_fee) if self.cancellation_fee is not None else 0.0,
            "is_late_cancellation": self.is_late_cancellation,
            "cancellation_reason": self.cancellation_reason,
            "cancelled_at": self.cancelled_at.strftime("%Y-%m-%d %H:%M:%S") if self.cancelled_at else None,
            "fee_waived": self.fee_waived,
            "waiver_reason": self.waiver_reason,
            "notes": self.notes,
            "reminder_sent": self.reminder_sent,
            "reminder_sent_at": self.reminder_sent_at.strftime("%Y-%m-%d %H:%M:%S") if self.reminder_sent_at else None,
            "no_show_at": self.no_show_at.strftime("%Y-%m-%d %H:%M:%S") if self.no_show_at else None,
            "completed_at": self.completed_at.strftime("%Y-%m-%d %H:%M:%S") if self.completed_at else None,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }


class NotificationOutbox(db.Model):
    __tablename__ = "notification_outbox"

    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, nullable=True, index=True)
    patient_id = db.Column(db.Integer, nullable=True)
    patient_name = db.Column(db.String(100), nullable=True)
    recipient = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), default="REMINDER", nullable=False)
    sent_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "appointment_id": self.appointment_id,
            "patient_id": self.patient_id,
            "patient_name": self.patient_name,
            "recipient": self.recipient,
            "phone": self.recipient,
            "message": self.message,
            "type": self.notification_type,
            "sent_at": self.sent_at.strftime("%Y-%m-%d %H:%M:%S") if self.sent_at else None,
            "timestamp": self.sent_at.isoformat() if self.sent_at else None,
        }


class ClinicSetting(db.Model):
    __tablename__ = "clinic_settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(255), nullable=True)

    @classmethod
    def get_val(cls, key: str, default=None):
        setting = cls.query.filter_by(key=key).first()
        if setting:
            return setting.value
        return default

    @classmethod
    def set_val(cls, key: str, value, description=None):
        setting = cls.query.filter_by(key=key).first()
        if not setting:
            setting = cls(key=key, value=str(value), description=description)
            db.session.add(setting)
        else:
            setting.value = str(value)
            if description:
                setting.description = description
        db.session.commit()
        return setting
