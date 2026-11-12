import csv
import io
import math
import secrets
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, jsonify, make_response, request
from flask_login import current_user, login_required
from werkzeug.security import check_password_hash, generate_password_hash

from app import csrf
from app.extensions import db
from app.models import (
    Alert,
    Appliance,
    BillingRecord,
    ConsumptionRecord,
    Device,
    EnergyRecommendation,
    TariffSlab,
    UsageLimit,
    utcnow,
)
from app.services.alerts import check_usage_limits
from app.services.calculations import calculate_energy, calculate_progressive_bill

api = Blueprint("api", __name__)


def _data():
    return request.get_json(silent=True) or {}


def _number(data, key, *, minimum=0, maximum=None, required=True):
    value = data.get(key)
    if value is None and not required:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{key} must be a number.")
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be a number.")
    if not math.isfinite(value) or value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{key} must be between {minimum} and {maximum if maximum is not None else 'a valid value'}.")
    return value


def _date(value, field):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except (AttributeError, TypeError, ValueError):
        raise ValueError(f"{field} must be an ISO 8601 date or datetime.")


def _owned_appliance(appliance_id):
    return Appliance.query.filter_by(id=appliance_id, user_id=current_user.id).first()


def _owned_reading(reading_id):
    return ConsumptionRecord.query.filter_by(id=reading_id, user_id=current_user.id).first()


def _appliance_json(item):
    return {
        "id": item.id, "name": item.name, "category": item.category,
        "power_w": item.power_w, "daily_hours": item.daily_hours,
        "quantity": item.quantity, "is_on": item.is_on,
        "daily_estimate_kwh": round(item.daily_energy_kwh, 3),
        "monthly_estimate_kwh": round(item.daily_energy_kwh * 30, 3),
    }


def _reading_json(item):
    return {
        "id": item.id, "appliance_id": item.appliance_id,
        "appliance_name": item.appliance.name if item.appliance else None,
        "energy_kwh": item.energy_kwh, "power_w": item.power_w,
        "duration_hours": item.duration_hours, "source": item.source,
        "recorded_at": item.recorded_at.isoformat(),
    }


def _add_reading(data, source=None):
    energy = data.get("energy_kwh")
    power = _number(data, "power_w", required=False)
    hours = _number(data, "duration_hours", required=False)
    if energy is None:
        if power is None or hours is None:
            raise ValueError("Provide energy_kwh or both power_w and duration_hours.")
        energy = calculate_energy(power, hours)
    else:
        energy = _number(data, "energy_kwh")
    if energy <= 0 or energy > 100000:
        raise ValueError("energy_kwh must be greater than 0 and no more than 100000.")
    appliance_id = data.get("appliance_id")
    appliance = None
    if appliance_id is not None:
        appliance = _owned_appliance(appliance_id)
        if not appliance:
            raise ValueError("The selected appliance was not found.")
    recorded_at = _date(data.get("recorded_at", utcnow().isoformat()), "recorded_at")
    if recorded_at > utcnow() + timedelta(minutes=5):
        raise ValueError("recorded_at cannot be in the future.")
    record_source = source or data.get("source", "manual")
    if record_source not in ("manual", "simulated"):
        raise ValueError("source must be manual or simulated.")
    return ConsumptionRecord(
        user_id=current_user.id,
        appliance=appliance,
        energy_kwh=energy,
        power_w=power,
        duration_hours=hours,
        source=record_source,
        recorded_at=recorded_at,
    )


