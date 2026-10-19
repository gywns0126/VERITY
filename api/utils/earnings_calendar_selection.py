"""Pure official-earnings selection shared by collection and public staging.

Only standard-library dependencies belong here: full-snapshot publishers do not
install the HTML collector's requests/BeautifulSoup dependencies.
"""
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def select_calendar(doc, ticker, today=None):
    """None=no authoritative override; []=known cancellation/ambiguity suppresses estimates."""
    today = today or datetime.now(KST).date()
    rows = [r for r in doc.get('records', []) if r.get('ticker') == ticker
            and r.get('status') != 'not_earnings']
    if not rows:
        return None
    try:
        checked = datetime.fromisoformat(doc['_meta']['checked_at']).date()
        if not 0 <= (today - checked).days <= 3:
            return []  # stale authority must not resurrect a contradictory estimate
    except (KeyError, TypeError, ValueError):
        return None
    latest = max(rows, key=lambda r: str(r.get('receipt') or ''))
    if latest.get('status') != 'confirmed' or latest.get('date', '') < today.isoformat():
        return []
    return [{k: latest[k] for k in ('event', 'kind', 'date', 'time_kst', 'is_estimated',
             'source', 'url', 'receipt', 'filed', 'observed_at', 'basis') if k in latest}]


def merge_calendar(existing, official):
    """Replace earnings only; preserve dividends and other independent events."""
    if official is None:
        return existing
    return [r for r in (existing or []) if not
            (r.get('kind') == '실적' or '실적' in str(r.get('event') or ''))] + official
