from datetime import date, datetime, timedelta

from flask import Response, abort, flash, redirect, render_template, request, url_for, make_response, jsonify
from flask_login import current_user, login_required

from app.blueprints.auth.forms import CreateUserForm, EditUserForm
from app.blueprints.dashboard import dashboard_bp
from app.extensions import db
from app.models import (
    AdminUser,
    AttendanceRecord,
    AttendanceSession,
    Person,
    Setting,
)
from app.utils.decorators import role_required
from app.utils.audit import record_audit


@dashboard_bp.route("/")
@login_required
def index():
    today = date.today()

    stats = {
        "persons_total": db.session.scalar(
            db.select(db.func.count())
            .select_from(Person)
            .where(Person.is_active.is_(True))
        ),
        "persons_enrolled": db.session.scalar(
            db.select(db.func.count())
            .select_from(Person)
            .where(Person.is_active.is_(True), Person.enrolled_at.is_not(None))
        ),
        "sessions_today": db.session.scalar(
            db.select(db.func.count())
            .select_from(AttendanceSession)
            .where(AttendanceSession.session_date == today)
        ),
        "attendance_today": db.session.scalar(
            db.select(db.func.count())
            .select_from(AttendanceRecord)
            .join(AttendanceSession)
            .where(AttendanceSession.session_date == today)
        ),
    }

    return render_template(
        "dashboard/index.html", stats=stats
    )


@dashboard_bp.route("/persons")
@login_required
def persons():
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip()
    department = request.args.get("department", "").strip()
    year = request.args.get("year", "").strip()

    query = db.select(Person)
    if q:
        query = query.where(Person.code.ilike(f"%{q}%") | Person.full_name.ilike(f"%{q}%"))
    if department:
        query = query.where(Person.department == department)
    if year:
        try:
            year_int = int(year)
            query = query.where(Person.year == year_int)
        except ValueError:
            pass

    query = query.order_by(Person.code)
    pagination = db.paginate(query, page=page, per_page=10, error_out=False)

    departments_raw = db.session.execute(
        db.select(Person.department)
        .where(Person.department.is_not(None))
        .where(Person.department != "")
        .distinct()
    ).scalars().all()
    departments = sorted([d for d in departments_raw if d])

    return render_template(
        "dashboard/persons.html",
        pagination=pagination,
        departments=departments,
        q=q,
        selected_department=department,
        selected_year=year,
    )


@dashboard_bp.route("/persons/<int:person_id>/edit")
@role_required("operator")
def edit_person(person_id):
    person = db.session.get(Person, person_id)
    if person is None:
        abort(404)
    return render_template("dashboard/edit_person.html", person=person)


@dashboard_bp.route("/persons/<int:person_id>/thumbnail.jpg")
@login_required
def person_thumbnail(person_id):
    person = db.session.get(Person, person_id)
    if person is None or not person.thumbnail:
        abort(404)
    return Response(person.thumbnail, mimetype="image/jpeg")


@dashboard_bp.route("/persons/<int:person_id>/enroll")
@role_required("operator")
def enroll(person_id):
    person = db.session.get(Person, person_id)
    if person is None:
        abort(404)
    return render_template(
        "dashboard/enroll.html",
        person=person,
        min_images=Setting.get_int("enroll_min_images", 5),
        max_images=Setting.get_int("enroll_max_images", 10),
    )


@dashboard_bp.route("/sessions")
@login_required
def sessions():
    # --- Filters ---
    q_name       = request.args.get("name", "").strip()
    q_dept       = request.args.get("department", "").strip()
    q_year       = request.args.get("year", "").strip()
    q_status     = request.args.get("status", "").strip()
    q_date       = request.args.get("date", "").strip()
    page         = request.args.get("page", 1, type=int)

    query = db.select(AttendanceSession)
    if q_name:
        query = query.where(AttendanceSession.name.ilike(f"%{q_name}%"))
    if q_dept:
        query = query.where(AttendanceSession.department == q_dept)
    if q_year:
        try:
            query = query.where(AttendanceSession.year == int(q_year))
        except ValueError:
            pass
    if q_status:
        query = query.where(AttendanceSession.status == q_status)
    if q_date:
        try:
            parsed_date = date.fromisoformat(q_date)
            query = query.where(AttendanceSession.session_date == parsed_date)
        except ValueError:
            pass

    query = query.order_by(AttendanceSession.start_time.desc())
    pagination = db.paginate(query, page=page, per_page=20, error_out=False)
    sess_list = pagination.items

    counts = dict(
        db.session.execute(
            db.select(
                AttendanceRecord.session_id,
                db.func.count(AttendanceRecord.id),
            )
            .where(AttendanceRecord.session_id.in_([s.id for s in sess_list] or [0]))
            .group_by(AttendanceRecord.session_id)
        ).all()
    )

    # Populate filter dropdowns from existing data
    dept_list = sorted(filter(None, db.session.scalars(
        db.select(AttendanceSession.department).distinct()
    ).all()))

    return render_template(
        "dashboard/sessions.html",
        sessions=sess_list,
        counts=counts,
        pagination=pagination,
        dept_list=dept_list,
        q_name=q_name, q_dept=q_dept, q_year=q_year,
        q_status=q_status, q_date=q_date,
    )


