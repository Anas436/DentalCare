from datetime import datetime
from langchain_core.tools import tool
from appointments.models import Appointment, Doctor


def _parse_date(date_str: str) -> datetime:
    """Parse a date string into a timezone‑aware datetime.

    The original implementation returned a naive ``datetime`` which caused
    mismatches when Django compared it against ``timezone.now()`` (an aware
    datetime). We now make the result aware using the current timezone.
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
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return timezone.make_aware(dt, timezone.get_current_timezone())
        except ValueError:
            continue
    raise ValueError(f"Unable to parse date: {date_str}")
    """Parse a date string into a timezone‑aware datetime.

    The original implementation returned a naive ``datetime`` which can cause
    mismatches when Django compares it against ``timezone.now()`` (an aware
    datetime). We now make the result aware using the current timezone.
    """
    date_str = date_str.strip()
    formats = [
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y %I:%M%p",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %I:%M %p",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unable to parse date: {date_str}")


def _find_patient(patient_phone: str, user_id=None):
    """Normalize phone number and retrieve associated Patient user.

    This function now robustly handles a wide variety of phone formats, including:
    * Optional leading '+' and surrounding whitespace.
    * Common separators such as spaces, dashes, or parentheses.
    * International formats (e.g., "+1xxxxxxxxxx") and local formats without a leading '+'
    * Bangladeshi numbers in both international ("+880XXXXXXXXX") and local ("01XXXXXXXXX") forms.
    * If a local number is stored without a leading zero but the input lacks it (e.g., "+1719..." vs "0179..."), a zero‑prefixed variant is added.
    * Additionally, for plain 10‑digit numbers that lack a country code, a "+1" prefix is tried (common US style).
    """
    # Strip whitespace and keep only digits and '+'
    cleaned = patient_phone.strip()
    cleaned = ''.join(ch for ch in cleaned if ch.isdigit() or ch == '+')
    cleaned_phone = cleaned.lstrip('+')

    # Start building variant set
    variants = set()
    # Raw digits (no plus) and with plus
    variants.add(cleaned_phone)
    variants.add('+' + cleaned_phone)

    # If the number appears to be an international format without '+', add '+'
    if not patient_phone.startswith('+') and cleaned_phone.isdigit() and len(cleaned_phone) > 7:
        variants.add('+' + cleaned_phone)

    # International Bangladeshi format -> local variant (e.g., 880xxxxxxxxx -> 01xxxxxxxxx)
    if cleaned_phone.startswith('880') and not cleaned_phone.startswith('8800'):
        local_bd = '0' + cleaned_phone[3:]
        variants.add(local_bd)
        variants.add('+' + local_bd)

    # If the number looks like a local Bangladeshi number without leading zero
    if not cleaned_phone.startswith('0') and cleaned_phone.isdigit() and len(cleaned_phone) == 10:
        zero_prefixed = '0' + cleaned_phone
        variants.add(zero_prefixed)
        variants.add('+' + zero_prefixed)

    # Common case: plain 10‑digit US number without country code – try adding +1
    if cleaned_phone.isdigit() and len(cleaned_phone) == 10:
        variants.add('+1' + cleaned_phone)
        variants.add('1' + cleaned_phone)

    from django.contrib.auth.models import User
    from appointments.models import PatientProfile
    patient = None
    if user_id:
        try:
            patient = User.objects.get(id=user_id)
        except User.DoesNotExist:
            pass
    if not patient:
        for phone_key in variants:
            try:
                profile = PatientProfile.objects.get(phone=phone_key)
                patient = profile.user
                break
            except PatientProfile.DoesNotExist:
                continue
    return patient
    from django.contrib.auth.models import User
    from appointments.models import PatientProfile
    patient = None
    if user_id:
        try:
            patient = User.objects.get(id=user_id)
        except User.DoesNotExist:
            pass
    if not patient and patient_phone:
        try:
            profile = PatientProfile.objects.get(phone=patient_phone.strip())
            patient = profile.user
        except PatientProfile.DoesNotExist:
            pass
    return patient


@tool
def book_appointment(patient_phone: str, doctor_name: str = None, date_slot: str = None, **kwargs) -> dict:
    """Book an appointment for a patient.
    Accepts both ``doctor_name`` and the alias ``doctorname`` (similarly for ``date_slot`` / ``dateslot``) to be tolerant of variations from the chatbot.
    """
    # Support alias arguments
    if doctor_name is None and "doctorname" in kwargs:
        doctor_name = kwargs["doctorname"]
    if date_slot is None and "dateslot" in kwargs:
        date_slot = kwargs["dateslot"]

    """Book an appointment for a patient.

    Args:
        patient_phone: Patient's phone number.
        doctor_name: Name of the doctor (case-insensitive; prefixes like 'Dr.' are stripped).
        date_slot: Desired appointment date and time in M/D/YYYY H:MM format.
        **kwargs: Additional context, e.g., user_id.

    Returns:
        dict with keys 'success' (bool) and 'message' (str) indicating outcome.
    """
    try:
        target_dt = _parse_date(date_slot)
    except Exception:
        return {"success": False, "message": f"Invalid date_slot format: {date_slot}"}
    try:
        clean_name = doctor_name.strip().lower()
        for prefix in ("dr. ", "dr.", "doctor "):
            if clean_name.startswith(prefix):
                clean_name = clean_name[len(prefix):].strip()
        doctor = Doctor.objects.get(name__iexact=clean_name)
    except Doctor.DoesNotExist:
        return {"success": False, "message": f"Doctor {doctor_name} not found."}
    try:
        appt = Appointment.objects.get(doctor=doctor, date_slot=target_dt)
    except Appointment.DoesNotExist:
        return {"success": False, "message": "Slot not found for this doctor."}
    if appt.status != "available":
        return {"success": False, "message": "Slot is already booked."}
    user_id = kwargs.get("user_id")
    patient = _find_patient(patient_phone, user_id=user_id)
    if not patient:
        return {"success": False, "message": f"No patient found with phone number {patient_phone}."}
    appt.patient = patient
    appt.status = "booked"
    appt.save()
    # Return normalized phone number for confirmation
    normalized_phone = None
    try:
        profile = patient.patient_profile
        normalized_phone = profile.phone
    except Exception:
        normalized_phone = patient_phone
    return {
        "success": True,
        "message": f"Appointment booked for {patient.get_full_name() or patient.username} with {doctor_name.title()} at {date_slot}.",
        "patient_phone": normalized_phone,
    }


@tool
def cancel_appointment(patient_phone: str, date_slot: str, **kwargs) -> dict:
    """Cancel a booked appointment for a patient.

    This function now frees the slot for future bookings by marking it
    as ``available`` and clearing the patient reference.
    """
    try:
        target_dt = _parse_date(date_slot)
    except Exception:
        return {"success": False, "message": f"Invalid date_slot format: {date_slot}"}
    user_id = kwargs.get("user_id")
    patient = _find_patient(patient_phone, user_id=user_id)
    if not patient:
        return {"success": False, "message": f"No patient found with phone number {patient_phone}."}
    try:
        appt = Appointment.objects.get(
            patient=patient, date_slot=target_dt, status="booked"
        )
    except Appointment.DoesNotExist:
        return {
            "success": False,
            "message": f"No booked appointment found for your account at {date_slot}.",
        }
    # Release the slot for reuse
    appt.status = "available"
    appt.patient = None
    appt.save()
    return {
        "success": True,
        "message": f"Appointment at {date_slot} for {patient.get_full_name() or patient.username} has been cancelled and slot is now available.",
    }


@tool
def reschedule_appointment(
    patient_phone: str,
    current_date_slot: str,
    new_date_slot: str,
    doctor_name: str,
    **kwargs,
) -> dict:
    """Reschedule an existing appointment for a patient.

    Args:
        patient_phone: Patient's phone number.
        current_date_slot: Current appointment date and time in M/D/YYYY H:MM format.
        new_date_slot: Desired new date and time in the same format.
        doctor_name: Name of the doctor (case-insensitive; prefixes stripped).
        **kwargs: Additional context, e.g., user_id.

    Returns:
        dict with keys 'success' (bool) and 'message' (str) indicating outcome.
    """
    try:
        current_dt = _parse_date(current_date_slot)
        new_dt = _parse_date(new_date_slot)
    except Exception as exc:
        return {"success": False, "message": f"Date parse error: {exc}"}
    user_id = kwargs.get("user_id")
    patient = _find_patient(patient_phone, user_id=user_id)
    if not patient:
        return {"success": False, "message": f"No patient found with phone number {patient_phone}."}
    try:
        clean_name = doctor_name.strip().lower()
        for prefix in ("dr. ", "dr.", "doctor "):
            if clean_name.startswith(prefix):
                clean_name = clean_name[len(prefix):].strip()
        doctor = Doctor.objects.get(name__iexact=clean_name)
    except Doctor.DoesNotExist:
        return {"success": False, "message": f"Doctor {doctor_name} not found."}
    try:
        old_appt = Appointment.objects.get(
            patient=patient, doctor=doctor, date_slot=current_dt, status="booked"
        )
    except Appointment.DoesNotExist:
        return {
            "success": False,
            "message": f"No existing booking found for phone number {patient_phone} at {current_date_slot}.",
        }
    try:
        new_appt = Appointment.objects.get(doctor=doctor, date_slot=new_dt)
    except Appointment.DoesNotExist:
        return {"success": False, "message": f"Slot {new_date_slot} does not exist for {doctor_name}."}
    if new_appt.status != "available":
        return {"success": False, "message": f"Slot {new_date_slot} is already taken."}
    old_appt.status = "cancelled"
    old_appt.save()
    new_appt.patient = patient
    new_appt.status = "booked"
    new_appt.save()
    return {
        "success": True,
        "message": (
            f"Appointment for {patient.get_full_name() or patient.username} rescheduled from "
            f"{current_date_slot} to {new_date_slot} with {doctor_name}."
        ),
    }
