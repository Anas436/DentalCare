---
name: Project Architecture
description: Comprehensive architecture overview of the Dental Appointment system covering backend, frontend, data layer, and deployment.
type: reference
---

# Dental Appointment System – Architecture Overview

This document provides a **full‑project** architectural diagram in markdown form, describing how the various parts of the codebase fit together, the data flow, and the deployment model.

---

## 1. High‑Level System View

```
+-------------------+      +-------------------+      +-------------------+
|   Frontend UI    | <--> |   FastAPI /      | <--> |   Database (SQLite) |
| (templates,      |      |   Flask (Django)  |      |   db.sqlite3      |
|   static files)  |      |   app entrypoint) |      +-------------------+
+-------------------+      +-------------------+
        ^                        ^
        |                        |
        |                        |
        v                        v
+-------------------+      +-------------------+
|   Agents Layer   |      |   Configuration   |
|  (booking,       |      |   (settings.py)   |
|   cancellation,  |      +-------------------+
|   info, etc.)    |
+-------------------+
```

* **Frontend UI** – HTML templates in `templates/`, static assets, and optional JavaScript for the chat interface.
* **Agents Layer** – Business‑logic components under `dental_agent/agents/` that implement booking, cancellation, rescheduling, information retrieval, and supervision.
* **Configuration** – Central settings in `dental_agent/config/settings.py` controlling environment variables, DB path, and feature toggles.
* **Database** – SQLite file `db.sqlite3` accessed via helper utilities in `dental_agent/tools/`.

---

## 2. Backend Components

| Module | Location | Responsibility |
|--------|----------|----------------|
| **Main Entrypoint** | `main.py` | Starts the FastAPI/Flask server, registers routes, and wires agents. |
| **Agents** | `dental_agent/agents/` | Encapsulate distinct use‑cases:
| | `booking_agent.py` | Handles new appointment creation, validates doctor availability, writes to DB. |
| | `cancellation_agent.py` | Cancels existing appointments, updates DB, sends confirmations. |
| | `rescheduling_agent.py` | Reschedules appointments, ensures no conflicts. |
| | `info_agent.py` | Provides read‑only information (available slots, doctor list). |
| | `supervisor.py` | Orchestrates multi‑agent workflows and error handling. |
| **State Model** | `dental_agent/models/state.py` | TypedDict definitions (`AppointmentState`) used across agents for type‑safe data exchange. |
| **Utilities** | `dental_agent/utils.py` | Shared helpers (date parsing, logger, response formatting). |
| **Configuration** | `dental_agent/config/settings.py` | Central config (DB path, environment flags, logging). |
| **DB Readers/Writers** | `dental_agent/tools/db_reader.py` & `db_writer.py` | Thin wrappers around `sqlite3` for CRUD operations. |
| **Legacy CSV Tools** *(deleted)* | `dental_agent/tools/csv_reader.py`, `csv_writer.py` | Previously used for CSV import/export; currently deprecated. |

---

## 3. Frontend / Presentation Layer

| Directory | Purpose |
|-----------|---------|
| `templates/` | Jinja2/HTML templates for the web UI (booking form, confirmation pages, admin view). |
| `static/` *(if present)* | CSS, JavaScript, and image assets. |
| `chatbot_app/` | Optional chatbot UI that leverages the agents via HTTP endpoints. |
| `accounts/` | User authentication and session management (if enabled). |

The UI communicates with the backend via HTTP endpoints exposed in `main.py` (e.g., `/book`, `/cancel`).

---

## 4. Data Layer

- **SQLite Database** – `db.sqlite3` stores tables for `appointments`, `doctors`, `patients`, and `availability`.
- **Schema Definition** – Managed implicitly through the helper modules; migrations are currently manual (SQL scripts under `migrations/` if they exist).
- **Legacy CSV Files** – `doctor_availability.csv` was used in early prototypes but has been removed; data now resides in the DB.

---

## 5. Deployment Model

| Aspect | Details |
|--------|---------|
| **Containerisation** | A `Dockerfile` (if provided) can build an image that installs `requirements.txt`, copies the source, and runs `uvicorn main:app` (or Flask run). |
| **CI/CD** | Typical GitHub Actions workflow (not present in the repo but can be added) would run `pip install -r requirements.txt`, execute unit tests, and push the Docker image to a registry. |
| **Environment Variables** | Loaded from `.env` (e.g., `DATABASE_URL`, `SECRET_KEY`). The `settings.py` module reads these values via `os.getenv`. |
| **Running Locally** | `python manage.py runserver` or `uvicorn main:app --reload`. |
| **Production** | Deploy to a PaaS (e.g., Azure App Service, AWS Elastic Beanstalk) behind a reverse proxy; the DB can be swapped for PostgreSQL while keeping the same data‑access layer. |

---

## 6. Interaction Flow Example (Booking an Appointment)
1. **User** submits a booking form → HTTP POST `/book`.
2. **Router** in `main.py` forwards request to `BookingAgent`.
3. `BookingAgent` calls `db_reader` to fetch doctor availability.
4. Business logic validates timeslots and creates an `AppointmentState` dict.
5. `db_writer` persists the new appointment.
6. Agent returns a success response; UI renders a confirmation page.

---

## 7. Extensibility Points
- **Add New Agents** – Create a new file under `dental_agent/agents/` that implements a subclass of `BaseAgent` (if such a base exists) and register its route in `main.py`.
- **Swap DB** – Replace SQLite helpers with SQLAlchemy models; only `db_reader`/`db_writer` need updating.
- **Authentication** – Plug in Django/Flask‑Login via the `accounts/` package and protect endpoints.
- **External APIs** – Integrate calendar services (Google Calendar, Outlook) by adding wrappers inside `dental_agent/tools/`.

---

*This architecture document is stored as a reference memory file, so future conversations can quickly locate the high‑level design of the Dental Appointment project.*
