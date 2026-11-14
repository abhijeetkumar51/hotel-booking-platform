# Hotel Booking Platform

A RESTful backend service for hotel room reservations built with Python Flask, PostgreSQL, and Docker. Designed with concurrency-safe booking logic to prevent double bookings, containerized with Docker Compose, and deployed using CI/CD pipelines.

## Tech Stack

- **Backend:** Python 3.12+, Flask 3.1, Gunicorn
- **Database:** PostgreSQL 16 (with `btree_gist` extension)
- **Containerization:** Docker, Docker Compose
- **CI/CD:** GitHub Actions
- **Testing & Quality:** Pytest, Ruff
- **Deployment:** AWS EC2 (Ubuntu), Nginx Reverse Proxy

---

## Features

- **Room & Availability Management:** Query room listings and filter available rooms by date range (`check_in`, `check_out`).
- **Reservation System:** Create and look up bookings using generated references (`HB-XXXXXXXX`).
- **Concurrency-Safe Overlap Prevention:** Uses PostgreSQL GiST exclusion constraint (`daterange`) to prevent double-booking at the database level.
- **Health Checks:** Dedicated `/health` (liveness) and `/ready` (database connectivity) endpoints.
- **Automated CI/CD:** Runs linter, runs test suite against an ephemeral PostgreSQL service container, builds Docker image, and publishes versioned tags to Docker Hub.

---

## Project Structure

```text
├── app/
│   ├── __init__.py        # Package init & DLL directory handling
│   ├── config.py          # Application configuration
│   ├── database.py        # Connection pooling and schema migrations
│   ├── main.py            # Flask app factory
│   └── routes.py          # API route handlers
├── tests/
│   ├── conftest.py        # Fixtures and test database lifecycle
│   └── test_api.py        # Unit, integration, and concurrency tests
├── .github/workflows/
│   └── ci-cd.yml          # GitHub Actions pipeline
├── Dockerfile             # Production container definition (non-root)
├── docker-compose.yml     # Multi-container local/prod environment
├── pyproject.toml         # Ruff and Pytest settings
├── requirements.txt       # Production dependencies
├── requirements-dev.txt   # Development dependencies
└── wsgi.py                # WSGI entrypoint
```

---

## Getting Started

### Prerequisites

- Python 3.12 or newer
- PostgreSQL 14+ or Docker
- Git

### 1. Local Setup

```bash
# Clone the repository
git clone https://github.com/abhijeetkumar51/hotel-booking-platform.git
cd hotel-booking-platform

# Create and activate virtual environment
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# Install dependencies
pip install -r requirements-dev.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your database credentials:

```bash
cp .env.example .env
```

### 3. Run Tests

```bash
pytest -v
```

---

## Running with Docker Compose

To start both the Flask application and the PostgreSQL database:

```bash
docker compose up -d --build
```

Check service status:

```bash
docker compose ps
```

Verify endpoints:

```bash
curl http://localhost:5000/health
curl http://localhost:5000/ready
curl http://localhost:5000/api/rooms
```

To stop:

```bash
docker compose down
```

---

## API Documentation

### 1. Health & Readiness

| Method | Endpoint | Description | Status Code |
|--------|----------|-------------|-------------|
| GET | `/health` | Liveness check (is service up) | 200 |
| GET | `/ready` | Readiness check (is DB connected) | 200 / 503 |

### 2. Rooms & Availability

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/rooms` | List all hotel rooms |
| GET | `/api/availability?check_in=YYYY-MM-DD&check_out=YYYY-MM-DD` | List available rooms for given dates |

### 3. Reservations

#### Create Reservation
- **Endpoint:** `POST /api/reservations`
- **Request Body:**
```json
{
  "room_id": 1,
  "guest_name": "Alice Smith",
  "guest_email": "alice@example.com",
  "check_in": "2026-12-10",
  "check_out": "2026-12-15"
}
```
- **Responses:**
  - `201 Created`: Booking successful, returns reservation details with reference.
  - `400 Bad Request`: Validation failure (past date, invalid format, missing field).
  - `404 Not Found`: Room ID does not exist.
  - `409 Conflict`: Room is already booked for overlapping dates.

#### Look up Reservation
- **Endpoint:** `GET /api/reservations/<booking_reference>`
- **Response:** `200 OK` with reservation object or `404 Not Found`.

---

## Database Design & Concurrency Strategy

To guarantee that overlapping reservations can never occur even under high concurrency, an exclusion constraint is defined using PostgreSQL's GiST index:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE reservations (
    id                SERIAL PRIMARY KEY,
    booking_reference VARCHAR(12)  NOT NULL UNIQUE,
    room_id           INTEGER      NOT NULL REFERENCES rooms(id),
    guest_name        VARCHAR(200) NOT NULL,
    guest_email       VARCHAR(200) NOT NULL,
    check_in          DATE         NOT NULL,
    check_out         DATE         NOT NULL,
    status            VARCHAR(20)  NOT NULL DEFAULT 'confirmed',
    created_at        TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT check_dates CHECK (check_out > check_in),
    EXCLUDE USING gist (
        room_id WITH =,
        daterange(check_in, check_out, '[)') WITH &&
    ) WHERE (status = 'confirmed')
);
```

Using half-open interval `[)` ensures that a guest checking out on date `D` allows another guest to check in on date `D` without conflict.
