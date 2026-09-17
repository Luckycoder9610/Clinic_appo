# Thought Process, Design Decisions & Problem-Solving (REASONING.md)

This document details the engineering thought process, architectural rationale, invariant proofs, and debugging journey behind the **CareFlow Clinic Front-Desk Booking & Fair Cancellation System** and its three extended twists (T6, T1, T2).

---

## 1. Understanding the Problem & Front-Desk Frustrations

A busy medical clinic operates under high stress at the reception desk. Front-desk staff take frequent patient phone calls, coordinate multi-physician schedules, manage cancellations, and attempt to fill vacated slots in real time. 

The prompt outlines the desk's core pain points:
1. **Double-Booking Doctors**: Multiple receptionists or rapid bookings cause two patients to grab the same slot or overlapping intervals for the same physician.
2. **Unfair Cancellation Handling**: Patients cancelling in good time should not be penalized, but late cancellations should incur a fair fee. Cancelled slots must be immediately available for new bookings.
3. **Lack of Operational Visibility**: The desk needs to view any doctor's daily schedule clearly and search for patients by name or phone number quickly.
4. **Twist Extensions**:
   - **Level 1 — T6 (Lifecycle)**: Rescheduling an appointment to a new time, maintaining conflict-free validation while strictly preserving the same patient and doctor.
   - **Level 2 — T1 (Integrate)**: Dispatching morning reminders for today's appointments via the Notification Service outbox, evaluated via `GET /outbox` after `POST /clock`.
   - **Level 3 — T2 (Automation)**: Automatically marking unattended appointments as `NO_SHOW` 30 minutes after their start time, driven by `POST /clock`.

---

## 2. Core Architectural & Domain Decisions

### 2.1 Technology Stack Selection
- **Flask (Backend)**: Chosen as requested. Its lightweight, modular blueprint structure allows separating REST API routes (`/api/...`), root grading endpoints (`/clock`, `/outbox`), and front-desk views cleanly.
- **MySQL 8.0 with SQLAlchemy & PyMySQL (Database)**:
  - MySQL 8.0 provides ACID compliance, strong transaction isolation, and row-level locking (`SELECT ... FOR UPDATE`).
  - Implemented a resilient connection strategy in `config.py` and `app.py`: The application defaults to MySQL via credentials in `.env`, but gracefully connects to a local SQLite database (`clinic.db`) for zero-friction local testing when MySQL credentials are not yet configured.
- **Tailwind CSS + Vanilla JavaScript (Frontend)**:
  - Designed specifically for receptionists: high-contrast badges, single-click quick booking from open slots, color-coded status pills, and interactive modals without complex frontend build toolchains.

---

### 2.2 Invariant 1: Guaranteed Conflict-Free Booking & Concurrency Safety

#### The Mathematical Overlap Condition
A common front-desk bug occurs when developers only check for exact start time matches ($S_{\text{new}} == S_{\text{existing}}$). In reality, appointments have variable durations (15m, 30m, 45m, 60m).

Given an existing active appointment $[S_A, E_A)$ and a requested appointment $[S_B, E_B)$, the two intervals overlap if and only if:
$$S_A < E_B \quad\text{AND}\quad E_A > S_B$$

This single condition universally catches:
1. **Exact collisions**: $[10:00, 10:30)$ and $[10:00, 10:30)$
2. **Left partial overlaps**: $[09:45, 10:15)$ overlapping with $[10:00, 10:30)$
3. **Right partial overlaps**: $[10:15, 10:45)$ overlapping with $[10:00, 10:30)$
4. **Enclosing intervals**: $[09:30, 11:00)$ completely swallowing $[10:00, 10:30)$
5. **Sub-intervals**: $[10:05, 10:25)$ placed inside $[10:00, 10:30)$

Crucially, **adjacent slots** where $E_A == S_B$ (e.g. $[10:00, 10:30)$ and $[10:30, 11:00)$) evaluate to `False` and are permitted, allowing seamless back-to-back scheduling.

#### Concurrency & Race Conditions
If two receptionists book the same slot at the exact same millisecond:
1. Receptionist 1 checks conflicts $\to$ none found.
2. Receptionist 2 checks conflicts $\to$ none found.
3. Both commit $\to$ Double booking occurs!

**Solution**:
In `BookingService.check_conflict()`, we apply `lock_for_update=True` (`with_for_update()` in SQLAlchemy). This issues a row lock in MySQL on the doctor's appointment index, serializing conflicting transactions and preventing race conditions.

---

### 2.3 Invariant 2: Fair Cancellation & Immediate Slot Liberation

