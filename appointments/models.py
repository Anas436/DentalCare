from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Doctor(models.Model):
    name = models.CharField(max_length=200)
    specialization = models.CharField(max_length=100, choices=[
        ('general_dentist', 'General Dentist'),
        ('oral_surgeon', 'Oral Surgeon'),
        ('orthodontist', 'Orthodontist'),
        ('cosmetic_dentist', 'Cosmetic Dentist'),
        ('prosthodontist', 'Prosthodontist'),
        ('pediatric_dentist', 'Pediatric Dentist'),
        ('emergency_dentist', 'Emergency Dentist'),
        ('endodontist', 'Endodontist'),
    ])
    bio = models.TextField(blank=True, default='')
    image = models.ImageField(upload_to='doctors/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        unique_together = ['name', 'specialization']

    def __str__(self):
        return f"Dr. {self.name} ({self.get_specialization_display()})"


class Appointment(models.Model):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('booked', 'Booked'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]

    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='appointments')
    date_slot = models.DateTimeField()
    patient = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='appointments')
    patient_id_external = models.CharField(max_length=50, blank=True, default='', help_text='External patient ID if not linked to user')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['date_slot']
        unique_together = ['doctor', 'date_slot']
        indexes = [
            models.Index(fields=['status', 'date_slot']),
            models.Index(fields=['patient', 'status']),
        ]

    def __str__(self):
        doctor_str = f"Dr. {self.doctor.name}" if self.doctor else "No Doctor"
        if self.patient:
            return f"{doctor_str} - {self.date_slot.strftime('%m/%d/%Y %H:%M')} - {self.patient.username}"
        return f"{doctor_str} - {self.date_slot.strftime('%m/%d/%Y %H:%M')} - Available"

    @property
    def is_available(self):
        return self.status == 'available'

    @property
    def is_upcoming(self):
        return self.date_slot > timezone.now() and self.status == 'booked'

    @property
    def is_past(self):
        return self.date_slot <= timezone.now()


class PatientProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='patient_profile')
    phone = models.CharField(max_length=20, blank=True, default='')
    date_of_birth = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True, default='')
    emergency_contact = models.CharField(max_length=100, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username}'s Profile"
