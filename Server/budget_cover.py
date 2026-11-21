"""Budget-only overage coverage and immutable month-end slush snapshots."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import re


def cents(value):
    return int((Decimal(str(value or 0)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def config(line, day):
    if line.get('billId'):
        return {'cadence': 'monthly', 'amount': line.get('billAmounts', {}).get(day[:7], 0)}
    history = sorted(line.get('history') or [dict(line, **{'from': day[:4] + '-01-01'})], key=lambda entry: entry['from'])
    eligible = [entry for entry in history if entry['from'] <= day]
    chosen = eligible[-1] if eligible else history[0]
    result = dict(line)
    result.update(chosen)
    result['recurrence'] = chosen.get('recurrence', 'recurring')
    return result


def period(configuration, day):
    if configuration.get('recurrence') == 'one-time':
        return 'once-' + configuration.get('budgetDate', '')
    if configuration['cadence'] == 'annual':
        return day[:4]
    if configuration['cadence'] == 'weekly':
        value = date.fromisoformat(day)
        return (value - timedelta(days=(value.weekday() + 1) % 7)).isoformat()
    return day[:7]


def charges(data):
    lines = {line['id']: line for line in data['budgets']}
    result = list(data['transactions'])
    for purchase in data['transactions']:
        for cover in purchase.get('budgetCovers', []):
            line = lines.get(cover['budgetId'], {})
            result.append({'id': 'cover-' + cover['id'], 'date': cover['date'], 'amount': cover['amount'],
                           'budgetId': cover['budgetId'], 'category': line.get('category', 'Uncategorized'),
                           'kind': 'budget-cover', 'purchaseId': purchase['id'], 'coverId': cover['id'],
                           'targetChargeId': cover.get('targetChargeId', purchase['id']),
                           'title': 'Budget cover · ' + purchase.get('title', 'Purchase')})
    return sorted(result, key=lambda entry: entry['date'])


def net_charges(data):
    entries = charges(data)
    targets = {entry['id']: entry for entry in entries}
    credits = []
    for entry in entries:
        if entry.get('kind') == 'budget-cover':
            target = targets.get(entry['targetChargeId'], {})
            if target.get('budgetId'):
                credits.append(dict(entry, id='credit-' + entry['coverId'], amount=-entry['amount'], budgetId=target['budgetId']))
    return entries + credits


def unpaid_calendar_budget(data, line, today):
    bill = next((bill for bill in data.get('bills', []) if bill.get('id') == line.get('billId') or bill.get('budgetId') == line['id']), None)
    if not line.get('billId') and not bill:
        return False
    month = today.strftime('%Y-%m')
    return not bill or bill.get('active') is False or not any(day.startswith(month) and paid for day, paid in bill.get('paid', {}).items())


def eligible_source(data, line, today):
    if unpaid_calendar_budget(data, line, today):
        return False
    first = min((entry['from'] for entry in line.get('history', [])), default=today.isoformat())
    configuration = config(line, today.isoformat())
    scheduled = configuration.get('budgetDate', '')
    if first > today.isoformat():
        return False
    return configuration.get('recurrence') != 'one-time' or (scheduled <= today.isoformat() and (scheduled[:7] == today.strftime('%Y-%m') if configuration['cadence'] == 'monthly' else scheduled[:4] == str(today.year)))


def coverage(data):
    lines = {line['id']: line for line in data['budgets']}
    frozen = {entry['id']: entry for archive in data.get('monthlyArchives', []) for entry in archive.get('slushEntries', [])}
    target_covers = {}
    for purchase in data['transactions']:
        for cover in purchase.get('budgetCovers', []):
            target = cover.get('targetChargeId', purchase['id'])
            target_covers[target] = target_covers.get(target, 0) + cents(cover['amount'])
    running, result = {}, []
    for entry in charges(data):
        line = lines.get(entry.get('budgetId'))
        allocation, over = 0, cents(entry['amount'])
        if line:
            configuration = config(line, entry['date'])
            allocation = cents(configuration['amount'])
            key = (line['id'], period(configuration, entry['date']))
            previous = running.get(key, 0)
            current = previous + cents(entry['amount'])
            running[key] = current
            over = max(0, current - allocation) - max(0, previous - allocation)
        transfer = entry.get('fundsTransfer', {})
        if not line and transfer.get('source') == 'covered' and transfer.get('amount') == entry['amount'] and transfer.get('budgetId') == entry.get('budgetId') and transfer.get('purchaseDate') == entry['date']:
            over = 0
        raw = over
        covered = target_covers.get(entry['id'], 0)
        calculated = dict(entry, rawOver=raw / 100, coveredAmount=covered / 100, over=max(0, over - covered) / 100, limit=allocation / 100)
        result.append(deepcopy(frozen.get(entry['id'], calculated)))
    return result


def available(data, budget_id, today):
    line = next(line for line in data['budgets'] if line['id'] == budget_id)
    configuration = config(line, today.isoformat())
    key = period(configuration, today.isoformat())
    allocation = cents(configuration['amount'])
    first = min((entry['from'] for entry in line.get('history', [])), default=today.isoformat())
    scheduled = configuration.get('budgetDate', '')
    if first > today.isoformat() or (configuration.get('recurrence') == 'one-time' and (scheduled > today.isoformat() or (configuration['cadence'] == 'monthly' and scheduled[:7] != today.strftime('%Y-%m')) or (configuration['cadence'] == 'annual' and scheduled[:4] != str(today.year)))):
        allocation = 0
    spent = sum(cents(entry['amount']) for entry in net_charges(data) if entry.get('budgetId') == budget_id
                and entry['date'] <= today.isoformat() and period(config(line, entry['date']), entry['date']) == key)
    return allocation - spent


def validate_changes(previous, current, today=None):
    today = today or date.today()
    month = today.strftime('%Y-%m')
    if not current['budgets'] and not current['transactions'] and not current['incomes']:
        return  # The existing explicit clear-financial-records action remains available.
    prior_archives = {archive['key']: archive for archive in previous.get('monthlyArchives', []) if 'slushEntries' in archive}
    incoming_archives = {archive['key']: archive for archive in current.get('monthlyArchives', [])}
    for key, archive in prior_archives.items():
        if incoming_archives.get(key) != archive:
            raise ValueError('Archived budgets and permanent slush coverage cannot be changed.')
    old = {purchase['id']: purchase for purchase in previous['transactions']}
    new = {purchase['id']: purchase for purchase in current['transactions']}
    financial = ('date', 'amount', 'budgetId', 'category', 'billId', 'billDueDate')
    for identifier, purchase in old.items():
        changed = identifier not in new or any(purchase.get(key) != new[identifier].get(key) for key in financial)
        if purchase['date'][:7] in prior_archives and (changed or purchase.get('budgetCovers', []) != new.get(identifier, {}).get('budgetCovers', [])):
            raise ValueError('This purchase belongs to an archived budget. Its financial details are locked.')
        if changed and purchase.get('budgetCovers'):
            raise ValueError('Undo budget covers before changing or deleting the covered purchase.')
    for identifier, purchase in new.items():
        if identifier not in old and purchase['date'][:7] in prior_archives:
            raise ValueError('New purchases cannot be added to an archived budget month.')
    ids = set()
    new_targets = set()
    for purchase in current['transactions']:
        covers = purchase.get('budgetCovers', [])
        if not isinstance(covers, list):
            raise ValueError('Invalid budget cover list.')
        prior = {cover['id']: cover for cover in old.get(purchase['id'], {}).get('budgetCovers', [])}
        incoming = {}
        for cover in covers:
            if not isinstance(cover, dict) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', str(cover.get('id', ''))):
                raise ValueError('Budget covers require a valid unique ID.')
            if cover['id'] in ids:
                raise ValueError('Budget cover IDs must be unique.')
            ids.add(cover['id'])
            incoming[cover['id']] = cover
            try:
                cover_day = date.fromisoformat(cover['date'])
                amount = Decimal(str(cover['amount']))
                valid_amount = amount.is_finite() and 0 < amount <= Decimal('1e12') and amount * 100 == (amount * 100).to_integral_value()
            except (KeyError, ValueError, TypeError, ArithmeticError):
                raise ValueError('Use a valid budget cover date and amount.')
            if not valid_amount or cover_day.isoformat() != cover['date']:
                raise ValueError('Budget cover amounts must be positive whole cents.')
            if cover['id'] in prior:
                if prior[cover['id']] != cover:
                    raise ValueError('Undo an existing budget cover before replacing it.')
                continue
            new_targets.add(cover.get('targetChargeId', purchase['id']))
            if cover['date'][:7] != month or purchase['date'][:7] != month or cover_day > today or purchase['date'] > today.isoformat():
                raise ValueError('Only current-month purchases can receive budget coverage.')
            line = next((line for line in current['budgets'] if line['id'] == cover.get('budgetId') and line.get('active') is not False), None)
            if not line or not eligible_source(current, line, today):
                raise ValueError('Choose an active budget item. Unpaid calendar bills cannot cover other purchases.')
        if set(prior) - set(incoming) and any(cover['date'][:7] != month for cover in prior.values()):
            raise ValueError('Budget covers in archived months cannot be undone.')
    all_charges = {entry['id']: entry for entry in charges(current)}
    for purchase in current['transactions']:
        for cover in purchase.get('budgetCovers', []):
            target_id = cover.get('targetChargeId', purchase['id'])
            target = all_charges.get(target_id)
            if not target or target.get('purchaseId', target['id']) != purchase['id'] or target.get('budgetId') == cover['budgetId']:
                raise ValueError('Choose a different budget item and a valid covered charge.')
            visited = {'cover-' + cover['id']}
            while target.get('kind') == 'budget-cover':
                if target['id'] in visited:
                    raise ValueError('Budget covers cannot form a circular reference.')
                visited.add(target['id'])
                target = all_charges.get(target['targetChargeId'])
                if not target:
                    raise ValueError('Undo covers that depend on this cover first.')
    calculated = coverage(current)
    for entry in calculated:
        if entry['id'] in new_targets and cents(entry.get('coveredAmount', 0)) > cents(entry.get('rawOver', 0)):
            raise ValueError('The new budget cover exceeds the uncovered overage. Choose a smaller amount.')


def monthly_limit(line, month):
    first = month + '-01'
    configuration = config(line, first)
    if configuration.get('recurrence') == 'one-time':
        dates = {entry.get('budgetDate') for entry in line.get('history', [line]) if entry.get('recurrence') == 'one-time'}
        return sum(cents(config(line, day)['amount']) for day in dates if day and day.startswith(month) and config(line, day).get('cadence') != 'annual') / 100
    if configuration['cadence'] == 'annual':
        return 0
    if configuration['cadence'] == 'monthly':
        return configuration['amount']
    # Retain historical weekly allocations in older budget snapshots.
    day = date.fromisoformat(first)
    total = cents(configuration['amount'])
    day += timedelta(days=1)
    while day.strftime('%Y-%m') == month:
        if day.weekday() == 6:
            total += cents(config(line, day.isoformat())['amount'])
        day += timedelta(days=1)
    return total / 100


def archive_months(data, today=None):
    today = today or date.today()
    current = today.strftime('%Y-%m')
    archives = data.setdefault('monthlyArchives', [])
    existing = {archive['key']: archive for archive in archives}
    months = {purchase['date'][:7] for purchase in data['transactions'] if purchase['date'][:7] < current}
    months.update(archive['key'] for archive in archives if archive['key'] < current)
    active = data.get('activeBudgetMonth', current)
    if active < current:
        cursor = date.fromisoformat(active + '-01')
        while cursor.strftime('%Y-%m') < current:
            months.add(cursor.strftime('%Y-%m'))
            cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    missing = sorted(month for month in months if 'slushEntries' not in existing.get(month, {}))
    if not missing and active >= current:
        return False
    calculated = coverage(data)
    all_charges = net_charges(data)
    for month in missing:
        transactions = [deepcopy(entry) for entry in data['transactions'] if entry['date'].startswith(month)]
        incomes = [deepcopy(entry) for entry in data['incomes'] if entry['date'].startswith(month)]
        rows = []
        for line in data['budgets']:
            if line.get('active') is False:
                continue
            rows.append({key: line.get(key) for key in ('id', 'name', 'category', 'group', 'cadence')} | {
                'limit': monthly_limit(line, month),
                'actual': sum(cents(entry['amount']) for entry in all_charges if entry.get('budgetId') == line['id'] and entry['date'].startswith(month)) / 100})
        archive = existing.get(month)
        if archive is None:
            archive = {'key': month, 'label': date.fromisoformat(month + '-01').strftime('%B %Y'),
                       'archivedAt': today.isoformat(), 'budgets': rows, 'transactions': transactions,
                       'incomes': incomes, 'bills': deepcopy(data.get('bills', [])),
                       'budgetTotal': sum(cents(row['limit']) for row in rows) / 100,
                       'actualTotal': sum(cents(entry['amount']) for entry in transactions) / 100,
                       'incomeTotal': sum(cents(entry['amount']) for entry in incomes) / 100}
            archives.append(archive)
        archive['slushEntries'] = [dict(entry, permanent=True) for entry in calculated if entry['date'].startswith(month)]
        archive['permanentSlush'] = sum(cents(entry['over']) for entry in archive['slushEntries']) / 100
    if active < current:
        data['activeBudgetMonth'] = current
        data.pop('rolloverPromptedFor', None)
    return True
