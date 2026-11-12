-- Demo data for an account already created through POWERWISE.
-- Replace this email with the account email you registered, then run in MySQL.
SET @user_id = (SELECT id FROM users WHERE email = 'you@example.com');

INSERT INTO appliances (user_id, name, category, power_w, daily_hours, quantity, is_on)
SELECT @user_id, 'Ceiling fan', 'Cooling', 75, 8, 2, TRUE
WHERE @user_id IS NOT NULL;

INSERT INTO appliances (user_id, name, category, power_w, daily_hours, quantity, is_on)
SELECT @user_id, 'LED lighting', 'Lighting', 12, 6, 5, FALSE
WHERE @user_id IS NOT NULL;

INSERT INTO consumption_records (user_id, energy_kwh, power_w, duration_hours, source, recorded_at)
SELECT @user_id, 1.2, 300, 4, 'manual', DATE_SUB(UTC_TIMESTAMP(), INTERVAL 1 DAY)
WHERE @user_id IS NOT NULL;

INSERT INTO usage_limits (user_id, period, limit_kwh)
SELECT @user_id, 'monthly', 180
WHERE @user_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM usage_limits WHERE user_id = @user_id AND period = 'monthly');

-- These are editable example rates, not a recommended or universal electricity tariff.
INSERT INTO tariff_slabs (user_id, lower_units, upper_units, rate_per_unit, `order`)
SELECT @user_id, 0, 100, 4.00, 0
WHERE @user_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM tariff_slabs WHERE user_id = @user_id);
INSERT INTO tariff_slabs (user_id, lower_units, upper_units, rate_per_unit, `order`)
SELECT @user_id, 100, NULL, 7.50, 1
WHERE @user_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM tariff_slabs WHERE user_id = @user_id AND `order` = 1);
