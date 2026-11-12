import re

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_user, logout_user
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import User

auth = Blueprint("auth", __name__)


def _payload():
    return request.get_json(silent=True) or {}


@auth.post("/register")
def register():
    data = _payload()
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = data.get("password", "")
    if not name or len(name) > 100:
        return jsonify(error="validation_error", message="Enter a name of 1 to 100 characters."), 400
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 254:
        return jsonify(error="validation_error", message="Enter a valid email address."), 400
    if not isinstance(password, str) or len(password) < 10 or len(password) > 128:
        return jsonify(error="validation_error", message="Password must be between 10 and 128 characters."), 400
    user = User(name=name, email=email)
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="conflict", message="An account with that email already exists."), 409
    login_user(user)
    return jsonify(message="Account created.", user={"id": user.id, "name": user.name, "email": user.email}), 201


@auth.post("/login")
def login():
    data = _payload()
    email = str(data.get("email", "")).strip().lower()
    password = data.get("password", "")
    user = User.query.filter_by(email=email).first()
    if not user or not isinstance(password, str) or not user.check_password(password):
        return jsonify(error="authentication_failed", message="Email or password is incorrect."), 401
    login_user(user, remember=bool(data.get("remember", False)))
    return jsonify(message="Signed in.", user={"id": user.id, "name": user.name, "email": user.email})


@auth.post("/logout")
def logout():
    if current_user.is_authenticated:
        logout_user()
    return jsonify(message="Signed out.")
