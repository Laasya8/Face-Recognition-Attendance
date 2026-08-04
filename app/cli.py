"""Operational CLI commands: flask init-db | create-admin | list-users."""

import click
from flask import current_app

from app.extensions import db
from app.models import AdminUser, Setting
from app.models.user import ROLES


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Create all tables and seed default settings (idempotent)."""
        db.create_all()
        seeded = 0
        for key, value in current_app.config["DEFAULT_SETTINGS"].items():
            if db.session.get(Setting, key) is None:
                db.session.add(Setting(key=key, value=value))
                seeded += 1
        db.session.commit()
        click.echo(f"Database initialised. Seeded {seeded} default setting(s).")

    @app.cli.command("create-admin")
    @click.option("--username", prompt=True, help="Login name for the new account.")
    @click.option(
        "--password",
        prompt=True,
        hide_input=True,
        confirmation_prompt=True,
        help="Password (min 8 characters).",
    )
    @click.option(
        "--role",
        default="admin",
        show_default=True,
        type=click.Choice(ROLES),
        help="Access level for the account.",
    )
    def create_admin(username, password, role):
        """Create a login account. There is no self-registration by design."""
        username = username.strip().lower()
        if len(username) < 3:
            raise click.ClickException("Username must be at least 3 characters.")
        if len(password) < 8:
            raise click.ClickException("Password must be at least 8 characters.")
        if AdminUser.query.filter_by(username=username).first() is not None:
            raise click.ClickException(f"User {username!r} already exists.")

        user = AdminUser(username=username, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Created {role} account {username!r} (id={user.id}).")

    @app.cli.command("list-users")
    def list_users():
        """Print all login accounts."""
        users = AdminUser.query.order_by(AdminUser.id).all()
        if not users:
            click.echo("No accounts exist yet. Run: flask create-admin")
            return
        for user in users:
            status = "active" if user.is_active else "disabled"
            click.echo(f"{user.id:>4}  {user.username:<24} {user.role:<9} {status}")
