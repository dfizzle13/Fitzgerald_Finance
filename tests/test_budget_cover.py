from copy import deepcopy
from datetime import date
from pathlib import Path
import json
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Server'))
import budget_cover
from main import FinanceHTTPServer
from test_server import Client, PASSWORD


def household(today=date(2026, 11, 15)):
    day = today.isoformat()
    return {'budgets': [
        {'id': 'birthday', 'name': 'Birthday', 'category': 'Gifts', 'cadence': 'annual', 'amount': 20},
        {'id': 'groceries', 'name': 'Groceries', 'category': 'Groceries', 'cadence': 'monthly', 'amount': 100}],
        'transactions': [
            {'id': 'gift', 'title': 'Birthday gift', 'date': day, 'amount': 20.28, 'budgetId': 'birthday', 'category': 'Gifts'},
            {'id': 'food', 'title': 'Food', 'date': day, 'amount': 10, 'budgetId': 'groceries', 'category': 'Groceries'}],
        'incomes': [], 'bills': [], 'categories': [], 'monthlyArchives': [], 'activeBudgetMonth': day[:7]}


def add_cover(data, identifier='allocation', amount=0.28):
    data['transactions'][0].setdefault('budgetCovers', []).append(
        {'id': identifier, 'date': data['transactions'][0]['date'], 'amount': amount, 'budgetId': 'groceries'})


