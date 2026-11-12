from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from flask_wtf.csrf import CSRFError, CSRFProtect, generate_csrf
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from config import Config
from app.extensions import db, login_manager

csrf = CSRFProtect()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY must be configured in the environment.")
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError("DATABASE_URL must be configured in the environment.")

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = "web.login"
    login_manager.login_message_category = "warning"

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith("/api/"):
            return jsonify(error="authentication_required", message="Sign in to access this resource."), 401
        return redirect(url_for("web.login"))

    from app.routes.api import api
    from app.routes.auth import auth
    from app.routes.web import web

    app.register_blueprint(auth, url_prefix="/api/auth")
    app.register_blueprint(api, url_prefix="/api")
    app.register_blueprint(web)

    @app.context_processor
    def inject_template_values():
        return {"csrf_token": generate_csrf, "current_user": current_user}

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        if request.path.startswith("/api/"):
            return jsonify(error="csrf_failed", message=error.description), 400
        return render_template("error.html", message=error.description), 400

    @app.get("/health")
    def health():
        try:
            db.session.execute(text("SELECT 1"))
            return jsonify(status="ok", database="connected")
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Database health check failed")
            return jsonify(status="error", database="unavailable"), 503

    @app.errorhandler(404)
    def not_found(error):
        if request.path.startswith("/api/"):
            return jsonify(error="not_found", message="The requested resource was not found."), 404
        return render_template("error.html", message="The page you requested could not be found."), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        app.logger.exception("Unhandled server error")
        if request.path.startswith("/api/"):
            return jsonify(error="internal_error", message="An unexpected server error occurred."), 500
        return render_template("error.html", message="An unexpected error occurred."), 500

    return app