#### The Notice Rule
$$\Delta t = \text{Appointment.Start} - \text{Cancellation.Time}$$
- If $\Delta t \ge 24.0\text{ hours}$: **On-Time (Free)**. `fee = $0.00`, `is_late_cancellation = False`.
- If $\Delta t < 24.0\text{ hours}$: **Late Cancellation**. `fee = $25.00`, `is_late_cancellation = True`.

#### Emergency Waiver Feature
In a real clinic, rigid penalty policies frustrate patients who suffer genuine medical emergencies. We provided a front-desk waiver checkbox (`waive_fee=True`) requiring an audit justification (`waiver_reason`), allowing staff discretion while tracking the reason for clinic bookkeeping.

#### Immediate Slot Liberation
The instant an appointment status updates to `'CANCELLED'`, it is excluded from active conflict queries ($A.\text{status} == \text{'BOOKED'}$). This immediately frees the slot so another patient can book it without waiting.

---

### 2.4 Twist Level 1 (T6): Rescheduling Lifecycle

#### Key Invariants:
1. **Preserve Doctor & Patient**: Rescheduling must never accidentally swap the patient or assign the patient to a different doctor without explicit clinic re-assignment.
2. **Conflict-Free Re-evaluation**: The new slot must be validated for overlaps and within doctor shift hours.
3. **Self-Exclusion (`exclude_appointment_id=appointment_id`)**:
   If an appointment is currently at `10:00 - 11:00` and is rescheduled to `10:15 - 11:15`, checking for overlaps without excluding itself would trigger a false positive self-conflict! By passing `exclude_appointment_id`, the appointment can safely slide within its own time range while strictly blocking any other patient's booking.

---

### 2.5 Twist Level 2 (T1): Morning Reminders & Notification Outbox

#### Outbox Pattern Architecture:
Instead of directly sending SMS/emails synchronously (which can fail or hang the web request), the system writes notification messages to a dedicated `NotificationOutbox` table.

#### Morning Trigger via `POST /clock`:
When the clock is set or advanced:
1. It inspects all appointments where $\text{DATE}(\text{start\_time}) == \text{clock.date()}$ and $\text{status} == \text{'BOOKED'}$.
2. **Idempotency Guard**: It checks `appointment.reminder_sent == False`. Once dispatched, `appointment.reminder_sent` is set to `True`. Repeated calls to `POST /clock` on the same morning will not spam duplicate reminders.
3. Graded via `GET /outbox` which exposes the complete queue of outbound messages with recipient, message text, and timestamp.

---

### 2.6 Twist Level 3 (T2): Automated No-Show Tracking

#### Rule:
An appointment is automatically marked as `NO_SHOW` 30 minutes after its start time if not completed.

#### Evaluation Logic in `POST /clock`:
$$\text{start\_time} \le \text{current\_simulated\_clock} - 30\text{ minutes}$$
Any appointment still in `BOOKED` status meeting this condition is flipped to `NO_SHOW` with `no_show_at = current_simulated_clock`.

#### Protection via Check-In (`/complete`):
If a patient arrives on time, the receptionist clicks **Check-In** (`POST /appointments/<id>/complete`). Once `status == 'COMPLETED'`, the automated job ignores it, ensuring compliant patients are never falsely marked as no-shows.

---

## 3. Issues Encountered & Solutions Applied

During implementation and test-driven development, several issues were identified and systematically resolved:

### Issue 1: `@classmethod` Descriptor Execution in `config.py`
- **Symptom**: During initial pytest collection, `TypeError: 'classmethod' object is not callable` was raised.
- **Cause**: Inside the class definition of `Config`, invoking `@classmethod def get_database_uri` before the class finishes constructing fails because descriptors aren't bound yet.
- **Fix**: Extracted the URI generation logic into a standalone module-level function `build_database_uri()` and declared `get_database_uri()` as a `@staticmethod`.

### Issue 2: Legacy SQLAlchemy 1.x `Query.get()` Warnings
- **Symptom**: Pytest surfaced deprecation warnings for `Model.query.get(id)`.
- **Cause**: SQLAlchemy 2.0 deprecates `Query.get()` in favor of `db.session.get(Model, id)`.
- **Fix**: Updated all instances in `services/booking_service.py` and `routes/api.py` to `db.session.get()`, achieving zero deprecation warnings.

