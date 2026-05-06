from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('appointments/', views.appointments_list, name='appointments_list'),
    path('appointments/<int:pk>/', views.appointment_detail, name='appointment_detail'),
    path('appointments/book/', views.book_appointment, name='book_appointment'),
    path('appointments/<int:pk>/cancel/', views.cancel_appointment, name='cancel_appointment'),
    path('appointments/<int:pk>/reschedule/', views.reschedule_appointment, name='reschedule_appointment'),
    path('slots/available/', views.available_slots, name='available_slots'),
    path('doctors/', views.doctors_list, name='doctors_list'),
]