@api.get("/dashboard/summary")
@login_required
def dashboard_summary():
    now = utcnow()
    month_start = datetime(now.year, now.month, 1)
    previous_start = datetime(now.year - (now.month == 1), 12 if now.month == 1 else now.month - 1, 1)
    records = ConsumptionRecord.query.filter(
        ConsumptionRecord.user_id == current_user.id,
        ConsumptionRecord.recorded_at >= previous_start,
        ConsumptionRecord.recorded_at < month_start + timedelta(days=monthrange(now.year, now.month)[1]),
    ).all()
    current_records = [r for r in records if r.recorded_at >= month_start]
    previous_records = [r for r in records if r.recorded_at < month_start]
    month_units = sum(r.energy_kwh for r in current_records)
    previous_units = sum(r.energy_kwh for r in previous_records)
    days_elapsed = max(now.day, 1)
    month_limit = UsageLimit.query.filter_by(user_id=current_user.id, period="monthly").first()
    power_records = [r for r in current_records if r.power_w is not None]
    latest_power_record = max(power_records, key=lambda r: r.recorded_at) if power_records else None
    current_power = latest_power_record.power_w if latest_power_record else None
    tariffs = _tariff_data()
    estimated_bill = None
    bill_note = "Configure your tariff slabs to see an estimated bill."
    if tariffs:
        bill = calculate_progressive_bill(month_units, tariffs)
        estimated_bill = bill["total_amount"]
        bill_note = "Month-to-date estimate from your configured rates; excludes fixed charges and taxes."
    # Daily labels are complete so gaps in recorded consumption remain visible as zeroes.
    daily = []
    for day in range(1, now.day + 1):
        target = date(now.year, now.month, day)
        daily.append({
            "date": target.isoformat(),
            "kwh": round(sum(r.energy_kwh for r in current_records if r.recorded_at.date() == target), 3),
        })
    monthly = []
    for offset in range(5, -1, -1):
        year, month = now.year, now.month - offset
        while month <= 0:
            year -= 1
            month += 12
        start = datetime(year, month, 1)
        end = datetime(year + (month == 12), 1 if month == 12 else month + 1, 1)
        monthly.append({
            "month": start.strftime("%b %Y"),
            "kwh": round(sum(r.energy_kwh for r in records if start <= r.recorded_at < end), 3),
        })
    check_usage_limits(current_user.id, now)
    recent_alerts = Alert.query.filter_by(user_id=current_user.id).order_by(Alert.created_at.desc()).limit(5).all()
    return jsonify({
        "data_basis": "Consumption totals use manual, simulated, and device-ingested records; appliance figures are estimates.",
        "total_consumption_kwh": round(month_units, 3),
        "current_power_w": current_power,
        "current_power_basis": f"latest {latest_power_record.source} reading" if latest_power_record else None,
        "estimated_monthly_bill": estimated_bill,
        "monthly_bill_note": bill_note,
        "average_daily_kwh": round(month_units / days_elapsed, 3),
        "monthly_limit_kwh": month_limit.limit_kwh if month_limit else None,
        "remaining_monthly_kwh": round(max(0, month_limit.limit_kwh - month_units), 3) if month_limit else None,
        "limit_basis": "configured monthly limit" if month_limit else None,
        "previous_month_kwh": round(previous_units, 3),
        "month_change_percent": round((month_units - previous_units) / previous_units * 100, 1) if previous_units else None,
        "daily": daily,
        "monthly": monthly,
        "recent_alerts": [{
            "id": a.id, "severity": a.severity, "description": a.description,
            "created_at": a.created_at.isoformat(), "is_read": a.is_read,
        } for a in recent_alerts],
        "recent_readings": [
            _reading_json(r) for r in ConsumptionRecord.query.filter_by(user_id=current_user.id)
            .order_by(ConsumptionRecord.recorded_at.desc()).limit(6).all()
        ],
    })


@api.get("/dashboard/consumption")
@login_required
def dashboard_consumption():
    return dashboard_summary()


@api.get("/appliances")
@login_required
def list_appliances():
    items = Appliance.query.filter_by(user_id=current_user.id).order_by(Appliance.name).all()
    return jsonify(appliances=[_appliance_json(item) for item in items])


