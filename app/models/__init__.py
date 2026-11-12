from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    appliances = db.relationship("Appliance", backref="user", cascade="all, delete-orphan")
    readings = db.relationship("ConsumptionRecord", backref="user", cascade="all, delete-orphan")
    tariffs = db.relationship("TariffSlab", backref="user", cascade="all, delete-orphan")
    limits = db.relationship("UsageLimit", backref="user", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Appliance(db.Model):
    __tablename__ = "appliances"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(60), nullable=False)
    power_w = db.Column(db.Float, nullable=False)
    daily_hours = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    is_on = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    @property
    def daily_energy_kwh(self):
        return self.power_w * self.daily_hours * self.quantity / 1000


class ConsumptionRecord(db.Model):
    __tablename__ = "consumption_records"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    appliance_id = db.Column(db.Integer, db.ForeignKey("appliances.id", ondelete="SET NULL"), nullable=True)
    energy_kwh = db.Column(db.Float, nullable=False)
    power_w = db.Column(db.Float, nullable=True)
    duration_hours = db.Column(db.Float, nullable=True)
    source = db.Column(db.String(20), nullable=False, default="manual")
    recorded_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    appliance = db.relationship("Appliance")


class TariffSlab(db.Model):
    __tablename__ = "tariff_slabs"
    __table_args__ = (db.UniqueConstraint("user_id", "order", name="uq_tariff_user_order"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    lower_units = db.Column(db.Float, nullable=False)
    upper_units = db.Column(db.Float, nullable=True)
    rate_per_unit = db.Column(db.Float, nullable=False)
    order = db.Column(db.Integer, nullable=False)


class BillingRecord(db.Model):
    __tablename__ = "billing_records"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    units = db.Column(db.Float, nullable=False)
    fixed_charges = db.Column(db.Float, nullable=False, default=0)
    additional_charges = db.Column(db.Float, nullable=False, default=0)
    tax_percent = db.Column(db.Float, nullable=False, default=0)
    total_amount = db.Column(db.Float, nullable=False)
    breakdown_json = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class UsageLimit(db.Model):
    __tablename__ = "usage_limits"
    __table_args__ = (db.UniqueConstraint("user_id", "period", name="uq_usage_limit_user_period"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    period = db.Column(db.String(10), nullable=False)
    limit_kwh = db.Column(db.Float, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class Alert(db.Model):
    __tablename__ = "alerts"
    __table_args__ = (
        db.UniqueConstraint("user_id", "period", "period_key", "threshold", name="uq_alert_threshold_event"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    period = db.Column(db.String(10), nullable=False)
    period_key = db.Column(db.String(20), nullable=False)
    threshold = db.Column(db.String(20), nullable=False)
    severity = db.Column(db.String(20), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class EnergyRecommendation(db.Model):
    __tablename__ = "energy_recommendations"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    estimated_saving_kwh = db.Column(db.Float, nullable=True)
    estimated_saving_amount = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class Device(db.Model):
    __tablename__ = "devices"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    token_hash = db.Column(db.String(255), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
