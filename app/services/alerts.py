from datetime import date, datetime, timedelta

from app.extensions import db
from app.models import Alert, ConsumptionRecord, UsageLimit, utcnow


def check_usage_limits(user_id, now=None):
    now = now or utcnow()
    today = now.date()
    limits = UsageLimit.query.filter_by(user_id=user_id).all()
    created = []
    for limit in limits:
        if limit.period == "daily":
            start = datetime.combine(today, datetime.min.time())
            period_key = today.isoformat()
        elif limit.period == "weekly":
            monday = today - timedelta(days=today.weekday())
            start = datetime.combine(monday, datetime.min.time())
            period_key = monday.isoformat()
        else:
            start = datetime(today.year, today.month, 1)
            period_key = today.strftime("%Y-%m")

        used = sum(
            row.energy_kwh
            for row in ConsumptionRecord.query.filter(
                ConsumptionRecord.user_id == user_id,
                ConsumptionRecord.recorded_at >= start,
                ConsumptionRecord.recorded_at <= now,
            ).all()
        )
        ratio = used / limit.limit_kwh if limit.limit_kwh else 0
        if ratio >= 1.2:
            threshold, severity = "critical", "critical"
        elif ratio >= 1:
            threshold, severity = "high", "high"
        elif ratio >= 0.8:
            threshold, severity = "warning", "warning"
        else:
            continue
        existing = Alert.query.filter_by(
            user_id=user_id, period=limit.period, period_key=period_key, threshold=threshold
        ).first()
        if not existing:
            alert = Alert(
                user_id=user_id,
                period=limit.period,
                period_key=period_key,
                threshold=threshold,
                severity=severity,
                description=f"{limit.period.title()} usage is {used:.2f} kWh of your {limit.limit_kwh:.2f} kWh limit ({ratio:.0%}).",
            )
            db.session.add(alert)
            created.append(alert)
    if created:
        db.session.commit()
    return created
