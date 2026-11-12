from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user

web = Blueprint("web", __name__)


@web.get("/")
def home():
    if current_user.is_authenticated:
        return redirect(url_for("web.dashboard"))
    return redirect(url_for("web.login"))


@web.get("/login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("web.dashboard"))
    return render_template("login.html")


@web.get("/register")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("web.dashboard"))
    return render_template("register.html")


@web.get("/dashboard")
def dashboard():
    if not current_user.is_authenticated:
        return redirect(url_for("web.login"))
    return render_template("dashboard.html", user=current_user)
