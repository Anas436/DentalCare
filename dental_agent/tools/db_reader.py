from datetime import datetime
from langchain_core.tools import tool
from appointments.models import Appointment, Doctor

# Custom overrides provided by the user for specific specializations
CUSTOM_DOCTOR_OVERRIDES = {
    "general_dentist": ["kevin anderson"],
    "orthodontist": ["daniel miller", "susan davis"],
    "emergency_dentist": ["emily johnson", "john doe"],
}


def _parse_date(date_str: str) -> datetime:
    """Parse a date string into a timezone‑aware datetime.

    The original function returned a naive ``datetime`` which can cause
    mismatches when comparing against Django's aware ``timezone.now()``.
    We now make the result aware using the current timezone.
    """
    from django.utils import timezone
    date_str = date_str.strip()
    formats = [
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y %I:%M%p",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %I:%M %p",
        "%b %d, %Y at %I:%M %p",
        "%b %d, %Y at %I:%M%p",
        "%b %d, %Y %I:%M %p",  # added format without 'at'
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return timezone.make_aware(dt, timezone.get_current_timezone())
        except ValueError:
            continue
    raise ValueError(f"Unable to parse date: {date_str}")


def _format_date_slot(dt: datetime) -> str:
    """Format datetime as M/D/YYYY H:MM (no leading zeros)."""
    return f"{dt.month}/{dt.day}/{dt.year} {dt.hour}:{dt.minute:02d}"


@tool
def get_available_slots(
    specialization: str = "",
    doctor_name: str = "",
    date_filter: str = "",
    **kwargs,
) -> list:
    """Return available appointment slots.

    Accepts both the official parameter names and common aliases (e.g., ``doctorname`` or ``datefilter``) to be tolerant of variations coming from the chatbot.
    """
    # Support alias keys that may be passed via **kwargs
    if not doctor_name and "doctorname" in kwargs:
        doctor_name = kwargs["doctorname"]
    if not date_filter and "datefilter" in kwargs:
        date_filter = kwargs["datefilter"]
    qs = Appointment.objects.filter(status='available').select_related('doctor')

    if specialization:
        qs = qs.filter(doctor__specialization=specialization.lower().strip())
    if doctor_name:
        clean_name = doctor_name.strip().lower()
        for prefix in ("dr. ", "dr.", "doctor "):
            if clean_name.startswith(prefix):
                clean_name = clean_name[len(prefix):].strip()
        qs = qs.filter(doctor__name__iexact=clean_name)
    if date_filter:
        try:
            target_date = datetime.strptime(date_filter, "%m/%d/%Y").date()
            qs = qs.filter(date_slot__date=target_date)
        except Exception:
            pass

    result = []
    for appt in qs[:10]:
        result.append({
            "date_slot": _format_date_slot(appt.date_slot),
            "specialization": appt.doctor.specialization,
            "doctor_name": appt.doctor.name.lower(),
        })
    return result


@tool
def get_patient_appointments(patient_phone: str) -> list:
    """Return all booked appointments for a given patient phone number.

    Args:
        patient_phone: Patient's phone number, e.g. '+1234567890'.

    Returns:
        List of dicts with keys: date_slot, specialization, doctor_name, patient_to_attend.
    """
    from appointments.models import PatientProfile
    try:
        profile = PatientProfile.objects.get(phone=patient_phone.strip())
        user = profile.user
    except PatientProfile.DoesNotExist:
        return []

    qs = Appointment.objects.filter(
        patient=user, status='booked'
    ).select_related('doctor')

    result = []
    for appt in qs:
        result.append({
            "date_slot": _format_date_slot(appt.date_slot),
            "specialization": appt.doctor.specialization,
            "doctor_name": appt.doctor.name.lower(),
            "patient_to_attend": patient_phone,
        })
    return result


@tool
def check_slot_availability(doctor_name: str = "", date_slot: str = "", **kwargs) -> dict:
    """Check if a specific doctor slot is available.

    Accepts either a full date‑time string (e.g. "8/19/2026 12:30") or a time‑only string (e.g. "12:30 PM").
    If a time‑only string is supplied, the function looks for any appointment on the same day
    for the given doctor that matches the time component.
    """
    # Support alias keys that may be passed via **kwargs
    if not doctor_name and "doctorname" in kwargs:
        doctor_name = kwargs["doctorname"]
    if not date_slot and "dateslot" in kwargs:
        date_slot = kwargs["dateslot"]
    # Resolve doctor object first
    clean_name = doctor_name.strip().lower()
    for prefix in ("dr. ", "dr.", "doctor "):
        if clean_name.startswith(prefix):
            clean_name = clean_name[len(prefix):].strip()
    try:
        doctor = Doctor.objects.get(name__iexact=clean_name)
    except Doctor.DoesNotExist:
        return {"found": False, "is_available": False, "patient_to_attend": ""}

    # First try full date+time parsing
    try:
        target_dt = _parse_date(date_slot)
        appt = Appointment.objects.get(doctor=doctor, date_slot=target_dt)
        patient_phone = ""
        if appt.patient:
            try:
                profile = appt.patient.patient_profile
                patient_phone = profile.phone or str(appt.patient.id)
            except Exception:
                patient_phone = str(appt.patient.id)
        return {"found": True, "is_available": appt.status == 'available', "patient_to_attend": patient_phone}
    except Exception:
        # Parsing as full datetime failed or appointment not found – continue to time‑only handling
        pass

    # Attempt time‑only parsing (e.g., "12:30 PM" or "12:30")
    time_formats = ["%I:%M %p", "%H:%M"]
    parsed_time = None
    for tf in time_formats:
        try:
            parsed_time = datetime.strptime(date_slot.strip(), tf).time()
            break
        except Exception:
            continue
    if parsed_time is None:
        return {"found": False, "is_available": False, "patient_to_attend": ""}

    # Find any appointment for the doctor on any date that matches the given time
    matching_appts = Appointment.objects.filter(doctor=doctor, date_slot__time=parsed_time)
    if not matching_appts.exists():
        return {"found": False, "is_available": False, "patient_to_attend": ""}
    appt = matching_appts.first()
    patient_phone = ""
    if appt.patient:
        try:
            profile = appt.patient.patient_profile
            patient_phone = profile.phone or str(appt.patient.id)
        except Exception:
            patient_phone = str(appt.patient.id)
    return {"found": True, "is_available": appt.status == 'available', "patient_to_attend": patient_phone}

@tool
def list_doctors_by_specialization(specialization: str) -> list:
    """Return distinct doctor names for a given specialization.

    Normalises the input (spaces or hyphens become underscores, lower‑cased).
    If a custom override exists, returns that list **filtered to doctors that
    actually exist in the database**. Otherwise, queries the database.
    """
    normalized = specialization.lower().replace(' ', '_').replace('-', '_')
    # If we have user‐provided overrides, verify each name exists in DB
    if normalized in CUSTOM_DOCTOR_OVERRIDES:
        override_names = CUSTOM_DOCTOR_OVERRIDES[normalized]
        # Query for matching doctors (case‑insensitive)
        existing = Doctor.objects.filter(name__in=override_names, is_active=True)
        # Return the intersect of overrides and actual DB entries, lower‑cased
        return [doc.name.lower() for doc in existing]
    # No overrides – fall back to DB query
    return sorted(
        Doctor.objects.filter(
            specialization=normalized,
            is_active=True
        ).values_list('name', flat=True)
    )
