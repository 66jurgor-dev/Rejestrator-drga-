import unittest

from trasy_app import calculate_active_calories


class CalorieTests(unittest.TestCase):
    def test_matches_recorder_formula_for_83kg(self):
        # HR 120 bpm for 60 minutes, with recorder constants:
        # resting HR 65, max HR 172 and VO2max 35.
        self.assertEqual(calculate_active_calories(120.0, 3600, 83.0), 403)

    def test_below_resting_rate_has_no_active_calories(self):
        self.assertEqual(calculate_active_calories(60.0, 3600, 83.0), 0)


if __name__ == "__main__":
    unittest.main()
