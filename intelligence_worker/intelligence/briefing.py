"""Free public calendar and spot-mover inputs; no persistence or trading actions."""
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
UK = ZoneInfo('Europe/London')
CALENDARS = {
    'BLS': 'https://www.bls.gov/schedule/news_release/bls.ics',
    'BEA': 'https://www.bea.gov/news/schedule/ics/online-calendar-subscription.ics',
}
STABLES = {'USDC', 'USDE', 'USDD', 'USDS', 'USD1', 'PYUSD', 'FDUSD', 'TUSD',
           'DAI', 'USDP', 'USDT', 'EUR', 'EURC', 'AEUR', 'RLUSD', 'GUSD'}


def calendar_events(raw, source, now):
    """Explicit timed VEVENTs only. Never infer release times from date-only entries."""
    text = raw.decode('utf-8-sig')
    text = re.sub(r'\r?\n[ \t]', '', text)
    if 'BEGIN:VCALENDAR' not in text or 'END:VCALENDAR' not in text:
        raise ValueError('Invalid calendar')
    future_dates, selected, revisions = [], {}, {}
    for index, block in enumerate(re.findall(r'BEGIN:VEVENT\s*(.*?)END:VEVENT', text, re.S)):
        values = {}
        for line in block.splitlines():
            if ':' in line:
                key, value = line.split(':', 1)
                values[key.split(';')[0]] = (key, value.strip())
        uid = values.get('UID', ('', str(index)))[1]
        try:
            sequence = int(values.get('SEQUENCE', ('', '0'))[1])
        except ValueError:
            continue
        if uid not in revisions or sequence >= revisions[uid][0]:
            revisions[uid] = (sequence, values)
    for _, values in revisions.values():
        if values.get('STATUS', ('', ''))[1] == 'CANCELLED' or 'RRULE' in values:
            continue
        try:
            key, value = values['DTSTART']
            if not re.fullmatch(r'\d{8}T\d{6}Z?', value):
                continue
            when = datetime.strptime(value.rstrip('Z'), '%Y%m%dT%H%M%S')
            if value.endswith('Z'):
                when = when.replace(tzinfo=UTC)
            else:
                tzid = re.search(r'TZID="?([^;":]+)', key)
                if not tzid:
                    continue
                zone = tzid.group(1)
                if zone not in ('America/New_York', 'US/Eastern', 'Europe/London'):
                    continue
                when = when.replace(tzinfo=ZoneInfo(zone))
            when = when.astimezone(UTC)
            future_dates.append(when)
            title = values['SUMMARY'][1].replace('\\,', ',').replace('\\;', ';')
            if not re.fullmatch(r'[A-Za-z0-9 ,()./&+\-]{1,160}', title):
                continue
            rules = [
                (r'Consumer Price Index', 'US CPI', 'Inflation may shift rate expectations.'),
                (r'Producer Price Index', 'US PPI', 'Watch inflation and rate expectations.'),
                (r'^Employment Situation(?:,|\s*$)', 'US jobs report', 'Jobs and wage data may move rate expectations.'),
                (r'Job Openings and Labor Turnover', 'US JOLTS', 'A labour-demand check for the rate outlook.'),
                (r'Employment Cost Index', 'US employment costs', 'Wage pressure matters for inflation.'),
                (r'^(Gross Domestic Product|GDP)\b(?! by)', 'US GDP', 'Growth data may affect yields and risk appetite.'),
                (r'^Personal Income and Outlays', 'US income / spending / PCE', 'PCE inflation may shift rate expectations.'),
                (r'^U.S. International Trade in Goods and Services', 'US trade balance', 'A growth and currency-risk checkpoint.'),
            ]
            for pattern, label, relevance in rules:
                if re.search(pattern, title, re.I):
                    if now.astimezone(UK).date() == when.astimezone(UK).date() or now <= when <= now+timedelta(hours=24):
                        identity = (label, when.isoformat())
                        selected[identity] = {'name': label, 'event_at': when.isoformat(),
                            'relevance': relevance, 'source': source}
                    break
        except (KeyError, ValueError):
            continue
    if not future_dates or max(future_dates) < now:
        raise ValueError('Calendar has no current or future coverage')
    return sorted(selected.values(), key=lambda row: row['event_at'])


def spot_movers(payload, now):
    """Rolling 24h ranking within one venue's liquid USDT spot universe."""
    if payload.get('retCode') != 0 or payload.get('result', {}).get('category') != 'spot':
        raise ValueError('Unavailable spot market snapshot')
    stamp = datetime.fromtimestamp(float(payload['time'])/1000, UTC)
    if not -timedelta(seconds=60) <= now-stamp <= timedelta(minutes=5):
        raise ValueError('Stale mover snapshot')
    rows, seen = [], set()
    for row in payload['result']['list']:
        symbol = row.get('symbol', '')
        if not re.fullmatch(r'[A-Z0-9]{2,20}USDT', symbol):
            continue
        base = symbol[:-4]
        if base in STABLES or re.search(r'[235][LS]$', base):
            continue
        try:
            from math import isfinite
            change, turnover, price = (float(row[k]) for k in ('price24hPcnt', 'turnover24h', 'lastPrice'))
            if not all(isfinite(x) for x in (change, turnover, price)) or change <= -1 or turnover < 10_000_000 or price <= 0:
                continue
            if symbol in seen:
                raise ValueError('Duplicate mover symbol')
            seen.add(symbol)
            rows.append({'symbol': base, 'change_pct': change*100})
        except (KeyError, TypeError):
            continue
        except ValueError:
            # Invalid numeric data invalidates the ranking rather than silently changing its universe.
            raise ValueError('Invalid or duplicated mover data') from None
    if len(rows) < 6:
        raise ValueError('Insufficient liquid spot coverage')
    return {'as_of': stamp.isoformat(), 'eligible_count': len(rows),
        'gainers': sorted((r for r in rows if r['change_pct'] > 0), key=lambda r: (-r['change_pct'], r['symbol']))[:3],
        'losers': sorted((r for r in rows if r['change_pct'] < 0), key=lambda r: (r['change_pct'], r['symbol']))[:3]}
