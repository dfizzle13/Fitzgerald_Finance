"""Reserved monthly budgets, applied only after explicit month-start approval."""
from copy import deepcopy
from datetime import date, timedelta
import math
import re


def validate(data, today=None):
    current = (today or date.today()).strftime('%Y-%m')
    plans = data.get('pendingBudgets', [])
    if not isinstance(plans, list):
        raise ValueError('Invalid pending budgets.')
    keys = set()
    for plan in plans:
        key = plan.get('key', '') if isinstance(plan, dict) else ''
        if not re.fullmatch(r'\d{4}-\d{2}', key):
            raise ValueError('Invalid pending budget month.')
        date.fromisoformat(key + '-01')
        if key in keys or plan.get('status', 'pending') not in ('pending', 'activate'):
            raise ValueError('Invalid pending budget status.')
        keys.add(key)
        if plan.get('status') == 'activate' and key != current:
            raise ValueError('Only this month’s reserved budget can be activated.')
        if not isinstance(plan.get('items'), list) or not isinstance(plan.get('billAmounts'), dict):
            raise ValueError('Invalid pending budget items.')
        ids = set()
        for item in plan['items']:
            if not isinstance(item, dict) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', str(item.get('id', ''))) or item['id'] in ids:
                raise ValueError('Invalid pending budget item ID.')
            ids.add(item['id'])
            if not isinstance(item.get('name'), str) or not item['name'].strip() or not isinstance(item.get('category'), str):
                raise ValueError('Enter a name and category for each pending budget item.')
            if item.get('recurrence', 'recurring') not in ('recurring', 'one-time'):
                raise ValueError('Invalid pending budget recurrence.')
        for amount in [item.get('amount') for item in plan['items']] + list(plan['billAmounts'].values()):
            if type(amount) not in (int, float) or not math.isfinite(amount) or not 0 <= amount <= 1e12:
                raise ValueError('Invalid pending budget amount.')


def activate(data, today=None):
    today = today or date.today()
    current = today.strftime('%Y-%m')
    changed = False
    for plan in list(data.get('pendingBudgets', [])):
        if plan.get('status') != 'activate':
            continue
        validate(data, today)
        previous = (date.fromisoformat(current + '-01') - timedelta(days=1)).strftime('%Y-%m')
        if not any(a['key'] == previous and 'slushEntries' in a for a in data.get('monthlyArchives', [])):
            raise ValueError('Archive the previous month before activating this budget.')
        lines = {line['id']: line for line in data['budgets']}
        for entry in plan['items']:
            line = lines.get(entry['id'])
            cfg = {'from': current + '-01', 'cadence': 'monthly', 'amount': entry['amount'], 'recurrence': entry.get('recurrence', 'recurring')}
            if cfg['recurrence'] == 'one-time':
                cfg['budgetDate'] = current + '-01'
            if line:
                if line.get('billId') or line.get('cadence') != 'monthly':
                    raise ValueError('A reserved monthly item conflicts with an existing budget item.')
                history = deepcopy(line.get('history') or [dict(line, **{'from': previous + '-01'})])
                line['history'] = [v for v in history if v['from'] < cfg['from']] + [cfg]
            else:
                line = {'id': entry['id'], 'history': [{'from': '1900-01-01', 'cadence': 'monthly', 'amount': 0}, cfg]}
                data['budgets'].append(line)
            line.update({k: entry[k] for k in ('name', 'category', 'amount')})
            line.update(group=entry.get('group', 'Other'), cadence='monthly', recurrence=cfg['recurrence'], active=True)
            if 'budgetDate' in cfg:
                line['budgetDate'] = cfg['budgetDate']
            else:
                line.pop('budgetDate', None)
        for bill in data.get('bills', []):
            if bill.get('active') is False or (bill.get('frequency') == 'yearly' and int(bill.get('month', 0)) != today.month):
                continue
            due = date(today.year, today.month, min(int(bill.get('day', 1)), (date(today.year + today.month // 12, today.month % 12 + 1, 1) - timedelta(days=1)).day)).isoformat()
            if bill.get('startDate', '') > due:
                continue
            amount = plan['billAmounts'].get(bill['id'], 0)
            bill.setdefault('monthlyAmounts', {})[current] = amount
            line = lines.get(bill.get('budgetId'))
            if line:
                line.setdefault('billAmounts', {})[current] = amount
                line['amount'] = amount
        data['pendingBudgets'].remove(plan)
        changed = True
    return changed
