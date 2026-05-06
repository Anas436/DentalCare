# DentalCare - AI-Powered Dental Appointment System

A modern, full-stack Django web application for managing dental appointments with an AI automations chatbot assistant powered by LangGraph and Groq (Llama 3).

## Features

- **AI Chatbot Assistant** - Natural language interface for booking, canceling, and rescheduling appointments
- **Interactive Dashboard** - View upcoming appointments, stats, and quick actions
- **Appointment Management** - Browse available slots, book, cancel, and reschedule appointments
- **User Authentication** - Registration, login, and profile management
- **Admin Panel** - Full Django admin for managing doctors, appointments, and users
- **Responsive Design** - Mobile-first design with TailwindCSS
- **HTMX-Powered Interactivity** - Dynamic, SPA-like experience with JavaScript frameworks

## Tech Stack

- **Backend**: Django 5+, Python 3.14
- **AI/ML**: LangGraph, LangChain, Groq (Llama 3.3 70B)
- **Frontend**: TailwindCSS, HTMX, Alpine.js
- **Database**: SQLite (development), PostgreSQL-ready
- **Deployment**: Whitenoise, Gunicorn-ready

## Installation

1. **Clone and navigate**:
   ```bash
   cd DentalCare 
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**:
   Create `.env` file with:
   ```
   SECRET_KEY=your-secret-key
   DEBUG=True
   GROQ_API_KEY=your-groq-api-key
   MODEL_NAME=llama-3.1-8b-instant
   TEMPERATURE=0
   ```

5. **Run migrations**:
   ```bash
   python manage.py migrate
   ```

6. **Create superuser**:
   ```bash
   python manage.py createsuperuser
   ```

7. **Start server**:
   ```bash
   python manage.py runserver
   ```

Visit `http://localhost:8000` to access the application.

## Project Structure

```
Dental-Appointment/
├── config/                 # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── appointments/           # Core appointment management app
│   ├── models.py          # Doctor, Appointment, PatientProfile
│   ├── views.py
│   ├── admin.py
│   └── templatetags/
├── chatbot_app/           # AI chatbot integration
│   ├── views.py
│   ├── services.py        # LangGraph wrapper
│   └── templates/chatbot_app/chat.html
├── accounts/              # User authentication
│   ├── views.py
│   ├── forms.py
│   └── templates/accounts/
├── templates/             # Global templates
│   ├── base.html
│   ├── home.html
│   └── dashboard.html
└── static/                # Static files
```

## Available Specializations

- General Dentist
- Oral Surgeon
- Orthodontist
- Cosmetic Dentist
- Prosthodontist
- Pediatric Dentist
- Emergency Dentist
- Endodontist 

## Admin Panel

Access at `/admin/` with your superuser credentials. Manage doctors, appointments, and user profiles.

