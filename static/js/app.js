// CareFlow Clinic Front Desk Client Application
let state = {
  doctors: [],
  selectedDoctorId: null,
  selectedDate: new Date().toISOString().split("T")[0],
  policy: {
    cutoff_hours: 24,
    late_fee: 25.0,
  },
  activeTab: "schedule",
};

// --- DOM ELEMENTS ---
const clockEl = document.getElementById("current-clock");
const policySummaryEl = document.getElementById("policy-summary-text");
const doctorPillsContainer = document.getElementById("doctor-pills-container");
const scheduleDatePicker = document.getElementById("schedule-date-picker");
const scheduleHeaderTitle = document.getElementById("schedule-header-title");
const scheduleHeaderSub = document.getElementById("schedule-header-sub");
const timelineSlotsContainer = document.getElementById("timeline-slots-container");
const metricBooked = document.getElementById("metric-booked");
const metricAvailable = document.getElementById("metric-available");
const metricCancelled = document.getElementById("metric-cancelled");
const cancelledSection = document.getElementById("cancelled-appointments-section");
const cancelledList = document.getElementById("cancelled-appointments-list");

// Modals
const modalBook = document.getElementById("modal-book");
const bookForm = document.getElementById("book-form");
const bookErrorBox = document.getElementById("book-error-box");
const bookErrorMessage = document.getElementById("book-error-message");
const bookDoctorSelect = document.getElementById("book-doctor-select");
const bookDateInput = document.getElementById("book-date-input");
const bookTimeInput = document.getElementById("book-time-input");
const bookDuration = document.getElementById("book-duration");

const modalCancel = document.getElementById("modal-cancel");
const cancelForm = document.getElementById("cancel-form");
const cancelApptIdInput = document.getElementById("cancel-appointment-id");
const cancelModalPatient = document.getElementById("cancel-modal-patient");
const cancelModalDoctor = document.getElementById("cancel-modal-doctor");
const cancelModalTime = document.getElementById("cancel-modal-time");
const cancelPolicyBox = document.getElementById("cancel-policy-evaluation-box");
const cancelWaiverContainer = document.getElementById("cancel-waiver-container");
const cancelWaiveCheckbox = document.getElementById("cancel-waive-checkbox");
const cancelWaiverReasonBlock = document.getElementById("cancel-waiver-reason-block");
const cancelWaiverReason = document.getElementById("cancel-waiver-reason");
const confirmCancelBtn = document.getElementById("confirm-cancel-btn");

const modalSettings = document.getElementById("modal-settings");
const settingsForm = document.getElementById("settings-form");
const settingsCutoff = document.getElementById("settings-cutoff");
const settingsFee = document.getElementById("settings-fee");

const modalAddDoctor = document.getElementById("modal-add-doctor");
const addDoctorForm = document.getElementById("add-doctor-form");

const patientSearchInput = document.getElementById("patient-search-input");
const clearSearchBtn = document.getElementById("clear-search-btn");
const searchResultsContainer = document.getElementById("search-results-container");
const doctorsGrid = document.getElementById("doctors-grid");

// --- UTILITIES ---
function showToast(message, type = "success") {
  const toast = document.getElementById("toast");
  const msg = document.getElementById("toast-msg");
  const icon = document.getElementById("toast-icon");

  msg.textContent = message;
  toast.className =
    "fixed bottom-5 right-5 z-50 transform transition-all duration-300 max-w-sm rounded-xl px-4 py-3 shadow-xl flex items-center gap-3 text-xs font-semibold show " +
    (type === "success"
      ? "bg-emerald-600 text-white"
      : type === "error"
      ? "bg-rose-600 text-white"
      : "bg-slate-800 text-white");

  icon.innerHTML =
    type === "success"
      ? '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"></path></svg>'
      : '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"></path></svg>';

  setTimeout(() => {
    toast.classList.remove("show");
  }, 4000);
}

function updateClock() {
  const now = new Date();
  if (clockEl) {
    clockEl.textContent = now.toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }
}
setInterval(updateClock, 1000);
updateClock();

// --- INITIALIZATION ---
async function initApp() {
  scheduleDatePicker.value = state.selectedDate;
  await fetchSettings();
  await fetchDoctors();
  setupEventListeners();
}