@dashboard_bp.route("/sessions/day-view")
@login_required
def sessions_day_view():
    q_dept      = request.args.get("department", "").strip()
    q_year      = request.args.get("year", "").strip()
    q_name      = request.args.get("name", "").strip()
    from_date_s = request.args.get("from_date", "").strip()
    to_date_s   = request.args.get("to_date", "").strip()

    query = db.select(AttendanceSession).order_by(
        AttendanceSession.session_date.desc(),
        AttendanceSession.start_time.asc(),
    )
    if q_dept:
        query = query.where(AttendanceSession.department == q_dept)
    if q_year:
        try:
            query = query.where(AttendanceSession.year == int(q_year))
        except ValueError:
            pass
    if q_name:
        query = query.where(AttendanceSession.name.ilike(f"%{q_name}%"))
    if from_date_s:
        try:
            query = query.where(AttendanceSession.session_date >= date.fromisoformat(from_date_s))
        except ValueError:
            pass
    if to_date_s:
        try:
            query = query.where(AttendanceSession.session_date <= date.fromisoformat(to_date_s))
        except ValueError:
            pass

    all_sessions = db.session.scalars(query).all()

    # Count records per session
    if all_sessions:
        rec_counts = dict(db.session.execute(
            db.select(AttendanceRecord.session_id, db.func.count(AttendanceRecord.id))
            .where(AttendanceRecord.session_id.in_([s.id for s in all_sessions]))
            .group_by(AttendanceRecord.session_id)
        ).all())
    else:
        rec_counts = {}

    # Total enrolled for rate calculation
    total_enrolled = db.session.scalar(
        db.select(db.func.count()).select_from(Person)
        .where(Person.is_active.is_(True), Person.enrolled_at.is_not(None))
    ) or 0

    # Group by date
    from collections import OrderedDict
    days: dict = OrderedDict()
    for s in all_sessions:
        d = s.session_date
        if d not in days:
            days[d] = {"sessions": [], "total_present": 0}
        present = rec_counts.get(s.id, 0)
        days[d]["sessions"].append({
            "session": s,
            "present": present,
            "rate": round(present / total_enrolled * 100, 1) if total_enrolled else 0,
        })
        days[d]["total_present"] += present

    dept_list = sorted(filter(None, db.session.scalars(
        db.select(AttendanceSession.department).distinct()
    ).all()))

    return render_template(
        "dashboard/sessions_day_view.html",
        days=days,
        dept_list=dept_list,
        q_dept=q_dept, q_year=q_year, q_name=q_name,
        from_date=from_date_s, to_date=to_date_s,
    )


