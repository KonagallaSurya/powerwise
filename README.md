# POWERWISE

POWERWISE is a Flask application for recording electricity consumption, estimating appliance use and bills, monitoring user-defined limits, and preparing for authenticated IoT data ingestion. It distinguishes user-entered and device-ingested readings from simulations and appliance estimates. It does not claim to be connected to a physical meter.

## Features

- Account registration, login/logout, password hashing, protected sessions, CSRF protection, and per-user data isolation.
- Responsive dashboard with current-month recorded consumption, optional current power, configured-limit remaining, tariff-based bill estimate, recent readings, and daily/monthly charts.
- Create, edit, filter, and delete consumption records. Energy can be entered directly or calculated as `power_w × duration_hours / 1000`.
- User-managed appliance estimates: daily energy is `power_w × hours × quantity / 1000`; monthly estimate uses 30 days.
- User-configurable progressive tariff slabs, fixed/additional charges, taxes, bill history, and slab breakdowns.
- Daily/weekly/monthly usage limits and de-duplicated 80%, 100%, and 120% threshold alerts.
- Rule-based energy recommendations with clearly labelled indicative savings.
- Daily, weekly, monthly, and yearly rollups; consumption CSV export.
- One-time device-token creation and a separate authenticated IoT ingestion endpoint. ESP32/sensor hardware is not connected or verified.
- MySQL schema, example data, and focused unit/API tests.

Forecasting is not implemented. POWERWISE does not label a simple extrapolation as an AI or machine-learning prediction.

## Architecture

```text
Browser (Bootstrap 5, vanilla JS, Chart.js)
        | same-origin JSON requests + Flask-WTF CSRF header
Flask application factory
  ├── auth blueprint (/api/auth)
  ├── API blueprint (/api)
  ├── web blueprint (HTML routes)
  ├── services (energy/bill calculations and alert rules)
  └── SQLAlchemy models
        |
      MySQL
```

`app/__init__.py` configures extensions and blueprints; `app/models/` defines persisted entities; `app/routes/` contains web/auth/API handlers; `app/services/` contains calculations; `app/templates/` and `app/static/` provide the interface. All application queries for account-owned resources are scoped by the signed-in user. IoT tokens are stored as salted password hashes and the raw token is displayed only once.

## Requirements and setup (Windows / VS Code)

1. Install Python 3.10+ and MySQL 8+, and ensure the MySQL service is running.
2. Create a database and least-privilege application user (or run `database/schema.sql` in MySQL Workbench / the MySQL client):

   ```sql
   CREATE DATABASE powerwise CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'powerwise'@'localhost' IDENTIFIED BY 'choose-a-strong-password';
   GRANT ALL PRIVILEGES ON powerwise.* TO 'powerwise'@'localhost';
   ```

3. Open the project folder in VS Code. In its PowerShell terminal:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   Copy-Item .env.example .env
   ```

4. Edit `.env` and set a random `SECRET_KEY` and the MySQL `DATABASE_URL`, for example:

   ```text
   SECRET_KEY=paste-a-long-random-secret-here
   DATABASE_URL=mysql+pymysql://powerwise:choose-a-strong-password@localhost:3306/powerwise?charset=utf8mb4
   FLASK_DEBUG=0
   SESSION_COOKIE_SECURE=0
   ```

   Keep `.env` private and out of source control. Set `SESSION_COOKIE_SECURE=1` when serving over HTTPS. The application does not create database tables implicitly; initialize MySQL with `database/schema.sql` before startup.

5. Start the server:

   ```powershell
   python run.py
   ```

6. Open `http://127.0.0.1:5000`, create an account, and configure your own tariff and usage limits. `/health` checks database connectivity.

For a quick isolated test run, the tests use an in-memory SQLite database and do not require MySQL:

```powershell
python -m unittest discover -v
```

## Database and sample data

`database/schema.sql` defines the required nine tables with foreign keys, indexes, timestamps, uniqueness constraints, and user ownership. Run `database/sample_data.sql` only after creating an account; replace `you@example.com` with the account email. The included sample tariff is explicitly an editable demonstration and is not a universal or recommended electricity tariff.

## API reference

