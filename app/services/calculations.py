from datetime import date
import math


def calculate_energy(power_w, hours, quantity=1):
    if any(isinstance(value, bool) for value in (power_w, hours, quantity)):
        raise ValueError("Power, hours, and quantity must be numeric.")
    if not all(math.isfinite(value) for value in (power_w, hours, quantity)) or power_w < 0 or hours < 0 or quantity < 1:
        raise ValueError("Power and hours must be non-negative and quantity must be at least one.")
    return power_w * hours * quantity / 1000


def calculate_progressive_bill(units, slabs, fixed_charges=0, additional_charges=0, tax_percent=0):
    if not all(math.isfinite(value) for value in (units, fixed_charges, additional_charges, tax_percent)):
        raise ValueError("Units, charges, and tax must be finite numbers.")
    if units < 0 or fixed_charges < 0 or additional_charges < 0:
        raise ValueError("Units and charges must be non-negative.")
    if not 0 <= tax_percent <= 100:
        raise ValueError("Tax percent must be between 0 and 100.")
    ordered = sorted(slabs, key=lambda slab: slab["lower_units"])
    if not ordered or ordered[0]["lower_units"] != 0:
        raise ValueError("Configure tariff slabs starting at 0 units.")

    expected_lower = 0.0
    for index, slab in enumerate(ordered):
        lower = slab["lower_units"]
        upper = slab["upper_units"]
        rate = slab["rate_per_unit"]
        if not all(math.isfinite(value) for value in (lower, rate)) or (upper is not None and not math.isfinite(upper)):
            raise ValueError("Tariff values must be finite numbers.")
        if lower != expected_lower or rate < 0:
            raise ValueError("Tariff slabs must be contiguous and rates must be non-negative.")
        if upper is None:
            if index != len(ordered) - 1:
                raise ValueError("Only the final tariff slab may have no upper bound.")
        elif upper <= lower:
            raise ValueError("Each finite tariff slab must have an upper bound above its lower bound.")
        elif index == len(ordered) - 1:
            raise ValueError("The final tariff slab must have no upper bound.")
        if upper is not None:
            expected_lower = upper

    cursor = 0.0
    energy_charge = 0.0
    breakdown = []
    for slab in ordered:
        lower = slab["lower_units"]
        upper = slab["upper_units"]
        slab_end = units if upper is None else min(units, upper)
        slab_units = max(0.0, slab_end - lower)
        charge = slab_units * slab["rate_per_unit"]
        breakdown.append({
            "from_units": lower,
            "to_units": upper,
            "units_charged": round(slab_units, 3),
            "rate_per_unit": slab["rate_per_unit"],
            "charge": round(charge, 2),
        })
        energy_charge += charge
        if upper is None or units <= upper:
            break
        cursor = upper
    else:
        if units > cursor:
            raise ValueError("Tariff slabs do not cover the entered consumption.")

    subtotal = energy_charge + fixed_charges + additional_charges
    tax = subtotal * tax_percent / 100
    return {
        "energy_charge": round(energy_charge, 2),
        "fixed_charges": round(fixed_charges, 2),
        "additional_charges": round(additional_charges, 2),
        "tax_percent": tax_percent,
        "tax_amount": round(tax, 2),
        "total_amount": round(subtotal + tax, 2),
        "slabs": breakdown,
    }


def period_bounds(period, today=None):
    today = today or date.today()
    if period == "daily":
        return today, today
    if period == "weekly":
        start = date.fromordinal(today.toordinal() - today.weekday())
        return start, today
    if period == "monthly":
        return today.replace(day=1), today
    raise ValueError("Period must be daily, weekly, or monthly.")
