from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from .models import Doctor, Appointment


def home(request):
    doctors = Doctor.objects.filter(is_active=True).select_related().order_by('specialization', 'name')

    specializations = [choice[0] for choice in Doctor._meta.get_field('specialization').choices]

    context = {
        'doctors': doctors,
        'specializations': specializations,
    }
    return render(request, 'home.html', context)


@login_required
def dashboard(request):
    now = timezone.now()
    upcoming_all = Appointment.objects.filter(
        patient=request.user,
        status='booked',
        date_slot__gt=now
    ).select_related('doctor').order_by('date_slot')

    upcoming = upcoming_all[:5]
    upcoming_count = upcoming_all.count()

    past_all = Appointment.objects.filter(
        patient=request.user,
        date_slot__lte=now
    ).select_related('doctor').order_by('-date_slot')

    past = past_all[:10]
    completed_count = past_all.filter(status='completed').count()

    cancelled = Appointment.objects.filter(
        patient=request.user,
        status='cancelled'
    ).select_related('doctor').order_by('-date_slot')[:10]

    total_appointments = Appointment.objects.filter(
        patient=request.user,
        status__in=['booked', 'completed']
    ).count()

    context = {
        'upcoming': upcoming,
        'upcoming_count': upcoming_count,
        'past': past,
        'cancelled': cancelled,
        'total_appointments': total_appointments,
        'completed_count': completed_count,
    }
    return render(request, 'dashboard.html', context)


def appointments_list(request):
    status = request.GET.get('status', '')
    specialization = request.GET.get('specialization', '')
    doctor_id = request.GET.get('doctor', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    appointments = Appointment.objects.select_related('doctor', 'patient').all()

    if status:
        appointments = appointments.filter(status=status)
    if specialization:
        appointments = appointments.filter(doctor__specialization=specialization)
    if doctor_id:
        appointments = appointments.filter(doctor_id=doctor_id)
    if date_from:
        appointments = appointments.filter(date_slot__gte=date_from)
    if date_to:
        appointments = appointments.filter(date_slot__lte=date_to)

    if request.user.is_authenticated:
        if status == 'booked':
            appointments = appointments.filter(patient=request.user)

    appointments = appointments.order_by('date_slot')

    doctors = Doctor.objects.filter(is_active=True).order_by('name')

    is_htmx = request.headers.get('HX-Request') == 'true'

    context = {
        'appointments': appointments,
        'doctors': doctors,
        'status': status,
        'specialization': specialization,
        'doctor_id': doctor_id,
        'date_from': date_from,
        'date_to': date_to,
    }

    if is_htmx:
        return render(request, 'appointments/partials/appointment_list.html', context)

    return render(request, 'appointments/appointments_list.html', context)


def appointment_detail(request, pk):
    appointment = get_object_or_404(
        Appointment.objects.select_related('doctor', 'patient'),
        pk=pk
    )
    context = {'appointment': appointment}

    is_htmx = request.headers.get('HX-Request') == 'true'
    if is_htmx:
        return render(request, 'appointments/partials/appointment_detail.html', context)

    return render(request, 'appointments/appointment_detail.html', context)


@login_required
def book_appointment(request):
    if request.method == 'POST':
        appointment_id = request.POST.get('appointment_id')
        notes = request.POST.get('notes', '')

        appointment = get_object_or_404(Appointment, pk=appointment_id)

        if appointment.status != 'available':
            context = {'error': 'This slot is no longer available.'}
            return render(request, 'appointments/partials/book_result.html', context, status=400)

        appointment.patient = request.user
        appointment.status = 'booked'
        appointment.notes = notes
        appointment.save()

        context = {'appointment': appointment, 'success': True}
        return render(request, 'appointments/partials/book_result.html', context)

    return HttpResponse('Method not allowed', status=405)


@login_required
def cancel_appointment(request, pk):
    if request.method == 'POST':
        appointment = get_object_or_404(Appointment, pk=pk)

        if appointment.patient != request.user and not request.user.is_staff:
            return HttpResponse('Forbidden', status=403)

        if appointment.status not in ('booked',):
            context = {'error': 'Cannot cancel this appointment.'}
            return render(request, 'appointments/partials/cancel_result.html', context, status=400)

        # Mark the slot as available again so it can be booked
        appointment.status = 'available'
        appointment.patient = None
        appointment.save()

        # Redirect to dashboard to show the updated state
        return redirect('dashboard')

    return HttpResponse('Method not allowed', status=405)


@login_required
def reschedule_appointment(request, pk):
    if request.method == 'POST':
        appointment = get_object_or_404(Appointment, pk=pk)

        if appointment.patient != request.user and not request.user.is_staff:
            return HttpResponse('Forbidden', status=403)

        if appointment.status != 'booked':
            context = {'error': 'Cannot reschedule this appointment.'}
            return render(request, 'appointments/partials/reschedule_result.html', context, status=400)

        new_date_slot = request.POST.get('new_date_slot')
        if not new_date_slot:
            context = {'error': 'New date/time is required.'}
            return render(request, 'appointments/partials/reschedule_result.html', context, status=400)

        try:
            from django.utils.dateparse import parse_datetime
            new_datetime = parse_datetime(new_date_slot)
            if not new_datetime:
                from datetime import datetime
                new_datetime = datetime.strptime(new_date_slot, '%Y-%m-%dT%H:%M')
        except (ValueError, TypeError):
            context = {'error': 'Invalid date format.'}
            return render(request, 'appointments/partials/reschedule_result.html', context, status=400)

        if new_datetime <= timezone.now():
            context = {'error': 'Cannot reschedule to a past date.'}
            return render(request, 'appointments/partials/reschedule_result.html', context, status=400)

        existing = Appointment.objects.filter(
            doctor=appointment.doctor,
            date_slot=new_datetime
        ).exclude(pk=appointment.pk).first()

        if existing:
            context = {'error': 'This slot is already taken.'}
            return render(request, 'appointments/partials/reschedule_result.html', context, status=400)

        appointment.date_slot = new_datetime
        appointment.save()

        # After successful reschedule, redirect to dashboard to show updated appointment
        return redirect('dashboard')

    return HttpResponse('Method not allowed', status=405)


def available_slots(request):
    doctor_id = request.GET.get('doctor_id')
    date = request.GET.get('date')

    now = timezone.now()

    slots = Appointment.objects.filter(
        status='available',
        date_slot__gte=now
    ).select_related('doctor')

    if doctor_id:
        slots = slots.filter(doctor_id=doctor_id)
    if date:
        slots = slots.filter(date_slot__date=date)

    slots = slots.order_by('date_slot')

    context = {
        'slots': slots,
        'doctor_id': doctor_id,
        'date': date,
    }

    return render(request, 'appointments/partials/available_slots.html', context)


def doctors_list(request):
    specialization = request.GET.get('specialization', '')

    doctors = Doctor.objects.filter(is_active=True)
    if specialization:
        doctors = doctors.filter(specialization=specialization)

    doctors = doctors.distinct().order_by('name')

    context = {
        'doctors': doctors,
        'specialization': specialization,
    }

    return render(request, 'appointments/partials/doctors_list.html', context)
