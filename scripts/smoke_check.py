"""End-to-end smoke check against the real development app and database.

Run after deploy or schema changes:

    .venv\\Scripts\\python.exe scripts\\smoke_check.py <username> <password>

Exercises: health probe, auth redirect, CSRF-protected login, dashboard
render, JSON error envelope, and the failed-login path. Exits non-zero on
the first failure.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402

CSRF_PATTERN = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')

failures = []


def check(label, condition, detail=""):
    status = "ok " if condition else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    username, password = sys.argv[1], sys.argv[2]

    app = create_app("development")
    client = app.test_client()

    # 1. Health probe answers and sees the database.
    response = client.get("/api/v1/health")
    body = response.get_json()
    check("health endpoint returns 200", response.status_code == 200,
          f"got {response.status_code}")
    check("health reports database ok", body and body.get("database") == "ok",
          repr(body))

    # 2. Anonymous dashboard access redirects to login.
    response = client.get("/", follow_redirects=False)
    check("anonymous / redirects to login",
          response.status_code == 302 and "/auth/login" in response.headers["Location"],
          f"{response.status_code} -> {response.headers.get('Location')}")

    # 3. Login page renders with a CSRF token.
    response = client.get("/auth/login")
    match = CSRF_PATTERN.search(response.get_data(as_text=True))
    check("login page renders with CSRF token",
          response.status_code == 200 and match is not None)
    if match is None:
        return finish()
    csrf_token = match.group(1)

    # 4. Wrong password is rejected with 401 and no session.
    response = client.post("/auth/login", data={
        "username": username, "password": "definitely-wrong-password",
        "csrf_token": csrf_token,
    })
    check("wrong password rejected with 401", response.status_code == 401)

    # 5. Correct credentials log in and land on the dashboard.
    response = client.post("/auth/login", data={
        "username": username, "password": password, "csrf_token": csrf_token,
    }, follow_redirects=True)
    page = response.get_data(as_text=True)
    check("login succeeds and dashboard renders",
          response.status_code == 200 and "Dashboard" in page,
          f"got {response.status_code}")
    check("dashboard shows stat cards", "Active Students" in page)

    # 6. API 404 uses the JSON error envelope.
    response = client.get("/api/v1/nonexistent")
    body = response.get_json()
    check("API 404 returns JSON error envelope",
          response.status_code == 404 and body
          and body.get("error", {}).get("code") == "not_found",
          repr(body))

    # 7. Security headers are present.
    response = client.get("/auth/login")
    check("security headers set",
          response.headers.get("X-Content-Type-Options") == "nosniff"
          and "Content-Security-Policy" in response.headers)

    return finish()


def finish():
    if failures:
        print(f"\n{len(failures)} check(s) failed.")
        return 1
    print("\nAll smoke checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