// --- API CALLS ---
async function fetchSettings() {
  try {
    const res = await fetch("/api/settings");
    const data = await res.json();
    if (data.success) {
      state.policy.cutoff_hours = data.cancellation_cutoff_hours;
      state.policy.late_fee = data.late_cancellation_fee;
      policySummaryEl.textContent = `Policy: ${state.policy.cutoff_hours}h Notice | $${state.policy.late_fee.toFixed(2)} Late Fee`;
      settingsCutoff.value = state.policy.cutoff_hours;
      settingsFee.value = state.policy.late_fee;
    }
  } catch (err) {
    console.error("Error fetching settings:", err);
  }
}

async function fetchDoctors() {
  try {
    const res = await fetch("/api/doctors");
    const data = await res.json();
    if (data.success && data.doctors.length > 0) {
      state.doctors = data.doctors;
      if (!state.selectedDoctorId) {
        state.selectedDoctorId = data.doctors[0].id;
      }
      renderDoctorPills();
      populateDoctorSelect();
      renderDoctorsDirectory();
      loadSchedule();
    } else {
      doctorPillsContainer.innerHTML = '<p class="text-xs text-slate-500">No doctors available. Add a doctor to begin.</p>';
    }
  } catch (err) {
    console.error("Error fetching doctors:", err);
  }
}

async function loadSchedule() {
  if (!state.selectedDoctorId) return;

  timelineSlotsContainer.innerHTML = `
    <div class="col-span-full py-12 text-center text-slate-400 animate-pulse">
      <div class="inline-block w-8 h-8 border-3 border-blue-600 border-t-transparent rounded-full animate-spin mb-2"></div>
      <p class="text-xs font-medium">Loading schedule...</p>
    </div>
  `;

  try {
    const res = await fetch(`/api/doctors/${state.selectedDoctorId}/day?date=${state.selectedDate}`);
    const data = await res.json();

    if (data.success) {
      const doc = data.doctor;
      scheduleHeaderTitle.textContent = `${doc.name} — ${doc.specialty}`;
      scheduleHeaderSub.textContent = `Working Hours: ${data.working_hours} (${data.slot_duration_mins}-min slots)`;

      metricBooked.textContent = `${data.booked_count} Booked`;
      metricCancelled.textContent = `${data.cancelled_count} Cancelled`;

      const availableCount = data.timeline.filter((s) => s.type === "AVAILABLE").length;
      metricAvailable.textContent = `${availableCount} Available`;

      renderTimeline(data.timeline);
      renderCancelledAppointments(data.cancelled_appointments);
    }
  } catch (err) {
    console.error("Error loading schedule:", err);
    timelineSlotsContainer.innerHTML = `
      <div class="col-span-full py-8 text-center text-rose-600 text-xs font-medium">
        Failed to load schedule. Please try again.
      </div>
    `;
  }
}

// --- RENDER FUNCTIONS ---
function renderDoctorPills() {
  doctorPillsContainer.innerHTML = "";
  state.doctors.forEach((doc) => {
    const btn = document.createElement("button");
    const isActive = doc.id === state.selectedDoctorId;
    btn.className = `doctor-pill px-4 py-2.5 rounded-xl border text-xs font-semibold flex items-center gap-2.5 cursor-pointer ${
      isActive
        ? "active"
        : "bg-white border-slate-200 text-slate-700 hover:border-slate-300 hover:bg-slate-50"
    }`;
    btn.innerHTML = `
      <div class="w-6 h-6 rounded-full flex items-center justify-center font-bold text-[11px] ${
        isActive ? "bg-white text-blue-600" : "bg-blue-100 text-blue-700"
      }">
        ${doc.name.split(" ").slice(-1)[0][0]}
      </div>
      <div class="text-left">
        <div>${doc.name}</div>
        <div class="text-[10px] font-normal ${isActive ? "text-blue-100" : "text-slate-400"}">${doc.specialty}</div>
      </div>
    `;
    btn.addEventListener("click", () => {
      state.selectedDoctorId = doc.id;
      renderDoctorPills();
      loadSchedule();
    });
    doctorPillsContainer.appendChild(btn);
  });
}

function populateDoctorSelect() {
  bookDoctorSelect.innerHTML = "";
  state.doctors.forEach((doc) => {
    const opt = document.createElement("option");
    opt.value = doc.id;
    opt.textContent = `${doc.name} (${doc.specialty})`;
    if (doc.id === state.selectedDoctorId) {
      opt.selected = true;
    }
    bookDoctorSelect.appendChild(opt);
  });
}