class BudgetCoverAccountingTests(unittest.TestCase):
    def test_twenty_eight_cents_and_partial_coverage(self):
        before = household()
        after = deepcopy(before)
        add_cover(after, amount=0.10)
        budget_cover.validate_changes(before, after, date(2026, 11, 15))
        self.assertEqual(budget_cover.coverage(after)[0]['over'], 0.18)
        add_cover(after, 'remaining', 0.18)
        budget_cover.validate_changes(before, after, date(2026, 11, 15))
        self.assertEqual(budget_cover.coverage(after)[0]['over'], 0)
        self.assertEqual(budget_cover.available(after, 'groceries', date(2026, 11, 15)), 8972)
        self.assertEqual(sum(budget_cover.cents(entry['amount']) for entry in after['transactions']), 3028)

    def test_overcover_rejected_and_donor_overdraft_becomes_slush(self):
        before = household()
        after = deepcopy(before)
        add_cover(after, amount=0.29)
        with self.assertRaisesRegex(ValueError, 'exceed'):
            budget_cover.validate_changes(before, after, date(2026, 11, 15))
        before['transactions'][1]['amount'] = 99.80
        before['transactions'] += [{'id': 'other', 'date': '2026-11-15', 'title': 'Other', 'amount': 0.20}]
        first = deepcopy(before)
        add_cover(first, amount=0.15)
        budget_cover.validate_changes(before, first, date(2026, 11, 15))
        merged = deepcopy(first)
        merged['transactions'][2]['budgetCovers'] = [{'id': 'second', 'date': '2026-11-15', 'amount': 0.15, 'budgetId': 'groceries'}]
        budget_cover.validate_changes(first, merged, date(2026, 11, 15))
        self.assertEqual(sum(budget_cover.cents(entry['over']) for entry in budget_cover.coverage(merged)), 28)

    def test_archive_freezes_remainder_and_records_donor_usage(self):
        data = household()
        add_cover(data, amount=0.10)
        self.assertTrue(budget_cover.archive_months(data, date(2026, 12, 1)))
        archive = data['monthlyArchives'][0]
        self.assertEqual(archive['permanentSlush'], 0.18)
        self.assertEqual(archive['actualTotal'], 30.28)
        self.assertEqual(next(row for row in archive['budgets'] if row['id'] == 'groceries')['actual'], 10.10)
        self.assertEqual(data['activeBudgetMonth'], '2026-12')
        self.assertFalse(budget_cover.archive_months(data, date(2026, 12, 1)))
        changed = deepcopy(data)
        changed['budgets'][0]['amount'] = 500
        budget_cover.validate_changes(data, changed, date(2026, 12, 1))
        self.assertEqual(budget_cover.coverage(changed)[0]['over'], 0.18)
        self.assertEqual(budget_cover.available(data, 'groceries', date(2026, 12, 1)), 10000)
        for mutate in (
            lambda value: value['transactions'][0].update(amount=20),
            lambda value: value['transactions'][0].update(budgetCovers=[]),
            lambda value: value['monthlyArchives'][0].update(permanentSlush=0)):
            invalid = deepcopy(data)
            mutate(invalid)
            with self.assertRaises(ValueError):
                budget_cover.validate_changes(data, invalid, date(2026, 12, 1))

    def test_existing_covers_do_not_block_budget_edits_or_later_saves(self):
        before = household()
        add_cover(before)
        changed = deepcopy(before)
        changed['budgets'][0]['amount'] = 25
        budget_cover.validate_changes(before, changed, date(2026, 11, 15))
        self.assertEqual(changed['transactions'][0]['budgetCovers'], before['transactions'][0]['budgetCovers'])
        later = deepcopy(changed)
        later['transactions'].append({'id': 'later', 'date': '2026-11-15', 'amount': 1, 'budgetId': 'groceries'})
        budget_cover.validate_changes(changed, later, date(2026, 11, 15))
        invalid = deepcopy(later)
        add_cover(invalid, 'extra', 0.01)
        with self.assertRaisesRegex(ValueError, 'new budget cover exceeds'):
            budget_cover.validate_changes(later, invalid, date(2026, 11, 15))

    def test_unpaid_bill_excluded_and_coverage_can_move_to_another_budget(self):
        before = household()
        before['budgets'].append({'id': 'empty', 'name': 'Empty', 'category': 'Fuel', 'cadence': 'monthly', 'amount': 0})
        after = deepcopy(before)
        add_cover(after)
        after['transactions'][0]['budgetCovers'][0]['budgetId'] = 'empty'
        budget_cover.validate_changes(before, after, date(2026, 11, 15))
        self.assertEqual(sum(budget_cover.cents(entry['over']) for entry in budget_cover.coverage(after)), 28)
        moved = deepcopy(after)
        moved['transactions'][0]['budgetCovers'].append({'id': 'move', 'date': '2026-11-15', 'amount': 0.28, 'budgetId': 'groceries', 'targetChargeId': 'cover-allocation'})
        budget_cover.validate_changes(after, moved, date(2026, 11, 15))
        self.assertEqual(sum(budget_cover.cents(entry['over']) for entry in budget_cover.coverage(moved)), 0)
        self.assertEqual(sum(budget_cover.cents(entry['amount']) for entry in budget_cover.net_charges(moved) if entry.get('budgetId') == 'birthday'), 2000)
        self.assertEqual(sum(budget_cover.cents(entry['amount']) for entry in budget_cover.net_charges(moved) if entry.get('budgetId') == 'empty'), 0)
        before['budgets'].append({'id': 'bill-line', 'name': 'Electric', 'billId': 'electric', 'cadence': 'monthly', 'amount': 100, 'billAmounts': {'2026-11': 100}})
        before['bills'] = [{'id': 'electric', 'budgetId': 'bill-line', 'paid': {}}]
        invalid = deepcopy(before)
        add_cover(invalid)
        invalid['transactions'][0]['budgetCovers'][0]['budgetId'] = 'bill-line'
        with self.assertRaisesRegex(ValueError, 'Unpaid calendar bills'):
            budget_cover.validate_changes(before, invalid, date(2026, 11, 15))
        before['bills'][0]['paid'] = {'2026-11-05': True}
        valid = deepcopy(before)
        add_cover(valid)
        valid['transactions'][0]['budgetCovers'][0]['budgetId'] = 'bill-line'
        budget_cover.validate_changes(before, valid, date(2026, 11, 15))

    def test_empty_rollover_and_existing_archive_are_idempotent(self):
        data = household()
        data['transactions'] = []
        self.assertTrue(budget_cover.archive_months(data, date(2027, 1, 1)))
        self.assertEqual([entry['key'] for entry in data['monthlyArchives']], ['2026-11', '2026-12'])
        self.assertTrue(all(entry['permanentSlush'] == 0 for entry in data['monthlyArchives']))
        self.assertFalse(budget_cover.archive_months(data, date(2027, 1, 1)))

    def test_invalid_or_expired_donors_and_historical_cover_rejected(self):
        before = household()
        for field, value in [('amount', 0), ('amount', 0.001), ('date', 'bad'), ('budgetId', 'birthday')]:
            after = deepcopy(before)
            add_cover(after)
            after['transactions'][0]['budgetCovers'][0][field] = value
            with self.assertRaises(ValueError):
                budget_cover.validate_changes(before, after, date(2026, 11, 15))
        after = deepcopy(before)
        add_cover(after)
        with self.assertRaisesRegex(ValueError, 'current-month'):
            budget_cover.validate_changes(before, after, date(2026, 12, 1))
        for start, scheduled in [('2026-10-01', '2026-10-15'), ('2026-12-01', '2026-12-15')]:
            after = deepcopy(before)
            after['budgets'][1].update(recurrence='one-time', budgetDate=scheduled,
                                      history=[{'from': start, 'cadence': 'monthly', 'amount': 100, 'recurrence': 'one-time', 'budgetDate': scheduled}])
            add_cover(after)
            with self.assertRaisesRegex(ValueError, 'active budget'):
                budget_cover.validate_changes(before, after, date(2026, 11, 15))


class BudgetCoverServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = FinanceHTTPServer(('127.0.0.1', 0), Path(self.temp.name) / 'finance.sqlite3')
        self.server.daemon_threads = False
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = Client('http://127.0.0.1:' + str(self.server.server_port))
        self.data = household(date.today())
        self.assertEqual(self.client.call('/api/setup', 'POST', {'username': 'householdAdmin', 'password': PASSWORD, 'data': self.data})[0], 201)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def test_cover_shared_and_stale_or_excess_updates_do_not_replace_data(self):
        current = self.client.call('/api/state')[1]
        changed = deepcopy(current['data'])
        add_cover(changed)
        status, saved = self.client.call('/api/state', 'PUT', {'revision': current['revision'], 'data': changed})
        self.assertEqual(status, 200)
        second = Client(self.client.url)
        self.assertEqual(second.call('/api/login', 'POST', {'username': 'householdAdmin', 'password': PASSWORD})[0], 200)
        self.assertEqual(second.call('/api/state')[1]['data'], changed)
        invalid = deepcopy(changed)
        add_cover(invalid, 'duplicate', 0.01)
        self.assertEqual(self.client.call('/api/state', 'PUT', {'revision': saved['revision'], 'data': invalid})[0], 400)
        self.assertEqual(self.client.call('/api/state', 'PUT', {'revision': current['revision'], 'data': changed})[0], 409)
        self.assertEqual(second.call('/api/state')[1]['data'], changed)

    def test_server_automatically_archives_prior_month(self):
        today = date.today()
        prior = today.replace(day=1) - __import__('datetime').timedelta(days=1)
        changed = deepcopy(self.data)
        changed['activeBudgetMonth'] = prior.strftime('%Y-%m')
        for entry in changed['transactions']:
            entry['date'] = prior.isoformat()
        self.assertEqual(self.client.call('/api/state', 'PUT', {'revision': 1, 'data': changed})[0], 200)
        result = self.client.call('/api/state')[1]
        archive = result['data']['monthlyArchives'][0]
        self.assertEqual(archive['key'], prior.strftime('%Y-%m'))
        self.assertEqual(archive['permanentSlush'], 0.28)
        self.assertEqual(result['data']['activeBudgetMonth'], today.strftime('%Y-%m'))
        frozen = deepcopy(result['data'])
        frozen['monthlyArchives'][0]['permanentSlush'] = 0
        self.assertEqual(self.client.call('/api/state', 'PUT', {'revision': result['revision'], 'data': frozen})[0], 400)
        self.assertEqual(self.client.call('/api/state')[1], result)
