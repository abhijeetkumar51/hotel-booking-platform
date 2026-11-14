# Cloud Deployment & CI/CD – Hotel Booking Platform
## Individual Technical Assessment Report

**Student Name:** Abhijeet Kumar  
**Project Title:** Cloud-Native Hotel Reservation API with CI/CD and AWS Deployment  
**Technology Stack:** Python (Flask), PostgreSQL, Docker, Docker Compose, GitHub Actions, Nginx, AWS EC2  
**Public Application URL:** `http://54.161.2.206`  
**GitHub Repository:** `https://github.com/abhijeetkumar51/hotel-booking-platform`  

---

## 1. Executive Summary

This project implements a production-grade, containerized RESTful hotel booking backend designed to solve critical real-world concurrency challenges in reservation management. The application is built with Python Flask, utilizes PostgreSQL with GiST exclusion constraints to prevent overlapping double-bookings at the database level, runs in non-root Docker containers orchestrated by Docker Compose, and is continuously integrated and deployed via GitHub Actions to an AWS EC2 Ubuntu instance reverse-proxied by Nginx.

---

## 2. System Architecture

```text
       +-------------------------------------------------------------+
       |                         Client Layer                        |
       |             (Browser, Postman, Mobile, Curl)                |
       +------------------------------+------------------------------+
                                      | HTTP (Port 80)
                                      v
       +-------------------------------------------------------------+
       |               AWS EC2 (Ubuntu 24.04 LTS)                     |
       |                                                             |
       |  +-------------------------------------------------------+  |
       |  |                 Nginx Reverse Proxy                   |  |
       |  |   - Listens on Port 80                                |  |
       |  |   - Buffers requests, handles client timeouts         |  |
       |  |   - Reverse proxies to http://127.0.0.1:5000          |  |
       |  +---------------------------+---------------------------+  |
       |                              |                              |
       |                              v                              |
       |  +-------------------------------------------------------+  |
       |  |                 Docker Bridge Network                 |  |
       |  |                                                       |  |
       |  |  +-------------------------+   +-------------------+  |  |
       |  |  |  hotel_app Container    |   | hotel_db Container|  |  |
       |  |  |  - Python 3.12-slim     |   | - PostgreSQL 16   |  |  |
       |  |  |  - Non-root (appuser)   |-->| - Persistent Vol  |  |  |
       |  |  |  - Gunicorn WSGI (:5000)|   | - btree_gist      |  |  |
       |  |  +-------------------------+   +-------------------+  |  |
       |  +-------------------------------------------------------+  |
       +-------------------------------------------------------------+
```

---

## 3. Concurrency Control & Database Integrity

### The Overbooking Challenge
In standard web applications, a traditional *check-then-insert* strategy (`SELECT` available rooms followed by `INSERT INTO reservations`) is prone to race conditions. When two requests arrive concurrently for the same room and date range, both checks may return true before either row is committed, leading to duplicate confirmed bookings.

### The Solution: GiST Exclusion Constraint
The database schema leverages PostgreSQL's `btree_gist` extension with an exclusion constraint on half-open date intervals (`[)`):

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

**Key Advantages:**
1. **Serialization Safety:** PostgreSQL enforces date-overlap rejection natively at the storage engine level.
2. **Back-to-Back Bookings:** The half-open interval `[)` allows Guest A to check out on date `D` and Guest B to check in on the same date `D` without conflict.
3. **Application Error Handling:** Overlapping insertions raise a `psycopg2.errors.ExclusionViolation`, which the API handles gracefully and returns an HTTP `409 Conflict`.

---

## 4. API Endpoints Specification

| Method | Endpoint | Description | Expected Status |
|--------|----------|-------------|-----------------|
| `GET` | `/` | API Overview and service discovery directory | `200 OK` |
| `GET` | `/health` | Liveness check verifying the application process | `200 OK` |
| `GET` | `/ready` | Readiness probe verifying PostgreSQL connection | `200 OK` / `503 Unavailable` |
| `GET` | `/api/rooms` | Lists all hotel rooms with pricing and capacity | `200 OK` |
| `GET` | `/api/availability` | Filters available rooms by `check_in` and `check_out` | `200 OK` / `400 Bad Request` |
| `POST` | `/api/reservations` | Books a room; rejects invalid dates and overlaps | `201 Created` / `400` / `409 Conflict` |
| `GET` | `/api/reservations/<ref>` | Looks up booking details by unique reference | `200 OK` / `404 Not Found` |

---

## 5. Automated Testing & Validation

A comprehensive test suite of 22 test cases was implemented using Pytest:
- **Unit & Validation Tests:** Request payload structure, email validation, date ordering (`check_out > check_in`), past date prevention.
- **Integration Tests:** Database connection lifecycle, room catalog queries, availability queries.
- **Concurrency Test:** `TestConcurrentBooking` launches concurrent worker threads attempting identical booking requests simultaneously; verified that exactly one request receives `201 Created` and the second receives `409 Conflict`.