@api.post("/appliances")
@login_required
def create_appliance():
    data = _data()
    try:
        name = str(data.get("name", "")).strip()
        category = str(data.get("category", "")).strip()
        if not name or len(name) > 100 or not category or len(category) > 60:
            raise ValueError("Name and category are required (up to 100 and 60 characters).")
        quantity = _number(data, "quantity", minimum=1, maximum=1000)
        if not quantity.is_integer():
            raise ValueError("quantity must be a whole number.")
        is_on = data.get("is_on", False)
        if not isinstance(is_on, bool):
            raise ValueError("is_on must be true or false.")
        appliance = Appliance(
            user_id=current_user.id, name=name, category=category,
            power_w=_number(data, "power_w", minimum=0.1, maximum=100000),
            daily_hours=_number(data, "daily_hours", maximum=24),
            quantity=int(quantity),
            is_on=is_on,
        )
        db.session.add(appliance)
        db.session.commit()
        return jsonify(appliance=_appliance_json(appliance)), 201
    except (ValueError, TypeError) as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 400


@api.put("/appliances/<int:appliance_id>")
@login_required
def update_appliance(appliance_id):
    appliance = _owned_appliance(appliance_id)
    if not appliance:
        return jsonify(error="not_found", message="Appliance not found."), 404
    data = _data()
    try:
        for key, maximum in (("name", None), ("category", None)):
            if key in data:
                value = str(data[key]).strip()
                if not value or len(value) > (100 if key == "name" else 60):
                    raise ValueError(f"Invalid {key}.")
                setattr(appliance, key, value)
        if "power_w" in data:
            appliance.power_w = _number(data, "power_w", minimum=0.1, maximum=100000)
        if "daily_hours" in data:
            appliance.daily_hours = _number(data, "daily_hours", maximum=24)
        if "quantity" in data:
            quantity = _number(data, "quantity", minimum=1, maximum=1000)
            if not quantity.is_integer():
                raise ValueError("quantity must be a whole number.")
            appliance.quantity = int(quantity)
        if "is_on" in data:
            if not isinstance(data["is_on"], bool):
                raise ValueError("is_on must be true or false.")
            appliance.is_on = data["is_on"]
        db.session.commit()
        return jsonify(appliance=_appliance_json(appliance))
    except (ValueError, TypeError) as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 400


@api.delete("/appliances/<int:appliance_id>")
@login_required
def delete_appliance(appliance_id):
    appliance = _owned_appliance(appliance_id)
    if not appliance:
        return jsonify(error="not_found", message="Appliance not found."), 404
    db.session.delete(appliance)
    db.session.commit()
    return jsonify(message="Appliance deleted.")


@api.get("/consumption")
@login_required
def list_consumption():
    query = ConsumptionRecord.query.filter_by(user_id=current_user.id)
    try:
        if request.args.get("start"):
            query = query.filter(ConsumptionRecord.recorded_at >= _date(request.args["start"], "start"))
        if request.args.get("end"):
            query = query.filter(ConsumptionRecord.recorded_at <= _date(request.args["end"], "end"))
    except ValueError as error:
        return jsonify(error="validation_error", message=str(error)), 400
    items = query.order_by(ConsumptionRecord.recorded_at.desc()).limit(500).all()
    return jsonify(readings=[_reading_json(item) for item in items])


@api.post("/consumption")
@login_required
def create_consumption():
    try:
        record = _add_reading(_data())
        db.session.add(record)
        db.session.commit()
        check_usage_limits(current_user.id, record.recorded_at)
        return jsonify(reading=_reading_json(record)), 201
    except (ValueError, TypeError) as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 400


@api.post("/consumption/simulate")
@login_required
def simulate_consumption():
    try:
        record = _add_reading(_data(), source="simulated")
        db.session.add(record)
        db.session.commit()
        check_usage_limits(current_user.id, record.recorded_at)
        return jsonify(reading=_reading_json(record), notice="This is a user-configured simulation, not a sensor measurement."), 201
    except (ValueError, TypeError) as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 400


