"""JSON API: health, person management, enrollment, sessions, recognition.

All endpoints except /health require a logged-in session cookie; mutating
endpoints additionally require the operator role and (outside testing) a
CSRF token in the X-CSRFToken header. Errors use the shared envelope from
app.errors via abort(status, description).
"""

from datetime import timedelta

from flask import abort, current_app, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.blueprints.api import api_bp
from app.extensions import db
from app.models import AttendanceSession, Person, utcnow
from app.models.audit import RecognitionLog
from app.services import attendance as attendance_service
from app.services import enrollment as enrollment_service
from app.services import face_engine, matcher
from app.utils.audit import record_audit
from app.utils.decorators import role_required

API_VERSION = "1.0"


@api_bp.route("/health")
def health():
    """Liveness/readiness probe: process up + database answering.

    Deliberately unauthenticated — it exposes no data and load balancers
    cannot log in.
    """
    try:
        db.session.execute(text("SELECT 1"))
        database_status = "ok"
        status_code = 200
    except Exception:  # pragma: no cover - only on catastrophic DB failure
        current_app.logger.exception("Health check: database unreachable")
        database_status = "error"
        status_code = 503

    return (
        jsonify(
            {
                "status": "ok" if database_status == "ok" else "degraded",
                "database": database_status,
                "api_version": API_VERSION,
            }
        ),
        status_code,
    )


# --------------------------------------------------------------------------
# helpers


def _json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="Request body must be a JSON object.")
    return data


def _require_string(data, field, max_length, required=True):
    value = data.get(field)
    if value is None:
        if required:
            abort(400, description=f"Field {field!r} is required.")
        return None
    if not isinstance(value, str) or not value.strip():
        abort(400, description=f"Field {field!r} must be a non-empty string.")
    value = value.strip()
    if len(value) > max_length:
        abort(400, description=f"Field {field!r} exceeds {max_length} characters.")
    return value


def _person_json(person):
    return {
        "id": person.id,
        "code": person.code,
        "full_name": person.full_name,
        "group_name": person.group_name,
        "department": person.department,
        "year": person.year,
        "email": person.email,
        "is_active": person.is_active,
        "is_enrolled": person.is_enrolled,
        "enrolled_at": person.enrolled_at.isoformat() if person.enrolled_at else None,
    }


def _session_json(session):
    return {
        "id": session.id,
        "name": session.name,
        "session_date": session.session_date.isoformat(),
        "start_time": session.start_time.isoformat(),
        "end_time": session.end_time.isoformat() if session.end_time else None,
        "late_after": session.late_after.isoformat() if session.late_after else None,
        "status": session.status,
        "department": session.department,
        "year": session.year,
    }


# --------------------------------------------------------------------------
# persons


@api_bp.route("/persons")
@login_required
def list_persons():
    persons = (
        db.session.execute(db.select(Person).order_by(Person.code))
        .scalars()
        .all()
    )
    return jsonify({"persons": [_person_json(p) for p in persons]})


@api_bp.route("/persons", methods=["POST"])
@role_required("operator")
def create_person():
    data = _json_body()
    code = _require_string(data, "code", 32)
    full_name = _require_string(data, "full_name", 120)
    group_name = _require_string(data, "group_name", 80, required=False)
    department = _require_string(data, "department", 80, required=False)
    email = _require_string(data, "email", 120, required=False)

    year = data.get("year")
    if year is not None and year != "":
        try:
            year = int(year)
        except (ValueError, TypeError):
            abort(400, description="Field 'year' must be an integer.")
    else:
        year = None

    if db.session.execute(
        db.select(Person).filter_by(code=code)
    ).scalar_one_or_none():
        abort(409, description=f"A person with code {code!r} already exists.")

    person = Person(
        code=code,
        full_name=full_name,
        group_name=group_name,
        department=department,
        year=year,
        email=email,
    )
    db.session.add(person)
    db.session.flush()  # assign person.id for the audit row
    record_audit(
        "person.create",
        entity="person",
        entity_id=person.id,
        details={"code": code, "full_name": full_name},
    )
    db.session.commit()
    return jsonify({"person": _person_json(person)}), 201


@api_bp.route("/persons/<int:person_id>", methods=["PUT"])
@role_required("operator")
def update_person(person_id):
    person = db.session.get(Person, person_id)
    if person is None:
        abort(404)

    data = _json_body()
    code = _require_string(data, "code", 32)
    full_name = _require_string(data, "full_name", 120)
    group_name = _require_string(data, "group_name", 80, required=False)
    department = _require_string(data, "department", 80, required=False)
    email = _require_string(data, "email", 120, required=False)
    is_active = data.get("is_active", True)
    if not isinstance(is_active, bool):
        abort(400, description="Field 'is_active' must be a boolean.")

    year = data.get("year")
    if year is not None and year != "":
        try:
            year = int(year)
        except (ValueError, TypeError):
            abort(400, description="Field 'year' must be an integer.")
    else:
        year = None

    existing = db.session.execute(
        db.select(Person).filter_by(code=code)
    ).scalar_one_or_none()
    if existing and existing.id != person.id:
        abort(409, description=f"A person with code {code!r} already exists.")

    person.code = code
    person.full_name = full_name
    person.group_name = group_name
    person.department = department
    person.year = year
    person.email = email
    person.is_active = is_active

    record_audit(
        "person.update",
        entity="person",
        entity_id=person.id,
        details={"code": code, "full_name": full_name},
    )
    matcher.invalidate_gallery()
    db.session.commit()
    return jsonify({"person": _person_json(person)})


