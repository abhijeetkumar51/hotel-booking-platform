"""Tests for the Hotel Booking API.

Covers:
  1. Health endpoint
  2. Database readiness
  3. Room listing
  4. Availability checking
  5. Successful reservation
  6. Invalid booking dates
  7. Overlapping / duplicate bookings (exclusion constraint)
  8. Concurrent reservation attempts
"""

import concurrent.futures
import datetime

# ---------------------------------------------------------------------------
# 1. Health endpoint
# ---------------------------------------------------------------------------



class TestHealth:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "healthy"

    def test_health_contains_service_name(self, client):
        data = client.get("/health").get_json()
        assert data["service"] == "hotel-booking-api"


# ---------------------------------------------------------------------------
# 2. Readiness
# ---------------------------------------------------------------------------


class TestReady:
    def test_ready_returns_200_when_db_connected(self, client):
        resp = client.get("/ready")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ready"
        assert data["database"] == "connected"


# ---------------------------------------------------------------------------
# 3. Room listing
# ---------------------------------------------------------------------------


class TestRooms:
    def test_list_rooms_returns_seeded_rooms(self, client):
        resp = client.get("/api/rooms")
        assert resp.status_code == 200
        rooms = resp.get_json()["rooms"]
        assert len(rooms) >= 5  # seeded rooms

    def test_room_has_expected_fields(self, client):
        rooms = client.get("/api/rooms").get_json()["rooms"]
        room = rooms[0]
        for field in ("id", "room_number", "room_type", "price_per_night", "capacity"):
            assert field in room


# ---------------------------------------------------------------------------
# 4. Availability
# ---------------------------------------------------------------------------


class TestAvailability:
    def test_availability_missing_params(self, client):
        resp = client.get("/api/availability")
        assert resp.status_code == 400

    def test_availability_invalid_dates(self, client):
        resp = client.get("/api/availability?check_in=bad&check_out=worse")
        assert resp.status_code == 400

    def test_availability_checkout_before_checkin(self, client):
        resp = client.get("/api/availability?check_in=2030-01-10&check_out=2030-01-05")
        assert resp.status_code == 400

    def test_availability_returns_rooms(self, client, clean_reservations):  # noqa: ARG002
        resp = client.get("/api/availability?check_in=2030-06-01&check_out=2030-06-05")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["available_rooms"]) >= 5


# ---------------------------------------------------------------------------
# 5. Successful reservation
# ---------------------------------------------------------------------------

_FUTURE = (datetime.date.today() + datetime.timedelta(days=60)).isoformat()
_FUTURE_END = (datetime.date.today() + datetime.timedelta(days=63)).isoformat()


class TestReservationSuccess:
    def test_create_reservation(self, client, clean_reservations):  # noqa: ARG002
        resp = client.post(
            "/api/reservations",
            json={
                "room_id": 1,
                "guest_name": "Alice Test",
                "guest_email": "alice@example.com",
                "check_in": _FUTURE,
                "check_out": _FUTURE_END,
            },
        )
        assert resp.status_code == 201
        res = resp.get_json()["reservation"]
        assert res["booking_reference"].startswith("HB-")
        assert res["status"] == "confirmed"

    def test_lookup_reservation(self, client, clean_reservations):  # noqa: ARG002
        # Create then look up
        create = client.post(
            "/api/reservations",
            json={
                "room_id": 2,
                "guest_name": "Bob Test",
                "guest_email": "bob@example.com",
                "check_in": _FUTURE,
                "check_out": _FUTURE_END,
            },
        )
        ref = create.get_json()["reservation"]["booking_reference"]

        resp = client.get(f"/api/reservations/{ref}")
        assert resp.status_code == 200
        assert resp.get_json()["reservation"]["guest_name"] == "Bob Test"

    def test_lookup_nonexistent_reservation(self, client):
        resp = client.get("/api/reservations/HB-DOESNTEX")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6. Invalid booking dates
# ---------------------------------------------------------------------------


