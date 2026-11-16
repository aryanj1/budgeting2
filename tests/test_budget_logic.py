import unittest
from datetime import date
from decimal import Decimal
from budget_logic import format_inr, summarize, weekly_withdrawals, filter_entries


class BudgetLogicTest(unittest.TestCase):
    def test_indian_currency_format(self):
        self.assertEqual(format_inr(340000), "₹3,40,000")
        self.assertEqual(format_inr(20000), "₹20,000")
        self.assertEqual(format_inr(-1234567.25), "-₹12,34,567.25")

    def test_opening_used_without_fictitious_transactions(self):
        result = summarize(340000, 20000, [])
        self.assertEqual(result["remaining"], Decimal("320000.00"))
        self.assertEqual(result["logged_used"], Decimal("0.00"))

    def test_new_transactions_count_once(self):
        entries = [{"used_on": "2026-11-16", "purpose": "Books", "amount": "1500.00"}]
        result = summarize(340000, 20000, entries)
        self.assertEqual(result["used"], Decimal("21500.00"))
        self.assertEqual(result["remaining"], Decimal("318500.00"))

    def test_weekly_grouping_and_filters(self):
        entries = [
            {"used_on": "2026-11-10", "purpose": "Groceries", "amount": "1000.00"},
            {"used_on": "2026-11-12", "purpose": "Taxi", "amount": "500.00"},
            {"used_on": "2026-11-16", "purpose": "Books", "amount": "200.00"},
        ]
        weekly = weekly_withdrawals(entries, today=date(2026, 11, 16), weeks=2)
        self.assertEqual([row["amount"] for row in weekly], [Decimal("1500.00"), Decimal("200.00")])
        self.assertEqual(len(filter_entries(entries, "Last 30 days", "book", today=date(2026, 11, 16))), 1)


if __name__ == "__main__":
    unittest.main()