@api.put("/consumption/<int:reading_id>")
@login_required
def update_consumption(reading_id):
    record = _owned_reading(reading_id)
    if not record:
        return jsonify(error="not_found", message="Reading not found."), 404
    data = _data()
    try:
        if "energy_kwh" in data or "power_w" in data or "duration_hours" in data:
            if "energy_kwh" in data:
                record.energy_kwh = _number(data, "energy_kwh", minimum=0.000001, maximum=100000)
            elif "power_w" in data and "duration_hours" in data:
                record.power_w = _number(data, "power_w")
                record.duration_hours = _number(data, "duration_hours")
                record.energy_kwh = calculate_energy(record.power_w, record.duration_hours)
            else:
                raise ValueError("To recalculate a reading, provide both power_w and duration_hours.")
        if "recorded_at" in data:
            record.recorded_at = _date(data["recorded_at"], "recorded_at")
        if "appliance_id" in data:
            appliance = _owned_appliance(data["appliance_id"]) if data["appliance_id"] else None
            if data["appliance_id"] and not appliance:
                raise ValueError("The selected appliance was not found.")
            record.appliance = appliance
        db.session.commit()
        check_usage_limits(current_user.id, record.recorded_at)
        return jsonify(reading=_reading_json(record))
    except (ValueError, TypeError) as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 400


@api.delete("/consumption/<int:reading_id>")
@login_required
def delete_consumption(reading_id):
    record = _owned_reading(reading_id)
    if not record:
        return jsonify(error="not_found", message="Reading not found."), 404
    db.session.delete(record)
    db.session.commit()
    return jsonify(message="Reading deleted.")


def _tariff_data():
    tariffs = TariffSlab.query.filter_by(user_id=current_user.id).order_by(TariffSlab.order).all()
    return [{
        "id": slab.id, "lower_units": slab.lower_units,
        "upper_units": slab.upper_units, "rate_per_unit": slab.rate_per_unit,
    } for slab in tariffs]


@api.get("/billing/tariffs")
@login_required
def get_tariffs():
    return jsonify(slabs=_tariff_data())


@api.put("/billing/tariffs")
@login_required
def put_tariffs():
    data = _data()
    slabs = data.get("slabs")
    if not isinstance(slabs, list) or not slabs:
        return jsonify(error="validation_error", message="Provide a non-empty slabs array."), 400
    normalized = []
    try:
        for slab in slabs:
            if not isinstance(slab, dict):
                raise ValueError("Each tariff slab must be an object.")
            normalized.append({
                "lower_units": _number(slab, "lower_units"),
                "upper_units": _number(slab, "upper_units", required=False),
                "rate_per_unit": _number(slab, "rate_per_unit"),
            })
        calculate_progressive_bill(0, normalized)
        if normalized[-1]["upper_units"] is not None:
            raise ValueError("The final tariff slab must have no upper_units value.")
        TariffSlab.query.filter_by(user_id=current_user.id).delete()
        for order, slab in enumerate(normalized):
            db.session.add(TariffSlab(user_id=current_user.id, order=order, **slab))
        db.session.commit()
        return jsonify(slabs=_tariff_data())
    except (ValueError, TypeError) as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 400


@api.post("/billing/calculate")
@login_required
def calculate_bill():
    data = _data()
    tariffs = _tariff_data()
    if not tariffs:
        return jsonify(error="tariff_required", message="Configure your own tariff slabs before calculating a bill."), 400
    try:
        units = _number(data, "units")
        fixed = _number(data, "fixed_charges", required=False) or 0
        additional = _number(data, "additional_charges", required=False) or 0
        tax = _number(data, "tax_percent", maximum=100, required=False) or 0
        start = date.fromisoformat(data.get("period_start", date.today().replace(day=1).isoformat()))
        end = date.fromisoformat(data.get("period_end", date.today().isoformat()))
        if end < start:
            raise ValueError("period_end must be on or after period_start.")
        result = calculate_progressive_bill(units, tariffs, fixed, additional, tax)
        record = BillingRecord(
            user_id=current_user.id, period_start=start, period_end=end,
            units=units, fixed_charges=fixed, additional_charges=additional,
            tax_percent=tax, total_amount=result["total_amount"], breakdown_json=result,
        )
        db.session.add(record)
        db.session.commit()
        result.update({
            "id": record.id, "units": units, "period_start": start.isoformat(),
            "period_end": end.isoformat(), "basis": "estimated from user-configured tariff; not a utility bill",
        })
        return jsonify(bill=result), 201
    except (ValueError, TypeError) as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 400


