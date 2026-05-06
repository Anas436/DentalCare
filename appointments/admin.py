from django.contrib import admin
from .models import Doctor, Appointment, PatientProfile


@admin.action(description='Mark selected appointments as completed')
def mark_as_completed(modeladmin, request, queryset):
    updated = queryset.update(status='completed')
    modeladmin.message_user(request, f'{updated} appointment(s) marked as completed.')


@admin.action(description='Mark selected appointments as cancelled')
def mark_as_cancelled(modeladmin, request, queryset):
    updated = queryset.update(status='cancelled')
    modeladmin.message_user(request, f'{updated} appointment(s) marked as cancelled.')


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ('name', 'specialization', 'is_active', 'created_at')
    list_filter = ('specialization', 'is_active', 'created_at')
    search_fields = ('name', 'bio')
    list_editable = ('is_active',)
    ordering = ('name',)


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('doctor', 'date_slot', 'patient', 'patient_id_external', 'status', 'created_at')
    list_filter = ('status', 'doctor__specialization', 'date_slot', 'doctor')
    search_fields = ('patient__username', 'patient__email', 'patient_id_external', 'notes')
    date_hierarchy = 'date_slot'
    ordering = ('-date_slot',)
    actions = [mark_as_completed, mark_as_cancelled]


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'date_of_birth', 'created_at', 'updated_at')
    search_fields = ('user__username', 'user__email', 'user__first_name', 'user__last_name', 'phone')
    list_filter = ('created_at', 'updated_at')
    ordering = ('-user__username',)