@api_bp.route("/persons/<int:person_id>", methods=["DELETE"])
@role_required("operator")
def delete_person(person_id):
    person = db.session.get(Person, person_id)
    if person is None:
        abort(404)

    db.session.delete(person)
    record_audit(
        "person.delete",
        entity="person",
        entity_id=person_id,
        details={"code": person.code, "full_name": person.full_name},
    )
    matcher.invalidate_gallery()
    db.session.commit()
    return jsonify({"status": "success", "message": f"Person {person_id} deleted."})


@api_bp.route("/persons/<int:person_id>/enroll", methods=["POST"])
@role_required("operator")
def enroll_person(person_id):
    person = db.session.get(Person, person_id)
    if person is None:
        abort(404)
    if not person.is_active:
        abort(409, description="Cannot enroll an inactive person.")

    data = _json_body()
    images = data.get("images")
    if not isinstance(images, list) or not all(
        isinstance(item, str) for item in images
    ):
        abort(400, description="Field 'images' must be a list of base64 strings.")

    try:
        sample_count = enrollment_service.enroll_person(person, images)
    except enrollment_service.EnrollmentError as exc:
        db.session.rollback()
        return (
            jsonify(
                {
                    "error": {
                        "code": "enrollment_rejected",
                        "message": str(exc),
                        "problems": exc.problems,
                    }
                }
            ),
            422,
        )

    record_audit(
        "person.enroll",
        entity="person",
        entity_id=person.id,
        details={"samples": sample_count},
    )
    db.session.commit()
    return jsonify({"person": _person_json(person), "samples": sample_count})


# --------------------------------------------------------------------------
# sessions


@api_bp.route("/sessions")
@login_required
def list_sessions():
    query = db.select(AttendanceSession).order_by(
        AttendanceSession.start_time.desc()
    )
    status = request.args.get("status")
    if status:
        query = query.filter_by(status=status)
    sessions = db.session.execute(query.limit(50)).scalars().all()
    return jsonify({"sessions": [_session_json(s) for s in sessions]})


@api_bp.route("/sessions", methods=["POST"])
@role_required("operator")
def create_session():
    data = _json_body()
    name = _require_string(data, "name", 120)

    now = utcnow()
    late_after = None
    late_after_minutes = data.get("late_after_minutes")
    if late_after_minutes is not None:
        if not isinstance(late_after_minutes, int) or late_after_minutes < 0:
            abort(
                400,
                description="Field 'late_after_minutes' must be a non-negative integer.",
            )
        late_after = now + timedelta(minutes=late_after_minutes)

    # Optional branch/year context
    department = data.get("department") or None
    year_raw = data.get("year")
    year = None
    if year_raw is not None and year_raw != "":
        try:
            year = int(year_raw)
        except (ValueError, TypeError):
            abort(400, description="Field 'year' must be an integer between 1 and 4.")

    session = AttendanceSession(
        name=name,
        session_date=now.date(),
        start_time=now,
        late_after=late_after,
        department=department,
        year=year,
        created_by_id=current_user.id,
    )
    db.session.add(session)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        dept_label = f" for {department}" if department else ""
        abort(
            409,
            description=f"A session named {name!r}{dept_label} already exists for today.",
        )
    record_audit(
        "session.create", entity="session", entity_id=session.id,
        details={"name": name, "department": department, "year": year},
    )
    db.session.commit()
    return jsonify({"session": _session_json(session)}), 201


@api_bp.route("/sessions/<int:session_id>/close", methods=["POST"])
@role_required("operator")
def close_session(session_id):
    session = db.session.get(AttendanceSession, session_id)
    if session is None:
        abort(404)
    if not session.is_open:
        abort(409, description="Session is already closed.")

    session.status = "closed"
    session.end_time = utcnow()
    record_audit("session.close", entity="session", entity_id=session.id)
    db.session.commit()
    return jsonify({"session": _session_json(session)})


