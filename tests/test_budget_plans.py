from copy import deepcopy
from datetime import date
import unittest
import budget_cover
import budget_plans
from main import validate_data, APIError
from test_budget_cover import household

class PendingBudgetTests(unittest.TestCase):
    def plan(self):
        data = household()
        data['bills'] = [{'id': 'power', 'budgetId': 'power-line', 'monthlyAmounts': {'2026-11': 80}}]
        data['budgets'].append({'id': 'power-line', 'billId': 'power', 'cadence': 'monthly', 'amount': 80, 'billAmounts': {'2026-11': 80}})
        data['pendingBudgets'] = [{'key': '2026-12', 'status': 'pending', 'items': [
            {'id': 'groceries', 'name': 'Groceries', 'category': 'Groceries', 'amount': 150},
            {'id': 'new', 'name': 'Holiday', 'category': 'Gifts', 'amount': 50, 'recurrence': 'one-time'}], 'billAmounts': {'power': 95}}]
        return data

    def test_reserve_survives_rollover_without_affecting_live_values(self):
        data = self.plan()
        validate_data(deepcopy(data))
        self.assertEqual(data['budgets'][1]['amount'], 100)
        budget_cover.archive_months(data, date(2026, 12, 1))
        self.assertEqual(data['budgets'][1]['amount'], 100)
        self.assertEqual(data['bills'][0]['monthlyAmounts'], {'2026-11': 80})
        self.assertEqual(len(data['pendingBudgets']), 1)

    def test_confirmed_activation_preserves_archive_and_history(self):
        data = self.plan()
        budget_cover.archive_months(data, date(2026, 12, 1))
        archive = deepcopy(data['monthlyArchives'])
        data['pendingBudgets'][0]['status'] = 'activate'
        self.assertTrue(budget_cover.archive_months(data, date(2026, 12, 1)))
        self.assertEqual(data['monthlyArchives'], archive)
        self.assertEqual(data['pendingBudgets'], [])
        self.assertEqual(budget_cover.config(data['budgets'][1], '2026-11-15')['amount'], 100)
        self.assertEqual(budget_cover.config(data['budgets'][1], '2026-12-15')['amount'], 150)
        self.assertEqual(data['bills'][0]['monthlyAmounts']['2026-12'], 95)
        self.assertEqual(data['budgets'][2]['billAmounts']['2026-12'], 95)
        new = data['budgets'][-1]
        self.assertEqual(budget_cover.monthly_limit(new, '2026-11'), 0)
        self.assertEqual(budget_cover.monthly_limit(new, '2026-12'), 50)
        self.assertEqual(budget_cover.monthly_limit(new, '2027-01'), 0)
        self.assertFalse(budget_cover.archive_months(data, date(2026, 12, 1)))

    def test_activation_requires_month_arrival_and_archive(self):
        data = self.plan()
        data['pendingBudgets'][0]['status'] = 'activate'
        with self.assertRaises(ValueError):
            budget_plans.activate(data, date(2026, 11, 30))
        with self.assertRaisesRegex(ValueError, 'Archive'):
            budget_plans.activate(data, date(2026, 12, 1))

    def test_invalid_reserve_rejected(self):
        for change in [lambda p: p['items'][0].update(amount=-1), lambda p: p.update(key='2026-13'), lambda p: p.update(billAmounts={'power': '95'}), lambda p: p['items'].append(deepcopy(p['items'][0]))]:
            data = self.plan()
            change(data['pendingBudgets'][0])
            with self.assertRaises(APIError):
                validate_data(data)