@api.get("/billing/history")
@login_required
def billing_history():
    bills = BillingRecord.query.filter_by(user_id=current_user.id).order_by(BillingRecord.created_at.desc()).limit(100).all()
    return jsonify(bills=[{
        "id": b.id, "period_start": b.period_start.isoformat(), "period_end": b.period_end.isoformat(),
        "units": b.units, "total_amount": b.total_amount, "breakdown": b.breakdown_json,
        "created_at": b.created_at.isoformat(),
    } for b in bills])


@api.get("/limits")
@login_required
def get_limits():
    limits = UsageLimit.query.filter_by(user_id=current_user.id).all()
    return jsonify(limits=[{"period": x.period, "limit_kwh": x.limit_kwh} for x in limits])


@api.put("/limits")
@login_required
def set_limits():
    data = _data()
    items = data.get("limits")
    if not isinstance(items, list):
        return jsonify(error="validation_error", message="Provide limits as an array."), 400
    try:
        normalized = {}
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Each usage limit must be an object.")
            period = item.get("period")
            if period not in ("daily", "weekly", "monthly"):
                raise ValueError("Limit period must be daily, weekly, or monthly.")
            normalized[period] = _number(item, "limit_kwh", minimum=0.001)
        UsageLimit.query.filter_by(user_id=current_user.id).delete()
        for period, limit in normalized.items():
            db.session.add(UsageLimit(user_id=current_user.id, period=period, limit_kwh=limit))
        db.session.commit()
        return get_limits()
    except (ValueError, TypeError) as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 400


@api.get("/alerts")
@login_required
def list_alerts():
    check_usage_limits(current_user.id)
    alerts = Alert.query.filter_by(user_id=current_user.id).order_by(Alert.created_at.desc()).limit(200).all()
    return jsonify(alerts=[{
        "id": a.id, "period": a.period, "threshold": a.threshold, "severity": a.severity,
        "description": a.description, "is_read": a.is_read, "created_at": a.created_at.isoformat(),
    } for a in alerts])


@api.patch("/alerts/<int:alert_id>/read")
@login_required
def mark_alert_read(alert_id):
    alert = Alert.query.filter_by(id=alert_id, user_id=current_user.id).first()
    if not alert:
        return jsonify(error="not_found", message="Alert not found."), 404
    alert.is_read = True
    db.session.commit()
    return jsonify(message="Alert marked as read.")


@api.get("/recommendations")
@login_required
def recommendations():
    appliances = Appliance.query.filter_by(user_id=current_user.id).all()
    tariffs = _tariff_data()
    average_rate = sum(s["rate_per_unit"] for s in tariffs) / len(tariffs) if tariffs else None
    generated = []
    active = [a for a in appliances if a.is_on]
    if active:
        saved = sum(a.daily_energy_kwh * 30 * 0.25 for a in active)
        generated.append({
            "title": "Review appliances marked as running",
            "description": "Check whether these appliances need to stay on; switching off unused equipment can reduce avoidable consumption.",
            "estimated_saving_kwh": round(saved, 2),
        })
    for appliance in appliances:
        monthly = appliance.daily_energy_kwh * 30
        if monthly >= 60:
            generated.append({
                "title": f"Reduce {appliance.name} operating time",
                "description": f"{appliance.name} has an estimated load of {monthly:.1f} kWh per 30 days. Try reducing daily use by one hour and compare the next readings.",
                "estimated_saving_kwh": round(appliance.power_w * appliance.quantity * 30 / 1000, 2),
            })
    if not generated and appliances:
        generated.append({
            "title": "Keep tracking your appliance estimates",
            "description": "Your estimates are currently moderate. Compare them with measured readings to find opportunities.",
            "estimated_saving_kwh": None,
        })
    for item in generated:
        item["estimated_saving_amount"] = (
            round(item["estimated_saving_kwh"] * average_rate, 2)
            if average_rate is not None and item["estimated_saving_kwh"] is not None else None
        )
        item["basis"] = "rule-based estimate from appliance nameplate power and entered usage; not a measured saving"
    return jsonify(recommendations=generated)


