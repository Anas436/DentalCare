from datetime import datetime
from typing import Optional
from langchain_core.tools import tool
from appointments.models import Appointment, Doctor
from dental_agent.tools.db_reader import _format_date_slot


def _parse_date(date_str: str) -> datetime:
    """Parse a date string into a timezone‑aware datetime.

    Handles common formats, ordinal day suffixes (e.g., "8th July 2026 at 10:30 AM"),
    and cleans up stray duplicate "at" tokens.
    """
    import re
    from django.utils import timezone
    # Normalize all whitespace (including double spaces), remove duplicate "at" occurrences
    date_str = re.sub(r'\s+', ' ', date_str)
    date_str = re.sub(r"\bat\b\s+\bat\b", "at", date_str, flags=re.IGNORECASE)
    # Remove ordinal suffixes like st, nd, rd, th (e.g., "8th" -> "8")
    date_str = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", date_str, flags=re.IGNORECASE)
    date_str = date_str.strip()
    formats = [
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y %I:%M%p",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %I:%M %p",
        "%d %B %Y at %I:%M %p",
        "%d %B %Y %I:%M %p",
        "%d %b %Y at %I:%M %p",
        "%d %b %Y %I:%M %p",
        "%b %d, %Y at %I:%M %p",
        "%b %d, %Y %I:%M %p",
        "%B %d, %Y at %I:%M %p",
        "%B %d, %Y %I:%M %p",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return timezone.make_aware(dt, timezone.get_current_timezone())
        except ValueError:
            continue
    raise ValueError(f"Unable to parse date: {date_str}")


def _find_patient(patient_phone: str, user_id=None, create_if_missing=False):
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

    # Additional handling: for numbers that start with a leading zero (e.g., 01792170982),
    # also try the version without the leading zero. This covers records stored without the
    # zero prefix while still accepting the user's format.
    if cleaned_phone.startswith('0') and len(cleaned_phone) > 1:
        stripped = cleaned_phone.lstrip('0')
        variants.add(stripped)
        if stripped.isdigit() and len(stripped) == 10:
            variants.add('+' + stripped)


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
    # Final fallback: try the raw cleaned phone string as stored
    if not patient:
        try:
            profile = PatientProfile.objects.get(phone=cleaned)
            patient = profile.user
        except PatientProfile.DoesNotExist:
            pass
    # Additional fuzzy fallback: match on last 10 digits (common local format)
    if not patient:
        try:
            last10 = cleaned_phone[-10:]
            profile = PatientProfile.objects.filter(phone__icontains=last10).first()
            if profile:
                patient = profile.user
        except Exception:
            pass
    return patient


@tool
def appointment(
    patient_phone: str = "",
    doctor_name: str = None,
    date_slot: str = None,
    patientphone: str = "",
    doctorname: str = None,
    dateslot: str = None,
    currentdateslot: str = "",
    current_date_slot: str = "",
    newdateslot: str = "",
    new_date_slot: str = "",
    user_id: Optional[int] = None,
    userid: Optional[int] = None,
) -> dict:
    """Book an appointment for a patient.
    Accepts both ``doctor_name`` and the alias ``doctorname`` (similarly for ``date_slot`` / ``dateslot``) to be tolerant of variations from the chatbot.
    """
    if user_id is None and userid is not None:
        user_id = userid
    # If called with rescheduling params, redirect
    if currentdateslot or current_date_slot or newdateslot or new_date_slot:
        return {
            "success": False,
            "message": "The appointment tool is for NEW bookings only. Use the reschedule_appointment tool to reschedule an existing booking."
        }
    if not patient_phone and patientphone:
        patient_phone = patientphone
    if doctor_name is None and doctorname is not None:
        doctor_name = doctorname
    if date_slot is None and dateslot is not None:
        date_slot = dateslot
    if not date_slot and not doctor_name:
        return {"success": False, "message": "Please provide a doctor name and date/time for the appointment."}
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
    patient = _find_patient(patient_phone, user_id=user_id)
    if not patient:
        # Try to locate a patient via existing appointments using the phone number
        try:
            profile = None
            from appointments.models import PatientProfile
            profile = PatientProfile.objects.get(phone=patient_phone.strip())
            patient = profile.user
        except Exception:
            pass
    if not patient:
        return {"success": False, "message": f"No patient found with phone number {patient_phone}."}
    # Guard: if the patient already has a booking with this doctor on this date at a different time,
    # they likely meant to reschedule — redirect them.
    existing = Appointment.objects.filter(
        patient=patient, doctor=doctor, status="booked",
        date_slot__date=target_dt.date()
    ).exclude(date_slot=target_dt).exists()
    if existing:
        return {
            "success": False,
            "message": "You already have a booking with this doctor on this date. Use the reschedule_appointment tool to reschedule it instead."
        }
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
def cancel_appointment(patient_phone: str = "", date_slot: str = "", dateslot: str = "", user_id: Optional[int] = None, userid: Optional[int] = None) -> dict:
    """Cancel a booked appointment for a patient.

    If ``date_slot`` is omitted or empty, the function will cancel the first
    booked appointment for the patient (useful when the user says "cancel this booking").
    This function also frees the slot for future bookings by marking it
    as ``available`` and clearing the patient reference.
    """
    if user_id is None and userid is not None:
        user_id = userid
    if not date_slot and dateslot:
        date_slot = dateslot
    patient = _find_patient(patient_phone, user_id=user_id)
    if not patient:
        # Try to locate a patient via existing appointments using the phone number
        try:
            profile = None
            from appointments.models import PatientProfile
            profile = PatientProfile.objects.get(phone=patient_phone.strip())
            patient = profile.user
        except Exception:
            pass
    if not patient:
        return {"success": False, "message": f"No patient found with phone number {patient_phone}."}
    # If a specific date_slot is provided, try to cancel that exact slot
    if date_slot:
        try:
            target_dt = _parse_date(date_slot)
        except Exception:
            return {"success": False, "message": f"Invalid date_slot format: {date_slot}"}
        try:
            appt = Appointment.objects.get(
                patient=patient, date_slot=target_dt, status="booked"
            )
        except Appointment.DoesNotExist:
            return {
                "success": False,
                "message": f"No booked appointment found for your account at {date_slot}.",
            }
    else:
        # No date provided: find any booked appointment for this patient
        appt_qs = Appointment.objects.filter(patient=patient, status="booked").order_by("date_slot")
        if not appt_qs.exists():
            return {"success": False, "message": "No booked appointments found to cancel."}
        appt = appt_qs.first()
        target_dt = appt.date_slot
        date_slot = _format_date_slot(target_dt) if hasattr(appt, "date_slot") else str(target_dt)
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
    patient_phone: str = "",
    new_date_slot: str = "",
    doctor_name: str = None,
    current_date_slot: str = "",
    patientphone: str = "",
    newdateslot: str = "",
    doctorname: str = None,
    currentdateslot: str = "",
    newdate_slot: str = "",
    newdate: str = "",
    currentdate: str = "",
    dateslot: str = "",
    user_id: Optional[int] = None,
    userid: Optional[int] = None,
) -> dict:
    """Reschedule an existing appointment.
    Accepts aliases: patientphone, doctorname, newdate_slot, newdate, currentdateslot, currentdate.
    """
    if user_id is None and userid is not None:
        user_id = userid
    if not patient_phone and patientphone:
        patient_phone = patientphone
    if not doctor_name and doctorname is not None:
        doctor_name = doctorname
    if not new_date_slot and newdateslot:
        new_date_slot = newdateslot
    if not new_date_slot and newdate_slot:
        new_date_slot = newdate_slot
    if not new_date_slot and newdate:
        new_date_slot = newdate
    if not current_date_slot and currentdateslot:
        current_date_slot = currentdateslot
    if not current_date_slot and currentdate:
        current_date_slot = currentdate
    if not new_date_slot and dateslot:
        new_date_slot = dateslot

    # Parse the new date slot (required)
    new_dt = None
    try:
        new_dt = _parse_date(new_date_slot)
    except Exception:
        pass
    # If new_date_slot is time-only (e.g. "11:00 AM"), infer date from current_date_slot
    if new_dt is None and current_date_slot:
        try:
            current_dt = _parse_date(current_date_slot)
            time_formats = ["%I:%M %p", "%H:%M"]
            for tf in time_formats:
                try:
                    parsed_time = datetime.strptime(new_date_slot.strip(), tf).time()
                    new_dt = current_dt.replace(hour=parsed_time.hour, minute=parsed_time.minute, second=0, microsecond=0)
                    break
                except Exception:
                    continue
        except Exception:
            pass
    if new_dt is None:
        try:
            new_dt = _parse_date(new_date_slot)
        except Exception as exc:
            return {"success": False, "message": f"Date parse error for new_date_slot: {exc}"}
    # Retrieve patient first (may be needed for doctor inference)
    patient = _find_patient(patient_phone, user_id=user_id)
    if not patient:
        # Attempt fallback lookup via existing appointments
        try:
            from appointments.models import PatientProfile
            profile = PatientProfile.objects.get(phone=patient_phone.strip())
            patient = profile.user
        except Exception:
            return {"success": False, "message": f"No patient found with phone number {patient_phone}."}
    # Resolve doctor if provided; otherwise will infer later
    doctor = None
    if doctor_name:
        clean_name = doctor_name.strip().lower()
        for prefix in ("dr. ", "dr.", "doctor "):
            if clean_name.startswith(prefix):
                clean_name = clean_name[len(prefix):].strip()
        try:
            doctor = Doctor.objects.get(name__iexact=clean_name)
        except Doctor.DoesNotExist:
            return {"success": False, "message": f"Doctor {doctor_name} not found."}
    # Parse current date slot if provided, otherwise find the existing booked appointment
    if current_date_slot:
        try:
            current_dt = _parse_date(current_date_slot)
        except Exception as exc:
            return {"success": False, "message": f"Date parse error for current_date_slot: {exc}"}
    else:
        # Need doctor to find appointment; if not provided, infer from existing appointment later
        if doctor:
            existing_appts = Appointment.objects.filter(doctor=doctor, status="booked").order_by("date_slot")
        else:
            existing_appts = Appointment.objects.filter(status="booked").order_by("date_slot")
        if not existing_appts.exists():
            return {"success": False, "message": "No existing booked appointment found. Provide current date or doctor."}
        old_appt = existing_appts.first()
        current_dt = old_appt.date_slot
        # Infer doctor if not already resolved
        if not doctor:
            doctor = old_appt.doctor
        # Infer patient from the existing appointment
        patient = old_appt.patient

    # Ensure we have a patient before proceeding
    if not patient:
        return {"success": False, "message": "Patient could not be identified for rescheduling."}
    # At this point doctor is resolved (either provided or inferred) and patient is set.
    # Retrieve the specific old appointment to cancel
    try:
        old_appt = Appointment.objects.get(
            patient=patient, doctor=doctor, date_slot=current_dt, status="booked"
        )
    except Appointment.DoesNotExist:
        # Fallback: any booked slot for this doctor at the given time
        try:
            old_appt = Appointment.objects.get(
                doctor=doctor, date_slot=current_dt, status="booked"
            )
            old_appt.patient = patient
            old_appt.save()
        except Appointment.DoesNotExist:
            return {"success": False, "message": f"No existing booking found for the specified time."}
    # Find the new slot
    try:
        new_appt = Appointment.objects.get(doctor=doctor, date_slot=new_dt)
    except Appointment.DoesNotExist:
        return {"success": False, "message": f"Slot {new_date_slot} does not exist for {doctor_name or doctor.name}."}
    if new_appt.status != "available":
        return {"success": False, "message": f"Slot {new_date_slot} is already taken."}
    # Perform reschedule
    old_appt.status = "cancelled"
    old_appt.save()
    new_appt.patient = patient
    new_appt.status = "booked"
    new_appt.save()
    return {
        "success": True,
        "message": (
            f"Appointment for {patient.get_full_name() or patient.username} rescheduled from "
            f"{current_date_slot or current_dt} to {new_date_slot} with {doctor_name or doctor.name}."
        ),
    }