@dashboard_bp.route("/sessions/branch-view")
@login_required
def sessions_branch_view():
    q_dept      = request.args.get("department", "").strip()
    q_year      = request.args.get("year", "").strip()
    from_date_s = request.args.get("from_date", "").strip()
    to_date_s   = request.args.get("to_date", "").strip()

    query = db.select(AttendanceSession).order_by(
        AttendanceSession.department.asc(),
        AttendanceSession.name.asc(),
        AttendanceSession.session_date.asc(),
    )
    if q_dept:
        query = query.where(AttendanceSession.department == q_dept)
    if q_year:
        try:
            query = query.where(AttendanceSession.year == int(q_year))
        except ValueError:
            pass
    if from_date_s:
        try:
            query = query.where(AttendanceSession.session_date >= date.fromisoformat(from_date_s))
        except ValueError:
            pass
    if to_date_s:
        try:
            query = query.where(AttendanceSession.session_date <= date.fromisoformat(to_date_s))
        except ValueError:
            pass

    all_sessions = db.session.scalars(query).all()

    if all_sessions:
        rec_counts = dict(db.session.execute(
            db.select(AttendanceRecord.session_id, db.func.count(AttendanceRecord.id))
            .where(AttendanceRecord.session_id.in_([s.id for s in all_sessions]))
            .group_by(AttendanceRecord.session_id)
        ).all())
    else:
        rec_counts = {}

    total_enrolled = db.session.scalar(
        db.select(db.func.count()).select_from(Person)
        .where(Person.is_active.is_(True), Person.enrolled_at.is_not(None))
    ) or 0

    # Group by (department, subject_name)
    from collections import OrderedDict
    branches: dict = OrderedDict()
    for s in all_sessions:
        dept = s.department or "Unassigned"
        if dept not in branches:
            branches[dept] = {}
        key = s.name
        if key not in branches[dept]:
            branches[dept][key] = {"year": s.year, "rows": [], "total_present": 0, "total_sessions": 0}
        present = rec_counts.get(s.id, 0)
        branches[dept][key]["rows"].append({
            "session": s,
            "present": present,
            "rate": round(present / total_enrolled * 100, 1) if total_enrolled else 0,
        })
        branches[dept][key]["total_present"] += present
        branches[dept][key]["total_sessions"] += 1

    # Compute avg rate per class
    for dept_data in branches.values():
        for cls_data in dept_data.values():
            n = cls_data["total_sessions"]
            rates = [r["rate"] for r in cls_data["rows"]]
            cls_data["avg_rate"] = round(sum(rates) / n, 1) if n else 0

    dept_list = sorted(filter(None, db.session.scalars(
        db.select(AttendanceSession.department).distinct()
    ).all()))

    return render_template(
        "dashboard/sessions_branch_view.html",
        branches=branches,
        dept_list=dept_list,
        q_dept=q_dept, q_year=q_year,
        from_date=from_date_s, to_date=to_date_s,
        total_enrolled=total_enrolled,
    )




@dashboard_bp.route("/kiosk")
@role_required("operator")
def kiosk():
    open_session = db.session.execute(
        db.select(AttendanceSession)
        .filter_by(status="open")
        .order_by(AttendanceSession.start_time.desc())
        .limit(1)
    ).scalar_one_or_none()

    recent_records = []
    total_marked = 0
    if open_session:
        from app.models import AttendanceRecord
        recent_records = db.session.execute(
            db.select(AttendanceRecord)
            .where(AttendanceRecord.session_id == open_session.id)
            .order_by(AttendanceRecord.marked_at.desc())
            .limit(10)
        ).scalars().all()
        total_marked = db.session.scalar(
            db.select(db.func.count(AttendanceRecord.id))
            .where(AttendanceRecord.session_id == open_session.id)
        ) or 0

    return render_template(
        "dashboard/kiosk.html",
        open_session=open_session,
        recent_records=recent_records,
        total_marked=total_marked
    )