All session-authenticated endpoints require a logged-in user. Mutating browser/API requests need the Flask-WTF CSRF token supplied in the HTML `<meta name="csrf-token">` value as `X-CSRFToken`. JSON validation errors use HTTP 400, unauthenticated requests use 401, missing owned records use 404, and duplicate registration uses 409.

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/auth/register` | Register and sign in; JSON `name`, `email`, `password` (10+ characters) |
| POST | `/api/auth/login` | Sign in; JSON `email`, `password` |
| POST | `/api/auth/logout` | End session |
| GET | `/api/dashboard/summary` | Dashboard metrics and chart series |
| GET | `/api/dashboard/consumption` | Dashboard consumption summary alias |
| GET/POST | `/api/appliances` | List / create owned appliances |
| PUT/DELETE | `/api/appliances/<id>` | Update / delete an owned appliance |
| GET/POST | `/api/consumption` | List (optional ISO `start`, `end`) / add reading |
| PUT/DELETE | `/api/consumption/<id>` | Update / delete an owned reading |
| POST | `/api/consumption/simulate` | Add user-parameterized record labelled `simulated` |
| GET/PUT | `/api/billing/tariffs` | Read / replace the user's contiguous tariff slabs |
| POST | `/api/billing/calculate` | Calculate and save a progressive bill estimate |
| GET | `/api/billing/history` | List bill estimates |
| GET/PUT | `/api/limits` | List / set daily, weekly, monthly kWh limits |
| GET | `/api/alerts` | List alert history and evaluate current thresholds |
| PATCH | `/api/alerts/<id>/read` | Mark an owned alert read |
| GET | `/api/recommendations` | Get appliance-driven rule-based advice |
| GET | `/api/analytics/daily` | Last 30 daily buckets |
| GET | `/api/analytics/weekly` | Last 12 weekly buckets |
| GET | `/api/analytics/monthly` | Last 12 monthly buckets |
| GET | `/api/analytics/yearly` | Last 5 yearly buckets |
| GET | `/api/analytics/export.csv` | Download recorded consumption CSV |
| GET/POST | `/api/devices` | List devices / create one-time bearer token |
| DELETE | `/api/devices/<id>` | Revoke an owned device credential |
| POST | `/api/iot/readings` | Device-authenticated reading ingestion (CSRF-exempt; token required) |
| GET | `/health` | Database connectivity status |

### IoT ingestion contract

Create a device under **Limits & devices**, then save the token securely; it is not recoverable from the app. A future client sends:

```http
POST /api/iot/readings
Authorization: Bearer <device-id>.<one-time-secret>
Content-Type: application/json

{"energy_kwh": 0.42, "power_w": 210, "duration_hours": 2, "recorded_at": "2026-01-15T10:30:00Z"}
```

Ingestion validates the credential, numeric bounds, and timestamp and labels accepted records `iot`. Use TLS for deployment. No MQTT broker, ESP32 firmware, sensor calibration, or live electrical hardware is supplied.

## Testing and demonstration

Run `python -m unittest discover -v`. The suite covers energy and progressive tariff calculations, malformed tariff bands, authentication, protected endpoints, and cross-user appliance access.

Suggested demonstration:

1. Register two accounts and show that their data is isolated.
2. Add appliances and show the distinction between estimated appliance load and actual recorded readings.
3. Add a manual reading, then a clearly labelled simulation; compare dashboard totals and charts.
4. Configure a tariff that matches your provider and calculate a bill with optional charges/tax.
5. Set a low monthly limit, add readings crossing a threshold, and demonstrate alert history/read state.
6. Open analytics, change the reporting period, and download the consumption CSV.
7. Create a future device token and explain the authenticated ingestion contract without claiming physical integration.

## Production notes and limitations

- Configure production secrets, HTTPS, a narrowly privileged MySQL account, backups, and appropriate network controls before deployment.
- Dashboard averages and bills are estimates from records to date; bill estimates exclude fixed charges and taxes unless a separate bill is calculated with those inputs.
- Appliance estimates use user-entered nameplate power and operating hours. Recommendations are rule-based and savings are indicative.
- Forecasting, live current/voltage, utility tariff discovery, email/SMS delivery, and verified hardware integration are not implemented.