@api_bp.route("/sessions/<int:session_id>", methods=["DELETE"])
@role_required("operator")
def delete_session(session_id):
    session = db.session.get(AttendanceSession, session_id)
    if session is None:
        abort(404)
    if session.is_open:
        abort(
            409,
            description="Cannot delete an open session. Close it first.",
        )

    session_name = session.name
    record_audit(
        "session.delete", entity="session", entity_id=session.id,
        details={"name": session_name},
    )
    # Manually delete child rows — SQLite FKs lack ON DELETE CASCADE
    # and lazy="dynamic" prevents ORM-level cascade from loading them.
    from app.models.attendance import AttendanceRecord
    from app.models.audit import RecognitionLog

    db.session.execute(
        db.delete(RecognitionLog).where(RecognitionLog.session_id == session_id)
    )
    db.session.execute(
        db.delete(AttendanceRecord).where(AttendanceRecord.session_id == session_id)
    )
    db.session.delete(session)
    db.session.commit()
    return jsonify({"message": f"Session '{session_name}' deleted."})


@api_bp.route("/sessions/<int:session_id>/restart", methods=["POST"])
@role_required("operator")
def restart_session(session_id):
    """Reopen or replicate a closed session.

    Same calendar date → reopen the existing session.
    Different date    → create a new session for today with the same
                        name, branch, year, and late-cutoff offset.
    """
    original = db.session.get(AttendanceSession, session_id)
    if original is None:
        abort(404)
    if original.is_open:
        abort(409, description="Session is already open.")

    today = utcnow().date()

    if original.session_date == today:
        # ── Same day: simply reopen ──────────────────────────────────────
        original.status = "open"
        original.end_time = None
        record_audit("session.reopen", entity="session", entity_id=original.id)
        db.session.commit()
        return jsonify({"session": _session_json(original), "action": "reopened"})

    # ── Different day: spawn a new session for today ──────────────────────
    now = utcnow()
    new_late_after = None
    if original.late_after and original.start_time:
        offset = original.late_after - original.start_time
        new_late_after = now + offset

    new_session = AttendanceSession(
        name=original.name,
        session_date=today,
        start_time=now,
        late_after=new_late_after,
        department=original.department,
        year=original.year,
        created_by_id=current_user.id,
    )
    db.session.add(new_session)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        abort(
            409,
            description=(
                f"A session named {original.name!r}"
                + (f" for {original.department}" if original.department else "")
                + " already exists for today."
            ),
        )
    record_audit(
        "session.create", entity="session", entity_id=new_session.id,
        details={"name": new_session.name, "restarted_from": session_id},
    )
    db.session.commit()
    return jsonify({"session": _session_json(new_session), "action": "created"}), 201


def _target_session(data):
    """Resolve the open session a recognition applies to.

    An explicit session_id must exist and be open; otherwise fall back to
    the single most recently started open session.
    """
    session_id = data.get("session_id")
    if session_id is not None:
        session = db.session.get(AttendanceSession, session_id)
        if session is None:
            abort(404, description="Session not found.")
        if not session.is_open:
            abort(409, description="Session is closed.")
        return session

    session = db.session.execute(
        db.select(AttendanceSession)
        .filter_by(status="open")
        .order_by(AttendanceSession.start_time.desc())
        .limit(1)
    ).scalar_one_or_none()
    if session is None:
        abort(409, description="No open attendance session.")
    return session


@api_bp.route("/recognize", methods=["POST"])
@role_required("operator")
def recognize():
    """Recognise every face in a frame and mark attendance on accept.

    Processes all detected faces in the image. Every match attempt is written
    to recognition_logs. Backwards-compatible fields are populated based on the
    largest face (observations[0]).
    """
    data = _json_body()
    image_data = data.get("image")
    if not isinstance(image_data, str) or not image_data:
        abort(400, description="Field 'image' must be a base64 string.")

    session = _target_session(data)

    try:
        image = face_engine.decode_image(image_data)
    except face_engine.FaceEngineError as exc:
        abort(400, description=str(exc))

    observations = face_engine.get_engine().analyze(image)
    if not observations:
        return jsonify({
            "outcome": "no_face",
            "session_id": session.id,
            "results": [],
            "faces_detected": 0
        })

    results = []
    for obs in observations:
        res = matcher.match_embedding(obs.embedding)

        db.session.add(
            RecognitionLog(
                session_id=session.id,
                person_id=res.person_id,
                similarity=res.similarity,
                outcome=res.outcome,
            )
        )

        match_data = {
            "outcome": res.outcome,
            "similarity": res.similarity,
            "bbox": [int(x) for x in obs.bbox],
        }

        if res.outcome == "accepted":
            person = db.session.get(Person, res.person_id)
            mark = attendance_service.mark_attendance(
                session, person, confidence=res.similarity
            )
            match_data["person"] = _person_json(person)
            match_data["attendance"] = {
                "created": mark.created,
                "status": mark.record.status,
                "marked_at": mark.record.marked_at.isoformat(),
            }
        results.append(match_data)

    db.session.commit()

    primary = results[0]
    response = {
        "outcome": primary["outcome"],
        "similarity": primary["similarity"],
        "session_id": session.id,
        "faces_detected": len(observations),
        "results": results,
    }
    if "person" in primary:
        response["person"] = primary["person"]
    if "attendance" in primary:
        response["attendance"] = primary["attendance"]

    return jsonify(response)