def _analytics(period):
    now = utcnow().date()
    if period == "daily":
        start = now - timedelta(days=29)
        bucket_count, step = 30, timedelta(days=1)
        label = lambda d: d.isoformat()
    elif period == "weekly":
        start = now - timedelta(weeks=11)
        start -= timedelta(days=start.weekday())
        bucket_count, step = 12, timedelta(weeks=1)
        label = lambda d: f"Week of {d.isoformat()}"
    elif period == "monthly":
        start = now.replace(day=1)
        for _ in range(11):
            start = (start - timedelta(days=1)).replace(day=1)
        bucket_count, step = 12, None
        label = lambda d: d.strftime("%b %Y")
    else:
        start = now.replace(month=1, day=1)
        start = start.replace(year=start.year - 4)
        bucket_count, step = 5, None
        label = lambda d: str(d.year)
    records = ConsumptionRecord.query.filter(
        ConsumptionRecord.user_id == current_user.id,
        ConsumptionRecord.recorded_at >= datetime.combine(start, datetime.min.time()),
    ).order_by(ConsumptionRecord.recorded_at).all()
    buckets = {}
    for record in records:
        day = record.recorded_at.date()
        if period == "daily":
            key = day
        elif period == "weekly":
            key = day - timedelta(days=day.weekday())
        elif period == "monthly":
            key = day.replace(day=1)
        else:
            key = day.replace(month=1, day=1)
        buckets[key] = buckets.get(key, 0) + record.energy_kwh
    labels = []
    cursor = start
    for _ in range(bucket_count):
        labels.append(cursor)
        if period == "daily":
            cursor += step
        elif period == "weekly":
            cursor += step
        elif period == "monthly":
            cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        else:
            cursor = cursor.replace(year=cursor.year + 1)
    values = [{"period": label(d), "kwh": round(buckets.get(d, 0), 3)} for d in labels]
    actual_values = [value["kwh"] for value in values]
    appliance_rows = Appliance.query.filter_by(user_id=current_user.id).all()
    bills = BillingRecord.query.filter_by(user_id=current_user.id).order_by(BillingRecord.created_at.desc()).limit(12).all()
    bills.reverse()
    bill_comparisons = []
    for index, bill in enumerate(bills):
        previous = bills[index - 1] if index else None
        bill_comparisons.append({
            "period_start": bill.period_start.isoformat(),
            "period_end": bill.period_end.isoformat(),
            "units": bill.units,
            "amount": bill.total_amount,
            "change_percent": round((bill.total_amount - previous.total_amount) / previous.total_amount * 100, 1)
            if previous and previous.total_amount else None,
        })
    highest = max(values, key=lambda x: x["kwh"], default=None)
    lowest = min(values, key=lambda x: x["kwh"], default=None)
    return {
        "period": period, "basis": "aggregated from recorded consumption; zeros mean no records in that period",
        "values": values, "total_kwh": round(sum(actual_values), 3),
        "highest_period": highest, "lowest_period": lowest,
        "bill_comparisons": bill_comparisons,
        "appliances": [{
            "name": a.name, "estimated_monthly_kwh": round(a.daily_energy_kwh * 30, 3),
            "basis": "estimated from rated power and entered operating hours",
        } for a in appliance_rows],
    }