### Test Execution Output:
```text
============================= test session starts =============================
platform win32 -- Python 3.14.7, pytest-8.3.5
collected 22 items

tests/test_api.py::TestIndex::test_index_returns_200_and_service_info PASSED [  4%]
tests/test_api.py::TestHealth::test_health_returns_200 PASSED            [  9%]
tests/test_api.py::TestHealth::test_health_contains_service_name PASSED  [ 13%]
tests/test_api.py::TestReady::test_ready_returns_200_when_db_connected PASSED [ 18%]
tests/test_api.py::TestRooms::test_list_rooms_returns_seeded_rooms PASSED [ 22%]
tests/test_api.py::TestRooms::test_room_has_expected_fields PASSED       [ 27%]
tests/test_api.py::TestAvailability::test_availability_missing_params PASSED [ 31%]
tests/test_api.py::TestAvailability::test_availability_invalid_dates PASSED [ 36%]
tests/test_api.py::TestAvailability::test_availability_checkout_before_checkin PASSED [ 40%]
tests/test_api.py::TestAvailability::test_availability_returns_rooms PASSED [ 45%]
tests/test_api.py::TestReservationSuccess::test_create_reservation PASSED [ 50%]
tests/test_api.py::TestReservationSuccess::test_lookup_reservation PASSED [ 54%]
tests/test_api.py::TestReservationSuccess::test_lookup_nonexistent_reservation PASSED [ 59%]
tests/test_api.py::TestReservationValidation::test_missing_fields PASSED [ 63%]
tests/test_api.py::TestReservationValidation::test_checkout_before_checkin PASSED [ 68%]
tests/test_api.py::TestReservationValidation::test_invalid_email PASSED  [ 72%]
tests/test_api.py::TestReservationValidation::test_nonexistent_room PASSED [ 77%]
tests/test_api.py::TestOverlappingBookings::test_exact_duplicate_rejected PASSED [ 81%]
tests/test_api.py::TestOverlappingBookings::test_partial_overlap_rejected PASSED [ 86%]
tests/test_api.py::TestOverlappingBookings::test_adjacent_booking_allowed PASSED [ 90%]
tests/test_api.py::TestOverlappingBookings::test_different_room_same_dates_allowed PASSED [ 95%]
tests/test_api.py::TestConcurrentBooking::test_concurrent_overlapping_booking_one_wins PASSED [100%]

============================= 22 passed in 1.87s ==============================
```

---

## 6. Containerization & Production Deployment

### Dockerfile Highlights
- Based on `python:3.12-slim` for minimal attack surface and small image size.
- Runs as non-root user `appuser` (UID 1000) for security isolation.
- Managed by Gunicorn WSGI with 2 worker processes and 4 threads.
- Container-level `HEALTHCHECK` directive verifying `/health`.

### Docker Compose Orchestration
- Sets up an isolated bridge network (`hotel_network`).
- Attaches a named volume (`postgres_data`) ensuring database state survives container restarts.
- Configures healthcheck dependencies (`condition: service_healthy`) ensuring Flask only starts after PostgreSQL passes `pg_isready`.

---

## 7. Cloud Infrastructure (AWS EC2 & Nginx)

- **Compute:** AWS EC2 `t3.micro` instance running Ubuntu 24.04 LTS.
- **Security Groups:** 
  - Inbound: Port 22 (SSH), Port 80 (HTTP), Port 443 (HTTPS).
  - Ports 5000 and 5432 are closed from external access.
- **Reverse Proxy:** Nginx routes incoming public traffic from port 80 to the application container on localhost:5000, passing forwarded headers (`X-Real-IP`, `X-Forwarded-For`).

---

## 8. Backup, Recovery & Rollback Evidence

### 8.1 Database Backup & Restoration
A binary compressed backup was produced using `pg_dump`:
```bash
sudo docker exec -t hotel_db pg_dump -U hotel_user -d hotel_booking -F c -f /tmp/backup.dump
sudo docker cp hotel_db:/tmp/backup.dump /home/ubuntu/db_backup.dump
```

The backup was restored into an independent verification database (`hotel_restore_test`):
```bash
sudo docker exec -i hotel_db pg_restore -U hotel_user -d hotel_restore_test < /home/ubuntu/db_backup.dump
```

Verification query proved that confirmed reservations were successfully recovered without data loss.

### 8.2 Rollback Strategy
Application rollback is managed using version-tagged Docker images (`v1.0.0`, `sha-*`) published to Docker Hub, enabling fast rollback without rebuilding by updating the container image tag in `docker-compose.yml`.

---

## 9. Submission Evidence Screenshots Checklist

Attach your screenshots to the corresponding sections below:

1. **[Screenshot 1]** AWS EC2 Console showing instance `hotel-booking-server` in the *Running* state with Public IP `54.161.2.206`.
2. **[Screenshot 2]** Browser window accessing `http://54.161.2.206/health` and `http://54.161.2.206/api/rooms`.
3. **[Screenshot 3]** GitHub Repository commit history showing clean, iterative commits.
4. **[Screenshot 4]** GitHub Actions tab showing green passing workflow for Lint, Test & Build.
5. **[Screenshot 5]** Terminal output of `docker compose ps` showing both `hotel_app` and `hotel_db` containers healthy.
6. **[Screenshot 6]** Terminal output of Database Restore command querying `hotel_restore_test`.