function renderTimeline(timeline) {
  timelineSlotsContainer.innerHTML = "";

  if (!timeline || timeline.length === 0) {
    timelineSlotsContainer.innerHTML = `
      <div class="col-span-full py-12 text-center text-slate-400 text-xs">
        No active slots scheduled for this doctor on this day.
      </div>
    `;
    return;
  }

  timeline.forEach((slot) => {
    const card = document.createElement("div");

    if (slot.type === "AVAILABLE") {
      card.className =
        "slot-card p-3.5 rounded-xl border-2 border-dashed border-emerald-300/80 bg-emerald-50/40 hover:bg-emerald-50 hover:border-emerald-500 cursor-pointer flex flex-col justify-between transition group";
      card.innerHTML = `
        <div class="flex items-center justify-between">
          <span class="text-xs font-extrabold text-slate-800">${slot.slot_start} - ${slot.slot_end}</span>
          <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">OPEN</span>
        </div>
        <div class="mt-3 flex items-center justify-between text-[11px] text-emerald-700 group-hover:text-emerald-800 font-semibold">
          <span class="flex items-center gap-1">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 4v16m8-8H4"></path></svg>
            Book Slot
          </span>
          <span class="text-[10px] text-slate-400 font-normal">Available</span>
        </div>
      `;
      card.addEventListener("click", () => {
        openBookingModal({
          doctorId: state.selectedDoctorId,
          date: state.selectedDate,
          time: slot.slot_start,
          duration: state.doctors.find((d) => d.id === state.selectedDoctorId)?.slot_duration_mins || 30,
        });
      });
    } else if (slot.type === "BOOKED") {
      const apt = slot.appointment;
      card.className =
        "slot-card p-3.5 rounded-xl border border-blue-200 bg-white shadow-xs flex flex-col justify-between";
      card.innerHTML = `
        <div>
          <div class="flex items-center justify-between mb-1.5">
            <span class="text-xs font-extrabold text-blue-900">${slot.slot_start} - ${slot.slot_end}</span>
            <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800">CONFIRMED</span>
          </div>
          <div class="font-bold text-xs text-slate-900 truncate" title="${apt.patient_name}">${apt.patient_name}</div>
          <div class="text-[11px] text-slate-500">${apt.patient_phone || "No phone"}</div>
          ${
            apt.notes
              ? `<div class="mt-1 text-[11px] text-slate-600 bg-slate-50 rounded px-2 py-1 italic truncate" title="${apt.notes}">${apt.notes}</div>`
              : ""
          }
        </div>
        <div class="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-between">
          <button class="cancel-slot-btn text-[11px] font-semibold text-rose-600 hover:text-rose-800 flex items-center gap-1 transition" data-apt-id="${apt.id}">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            Cancel Visit
          </button>
          <span class="text-[10px] text-slate-400 font-mono">#${apt.id}</span>
        </div>
      `;

      const cancelBtn = card.querySelector(".cancel-slot-btn");
      cancelBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        openCancelModal(apt.id);
      });
    }

    timelineSlotsContainer.appendChild(card);
  });
}

function renderCancelledAppointments(cancelledListItems) {
  if (!cancelledListItems || cancelledListItems.length === 0) {
    cancelledSection.classList.add("hidden");
    return;
  }

  cancelledSection.classList.remove("hidden");
  cancelledList.innerHTML = "";

  cancelledListItems.forEach((apt) => {
    const item = document.createElement("div");
    item.className =
      "p-3 rounded-xl bg-slate-50 border border-slate-200/80 flex flex-wrap items-center justify-between text-xs gap-2";

    const feeBadge =
      apt.cancellation_fee > 0
        ? `<span class="px-2 py-0.5 rounded-md bg-rose-100 text-rose-800 font-bold text-[11px]">Late Fee: $${apt.cancellation_fee.toFixed(2)}</span>`
        : apt.fee_waived
        ? `<span class="px-2 py-0.5 rounded-md bg-amber-100 text-amber-800 font-bold text-[11px]">Fee Waived</span>`
        : `<span class="px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-800 font-bold text-[11px]">Free ($0.00)</span>`;

    item.innerHTML = `
      <div>
        <span class="font-bold text-slate-800">${apt.patient_name}</span>
        <span class="text-slate-400 mx-1">&bull;</span>
        <span class="text-slate-600 font-medium">${apt.start_time.split(" ")[1]} - ${apt.end_time.split(" ")[1]}</span>
        <span class="text-slate-400 text-[11px] ml-2">Reason: ${apt.cancellation_reason || "None specified"}</span>
      </div>
      <div class="flex items-center gap-2">
        ${feeBadge}
        <span class="text-[10px] text-slate-400">Slot Liberated</span>
      </div>
    `;
    cancelledList.appendChild(item);
  });
}

