"""Pure, testable budget calculations. Monetary values use Decimal."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def as_money(value):
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def format_inr(value):
    """Format using Indian digit grouping: ₹3,40,000 / -₹1,200.50."""
    amount = as_money(value)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    whole, frac = f"{amount:.2f}".split(".")
    if len(whole) > 3:
        last_three, rest = whole[-3:], whole[:-3]
        groups = []
        while rest:
            groups.append(rest[-2:])
            rest = rest[:-2]
        whole = ",".join(reversed(groups)) + "," + last_three
    decimal = f".{frac}" if frac != "00" else ""
    return f"{sign}₹{whole}{decimal}"


def summarize(total_credit, opening_used, entries):
    credit = as_money(total_credit)
    opening = as_money(opening_used)
    logged = sum((as_money(e["amount"]) for e in entries), Decimal("0.00"))
    used = opening + logged
    remaining = credit - used
    pct_used = float(used / credit * 100) if credit > 0 else 0.0
    return {
        "total_credit": credit,
        "opening_used": opening,
        "logged_used": logged,
        "used": used,
        "remaining": remaining,
        "pct_used": pct_used,
    }


def weekly_withdrawals(entries, today=None, weeks=8):
    """Calendar weeks, Monday-Sunday. Opening usage has no date and is excluded."""
    today = today or date.today()
    current_monday = today - timedelta(days=today.weekday())
    mondays = [current_monday - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    by_monday = defaultdict(lambda: Decimal("0.00"))
    for entry in entries:
        spent_date = date.fromisoformat(str(entry["used_on"])[:10])
        monday = spent_date - timedelta(days=spent_date.weekday())
        by_monday[monday] += as_money(entry["amount"])
    return [
        {"start": monday, "label": monday.strftime("%d %b"), "amount": by_monday[monday]}
        for monday in mondays
    ]


def filter_entries(entries, period, query, today=None):
    today = today or date.today()
    query = (query or "").casefold().strip()
    filtered = []
    for entry in entries:
        spent_date = date.fromisoformat(str(entry["used_on"])[:10])
        if period == "This month" and (spent_date.year, spent_date.month) != (today.year, today.month):
            continue
        if period == "Last 30 days" and not (today - timedelta(days=29) <= spent_date <= today):
            continue
        if query and query not in entry["purpose"].casefold():
            continue
        filtered.append(entry)
    return filtered
