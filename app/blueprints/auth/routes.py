from urllib.parse import urlsplit

from flask import flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.blueprints.auth import auth_bp
from app.blueprints.auth.forms import LoginForm
from app.extensions import db
from app.models import AdminUser, utcnow
from app.utils.audit import record_audit


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip().lower()
        user = AdminUser.query.filter_by(username=username).first()

        # One shared message for unknown user / wrong password / disabled
        # account: no username enumeration through differing responses.
        if user is None or not user.is_active or not user.check_password(
            form.password.data
        ):
            flash("Invalid username or password.", "danger")
            return render_template("auth/login.html", form=form), 401

        session.permanent = True
        login_user(user)
        user.last_login_at = utcnow()
        record_audit("login", entity="admin_user", entity_id=user.id, actor=user)
        db.session.commit()

        return redirect(_safe_next_url())

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    record_audit("logout", entity="admin_user", entity_id=current_user.id)
    db.session.commit()
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))


def _safe_next_url():
    """Honour ?next= only for relative URLs to prevent open redirects."""
    next_url = request.args.get("next")
    if not next_url:
        return url_for("dashboard.index")

    parsed = urlsplit(next_url)
    if parsed.scheme or parsed.netloc:
        return url_for("dashboard.index")

    # Ensure it starts with a single '/' and isn't followed by another slash or backslash
    if next_url.startswith("/") and not next_url.startswith("//") and not next_url.startswith("/\\"):
        return next_url

    return url_for("dashboard.index")