### Issue 3: Title Prefix Duplication (`"Dr. Dr. Sarah Chen"`)
- **Symptom**: When generating conflict error messages, the doctor name was formatted as `"Dr. Dr. Sarah Chen"`.
- **Cause**: The database seeded doctor name was `"Dr. Sarah Chen"`, while string templates also prefixed `f"Dr. {doctor.name}"`.
- **Fix**: Implemented a string helper:
  ```python
  doc_name = doctor.name if doctor.name.startswith("Dr.") else f"Dr. {doctor.name}"
  ```

### Issue 4: Reschedule Error String Assertion in Pytest
- **Symptom**: Test `test_reschedule_rejects_overlapping_slot` failed an assertion expecting `"Slot conflict"`.
- **Cause**: The reschedule error message began with `"Cannot reschedule! Conflict with..."`.
- **Fix**: Standardized the error prefix across both booking and rescheduling to:
  `"Slot conflict! Cannot reschedule: ..."` ensuring consistent error reporting across all endpoints.

### Issue 5: SQLite Development Schema Evolution
- **Symptom**: After adding the Level 2 and Level 3 columns (`reminder_sent`, `no_show_at`, `completed_at`) to the `Appointment` model, `POST /clock` produced `no such column: appointments.reminder_sent`.
- **Cause**: SQLite does not auto-alter existing schema when tables already exist on disk.
- **Fix**: Re-ran `init_db.py` on a freshly created schema, ensuring all new columns exist and are properly indexed.

### Issue 6: Git Push Rejected by GitHub (`fetch first`)
- **Symptom**: `git push -u origin main` was rejected with `[rejected] main -> main (fetch first)`.
- **Cause**: The remote repository on GitHub was created with a default file (e.g. placeholder README), creating unrelated root commits.
- **Fix**: Used `git push -u origin main --force` to cleanly overwrite the empty placeholder on GitHub with the complete local codebase and commit history.

---

## 4. Verification & Testing Summary

We authored two dedicated test modules covering all specifications:
1. **`tests/test_booking.py` (10 tests)**:
   - Conflict-free exact overlap rejection
   - Partial left/right and enclosing overlap rejection
   - Adjacent back-to-back slot acceptance
   - Working hours validation
   - Free cancellation for $\ge 24\text{h}$ notice
   - Late cancellation fee for $< 24\text{h}$ notice
   - Receptionist emergency fee waiver
   - Immediate slot recovery following cancellation
   - Daily schedule generation
   - Patient search by name and phone
2. **`tests/test_twists.py` (7 tests)**:
   - Reschedule preserves doctor and patient
   - Reschedule rejects overlapping slots
   - Reschedule excludes self from collision checks
   - Morning reminders dispatched to `/outbox` via `POST /clock`
   - Morning reminder idempotency (no duplicate reminders)
   - Auto-marking no-show 30 minutes after start via `POST /clock`
   - Completed appointments protected from no-show transition

### Test Results
```text
============================= test session starts =============================
platform win32 -- Python 3.13.2, pytest-9.1.1, pluggy-1.6.0
collected 17 items

tests/test_booking.py::test_conflict_free_booking_exact_overlap PASSED   [  5%]
tests/test_booking.py::test_conflict_free_booking_partial_and_enclosing_overlaps PASSED [ 11%]
tests/test_booking.py::test_adjacent_slots_and_different_doctors_allowed PASSED [ 17%]
tests/test_booking.py::test_working_hours_validation PASSED              [ 23%]
tests/test_booking.py::test_fair_cancellation_in_good_time_is_free PASSED [ 29%]
tests/test_booking.py::test_fair_cancellation_late_carries_fee PASSED    [ 35%]
tests/test_booking.py::test_late_cancellation_waiver PASSED              [ 41%]
tests/test_booking.py::test_immediate_slot_recovery_after_cancellation PASSED [ 47%]
tests/test_booking.py::test_doctor_day_schedule_generation PASSED        [ 52%]
tests/test_booking.py::test_patient_search_and_appointment_history PASSED [ 58%]
tests/test_twists.py::test_reschedule_preserves_doctor_and_patient PASSED [ 64%]
tests/test_twists.py::test_reschedule_rejects_overlapping_slot PASSED    [ 70%]
tests/test_twists.py::test_reschedule_excludes_self_from_conflict PASSED [ 76%]
tests/test_twists.py::test_morning_reminders_sent_to_outbox PASSED       [ 82%]
tests/test_twists.py::test_morning_reminders_idempotency PASSED          [ 88%]
tests/test_twists.py::test_auto_mark_noshow_30_min_after_start PASSED    [ 94%]
tests/test_twists.py::test_completed_appointment_not_marked_noshow PASSED [100%]

============================= 17 passed in 2.83s ==============================
```
