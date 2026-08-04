from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, ValidationError


class LoginForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[DataRequired(), Length(min=3, max=64)],
        render_kw={"autofocus": True, "autocomplete": "username"},
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=8, max=128)],
        render_kw={"autocomplete": "current-password"},
    )
    submit = SubmitField("Sign in")


class CreateUserForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[DataRequired(), Length(min=3, max=64)],
        render_kw={"placeholder": "e.g. john.doe", "autocomplete": "username"},
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=8, max=128)],
        render_kw={"placeholder": "Min 8 characters", "autocomplete": "new-password"},
    )
    role = SelectField(
        "Role",
        choices=[("viewer", "Viewer"), ("operator", "Operator"), ("admin", "Admin")],
        validators=[DataRequired()],
    )
    submit = SubmitField("Create User")

    def validate_username(self, field):
        from app.models import AdminUser
        username = field.data.strip().lower()
        if AdminUser.query.filter_by(username=username).first() is not None:
            raise ValidationError("Username is already taken.")


class EditUserForm(FlaskForm):
    role = SelectField(
        "Role",
        choices=[("viewer", "Viewer"), ("operator", "Operator"), ("admin", "Admin")],
        validators=[DataRequired()],
    )
    is_active = BooleanField("Active Account", default=True)
    password = PasswordField(
        "Reset Password",
        validators=[Optional(), Length(min=8, max=128)],
        render_kw={"placeholder": "Leave blank to keep current password", "autocomplete": "new-password"},
    )
    submit = SubmitField("Save Changes")