function renderDoctorsDirectory() {
  doctorsGrid.innerHTML = "";
  state.doctors.forEach((doc) => {
    const card = document.createElement("div");
    card.className = "bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs space-y-3";
    card.innerHTML = `
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-blue-100 text-blue-700 flex items-center justify-center font-bold text-sm">
          ${doc.name.split(" ").slice(-1)[0][0]}
        </div>
        <div>
          <h3 class="font-bold text-slate-900 text-sm">${doc.name}</h3>
          <p class="text-xs text-blue-600 font-medium">${doc.specialty}</p>
        </div>
      </div>
      <div class="text-xs text-slate-600 space-y-1 pt-2 border-t border-slate-100">
        <div class="flex justify-between">
          <span class="text-slate-400">Shift Hours:</span>
          <span class="font-medium text-slate-700">${doc.shift_start} - ${doc.shift_end}</span>
        </div>
        <div class="flex justify-between">
          <span class="text-slate-400">Slot Duration:</span>
          <span class="font-medium text-slate-700">${doc.slot_duration_mins} mins</span>
        </div>
        <div class="flex justify-between">
          <span class="text-slate-400">Contact:</span>
          <span class="font-medium text-slate-700">${doc.email || doc.phone || "On File"}</span>
        </div>
      </div>
      <button class="w-full mt-2 py-2 rounded-xl bg-slate-50 hover:bg-slate-100 text-slate-700 font-semibold text-xs transition view-doc-day-btn" data-doc-id="${doc.id}">
        View Schedule
      </button>
    `;

    card.querySelector(".view-doc-day-btn").addEventListener("click", () => {
      state.selectedDoctorId = doc.id;
      switchTab("schedule");
      renderDoctorPills();
      loadSchedule();
    });

    doctorsGrid.appendChild(card);
  });
}

// --- BOOKING MODAL LOGIC ---
function openBookingModal(defaults = {}) {
  bookErrorBox.classList.add("hidden");
  bookForm.reset();

  if (defaults.doctorId) {
    bookDoctorSelect.value = defaults.doctorId;
  }
  bookDateInput.value = defaults.date || state.selectedDate;
  bookTimeInput.value = defaults.time || "09:00";

  const duration = defaults.duration || 30;
  bookDuration.value = duration;
  document.querySelectorAll(".duration-btn").forEach((btn) => {
    if (parseInt(btn.dataset.duration) === duration) {
      btn.className =
        "duration-btn active-duration py-1.5 rounded-lg border border-blue-600 bg-blue-50 text-blue-700 text-center font-semibold";
    } else {
      btn.className =
        "duration-btn py-1.5 rounded-lg border border-slate-200 text-center font-medium hover:bg-slate-50";
    }
  });

  modalBook.classList.remove("hidden");
}

function closeBookingModal() {
  modalBook.classList.add("hidden");
}

async function handleBookingSubmit(e) {
  e.preventDefault();
  bookErrorBox.classList.add("hidden");

  const doctorId = bookDoctorSelect.value;
  const dateVal = bookDateInput.value;
  const timeVal = bookTimeInput.value;
  const duration = parseInt(bookDuration.value) || 30;
  const patientName = document.getElementById("book-patient-name").value.trim();
  const patientPhone = document.getElementById("book-patient-phone").value.trim();
  const patientEmail = document.getElementById("book-patient-email").value.trim();
  const notes = document.getElementById("book-notes").value.trim();

  const startFormatted = `${dateVal} ${timeVal}`;

  try {
    const res = await fetch("/api/appointments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        doctor_id: doctorId,
        start_time: startFormatted,
        duration_mins: duration,
        patient_name: patientName,
        patient_phone: patientPhone,
        patient_email: patientEmail,
        notes: notes,
      }),
    });

    const data = await res.json();

    if (!res.ok || !data.success) {
      // Conflict or validation error!
      bookErrorBox.classList.remove("hidden");
      bookErrorMessage.innerHTML = data.error || "Could not book appointment.";
      return;
    }

    // Success!
    closeBookingModal();
    showToast(`Appointment booked successfully for ${patientName}!`, "success");
    state.selectedDate = dateVal;
    scheduleDatePicker.value = dateVal;
    loadSchedule();
  } catch (err) {
    console.error("Booking error:", err);
    bookErrorBox.classList.remove("hidden");
    bookErrorMessage.textContent = "A network or server error occurred. Please try again.";
  }
}

