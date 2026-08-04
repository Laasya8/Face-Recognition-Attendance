"""Tests for the Admin User Management features."""

import pytest
from app.extensions import db
from app.models import AdminUser
from tests.conftest import login


def make_admin(username="admin", password="password123"):
    admin = AdminUser(username=username, role="admin")
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    return admin


def test_admin_only_access_users_list(client):
    # Unauthenticated visitor
    response = client.get("/users")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]

    # Viewer role (should be 403 Forbidden)
    login(client, username="viewer")
    response = client.get("/users")
    assert response.status_code == 403

    # Log out viewer, then log in as operator
    client.get("/auth/logout")

    # Operator role (should be 403 Forbidden)
    login(client, username="operator")
    response = client.get("/users")
    assert response.status_code == 403

    # Log out operator, then log in as admin
    client.get("/auth/logout")

    # Admin role (should be 200 OK)
    make_admin()
    login(client, username="admin")
    response = client.get("/users")
    assert response.status_code == 200
    assert b"User Management" in response.data


def test_admin_only_access_edit_user(client):
    make_admin()
    target_user = AdminUser.query.filter_by(username="viewer").first()

    # Unauthenticated
    response = client.get(f"/users/{target_user.id}/edit")
    assert response.status_code == 302

    # Viewer
    login(client, username="viewer")
    response = client.get(f"/users/{target_user.id}/edit")
    assert response.status_code == 403

    # Log out viewer, then log in as admin
    client.get("/auth/logout")

    # Admin
    login(client, username="admin")
    response = client.get(f"/users/{target_user.id}/edit")
    assert response.status_code == 200


def test_create_user_success(client):
    make_admin()
    login(client, username="admin")

    # POST new user
    response = client.post(
        "/users",
        data={
            "username": "newoperator",
            "password": "securepassword123",
            "role": "operator",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"newoperator" in response.data
    assert b"created successfully" in response.data

    # Verify user created in DB
    new_user = AdminUser.query.filter_by(username="newoperator").first()
    assert new_user is not None
    assert new_user.role == "operator"
    assert new_user.is_active is True
    assert new_user.check_password("securepassword123") is True

    # Verify user can log in
    client.get("/auth/logout", follow_redirects=True)
    login_response = login(client, username="newoperator", password="securepassword123")
    # Redirects to dashboard index on success
    assert login_response.status_code == 302


def test_create_user_validation_fails(client):
    make_admin()
    login(client, username="admin")

    # 1. Duplicate username
    response = client.post(
        "/users",
        data={
            "username": "viewer",  # default user created in conftest
            "password": "securepassword123",
            "role": "viewer",
        },
    )
    assert response.status_code == 200
    assert b"Username is already taken" in response.data

    # 2. Username too short
    response = client.post(
        "/users",
        data={
            "username": "ab",
            "password": "securepassword123",
            "role": "viewer",
        },
    )
    assert response.status_code == 200
    assert b"Field must be between 3 and 64 characters long" in response.data

    # 3. Password too short
    response = client.post(
        "/users",
        data={
            "username": "shortpassuser",
            "password": "short",
            "role": "viewer",
        },
    )
    assert response.status_code == 200
    assert b"Field must be between 8 and 128 characters long" in response.data


def test_edit_user_success(client):
    make_admin()
    login(client, username="admin")
    target_user = AdminUser.query.filter_by(username="viewer").first()

    # Edit role, status, keep password same
    response = client.post(
        f"/users/{target_user.id}/edit",
        data={
            "role": "operator",
            "is_active": "y",  # BooleanField accepts 'y' or 'true' or 'on'
            "password": "",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    db.session.refresh(target_user)
    assert target_user.role == "operator"
    assert target_user.is_active is True
    # Verify password is still the original one ("password123")
    assert target_user.check_password("password123") is True

    # Reset password
    response = client.post(
        f"/users/{target_user.id}/edit",
        data={
            "role": "operator",
            "is_active": "y",
            "password": "newchangedpassword123",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    db.session.refresh(target_user)
    assert target_user.check_password("newchangedpassword123") is True

    # Deactivate the user via form
    response = client.post(
        f"/users/{target_user.id}/edit",
        data={
            "role": "operator",
            # omitting "is_active" represents checkbox unchecked
            "password": "",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    db.session.refresh(target_user)
    assert target_user.is_active is False


def test_user_deactivation_blocks_access(client):
    # 1. Create a user we can deactivate
    user = AdminUser(username="testuser", role="operator")
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()

    # 2. Log in as that user and verify access
    login_response = login(client, username="testuser", password="password123")
    assert login_response.status_code == 302

    response = client.get("/sessions")
    assert response.status_code == 200

    # 3. Deactivate the user in DB
    user.is_active = False
    db.session.commit()

    # 4. Try accessing a page in active session (Flask-Login should reject due to is_active=False)
    response = client.get("/sessions")
    assert response.status_code == 302  # redirected to login page

    # 5. Try logging in again
    client.get("/auth/logout", follow_redirects=True)
    login_response = login(client, username="testuser", password="password123")
    assert login_response.status_code == 401  # login fails


def test_admin_prevent_self_lockout(client):
    admin = make_admin(username="selfadmin")
    login(client, username="selfadmin")

    # Try to deactivate self
    response = client.post(
        f"/users/{admin.id}/edit",
        data={
            "role": "admin",
            # omitting is_active to deactivate
            "password": "",
        },
    )
    assert response.status_code == 200
    assert b"You cannot deactivate your own account" in response.data
    db.session.refresh(admin)
    assert admin.is_active is True

    # Try to downgrade self role
    response = client.post(
        f"/users/{admin.id}/edit",
        data={
            "role": "operator",
            "is_active": "y",
            "password": "",
        },
    )
    assert response.status_code == 200
    assert b"You cannot downgrade your own role" in response.data
    db.session.refresh(admin)
    assert admin.role == "admin"


def test_login_safe_next_url(client):
    make_admin(username="adminuser")

    # Safe next URL: redirect to dashboard or specified sessions route
    response = client.post(
        "/auth/login?next=/sessions",
        data={"username": "adminuser", "password": "password123"},
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/sessions"

    client.get("/auth/logout")

    # Unsafe next URL (absolute)
    response = client.post(
        "/auth/login?next=http://attacker.com/malicious",
        data={"username": "adminuser", "password": "password123"},
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/"

    client.get("/auth/logout")

    # Unsafe next URL (protocol relative //)
    response = client.post(
        "/auth/login?next=//attacker.com",
        data={"username": "adminuser", "password": "password123"},
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/"

    client.get("/auth/logout")

    # Unsafe next URL (triple slash ///)
    response = client.post(
        "/auth/login?next=///attacker.com",
        data={"username": "adminuser", "password": "password123"},
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/"