@dashboard_bp.route("/users", methods=["GET", "POST"])
@role_required("admin")
def users():
    form = CreateUserForm()
    if form.validate_on_submit():
        username = form.username.data.strip().lower()
        user = AdminUser(username=username, role=form.role.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()
        record_audit(
            "user.create",
            entity="admin_user",
            entity_id=user.id,
            details={"username": username, "role": user.role},
        )
        db.session.commit()
        flash(f"User '{username}' created successfully.", "success")
        return redirect(url_for("dashboard.users"))

    users = (
        db.session.execute(db.select(AdminUser).order_by(AdminUser.id))
        .scalars()
        .all()
    )
    return render_template("dashboard/users.html", users=users, form=form)


@dashboard_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def edit_user(user_id):
    user = db.session.get(AdminUser, user_id)
    if user is None:
        abort(404)

    form = EditUserForm(obj=user)
    if form.validate_on_submit():
        if user.id == current_user.id:
            if not form.is_active.data:
                flash("You cannot deactivate your own account.", "danger")
                return render_template("dashboard/edit_user.html", user=user, form=form)
            if form.role.data != "admin":
                flash("You cannot downgrade your own role.", "danger")
                return render_template("dashboard/edit_user.html", user=user, form=form)

        old_role = user.role
        old_active = user.is_active

        user.role = form.role.data
        user.is_active = form.is_active.data
        password_changed = False
        if form.password.data:
            user.set_password(form.password.data)
            password_changed = True

        record_audit(
            "user.edit",
            entity="admin_user",
            entity_id=user.id,
            details={
                "username": user.username,
                "role_changed": old_role != user.role,
                "role": user.role,
                "active_changed": old_active != user.is_active,
                "is_active": user.is_active,
                "password_changed": password_changed,
            },
        )
        db.session.commit()
        flash(f"User '{user.username}' updated successfully.", "success")
        return redirect(url_for("dashboard.users"))

    return render_template("dashboard/edit_user.html", user=user, form=form)


@dashboard_bp.route("/settings", methods=["GET", "POST"])
@role_required("operator")
def settings():
    if request.method == "POST":
        accept = request.form.get("similarity_threshold_accept", "").strip()
        review = request.form.get("similarity_threshold_review", "").strip()
        min_img = request.form.get("enroll_min_images", "").strip()
        max_img = request.form.get("enroll_max_images", "").strip()
        cooldown = request.form.get("attendance_cooldown_minutes", "").strip()
        store_orig = request.form.get("store_original_images", "false").strip()

        try:
            accept_val = float(accept)
            review_val = float(review)
            if not 0.0 <= accept_val <= 1.0 or not 0.0 <= review_val <= 1.0:
                raise ValueError("Similarity thresholds must be between 0.0 and 1.0.")
            if review_val > accept_val:
                raise ValueError("Review threshold cannot be higher than Accept threshold.")
            
            min_img_val = int(min_img)
            max_img_val = int(max_img)
            if min_img_val < 1 or max_img_val < min_img_val:
                raise ValueError("Enrollment limits must be positive integers, with maximum >= minimum.")
                
            cooldown_val = int(cooldown)
            if cooldown_val < 0:
                raise ValueError("Cooldown must be non-negative.")

            Setting.set("similarity_threshold_accept", str(accept_val))
            Setting.set("similarity_threshold_review", str(review_val))
            Setting.set("enroll_min_images", str(min_img_val))
            Setting.set("enroll_max_images", str(max_img_val))
            Setting.set("attendance_cooldown_minutes", str(cooldown_val))
            Setting.set("store_original_images", "true" if store_orig == "true" else "false")
            
            record_audit(
                "settings.update",
                entity="settings",
                details={
                    "similarity_threshold_accept": accept_val,
                    "similarity_threshold_review": review_val,
                    "enroll_min_images": min_img_val,
                    "enroll_max_images": max_img_val,
                    "attendance_cooldown_minutes": cooldown_val,
                    "store_original_images": store_orig == "true",
                },
            )
            db.session.commit()
            flash("System configurations updated successfully.", "success")
            return redirect(url_for("dashboard.settings"))
        except ValueError as e:
            flash(f"Invalid configurations: {str(e)}", "danger")

    accept = Setting.get("similarity_threshold_accept", "0.45")
    review = Setting.get("similarity_threshold_review", "0.35")
    min_img = Setting.get("enroll_min_images", "5")
    max_img = Setting.get("enroll_max_images", "10")
    cooldown = Setting.get("attendance_cooldown_minutes", "0")
    store_orig = Setting.get("store_original_images", "false")

    return render_template(
        "dashboard/settings.html",
        similarity_threshold_accept=accept,
        similarity_threshold_review=review,
        enroll_min_images=min_img,
        enroll_max_images=max_img,
        attendance_cooldown_minutes=cooldown,
        store_original_images=store_orig,
    )


@dashboard_bp.route("/sessions/<int:session_id>")
@login_required
def session_detail(session_id):
    session = db.session.get(AttendanceSession, session_id)
    if session is None:
        abort(404)

    # Search & filters
    q = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "").strip().lower()
    dept_filter = request.args.get("department", "").strip()
    year_filter = request.args.get("year", "").strip()

    # Query all active enrolled persons or anyone with an attendance record in this session
    persons_query = db.select(Person).where(
        (Person.is_active.is_(True) & Person.enrolled_at.is_not(None)) |
        Person.id.in_(
            db.select(AttendanceRecord.person_id).where(AttendanceRecord.session_id == session.id)
        )
    )
    persons = db.session.scalars(persons_query.order_by(Person.code)).all()

    # Query all attendance records for this session
    records = db.session.scalars(
        db.select(AttendanceRecord).where(AttendanceRecord.session_id == session.id)
    ).all()
    record_map = {r.person_id: r for r in records}

    # Fetch unique departments for filters
    departments = sorted(db.session.execute(
        db.select(Person.department)
        .where(Person.department.is_not(None))
        .where(Person.department != "")
        .distinct()
    ).scalars().all())

    # Build final list matching status, search query, dept, and year
    attendance_rows = []
    stats = {"present": 0, "late": 0, "absent": 0, "total": 0}

    for p in persons:
        rec = record_map.get(p.id)
        status = rec.status if rec else "absent"
        marked_at = rec.marked_at if rec else None
        confidence = rec.confidence if rec else None

        # Stats collection (before filters, representing full roster stats)
        stats[status] += 1
        stats["total"] += 1

        # Search filter
        if q:
            if q.lower() not in p.full_name.lower() and q.lower() not in p.code.lower():
                continue

        # Status filter
        if status_filter and status != status_filter:
            continue

        # Department filter
        if dept_filter and p.department != dept_filter:
            continue

        # Year filter
        if year_filter and str(p.year) != year_filter:
            continue

        attendance_rows.append({
            "person": p,
            "status": status,
            "marked_at": marked_at,
            "confidence": confidence,
        })

    stats["present_rate"] = (
        ((stats["present"] + stats["late"]) / stats["total"] * 100.0)
        if stats["total"] > 0
        else 0.0
    )

    return render_template(
        "dashboard/session_detail.html",
        session=session,
        attendance_rows=attendance_rows,
        departments=departments,
        stats=stats,
        q=q,
        selected_status=status_filter,
        selected_department=dept_filter,
        selected_year=year_filter,
    )