// --- CANCELLATION MODAL LOGIC ---
async function openCancelModal(appointmentId) {
  cancelApptIdInput.value = appointmentId;
  cancelForm.reset();
  cancelWaiverContainer.classList.add("hidden");
  cancelWaiverReasonBlock.classList.add("hidden");
  cancelWaiveCheckbox.checked = false;

  cancelPolicyBox.innerHTML = `
    <div class="text-center py-2 text-slate-400">Evaluating cancellation rules...</div>
  `;
  modalCancel.classList.remove("hidden");

  try {
    const res = await fetch(`/api/appointments/${appointmentId}/preview-cancel`);
    const data = await res.json();

    if (!data.success) {
      showToast(data.error || "Cannot preview cancellation", "error");
      modalCancel.classList.add("hidden");
      return;
    }

    cancelModalPatient.textContent = data.patient_name;
    cancelModalDoctor.textContent = data.doctor_name;
    cancelModalTime.textContent = `${data.start_time} (${data.hours_notice}h notice)`;

    if (data.is_late) {
      // Late cancellation: fee applies!
      cancelPolicyBox.className =
        "p-3.5 rounded-xl border border-rose-200 bg-rose-50 text-rose-900 text-xs space-y-1";
      cancelPolicyBox.innerHTML = `
        <div class="flex items-center gap-1.5 font-bold text-rose-700">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
          Late Cancellation Policy Applied
        </div>
        <p class="font-medium text-rose-800">
          Cancellation is within ${data.cutoff_hours} hours of the appointment (${data.hours_notice}h notice).
        </p>
        <div class="mt-2 pt-2 border-t border-rose-200 flex justify-between items-center font-extrabold text-sm text-rose-900">
          <span>Fee Incurred:</span>
          <span>$${data.fee.toFixed(2)}</span>
        </div>
      `;
      cancelWaiverContainer.classList.remove("hidden");
      confirmCancelBtn.className =
        "px-5 py-2 rounded-lg bg-rose-600 hover:bg-rose-700 text-white font-semibold transition";
      confirmCancelBtn.textContent = `Confirm Cancellation ($${data.fee.toFixed(2)} Fee)`;
    } else {
      // Good time cancellation: Free!
      cancelPolicyBox.className =
        "p-3.5 rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-900 text-xs space-y-1";
      cancelPolicyBox.innerHTML = `
        <div class="flex items-center gap-1.5 font-bold text-emerald-700">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"></path></svg>
          Free Cancellation (Ample Notice)
        </div>
        <p class="font-medium text-emerald-800">
          Notice provided: ${data.hours_notice} hours in advance (policy requirement is ${data.cutoff_hours}h).
        </p>
        <div class="mt-2 pt-2 border-t border-emerald-200 flex justify-between items-center font-extrabold text-sm text-emerald-900">
          <span>Fee Incurred:</span>
          <span>$0.00 (Free)</span>
        </div>
      `;
      confirmCancelBtn.className =
        "px-5 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-white font-semibold transition";
      confirmCancelBtn.textContent = "Confirm Cancellation (Free)";
    }
  } catch (err) {
    console.error("Cancellation preview error:", err);
    modalCancel.classList.add("hidden");
    showToast("Failed to evaluate cancellation rules", "error");
  }
}

function closeCancelModal() {
  modalCancel.classList.add("hidden");
}