for _period in ("daily", "weekly", "monthly", "yearly"):
    def _handler(period=_period):
        return jsonify(_analytics(period))
    _handler.__name__ = f"analytics_{_period}"
    api.add_url_rule(f"/analytics/{_period}", endpoint=_handler.__name__, view_func=login_required(_handler), methods=["GET"])


@api.get("/analytics/export.csv")
@login_required
def export_csv():
    rows = ConsumptionRecord.query.filter_by(user_id=current_user.id).order_by(ConsumptionRecord.recorded_at).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["recorded_at", "energy_kwh", "power_w", "duration_hours", "source", "appliance"])
    for row in rows:
        writer.writerow([row.recorded_at.isoformat(), row.energy_kwh, row.power_w, row.duration_hours, row.source, row.appliance.name if row.appliance else ""])
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=powerwise-consumption.csv"
    return response


@api.get("/devices")
@login_required
def list_devices():
    devices = Device.query.filter_by(user_id=current_user.id).order_by(Device.created_at.desc()).all()
    return jsonify(devices=[{"id": d.id, "name": d.name, "is_active": d.is_active, "created_at": d.created_at.isoformat()} for d in devices])


@api.post("/devices")
@login_required
def create_device():
    name = str(_data().get("name", "")).strip()
    if not name or len(name) > 100:
        return jsonify(error="validation_error", message="Device name is required and must be at most 100 characters."), 400
    device = Device(user_id=current_user.id, name=name, token_hash="pending")
    db.session.add(device)
    db.session.flush()
    token = f"{device.id}.{secrets.token_urlsafe(32)}"
    device.token_hash = generate_password_hash(token)
    db.session.commit()
    return jsonify(device={"id": device.id, "name": device.name}, device_token=token, notice="Save this token securely; it is shown only once. Hardware is not connected or verified."), 201


@api.delete("/devices/<int:device_id>")
@login_required
def delete_device(device_id):
    device = Device.query.filter_by(id=device_id, user_id=current_user.id).first()
    if not device:
        return jsonify(error="not_found", message="Device not found."), 404
    db.session.delete(device)
    db.session.commit()
    return jsonify(message="Device credential revoked.")


@api.post("/iot/readings")
@csrf.exempt
def ingest_iot_reading():
    authorization = request.headers.get("Authorization", "")
    token = authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else ""
    data = _data()
    if not token:
        return jsonify(error="authentication_required", message="Provide a device bearer token."), 401
    # Device tokens are individually salted hashes; check each active device rather than storing credentials in plaintext.
    try:
        device_id_text, secret = token.split(".", 1)
        device_id = int(device_id_text)
    except (ValueError, AttributeError):
        return jsonify(error="authentication_failed", message="Device token is invalid or inactive."), 401
    device = Device.query.filter_by(id=device_id, is_active=True).first()
    if not device or not check_password_hash(device.token_hash, f"{device.id}.{secret}"):
        return jsonify(error="authentication_failed", message="Device token is invalid or inactive."), 401
    try:
        energy = _number(data, "energy_kwh", minimum=0.000001, maximum=100000)
        power = _number(data, "power_w", minimum=0.001, maximum=1000000, required=False)
        duration = _number(data, "duration_hours", maximum=744, required=False)
        recorded_at = _date(data.get("recorded_at", utcnow().isoformat()), "recorded_at")
        if recorded_at > utcnow() + timedelta(minutes=5):
            raise ValueError("recorded_at cannot be in the future.")
        record = ConsumptionRecord(
            user_id=device.user_id, energy_kwh=energy, power_w=power,
            duration_hours=duration, source="iot", recorded_at=recorded_at,
        )
        db.session.add(record)
        db.session.commit()
        check_usage_limits(device.user_id, recorded_at)
        return jsonify(message="Device reading accepted.", reading_id=record.id, source="iot"), 201
    except (ValueError, TypeError) as error:
        db.session.rollback()
        return jsonify(error="validation_error", message=str(error)), 400
