"""API route handlers for the hotel booking platform."""

import datetime
import logging
import re
import uuid

import psycopg2
import psycopg2.extras
from flask import Blueprint, jsonify, request

from app.database import check_connection, get_connection

logger = logging.getLogger(__name__)

api = Blueprint("api", __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_booking_ref() -> str:
    """Generate a short, unique booking reference like 'HB-A1B2C3D4'."""
    return "HB-" + uuid.uuid4().hex[:8].upper()


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_reservation_payload(data: dict) -> list[str]:
    """Return a list of validation error messages (empty = valid)."""
    errors: list[str] = []

    if not data:
        return ["Request body must be JSON."]

    for field in ("room_id", "guest_name", "guest_email", "check_in", "check_out"):
        if field not in data or data[field] is None:
            errors.append(f"Missing required field: {field}")

    if errors:
        return errors

    # Types
    if not isinstance(data["room_id"], int):
        errors.append("room_id must be an integer.")

    if not isinstance(data["guest_name"], str) or len(data["guest_name"].strip()) == 0:
        errors.append("guest_name must be a non-empty string.")

    if not isinstance(data["guest_email"], str) or not _EMAIL_RE.match(
        data.get("guest_email", "")
    ):
        errors.append("guest_email must be a valid email address.")

    # Dates
    for date_field in ("check_in", "check_out"):
        try:
            datetime.date.fromisoformat(data[date_field])
        except (ValueError, TypeError):
            errors.append(f"{date_field} must be a valid ISO date (YYYY-MM-DD).")

    if not errors:
        ci = datetime.date.fromisoformat(data["check_in"])
        co = datetime.date.fromisoformat(data["check_out"])
        if co <= ci:
            errors.append("check_out must be after check_in.")
        if ci < datetime.date.today():
            errors.append("check_in cannot be in the past.")

    return errors


# ---------------------------------------------------------------------------
# Health / Readiness
# ---------------------------------------------------------------------------


@api.route("/health")
def health():
    """Liveness check – always returns 200 if the app process is up."""
    return jsonify({"status": "healthy", "service": "hotel-booking-api"}), 200


@api.route("/ready")
def ready():
    """Readiness check – returns 200 only when the database is reachable."""
    if check_connection():
        return jsonify({"status": "ready", "database": "connected"}), 200
    return jsonify({"status": "not ready", "database": "disconnected"}), 503


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------


@api.route("/api/rooms")
def list_rooms():
    """Return all rooms."""
    with get_connection() as conn, conn.cursor(
        cursor_factory=psycopg2.extras.RealDictCursor
    ) as cur:
        cur.execute(
            "SELECT id, room_number, room_type, "
            "price_per_night::text AS price_per_night, capacity, description "
            "FROM rooms ORDER BY room_number"
        )
        rooms = cur.fetchall()
    return jsonify({"rooms": [dict(r) for r in rooms]}), 200


@api.route("/api/availability")
def check_availability():
    """Return rooms available for a given date range.

    Query params: check_in, check_out (ISO dates).
    """
    check_in = request.args.get("check_in")
    check_out = request.args.get("check_out")

    if not check_in or not check_out:
        return (
            jsonify({"error": "check_in and check_out query parameters are required."}),
            400,
        )

    try:
        ci = datetime.date.fromisoformat(check_in)
        co = datetime.date.fromisoformat(check_out)
    except ValueError:
        return jsonify({"error": "Dates must be valid ISO format (YYYY-MM-DD)."}), 400

    if co <= ci:
        return jsonify({"error": "check_out must be after check_in."}), 400

    with get_connection() as conn, conn.cursor(
        cursor_factory=psycopg2.extras.RealDictCursor
    ) as cur:
        cur.execute(
            """
            SELECT id, room_number, room_type,
                   price_per_night::text AS price_per_night,
                   capacity, description
            FROM rooms
            WHERE id NOT IN (
                SELECT room_id FROM reservations
                WHERE status = 'confirmed'
                  AND daterange(check_in, check_out, '[)') &&
                      daterange(%s, %s, '[)')
            )
            ORDER BY room_number
            """,
            (ci, co),
        )
        rooms = cur.fetchall()

    return (
        jsonify(
            {
                "check_in": check_in,
                "check_out": check_out,
                "available_rooms": [dict(r) for r in rooms],
            }
        ),
        200,
    )


# ---------------------------------------------------------------------------
# Reservations
# ---------------------------------------------------------------------------


@api.route("/api/reservations", methods=["POST"])
def create_reservation():
    """Create a new reservation."""
    data = request.get_json(silent=True)
    errors = _validate_reservation_payload(data or {})
    if errors:
        return jsonify({"errors": errors}), 400

    room_id = data["room_id"]
    guest_name = data["guest_name"].strip()
    guest_email = data["guest_email"].strip()
    check_in = datetime.date.fromisoformat(data["check_in"])
    check_out = datetime.date.fromisoformat(data["check_out"])
    booking_ref = _generate_booking_ref()

    # Verify room exists
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM rooms WHERE id = %s", (room_id,))
        if cur.fetchone() is None:
            return jsonify({"error": f"Room with id {room_id} not found."}), 404

    # Attempt insertion – the exclusion constraint will reject overlaps
    try:
        with get_connection() as conn, conn.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor
        ) as cur:
            cur.execute(
                """
                INSERT INTO reservations
                    (booking_reference, room_id, guest_name, guest_email,
                     check_in, check_out, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'confirmed')
                RETURNING id, booking_reference, room_id, guest_name,
                          guest_email,
                          check_in::text, check_out::text,
                          status, created_at::text
                """,
                (booking_ref, room_id, guest_name, guest_email, check_in, check_out),
            )
            reservation = dict(cur.fetchone())
    except psycopg2.errors.ExclusionViolation:
        logger.warning(
            "Overlapping reservation rejected for room %s (%s – %s)",
            room_id,
            check_in,
            check_out,
        )
        return (
            jsonify(
                {
                    "error": "Room is already booked for the requested dates.",
                    "room_id": room_id,
                    "check_in": str(check_in),
                    "check_out": str(check_out),
                }
            ),
            409,
        )

    logger.info("Reservation created: %s", booking_ref)
    return jsonify({"reservation": reservation}), 201


@api.route("/api/reservations/<booking_reference>")
def get_reservation(booking_reference):
    """Look up a reservation by its booking reference."""
    with get_connection() as conn, conn.cursor(
        cursor_factory=psycopg2.extras.RealDictCursor
    ) as cur:
        cur.execute(
            """
            SELECT r.id, r.booking_reference, r.room_id,
                   rm.room_number, rm.room_type,
                   r.guest_name, r.guest_email,
                   r.check_in::text, r.check_out::text,
                   r.status, r.created_at::text
            FROM reservations r
            JOIN rooms rm ON rm.id = r.room_id
            WHERE r.booking_reference = %s
            """,
            (booking_reference,),
        )
        reservation = cur.fetchone()

    if reservation is None:
        return jsonify({"error": "Reservation not found."}), 404

    return jsonify({"reservation": dict(reservation)}), 200