async function handleCancelSubmit(e) {
  e.preventDefault();
  const appointmentId = cancelApptIdInput.value;
  const reason = document.getElementById("cancel-reason-input").value.trim();
  const waiveFee = cancelWaiveCheckbox.checked;
  const waiverReason = cancelWaiverReason.value.trim();

  try {
    const res = await fetch(`/api/appointments/${appointmentId}/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reason: reason,
        waive_fee: waiveFee,
        waiver_reason: waiverReason,
      }),
    });

    const data = await res.json();
    if (!res.ok || !data.success) {
      showToast(data.error || "Could not cancel appointment", "error");
      return;
    }

    closeCancelModal();
    showToast(data.message, "success");
    loadSchedule();
    if (state.activeTab === "search") {
      performPatientSearch();
    }
  } catch (err) {
    console.error("Cancel submit error:", err);
    showToast("Error processing cancellation", "error");
  }
}

// --- PATIENT SEARCH LOGIC ---
let searchDebounce = null;
function handlePatientSearchInput() {
  const query = patientSearchInput.value.trim();
  clearSearchBtn.classList.toggle("hidden", query.length === 0);

  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => {
    performPatientSearch();
  }, 250);
}

async function performPatientSearch() {
  const query = patientSearchInput.value.trim();
  if (!query) {
    searchResultsContainer.innerHTML = `
      <div class="bg-white rounded-2xl p-10 border border-slate-200 text-center text-slate-500">
        <svg class="w-12 h-12 mx-auto text-slate-300 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path>
        </svg>
        <p class="font-medium">Enter a patient name or phone number above to find appointments.</p>
      </div>
    `;
    return;
  }

  try {
    const res = await fetch(`/api/patients/search?q=${encodeURIComponent(query)}`);
    const data = await res.json();

    if (!data.success || data.results.length === 0) {
      searchResultsContainer.innerHTML = `
        <div class="bg-white rounded-2xl p-8 border border-slate-200 text-center text-slate-500 text-xs">
          No patients or appointments found matching "<strong>${escapeHtml(query)}</strong>".
        </div>
      `;
      return;
    }

    renderSearchResults(data.results);
  } catch (err) {
    console.error("Patient search error:", err);
  }
}

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderSearchResults(patientsList) {
  searchResultsContainer.innerHTML = "";

  patientsList.forEach((item) => {
    const p = item.patient;
    const apts = item.appointments;
    const card = document.createElement("div");
    card.className = "bg-white rounded-2xl p-6 border border-slate-200/80 shadow-xs space-y-4";

    let aptsHtml = "";
    if (apts.length === 0) {
      aptsHtml = '<p class="text-xs text-slate-400 italic">No appointments on record.</p>';
    } else {
      aptsHtml = apts
        .map((apt) => {
          let badge = "";
          let cancelBtn = "";

          if (apt.status === "BOOKED") {
            badge = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-100 text-blue-800">CONFIRMED</span>';
            cancelBtn = `
              <button class="search-cancel-btn text-xs font-semibold text-rose-600 hover:text-rose-800 transition" data-apt-id="${apt.id}">
                Cancel
              </button>
            `;
          } else if (apt.status === "CANCELLED") {
            const feeInfo =
              apt.cancellation_fee > 0
                ? `$${apt.cancellation_fee.toFixed(2)} Late Fee`
                : apt.fee_waived
                ? "Fee Waived"
                : "Free";
            badge = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-600">CANCELLED (${feeInfo})</span>`;
          } else {
            badge = `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800">${apt.status}</span>`;
          }

          return `
            <div class="p-3 rounded-xl bg-slate-50 border border-slate-200 flex flex-wrap items-center justify-between gap-3 text-xs">
              <div>
                <div class="font-bold text-slate-900">${apt.doctor_name} (${apt.doctor_specialty})</div>
                <div class="text-slate-500 font-medium">${apt.start_time} - ${apt.end_time.split(" ")[1]}</div>
                ${apt.notes ? `<div class="text-slate-400 italic text-[11px]">${escapeHtml(apt.notes)}</div>` : ""}
              </div>
              <div class="flex items-center gap-3">
                ${badge}
                ${cancelBtn}
              </div>
            </div>
          `;
        })
        .join("");
    }

    card.innerHTML = `
      <div class="flex flex-wrap items-center justify-between pb-3 border-b border-slate-100 gap-2">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center font-bold text-sm">
            ${p.name[0]}
          </div>
          <div>
            <h3 class="font-bold text-slate-900 text-sm">${escapeHtml(p.name)}</h3>
            <p class="text-xs text-slate-500">${escapeHtml(p.phone)} &bull; ${escapeHtml(p.email || "No email")}</p>
          </div>
        </div>
        <div class="flex items-center gap-3 text-xs">
          <span class="px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 font-semibold border border-blue-200">
            ${item.active_count} Active Bookings
          </span>
          ${
            item.total_cancellation_fees > 0
              ? `<span class="px-2.5 py-1 rounded-full bg-rose-50 text-rose-700 font-semibold border border-rose-200">
                  Total Late Fees: $${item.total_cancellation_fees.toFixed(2)}
                </span>`
              : ""
          }
        </div>
      </div>
      <div class="space-y-2">
        <h4 class="text-xs font-semibold text-slate-600 uppercase tracking-wider">Appointments History</h4>
        <div class="space-y-2">
          ${aptsHtml}
        </div>
      </div>
    `;

    // Attach cancel events
    card.querySelectorAll(".search-cancel-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        openCancelModal(btn.dataset.aptId);
      });
    });

    searchResultsContainer.appendChild(card);
  });
}

