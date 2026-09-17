# CareFlow Clinic — Front-Desk Booking & Fair Cancellation System

A full-stack clinic scheduling and front-desk automation system built with **Flask**, **MySQL**, and modern responsive web technologies. Designed specifically to eliminate doctor double-booking, enforce fair cancellation fees, provide physician daily schedule visibility, and automate lifecycle workflows (rescheduling, morning reminders via Notification Service, and automated no-show tracking).

---

## Evaluation Files in Root Folder

As required for evaluation, this repository contains three core root documentation files:
1. [README.md](file:///c:/Users/madhu/Documents/ClinicApp/README.md) — How to set up, run, test, and debug the project, plus the complete list of API endpoints.
2. [REASONING.md](file:///c:/Users/madhu/Documents/ClinicApp/REASONING.md) — The comprehensive thought process, mathematical invariant proofs, concurrency locking strategy, and step-by-step issue resolutions.
3. [AI_LOGS.md](file:///c:/Users/madhu/Documents/ClinicApp/AI_LOGS.md) — The complete, unaltered conversation transcript with the AI tool throughout the project.

---

## Key Features

### 1. Conflict-Free Booking Engine (Never Double-Book)
- **Strict Interval Overlap Detection**: An appointment is only allowed if no other active (`BOOKED`) appointment for that doctor satisfies:
  $$\text{Existing.Start} < \text{Requested.End} \quad\text{and}\quad \text{Existing.End} > \text{Requested.Start}$$
- **Atomic Concurrency Protection**: Uses transactional row locking (`with_for_update`) to prevent race conditions when multiple receptionists book simultaneously.
- **Doctor Shift Hours**: Enforces start and end of shifts (e.g. 09:00 - 17:00).
- **Independent Schedules**: Physicians maintain independent schedules—Dr. Patel and Dr. Chen can have appointments at the exact same hour without collision.

### 2. Fair Cancellation Policy & Immediate Slot Recovery
- **Notice Cutoff Evaluation**:
  $$\Delta t = \text{Appointment.Start} - \text{Cancellation.Time}$$
  - **$\ge 24\text{ hours}$ notice**: **100% Free** (`fee = $0.00`).
  - **$< 24\text{ hours}$ notice**: **Late Cancellation Fee** (`fee = $25.00`).
- **Immediate Slot Liberation**: Cancelled appointments immediately free their time slot on the schedule so another patient can book it without delay.
- **Emergency Waiver**: Front desk staff can check *"Waive late cancellation fee"* with an audit reason (e.g. hospitalization, medical emergency).
- **Customizable Policy**: Cutoff hours and fee amount can be adjusted dynamically from the UI or `.env`.

### 3. Extended Twists (T6, T1, T2)
- **Level 1 — T6 (Lifecycle Rescheduling)**: Front desk can reschedule an appointment to a new date and time. It strictly preserves the same patient and doctor while re-running full conflict-free overlap validation (excluding its own appointment record to prevent self-collision false positives).
- **Level 2 — T1 (Notification Service Integration via `/outbox`)**: Each morning, patients with appointments today receive reminders in the Notification Service outbox. Graded via `GET /outbox` after `POST /clock`. Includes idempotency guard to prevent duplicate reminder dispatches.
- **Level 3 — T2 (Automated No-Show Tracking)**: An automated background job transitions unattended appointments to `NO_SHOW` 30 minutes after their start time. Driven by `POST /clock`. Patients checked in via `POST /appointments/<id>/complete` are preserved as `COMPLETED`.

---

## Tech Stack

- **Backend**: Python 3.13, Flask 3.1, Flask-SQLAlchemy 3.1
- **Database**: MySQL 8.0 (via `PyMySQL` and `cryptography`), with automatic SQLite fallback (`clinic.db`) for zero-config local testing
- **Frontend**: HTML5, Tailwind CSS, Vanilla ES6+ JavaScript, Plus Jakarta Sans typography
- **Testing**: Pytest (17 automated unit and integration tests)

---

## Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/Luckycoder9610/Clinic_appo.git
cd Clinic_appo
```

### 2. Install Python Dependencies
```bash
python -m pip install -r requirements.txt
```

### 3. Configure Database (.env)
Copy the template configuration:
```bash
cp .env.example .env
```
Open `.env` and configure your MySQL credentials:
```ini
DB_TYPE=mysql
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_HOST=localhost
DB_PORT=3306
DB_NAME=clinic_db

CANCELLATION_CUTOFF_HOURS=24
LATE_CANCELLATION_FEE=25.00
```
> **Resilient Fallback**: If `DB_PASSWORD` is not yet set or MySQL is unavailable, the application gracefully initializes a local `clinic.db` SQLite database so you can test immediately.

### 4. Initialize & Seed Database
Run the bootstrap script to create tables and seed realistic sample doctors, patients, and schedules:
```bash
python init_db.py
```

### 5. Run the Application
```bash
python app.py
```
Open your browser and navigate to:
👉 **`http://127.0.0.1:5000`**

---

## Complete API Documentation

### Core Scheduling & Lookups
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/doctors` | List all active physicians |
| `POST` | `/api/doctors` | Add a new doctor with specialty and shift hours |
| `GET` | `/api/doctors/<id>/day?date=YYYY-MM-DD` | Get doctor's full day schedule (booked, available, and cancelled slots) |
| `POST` | `/api/appointments` | Book appointment (returns `409 Conflict` if overlapping) |
| `GET` | `/api/appointments/<id>` | Retrieve appointment details |
| `GET` | `/api/appointments/<id>/preview-cancel` | Preview notice hours and late cancellation fee |
| `POST` | `/api/appointments/<id>/cancel` | Cancel appointment, apply fee, and immediately liberate slot |
| `GET` | `/api/patients/search?q=<term>` | Search appointments by patient name or phone number |
| `GET` | `/api/settings` | Get current cancellation policy settings |
| `PUT` | `/api/settings` | Update cutoff hours or late fee |
| `GET` | `/health` | Application and database health check |

### Twists Endpoints (T6, T1, T2)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/appointments/<id>/reschedule` | **Level 1 (T6)**: Reschedule appointment (preserves patient & doctor, re-checks conflicts) |
| `POST` | `/appointments/<id>/complete` | Mark patient attended / completed (protects against no-show) |
| `POST` | `/clock` | **Level 2 & 3**: Advance or set simulated clock. Triggers morning reminders and auto-marks no-shows ($\ge 30\text{m}$) |
| `GET` | `/clock` | Get current simulated clock timestamp |
| `GET` | `/outbox` | **Level 2 (T1)**: Retrieve Notification Service outbox messages (graded by harness) |
| `POST` | `/outbox/clear` | Clear outbox notifications (test reset helper) |

*Note: All twist routes are accessible both at root (`/clock`, `/outbox`, `/appointments/...`) and under `/api/...` for full test compatibility.*

---

## Running Automated Tests

Run the complete 17-test automated test suite:
```bash
python -m pytest -v tests/
```

### Test Coverage Breakdown:
1. **Double-Booking & Conflict Invariants (`tests/test_booking.py`)**:
   - `test_conflict_free_booking_exact_overlap`: Exact slot collision blocked.
   - `test_conflict_free_booking_partial_and_enclosing_overlaps`: Left overlap, right overlap, enclosing, and sub-intervals blocked.
   - `test_adjacent_slots_and_different_doctors_allowed`: Back-to-back appointments and multi-doctor independence confirmed.
   - `test_working_hours_validation`: Rejection of appointments outside physician shift hours.
2. **Fair Cancellation Invariants (`tests/test_booking.py`)**:
   - `test_fair_cancellation_in_good_time_is_free`: Free cancellation for $\ge 24\text{h}$ notice.
   - `test_fair_cancellation_late_carries_fee`: $25 late fee assessed for $< 24\text{h}$ notice.
   - `test_late_cancellation_waiver`: Receptionist emergency fee waiver with audit trail.
   - `test_immediate_slot_recovery_after_cancellation`: Liberated slot can be booked immediately.
   - `test_doctor_day_schedule_generation`: Complete daily schedule generation.
   - `test_patient_search_and_appointment_history`: Fuzzy patient name and phone lookup.
3. **Twists Verification (`tests/test_twists.py`)**:
   - `test_reschedule_preserves_doctor_and_patient`: Strict preservation of doctor and patient identity.
   - `test_reschedule_rejects_overlapping_slot`: Overlap rejection on reschedule.
   - `test_reschedule_excludes_self_from_conflict`: Moving slot within partial own window allowed (no self-conflict).
   - `test_morning_reminders_sent_to_outbox`: Dispatches reminders for today's visits to `/outbox` via `POST /clock`.
   - `test_morning_reminders_idempotency`: No duplicate reminders on repeated morning clock pulses.
   - `test_auto_mark_noshow_30_min_after_start`: Transition from `BOOKED` to `NO_SHOW` 30 minutes after start time.
   - `test_completed_appointment_not_marked_noshow`: Attended appointments are protected from no-show transition.

---

## Debugging Guide

### 1. Database Inspection
- **SQLite (Default dev)**:
  Inspect tables directly using Python:
  ```powershell
  python -c "from app import create_app; from models import Appointment; app=create_app(); with app.app_context(): print([(a.id, a.start_time, a.status) for a in Appointment.query.all()])"
  ```
- **MySQL**:
  Connect using MySQL client:
  ```powershell
  mysql -u root -p clinic_db
  SELECT id, doctor_id, start_time, end_time, status, cancellation_fee FROM appointments;
  SELECT * FROM notification_outbox;
  ```

### 2. Testing Conflicts via `curl`
Attempt to book two overlapping slots for Dr. Sarah Chen (Doctor ID 1):
```powershell
# First booking: 10:00 - 10:30
curl -X POST http://127.0.0.1:5000/api/appointments -H "Content-Type: application/json" -d "{\"doctor_id\": 1, \"start_time\": \"2026-10-25 10:00\", \"duration_mins\": 30, \"patient_name\": \"Patient A\", \"patient_phone\": \"555-0001\"}"

# Second overlapping booking: 10:15 - 10:45 -> Returns HTTP 409 Conflict
curl -X POST http://127.0.0.1:5000/api/appointments -H "Content-Type: application/json" -d "{\"doctor_id\": 1, \"start_time\": \"2026-10-25 10:15\", \"duration_mins\": 30, \"patient_name\": \"Patient B\", \"patient_phone\": \"555-0002\"}"
```

### 3. Testing Clock Automation & Outbox via `curl`
```powershell
# Set clock to morning 08:00
curl -X POST http://127.0.0.1:5000/clock -H "Content-Type: application/json" -d "{\"timestamp\": \"2026-09-17T08:00:00\"}"

# Inspect notification outbox
curl http://127.0.0.1:5000/outbox

# Advance clock 30 minutes to trigger auto-no-show
curl -X POST http://127.0.0.1:5000/clock -H "Content-Type: application/json" -d "{\"advance_minutes\": 30}"
```