@dashboard_bp.route("/sessions/<int:session_id>/export")
@login_required
def session_export(session_id):
    session = db.session.get(AttendanceSession, session_id)
    if session is None:
        abort(404)

    fmt = request.args.get("format", "csv").lower()
    
    # We query all active enrolled persons or anyone with a record in this session
    persons = db.session.scalars(
        db.select(Person)
        .where(
            (Person.is_active.is_(True) & Person.enrolled_at.is_not(None)) |
            Person.id.in_(
                db.select(AttendanceRecord.person_id).where(AttendanceRecord.session_id == session.id)
            )
        )
        .order_by(Person.code)
    ).all()

    records = db.session.scalars(
        db.select(AttendanceRecord).where(AttendanceRecord.session_id == session.id)
    ).all()
    record_map = {r.person_id: r for r in records}

    # Fetch and build attendance rows
    attendance_rows = []
    for p in persons:
        rec = record_map.get(p.id)
        status = rec.status if rec else "absent"
        marked_at = rec.marked_at if rec else None
        confidence = rec.confidence if rec else None
        attendance_rows.append({
            "person": p,
            "status": status,
            "marked_at": marked_at,
            "confidence": confidence,
        })

    if fmt == "excel":
        from openpyxl import Workbook
        import io
        wb = Workbook()
        ws = wb.active
        ws.title = "Attendance"
        ws.append(["Roll Number", "Name", "Department", "Year", "Email", "Status", "Marked At", "Confidence"])
        for row in attendance_rows:
            p = row["person"]
            marked_at_str = row["marked_at"].strftime("%Y-%m-%d %H:%M:%S") if row["marked_at"] else "—"
            conf = float(row["confidence"]) if (row["confidence"] is not None) else "—"
            ws.append([p.code, p.full_name, p.department or "—", p.year or "—", p.email or "—", row["status"].capitalize(), marked_at_str, conf])
        out = io.BytesIO()
        wb.save(out)
        response = make_response(out.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename=attendance_session_{session_id}.xlsx"
        response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return response
    else:
        import csv
        import io
        output = io.StringIO()
        output.write('\ufeff')
        writer = csv.writer(output)
        writer.writerow(["Roll Number", "Name", "Department", "Year", "Email", "Status", "Marked At", "Confidence"])
        for row in attendance_rows:
            p = row["person"]
            marked_at_str = row["marked_at"].strftime("%Y-%m-%d %H:%M:%S") if row["marked_at"] else "—"
            conf = f"{row['confidence']:.2f}" if (row["confidence"] is not None) else "—"
            writer.writerow([p.code, p.full_name, p.department or "—", p.year or "—", p.email or "—", row["status"].capitalize(), marked_at_str, conf])
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename=attendance_session_{session_id}.csv"
        response.headers["Content-Type"] = "text/csv; charset=utf-8"
        return response


@dashboard_bp.route("/attendance/stats")
@role_required("operator")
def attendance_stats():
    # 1. Overall Student summaries
    persons = db.session.execute(
        db.select(Person)
        .where(Person.is_active.is_(True), Person.enrolled_at.is_not(None))
        .order_by(Person.code)
    ).scalars().all()

    total_sessions = db.session.scalar(
        db.select(db.func.count()).select_from(AttendanceSession)
    ) or 0

    attendance_counts = dict(
        db.session.execute(
            db.select(AttendanceRecord.person_id, db.func.count(AttendanceRecord.id))
            .group_by(AttendanceRecord.person_id)
        ).all()
    )

    student_summaries = []
    for p in persons:
        attended = attendance_counts.get(p.id, 0)
        rate = (attended / total_sessions * 100.0) if total_sessions > 0 else 0.0
        student_summaries.append({
            "person": p,
            "attended": attended,
            "total": total_sessions,
            "rate": rate
        })

    # Sort student summaries
    sort_by = request.args.get("sort", "code")
    if sort_by == "rate":
        student_summaries.sort(key=lambda s: s["rate"], reverse=True)
    elif sort_by == "rate_asc":
        student_summaries.sort(key=lambda s: s["rate"])
    else:
        student_summaries.sort(key=lambda s: s["person"].code)

    # 2. Daily stats for the last 30 days
    sessions_30 = db.session.execute(
        db.select(AttendanceSession)
        .order_by(AttendanceSession.start_time.desc())
        .limit(30)
    ).scalars().all()

    session_record_counts = dict(
        db.session.execute(
            db.select(AttendanceRecord.session_id, db.func.count(AttendanceRecord.id))
            .where(AttendanceRecord.session_id.in_([s.id for s in sessions_30] or [0]))
            .group_by(AttendanceRecord.session_id)
        ).all()
    )

    total_active_enrolled = db.session.scalar(
        db.select(db.func.count())
        .select_from(Person)
        .where(Person.is_active.is_(True), Person.enrolled_at.is_not(None))
    ) or 0

    daily_stats = []
    for s in reversed(sessions_30):
        attended = session_record_counts.get(s.id, 0)
        rate = (attended / total_active_enrolled * 100.0) if total_active_enrolled > 0 else 0.0
        daily_stats.append({
            "date": s.session_date.strftime("%Y-%m-%d"),
            "name": s.name,
            "rate": rate,
            "attended": attended,
            "total": total_active_enrolled
        })

    return render_template(
        "dashboard/attendance_stats.html",
        student_summaries=student_summaries,
        daily_stats=daily_stats,
        total_sessions=total_sessions
    )


@dashboard_bp.route("/attendance/stats/export")
@role_required("operator")
def attendance_stats_export():
    fmt = request.args.get("format", "csv").lower()
    
    persons = db.session.execute(
        db.select(Person)
        .where(Person.is_active.is_(True), Person.enrolled_at.is_not(None))
        .order_by(Person.code)
    ).scalars().all()

    total_sessions = db.session.scalar(
        db.select(db.func.count()).select_from(AttendanceSession)
    ) or 0

    attendance_counts = dict(
        db.session.execute(
            db.select(AttendanceRecord.person_id, db.func.count(AttendanceRecord.id))
            .group_by(AttendanceRecord.person_id)
        ).all()
    )

    if fmt == "excel":
        from openpyxl import Workbook
        import io
        wb = Workbook()
        ws = wb.active
        ws.title = "Attendance Summary"
        ws.append(["Roll Number", "Name", "Department", "Year", "Attended Classes", "Total Classes", "Attendance Rate (%)"])
        for p in persons:
            attended = attendance_counts.get(p.id, 0)
            rate = (attended / total_sessions * 100.0) if total_sessions > 0 else 0.0
            ws.append([p.code, p.full_name, p.department or "—", p.year or "—", attended, total_sessions, round(rate, 2)])
        out = io.BytesIO()
        wb.save(out)
        response = make_response(out.getvalue())
        response.headers["Content-Disposition"] = "attachment; filename=attendance_summary.xlsx"
        response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return response
    else:
        import csv
        import io
        output = io.StringIO()
        output.write('\ufeff')
        writer = csv.writer(output)
        writer.writerow(["Roll Number", "Name", "Department", "Year", "Attended Classes", "Total Classes", "Attendance Rate (%)"])
        for p in persons:
            attended = attendance_counts.get(p.id, 0)
            rate = (attended / total_sessions * 100.0) if total_sessions > 0 else 0.0
            writer.writerow([p.code, p.full_name, p.department or "—", p.year or "—", attended, total_sessions, f"{rate:.2f}"])
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = "attachment; filename=attendance_summary.csv"
        response.headers["Content-Type"] = "text/csv; charset=utf-8"
        return response