// --- TAB SWITCHING ---
function switchTab(tabId) {
  state.activeTab = tabId;
  const viewSchedule = document.getElementById("view-schedule");
  const viewSearch = document.getElementById("view-search");
  const viewDoctors = document.getElementById("view-doctors");

  const tabScheduleBtn = document.getElementById("tab-schedule-btn");
  const tabSearchBtn = document.getElementById("tab-search-btn");
  const tabDoctorsBtn = document.getElementById("tab-doctors-btn");

  [viewSchedule, viewSearch, viewDoctors].forEach((v) => v.classList.add("hidden"));
  [tabScheduleBtn, tabSearchBtn, tabDoctorsBtn].forEach((b) => {
    b.className =
      "tab-btn flex items-center gap-2 py-3 text-sm font-medium border-b-2 border-transparent text-slate-500 hover:text-slate-800 transition";
  });

  if (tabId === "schedule") {
    viewSchedule.classList.remove("hidden");
    tabScheduleBtn.className =
      "tab-btn active-tab flex items-center gap-2 py-3 text-sm font-medium border-b-2 border-blue-600 text-blue-600";
  } else if (tabId === "search") {
    viewSearch.classList.remove("hidden");
    tabSearchBtn.className =
      "tab-btn active-tab flex items-center gap-2 py-3 text-sm font-medium border-b-2 border-blue-600 text-blue-600";
    patientSearchInput.focus();
  } else if (tabId === "doctors") {
    viewDoctors.classList.remove("hidden");
    tabDoctorsBtn.className =
      "tab-btn active-tab flex items-center gap-2 py-3 text-sm font-medium border-b-2 border-blue-600 text-blue-600";
  }
}

