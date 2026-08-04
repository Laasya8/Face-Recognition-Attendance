"""Domain services: face analysis, matching, enrollment, attendance.

Services hold the recognition business logic so that blueprints stay thin
and the logic stays testable without HTTP. Modules here import the heavy
vision stack (cv2, insightface) lazily — the web app must remain importable
on machines that only run the dashboard.
"""
