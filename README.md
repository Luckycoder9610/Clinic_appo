# CareFlow Clinic — Front-Desk Booking & Fair Cancellation System

A full-stack clinic management system tailored specifically for front-desk receptionists. Built with **Flask**, **MySQL**, and modern responsive web technologies to eliminate the two biggest front-desk headaches: **doctor double-booking** and **unfair cancellation handling**.

---

## Key Features

### 1. Conflict-Free Booking Engine (Never Double-Book)
- **Strict Interval Overlap Detection**: An appointment is only allowed if no other active (`BOOKED`) appointment for that doctor satisfies:
  $$\text{Existing.Start} < \text{Requested.End} \quad\text{and}\quad \text{Existing.End} > \text{Requested.Start}$$
- **Atomic Locking**: Uses transactional row locking (`with_for_update`) to prevent race conditions when multiple receptionists book at the same moment.
- **Doctor Shift Enforcement**: Rejects bookings scheduled outside a doctor's shift hours.
- **Independent Schedules**: Doctors have completely independent schedules—Dr. Patel and Dr. Chen can comfortably have appointments at the same time.

### 2. Fair Cancellation Policy
- **Transparent Notice Rule**:
  $$\Delta t = \text{Appointment.Start} - \text{Cancellation.Time}$$
  - **$\ge 24\text{ hours}$ notice**: **Free of charge** (`fee = $0.00`). Receptionist receives an immediate green confirmation: *"Cancelled in good time — No fee charged."*
  - **$< 24\text{ hours}$ notice**: **Late cancellation fee** (`fee = $25.00`). Receptionist is shown an explicit policy notice with the fee amount.
- **Immediate Slot Recovery**: The instant an appointment is cancelled, its status changes to `CANCELLED` and the time slot is immediately liberated for other patients to book.
- **Emergency Waiver**: Front desk staff can check *"Waive late cancellation fee"* with an audit reason (e.g. hospitalization, medical emergency).
- **Customizable Policy**: Cutoff hours and fee amount can be adjusted directly from the front-desk UI or `.env`.

### 3. Front Desk Operations & Lookups
- **Doctor's Day Schedule View**: Interactive daily timeline for any physician and date showing booked slots, available open slots, patient names, and cancelled visits.
- **One-Click Quick Booking**: Click any open slot on the timeline to pre-fill the doctor, date, and start time.
- **Patient Appointment Lookup**: Instant search-as-you-type by patient name or phone number with active booking counts, appointment history, and fee breakdown.
- **Physician Roster**: Directory of doctors with working hours and custom slot durations (15m, 30m, 45m, 60m).

---

## Tech Stack

- **Backend**: Python 3.13, Flask 3.1, Flask-SQLAlchemy 3.1
- **Database**: MySQL 8.0 (via `PyMySQL` and `cryptography`), with automatic SQLite fallback for zero-config local testing
- **Frontend**: HTML5, Tailwind CSS, Vanilla ES6+ JavaScript, Plus Jakarta Sans typography
- **Test Suite**: Pytest (10 comprehensive automated unit & integration tests)

---

## Installation & Setup

### 1. Clone or Open the Repository
```bash
cd ClinicApp
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
> **Note**: If `DB_PASSWORD` is left empty or MySQL is unavailable, the system automatically uses a local `clinic.db` SQLite database so you can test and use the application immediately.

### 4. Initialize & Seed the Database
Run the bootstrap script to create tables and seed realistic sample doctors, patients, and schedules:
```bash
python init_db.py
```

### 5. Run the Application
```bash
python app.py
```
Open your browser and navigate to:
**`http://127.0.0.1:5000`**

---

## Running the Automated Test Suite

Run pytest to verify all overlap rules, cancellation fees, slot liberation, and search lookups:
```bash
python -m pytest -v
```

All 10 tests will execute:
- `test_conflict_free_booking_exact_overlap`: Verifies exact collision rejection.
- `test_conflict_free_booking_partial_and_enclosing_overlaps`: Tests left-overlap, right-overlap, enclosing, and sub-intervals.
- `test_adjacent_slots_and_different_doctors_allowed`: Confirms back-to-back bookings and multi-doctor independence.
- `test_working_hours_validation`: Rejects bookings outside doctor shifts.
- `test_fair_cancellation_in_good_time_is_free`: Verifies $0 fee when notice $\ge 24\text{ hours}$.
- `test_fair_cancellation_late_carries_fee`: Verifies $25 fee when notice $< 24\text{ hours}$.
- `test_late_cancellation_waiver`: Tests receptionist emergency fee waivers.
- `test_immediate_slot_recovery_after_cancellation`: Confirms cancelled slots can be booked immediately.
- `test_doctor_day_schedule_generation`: Tests full timeline generation.
- `test_patient_search_and_appointment_history`: Tests fast patient name/phone lookups.

---

## API Documentation

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/doctors` | List all active physicians |
| `POST` | `/api/doctors` | Add a new doctor to the roster |
| `GET` | `/api/doctors/<id>/day?date=YYYY-MM-DD` | Get doctor's full day timeline (open & booked slots) |
| `POST` | `/api/appointments` | Book appointment (returns `409 Conflict` if overlapping) |
| `GET` | `/api/appointments/<id>/preview-cancel` | Preview notice hours and late fee |
| `POST` | `/api/appointments/<id>/cancel` | Cancel appointment, apply fee, and liberate slot |
| `GET` | `/api/patients/search?q=<term>` | Search appointments by patient name or phone |
| `GET` | `/api/settings` | Get cancellation policy settings |
| `PUT` | `/api/settings` | Update cutoff hours or late fee |

---

## Pushing to GitHub / Remote Git

To publish this project to your GitHub account:

```bash
# 1. Initialize git (if not already initialized)
git init

# 2. Stage and commit all files
git add .
git commit -m "Initial commit: Clinic appointment booking and fair cancellation system"

# 3. Rename branch to main
git branch -M main

# 4. Link your remote repository (replace with your GitHub repository URL)
git remote add origin https://github.com/<your-username>/<your-repo-name>.git

# 5. Push code to remote
git push -u origin main
```
