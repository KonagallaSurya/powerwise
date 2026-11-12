import unittest

from app import create_app
from app.extensions import db


class AuthAndIsolationTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-key-not-for-production",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "WTF_CSRF_ENABLED": False,
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def register(self, email):
        return self.client.post("/api/auth/register", json={
            "name": email.split("@")[0],
            "email": email,
            "password": "secure-password-123",
        })

    def test_registration_hashes_password_and_authenticates(self):
        response = self.register("first@example.com")
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("password", response.get_json()["user"])
        self.assertEqual(self.client.get("/api/appliances").status_code, 200)

    def test_protected_resource_requires_authentication(self):
        response = self.client.get("/api/appliances")
        self.assertEqual(response.status_code, 401)

    def test_unknown_api_route_returns_json_404(self):
        response = self.client.get("/api/unknown")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "not_found")

    def test_static_assets_serve_from_vercel_public_directory(self):
        css = self.client.get("/static/css/style.css")
        javascript = self.client.get("/static/js/dashboard.js")
        self.assertEqual(css.status_code, 200)
        self.assertIn(b"--bg:#0b1220", css.data)
        self.assertEqual(javascript.status_code, 200)
        css.close()
        javascript.close()

    def test_user_cannot_access_another_users_appliance(self):
        self.register("first@example.com")
        created = self.client.post("/api/appliances", json={
            "name": "Fan", "category": "Cooling", "power_w": 70,
            "daily_hours": 6, "quantity": 1,
        })
        appliance_id = created.get_json()["appliance"]["id"]
        self.client.post("/api/auth/logout", json={})
        self.register("second@example.com")
        response = self.client.put(f"/api/appliances/{appliance_id}", json={"name": "Changed"})
        self.assertEqual(response.status_code, 404)

    def test_bill_calculation_uses_configured_progressive_slabs(self):
        self.register("billing@example.com")
        tariffs = self.client.put("/api/billing/tariffs", json={"slabs": [
            {"lower_units": 0, "upper_units": 100, "rate_per_unit": 2},
            {"lower_units": 100, "upper_units": None, "rate_per_unit": 5},
        ]})
        self.assertEqual(tariffs.status_code, 200)
        response = self.client.post("/api/billing/calculate", json={
            "units": 150, "fixed_charges": 10, "additional_charges": 0, "tax_percent": 0,
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["bill"]["total_amount"], 460)

    def test_limit_alert_is_created_once_per_threshold_event(self):
        self.register("alerts@example.com")
        self.client.put("/api/limits", json={"limits": [{"period": "monthly", "limit_kwh": 0.5}]})
        response = self.client.post("/api/consumption", json={"energy_kwh": 0.45})
        self.assertEqual(response.status_code, 201)
        first = self.client.get("/api/alerts").get_json()["alerts"]
        second = self.client.get("/api/alerts").get_json()["alerts"]
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(first[0]["severity"], "warning")

    def test_iot_reading_requires_a_device_token_and_records_iot_source(self):
        self.register("device@example.com")
        created = self.client.post("/api/devices", json={"name": "Demo ESP32"})
        token = created.get_json()["device_token"]
        response = self.client.post("/api/iot/readings", json={"energy_kwh": 0.25}, headers={
            "Authorization": f"Bearer {token}",
        })
        self.assertEqual(response.status_code, 201)
        readings = self.client.get("/api/consumption").get_json()["readings"]
        self.assertEqual(readings[0]["source"], "iot")
        self.assertEqual(self.client.delete(f"/api/devices/{created.get_json()['device']['id']}").status_code, 200)
        revoked = self.client.post("/api/iot/readings", json={"energy_kwh": 0.1}, headers={
            "Authorization": f"Bearer {token}",
        })
        self.assertEqual(revoked.status_code, 401)


if __name__ == "__main__":
    unittest.main()