// --- EVENT LISTENERS ---
function setupEventListeners() {
  // Tabs
  document.getElementById("tab-schedule-btn").addEventListener("click", () => switchTab("schedule"));
  document.getElementById("tab-search-btn").addEventListener("click", () => switchTab("search"));
  document.getElementById("tab-doctors-btn").addEventListener("click", () => switchTab("doctors"));

  // Date Navigation
  scheduleDatePicker.addEventListener("change", (e) => {
    state.selectedDate = e.target.value;
    loadSchedule();
  });

  document.getElementById("today-btn").addEventListener("click", () => {
    state.selectedDate = new Date().toISOString().split("T")[0];
    scheduleDatePicker.value = state.selectedDate;
    loadSchedule();
  });

  document.getElementById("tomorrow-btn").addEventListener("click", () => {
    const tmrw = new Date();
    tmrw.setDate(tmrw.getDate() + 1);
    state.selectedDate = tmrw.toISOString().split("T")[0];
    scheduleDatePicker.value = state.selectedDate;
    loadSchedule();
  });

  document.getElementById("prev-day-btn").addEventListener("click", () => {
    const d = new Date(state.selectedDate);
    d.setDate(d.getDate() - 1);
    state.selectedDate = d.toISOString().split("T")[0];
    scheduleDatePicker.value = state.selectedDate;
    loadSchedule();
  });

  document.getElementById("next-day-btn").addEventListener("click", () => {
    const d = new Date(state.selectedDate);
    d.setDate(d.getDate() + 1);
    state.selectedDate = d.toISOString().split("T")[0];
    scheduleDatePicker.value = state.selectedDate;
    loadSchedule();
  });

  // Book Modal Triggers
  document.getElementById("header-book-btn").addEventListener("click", () => openBookingModal());
  document.getElementById("close-book-modal-btn").addEventListener("click", closeBookingModal);
  document.getElementById("cancel-book-modal-btn").addEventListener("click", closeBookingModal);
  bookForm.addEventListener("submit", handleBookingSubmit);

  // Duration Buttons in Booking Modal
  document.querySelectorAll(".duration-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".duration-btn").forEach((b) => {
        b.className =
          "duration-btn py-1.5 rounded-lg border border-slate-200 text-center font-medium hover:bg-slate-50";
      });
      btn.className =
        "duration-btn active-duration py-1.5 rounded-lg border border-blue-600 bg-blue-50 text-blue-700 text-center font-semibold";
      bookDuration.value = btn.dataset.duration;
    });
  });

  // Cancel Modal Triggers
  document.getElementById("close-cancel-modal-btn").addEventListener("click", closeCancelModal);
  document.getElementById("abort-cancel-btn").addEventListener("click", closeCancelModal);
  cancelForm.addEventListener("submit", handleCancelSubmit);

  // Waiver toggle
  cancelWaiveCheckbox.addEventListener("change", (e) => {
    cancelWaiverReasonBlock.classList.toggle("hidden", !e.target.checked);
    if (e.target.checked) {
      confirmCancelBtn.textContent = "Confirm Cancellation (Fee Waived)";
      confirmCancelBtn.className =
        "px-5 py-2 rounded-lg bg-amber-600 hover:bg-amber-700 text-white font-semibold transition";
    } else {
      confirmCancelBtn.textContent = `Confirm Cancellation ($${state.policy.late_fee.toFixed(2)} Fee)`;
      confirmCancelBtn.className =
        "px-5 py-2 rounded-lg bg-rose-600 hover:bg-rose-700 text-white font-semibold transition";
    }
  });

  // Settings Modal Triggers
  document.getElementById("open-settings-btn").addEventListener("click", () => {
    modalSettings.classList.remove("hidden");
  });
  document.getElementById("close-settings-modal-btn").addEventListener("click", () => {
    modalSettings.classList.add("hidden");
  });
  document.getElementById("cancel-settings-btn").addEventListener("click", () => {
    modalSettings.classList.add("hidden");
  });
  settingsForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const cutoff = parseFloat(settingsCutoff.value);
    const fee = parseFloat(settingsFee.value);

    try {
      const res = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cancellation_cutoff_hours: cutoff,
          late_cancellation_fee: fee,
        }),
      });
      const data = await res.json();
      if (data.success) {
        state.policy.cutoff_hours = data.cancellation_cutoff_hours;
        state.policy.late_fee = data.late_cancellation_fee;
        policySummaryEl.textContent = `Policy: ${state.policy.cutoff_hours}h Notice | $${state.policy.late_fee.toFixed(2)} Late Fee`;
        modalSettings.classList.add("hidden");
        showToast("Clinic policy updated successfully!", "success");
      }
    } catch (err) {
      console.error("Failed to update settings:", err);
    }
  });

  // Add Doctor Modal Triggers
  document.getElementById("add-doctor-modal-btn").addEventListener("click", () => {
    addDoctorForm.reset();
    modalAddDoctor.classList.remove("hidden");
  });
  document.getElementById("close-doctor-modal-btn").addEventListener("click", () => {
    modalAddDoctor.classList.add("hidden");
  });
  document.getElementById("cancel-doctor-btn").addEventListener("click", () => {
    modalAddDoctor.classList.add("hidden");
  });
  addDoctorForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("doc-name").value.trim();
    const specialty = document.getElementById("doc-specialty").value.trim();
    const start = document.getElementById("doc-start").value;
    const end = document.getElementById("doc-end").value;
    const duration = parseInt(document.getElementById("doc-duration").value);

    try {
      const res = await fetch("/api/doctors", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name,
          specialty: specialty,
          shift_start: start,
          shift_end: end,
          slot_duration_mins: duration,
        }),
      });
      const data = await res.json();
      if (data.success) {
        modalAddDoctor.classList.add("hidden");
        showToast(`Dr. ${name} added successfully!`, "success");
        await fetchDoctors();
      } else {
        showToast(data.error || "Failed to add doctor", "error");
      }
    } catch (err) {
      console.error("Add doctor error:", err);
    }
  });

  // Patient Search Input
  patientSearchInput.addEventListener("input", handlePatientSearchInput);
  clearSearchBtn.addEventListener("click", () => {
    patientSearchInput.value = "";
    handlePatientSearchInput();
  });
}

// Start
document.addEventListener("DOMContentLoaded", initApp);