class TestReservationValidation:
    def test_missing_fields(self, client):
        resp = client.post("/api/reservations", json={"room_id": 1})
        assert resp.status_code == 400
        assert "errors" in resp.get_json()

    def test_checkout_before_checkin(self, client):
        resp = client.post(
            "/api/reservations",
            json={
                "room_id": 1,
                "guest_name": "Bad Dates",
                "guest_email": "bad@example.com",
                "check_in": "2030-06-10",
                "check_out": "2030-06-05",
            },
        )
        assert resp.status_code == 400

    def test_invalid_email(self, client):
        resp = client.post(
            "/api/reservations",
            json={
                "room_id": 1,
                "guest_name": "No Email",
                "guest_email": "not-an-email",
                "check_in": _FUTURE,
                "check_out": _FUTURE_END,
            },
        )
        assert resp.status_code == 400

    def test_nonexistent_room(self, client):
        resp = client.post(
            "/api/reservations",
            json={
                "room_id": 9999,
                "guest_name": "Ghost",
                "guest_email": "ghost@example.com",
                "check_in": _FUTURE,
                "check_out": _FUTURE_END,
            },
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 7. Overlapping / duplicate bookings
# ---------------------------------------------------------------------------


class TestOverlappingBookings:
    def test_exact_duplicate_rejected(self, client, clean_reservations):  # noqa: ARG002
        payload = {
            "room_id": 1,
            "guest_name": "First Guest",
            "guest_email": "first@example.com",
            "check_in": "2030-07-01",
            "check_out": "2030-07-05",
        }
        r1 = client.post("/api/reservations", json=payload)
        assert r1.status_code == 201

        payload["guest_name"] = "Second Guest"
        payload["guest_email"] = "second@example.com"
        r2 = client.post("/api/reservations", json=payload)
        assert r2.status_code == 409

    def test_partial_overlap_rejected(self, client, clean_reservations):  # noqa: ARG002
        r1 = client.post(
            "/api/reservations",
            json={
                "room_id": 1,
                "guest_name": "Guest A",
                "guest_email": "a@example.com",
                "check_in": "2030-08-01",
                "check_out": "2030-08-10",
            },
        )
        assert r1.status_code == 201

        r2 = client.post(
            "/api/reservations",
            json={
                "room_id": 1,
                "guest_name": "Guest B",
                "guest_email": "b@example.com",
                "check_in": "2030-08-05",
                "check_out": "2030-08-12",
            },
        )
        assert r2.status_code == 409

    def test_adjacent_booking_allowed(self, client, clean_reservations):  # noqa: ARG002
        """Check-out day = next check-in day should be allowed."""
        r1 = client.post(
            "/api/reservations",
            json={
                "room_id": 1,
                "guest_name": "Guest C",
                "guest_email": "c@example.com",
                "check_in": "2030-09-01",
                "check_out": "2030-09-05",
            },
        )
        assert r1.status_code == 201

        r2 = client.post(
            "/api/reservations",
            json={
                "room_id": 1,
                "guest_name": "Guest D",
                "guest_email": "d@example.com",
                "check_in": "2030-09-05",
                "check_out": "2030-09-10",
            },
        )
        assert r2.status_code == 201

    def test_different_room_same_dates_allowed(self, client, clean_reservations):  # noqa: ARG002
        payload = {
            "guest_name": "Multi Room",
            "guest_email": "multi@example.com",
            "check_in": "2030-10-01",
            "check_out": "2030-10-05",
        }
        r1 = client.post("/api/reservations", json={**payload, "room_id": 1})
        assert r1.status_code == 201

        r2 = client.post("/api/reservations", json={**payload, "room_id": 2})
        assert r2.status_code == 201


# ---------------------------------------------------------------------------
# 8. Concurrent reservation attempts
# ---------------------------------------------------------------------------


class TestConcurrentBooking:
    def test_concurrent_overlapping_booking_one_wins(
        self, client, clean_reservations  # noqa: ARG002
    ):
        """Fire two identical booking requests concurrently.

        Exactly one should succeed (201) and the other should fail (409).
        """
        from app.config import TestConfig
        from app.main import create_app

        app = create_app(TestConfig())
        app.config["TESTING"] = True

        results = []

        def _book():
            with app.test_client() as c:
                return c.post(
                    "/api/reservations",
                    json={
                        "room_id": 3,
                        "guest_name": "Racer",
                        "guest_email": "racer@example.com",
                        "check_in": "2030-11-01",
                        "check_out": "2030-11-05",
                    },
                )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(_book) for _ in range(2)]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result().status_code)

        results.sort()
        assert results == [201, 409], (
            f"Expected exactly one 201 and one 409, got {results}"
        )
