import unittest

from app.services.calculations import calculate_energy, calculate_progressive_bill


class EnergyCalculationTests(unittest.TestCase):
    def test_energy_from_power_and_time(self):
        self.assertAlmostEqual(calculate_energy(1200, 2.5), 3.0)

    def test_appliance_energy_includes_quantity(self):
        self.assertAlmostEqual(calculate_energy(10, 5, 4), 0.2)

    def test_energy_rejects_negative_inputs(self):
        with self.assertRaises(ValueError):
            calculate_energy(-1, 2)

    def test_energy_rejects_non_finite_inputs(self):
        with self.assertRaises(ValueError):
            calculate_energy(float("nan"), 2)

    def test_progressive_tariff_applies_each_rate_to_its_band(self):
        slabs = [
            {"lower_units": 0, "upper_units": 100, "rate_per_unit": 2},
            {"lower_units": 100, "upper_units": None, "rate_per_unit": 5},
        ]
        result = calculate_progressive_bill(150, slabs, fixed_charges=10, additional_charges=5, tax_percent=10)
        self.assertEqual(result["energy_charge"], 450)
        self.assertEqual(result["tax_amount"], 46.5)
        self.assertEqual(result["total_amount"], 511.5)

    def test_progressive_tariff_rejects_gaps(self):
        with self.assertRaisesRegex(ValueError, "contiguous"):
            calculate_progressive_bill(150, [
                {"lower_units": 0, "upper_units": 100, "rate_per_unit": 2},
                {"lower_units": 101, "upper_units": None, "rate_per_unit": 5},
            ])

    def test_progressive_tariff_validates_all_slabs_even_when_usage_is_low(self):
        with self.assertRaisesRegex(ValueError, "contiguous"):
            calculate_progressive_bill(10, [
                {"lower_units": 0, "upper_units": 100, "rate_per_unit": 2},
                {"lower_units": 101, "upper_units": None, "rate_per_unit": 5},
            ])


if __name__ == "__main__":
    unittest.main()
