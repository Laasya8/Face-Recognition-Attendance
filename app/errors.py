"""Application-wide error handlers with HTML/JSON content negotiation."""

from flask import jsonify, render_template, request

from app.extensions import db

_ERROR_MESSAGES = {
    400: ("bad_request", "The request could not be understood."),
    403: ("forbidden", "You do not have permission to access this resource."),
    404: ("not_found", "The requested resource was not found."),
    405: ("method_not_allowed", "That HTTP method is not allowed here."),
    409: ("conflict", "The request conflicts with the current state."),
    413: ("payload_too_large", "The uploaded data exceeds the size limit."),
    500: ("internal_error", "An unexpected error occurred."),
}


def _wants_json():
    if request.path.startswith("/api/"):
        return True
    accepts = request.accept_mimetypes
    return accepts["application/json"] >= accepts["text/html"]


def _render_error(status_code, message=None):
    code, default_message = _ERROR_MESSAGES[status_code]
    message = message or default_message
    if _wants_json():
        body = jsonify({"error": {"code": code, "message": message}})
        return body, status_code
    return (
        render_template(
            "errors/error.html", status_code=status_code, message=message
        ),
        status_code,
    )


def register_error_handlers(app):
    @app.errorhandler(400)
    def bad_request(error):
        return _render_error(400, getattr(error, "description", None))

    @app.errorhandler(403)
    def forbidden(_error):
        return _render_error(403)

    @app.errorhandler(404)
    def not_found(_error):
        return _render_error(404)

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return _render_error(405)

    @app.errorhandler(409)
    def conflict(error):
        return _render_error(409, getattr(error, "description", None))

    @app.errorhandler(413)
    def payload_too_large(_error):
        return _render_error(413)

    @app.errorhandler(500)
    def internal_error(error):
        # A failed request can leave the session in a broken transaction;
        # roll back so subsequent requests on this worker are unaffected.
        db.session.rollback()
        app.logger.exception("Unhandled exception: %s", error)
        return _render_error(500)
