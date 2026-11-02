"""Evidence collection and subscriber rendering. No exchange trading endpoints."""
import hashlib
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

UTC = timezone.utc
UK = ZoneInfo('Europe/London')
SYMBOLS = ('BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'HYPEUSDT')
PRIVATE_TERMS = re.compile(
    r'coinalyze|coinglass|defillama|nansen|cryptoquant|bybit|glassnode|'
    r'\bcvd\b|\boi\b|open interest|funding rate|ema\s*\d|api[_ -]?key|'
    r'https?://|\b(?:GMT|BST|UTC)\b', re.I)


def instant(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timestamp must include an offset')
    return result.astimezone(UTC)


def number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('Non-finite number')
    return result


def fetch(url, headers=None):
    """Bounded public GET only. Never log a credential or response body on error."""
    request = urllib.request.Request(url, headers={'User-Agent': 'CryptoEdgeLab-Pilot/1.0', **(headers or {})})
    with urllib.request.urlopen(request, timeout=15) as response:
        raw = response.read(32_000_001)
        if len(raw) > 32_000_000:
            raise ValueError('Response too large')
        return raw


def get_json(url):
    return json.loads(fetch(url))


def bybit(path, params):
    value = get_json('https://api.bybit.com/v5/market/' + path + '?' + urllib.parse.urlencode(params))
    if value.get('retCode') != 0:
        raise ValueError('Public market request unsuccessful')
    return value['result']


def candles(rows, now, hours):
    step = hours * 3_600_000
    now_ms = int(now.timestamp() * 1000)
    completed = sorted((r for r in rows if int(r[0]) + step <= now_ms), key=lambda r: int(r[0]))
    if len(completed) < 50:
        raise ValueError('Insufficient completed history')
    starts = [int(r[0]) for r in completed]
    if len(set(starts)) != len(starts) or any(b-a != step for a, b in zip(starts, starts[1:])):
        raise ValueError('Duplicate or missing candles')
    # Require the most recently completed bar, including at exact boundaries.
    if starts[-1] != (now_ms // step - 1) * step:
        raise ValueError('Stale candle history')
    closes = [number(r[4]) for r in completed]
    if any(x <= 0 for x in closes):
        raise ValueError('Invalid close')
    fast, slow = closes[0], closes[0]
    for close in closes[1:]:
        fast += 2/13 * (close-fast)
        slow += 2/22 * (close-slow)
    return {'direction': 'up' if fast > slow else 'down' if fast < slow else 'flat',
            'last_close': closes[-1], 'fast': fast, 'slow': slow,
            'closed_at': datetime.fromtimestamp((starts[-1]+step)/1000, UTC).isoformat(),
            'support': min(number(r[3]) for r in completed[-24:]),
            'resistance': max(number(r[2]) for r in completed[-24:])}


def market(symbol, now):
    views, raw = {}, {}
    for interval, hours in [('60', 1), ('240', 4)]:
        rows = bybit('kline', {'category': 'linear', 'symbol': symbol, 'interval': interval, 'limit': 150})['list']
        raw[interval] = rows
        views[interval] = candles(rows, now, hours)
    one, four = views['60'], views['240']
    stance = one['direction'] if one['direction'] == four['direction'] else 'mixed'
    return {'symbol': symbol, 'stance': stance, 'views': views, 'raw': raw,
            'retrieved_at': datetime.now(UTC).isoformat()}


def feed_candidates(raw, source, now):
    """Discovery only: no external feed text becomes subscriber copy automatically."""
    root = ET.fromstring(raw)
    items = root.findall('.//item') + root.findall('{http://www.w3.org/2005/Atom}entry')
    result = []
    for item in items:
        title = item.findtext('title') or item.findtext('{http://www.w3.org/2005/Atom}title') or ''
        date = item.findtext('pubDate') or item.findtext('{http://www.w3.org/2005/Atom}published') or item.findtext('{http://www.w3.org/2005/Atom}updated')
        link = item.findtext('link')
        if not link:
            element = item.find('{http://www.w3.org/2005/Atom}link')
            link = element.get('href') if element is not None else ''
        try:
            published = parsedate_to_datetime(date) if date and ',' in date else instant(date)
            if published.tzinfo is None:
                continue
            published = published.astimezone(UTC)
        except (ValueError, TypeError, AttributeError):
            continue
        if now-timedelta(hours=24) <= published <= now and title and link:
            result.append({'id': hashlib.sha256(link.encode()).hexdigest()[:16],
                           'title': title[:300], 'url': link, 'source': source,
                           'published_at': published.isoformat(), 'status': 'unverified_candidate'})
    return result[:20]


def private_order_flow(mapping, now):
    """Configured venue coverage only. No assumed all-exchange aggregation."""
    key = os.environ.get('COINALYZE_API_KEY')
    if not key or not mapping:
        raise ValueError('Order-flow API access or market mapping missing')
    # Provider counts each requested symbol as one call, even in a batch.
    if sum(len(m.get('spot', []))+3*len(m.get('futures', [])) for m in mapping.values()) > 35:
        raise ValueError('Coverage exceeds this worker\'s per-minute request budget')
    end = int(now.timestamp()) // 3600 * 3600
    result = {}
    for symbol, markets in mapping.items():
        if symbol not in SYMBOLS or not markets.get('spot') or not markets.get('futures'):
            raise ValueError('Incomplete market coverage')
        result[symbol] = {'spot': [], 'futures': [], 'oi': [], 'funding': []}
        for kind in ('spot', 'futures'):
            ids = markets[kind]
            if not isinstance(ids, list) or len(ids) > 3 or len(set(ids)) != len(ids):
                raise ValueError('Use one to three distinct provider market IDs per type')
            params = {'symbols': ','.join(ids), 'interval': '1hour', 'from': end-3600, 'to': end-1}
            url = 'https://api.coinalyze.net/v1/ohlcv-history?'+urllib.parse.urlencode(params)
            rows = json.loads(fetch(url, {'api_key': key}))
            if {r['symbol'] for r in rows} != set(ids) or len(rows) != len(ids):
                raise ValueError('Missing market')
            for row in rows:
                history = row['history']
                if len(history) != 1 or int(history[0]['t']) != end-3600:
                    raise ValueError('Missing completed order-flow interval')
                bar = history[0]
                volume, buys = number(bar['v']), number(bar['bv'])
                if volume < 0 or not 0 <= buys <= volume:
                    raise ValueError('Invalid buy/sell volume')
                result[symbol][kind].append({'market': row['symbol'], 'bar': bar,
                    'delta_in_provider_volume_units': 2*buys-volume,
                    'direction': 'buy' if 2*buys > volume else 'sell' if 2*buys < volume else 'flat'})
        for endpoint, destination in [('open-interest', 'oi'), ('funding-rate', 'funding')]:
            params = {'symbols': ','.join(markets['futures'])}
            rows = json.loads(fetch('https://api.coinalyze.net/v1/'+endpoint+'?'+urllib.parse.urlencode(params), {'api_key': key}))
            if {r['symbol'] for r in rows} != set(markets['futures']) or len(rows) != len(markets['futures']):
                raise ValueError('Missing positioning market')
            for row in rows:
                age = now.timestamp()-number(row['update'])
                if not 0 <= age <= 1800:
                    raise ValueError('Stale positioning observation')
                number(row['value'])
            result[symbol][destination] = rows
    if set(result) != set(SYMBOLS):
        raise ValueError('Order-flow mapping must cover the complete watchlist')
    return result


def defi_observations(rows):
    # Explicit child-protocol scopes, not invented parent aggregates.
    scopes = {'aave-v3', 'uniswap-v3', 'hyperliquid-bridge'}
    selected = [{k: row.get(k) for k in ('name', 'slug', 'symbol', 'tvl', 'change_1d', 'change_7d')}
                for row in rows if row.get('slug') in scopes]
    if {row['slug'] for row in selected} != scopes or len(selected) != len(scopes):
        raise ValueError('Required DeFi protocol scope missing or duplicated')
    for row in selected:
        if number(row['tvl']) < 0:
            raise ValueError('Invalid locked value')
        number(row['change_7d'])
    return selected


def collect(now, feeds, mapping=None, order_flow_enabled=False):
    snapshot = {'version': 1, 'as_of': now.isoformat(), 'mode': 'live',
                'markets': {}, 'defi': [], 'news_candidates': [], 'failures': {}}
    if order_flow_enabled:
        try:
            snapshot['order_flow'] = private_order_flow(mapping, now)
        except Exception as exc:
            snapshot['failures']['order_flow'] = type(exc).__name__
    for symbol in SYMBOLS:
        try:
            snapshot['markets'][symbol] = market(symbol, now)
        except Exception as exc:
            snapshot['failures'][symbol] = type(exc).__name__
    try:
        rows = get_json('https://api.llama.fi/protocols')
        snapshot['defi'] = defi_observations(rows)
        snapshot['defi_retrieved_at'] = datetime.now(UTC).isoformat()
        snapshot['defi_source'] = 'https://api.llama.fi/protocols'
    except Exception as exc:
        snapshot['failures']['defi'] = type(exc).__name__
    seen = set()
    for url in feeds:
        try:
            for item in feed_candidates(fetch(url), url, now):
                if item['id'] not in seen:
                    snapshot['news_candidates'].append(item)
                    seen.add(item['id'])
        except Exception as exc:
            snapshot['failures'][url] = type(exc).__name__
    return snapshot


def safe_copy(text, limit=320):
    if not isinstance(text, str) or not text.strip() or len(text) > limit:
        raise ValueError('Missing or excessive subscriber text')
    if PRIVATE_TERMS.search(text) or any(ord(c) < 32 for c in text):
        raise ValueError('Private details, links, timezone label or multiline copy')
    return text.strip()


def editorial_items(editorial, kind, now):
    accepted, rejected = [], []
    for item in editorial.get(kind, []):
        try:
            if item.get('status') != 'verified' or not item.get('reviewed_by'):
                raise ValueError('Not verified')
            url = urllib.parse.urlparse(item['source_url'])
            if url.scheme != 'https' or not url.hostname or url.username or url.password:
                raise ValueError('Missing source')
            verified = instant(item['verified_at'])
            if not now-timedelta(hours=24) <= verified <= now:
                raise ValueError('Verification expired')
            if not instant(item['valid_from']) <= now <= instant(item['valid_until']):
                raise ValueError('Outside validity window')
            if kind == 'events':
                event_at = instant(item['event_at'])
                if not now <= event_at <= now+timedelta(hours=24):
                    raise ValueError('Outside event horizon')
            else:
                published = instant(item['published_at'])
                if published > now or published > verified:
                    raise ValueError('Future publication or review predates publication')
            copy = safe_copy(item['subscriber_copy'])
            prefix = instant(item['event_at']).astimezone(UK).strftime('%d %b %H:%M') + ' — ' if kind == 'events' else ''
            accepted.append(prefix+copy)
        except (ValueError, KeyError, TypeError):
            rejected.append(item.get('id', 'missing-id'))
    return accepted[:3], rejected


def render(snapshot, editorial, now, edition='daily'):
    as_of = instant(snapshot['as_of'])
    if not timedelta(0) <= now-as_of <= timedelta(minutes=20):
        raise ValueError('Snapshot expired or from the future')
    title = 'DAILY MARKET BRIEF' if edition == 'daily' else 'MARKET OUTLOOK UPDATE'
    lines = ['CRYPTOEDGELAB — '+title, as_of.astimezone(UK).strftime('%d %b %Y | %H:%M'), '']
    if snapshot.get('mode') != 'live':
        lines += ['DEMONSTRATION — FICTIONAL DATA', '']
    markets = snapshot.get('markets', {})
    btc = markets.get('BTCUSDT', {})
    stance = btc.get('stance', 'unavailable')
    outlook = {'up': 'Cautiously bullish', 'down': 'Cautiously bearish',
               'mixed': 'Mixed; wait for confirmation', 'flat': 'Neutral',
               'unavailable': 'Assessment limited'}[stance]
    explanation = {'up': 'BTC structure supports continuation while established support holds.',
                   'down': 'BTC structure remains weak. A sustained recovery through resistance would challenge this view.',
                   'mixed': 'Shorter-term movement and the wider structure disagree. Avoid treating direction as settled.',
                   'flat': 'There is no clear directional preference.',
                   'unavailable': 'A reliable current directional assessment is unavailable.'}[stance]
    lines += ['MARKET OUTLOOK: '+outlook, explanation, '', 'FA & NEWS']
    news, rejected_news = editorial_items(editorial, 'news', now)
    lines += ['• '+x for x in news] or ['No verified material catalyst included in this edition.']
    lines += ['', 'UPCOMING EVENTS']
    events, rejected_events = editorial_items(editorial, 'events', now)
    lines += ['• '+x for x in events] or ['No verified scheduled event included. Calendar coverage is incomplete.']
    lines += ['', 'DEFI WATCH']
    defi_lines = []
    for row in snapshot.get('defi', []):
        try:
            growth = number(row['change_7d'])
            name = safe_copy(row['name'], 60)
            if abs(growth) >= 5:
                word = 'increased' if growth > 0 else 'declined'
                defi_lines.append(f'{name}: reported locked value has {word} over seven days. Price effects and token value capture still need review.')
        except (ValueError, TypeError, KeyError):
            continue
    lines += ['• '+x for x in defi_lines[:2]] or ['No material DeFi change highlighted from available coverage.']
    lines += ['', 'WATCHLIST']
    watch = {'up': 'Continuation watch; await a separate confirmed setup.',
             'down': 'Weak structure; await a separate confirmed setup.',
             'mixed': 'Mixed conditions; wait for clarity.', 'flat': 'No clear directional preference.'}
    for symbol in SYMBOLS:
        view = markets.get(symbol)
        lines.append(symbol.removesuffix('USDT')+': '+(watch[view['stance']] if view else 'Current assessment unavailable.'))
    lines += ['', 'WHAT CHANGES THE VIEW',
              'A sustained break of established support or recovery through resistance requires reassessment.',
              '', 'CRYPTOEDGE STATUS',
              'Research watch only. Confirmed BTC entries, stops, targets and position updates are posted separately in this public channel. Premium adds altcoin trade coverage.']
    if snapshot.get('failures'):
        lines += ['', 'Coverage is incomplete; this assessment is limited.']
    text = '\n'.join(lines)
    if len(text.encode('utf-16-le'))//2 > 3900 or PRIVATE_TERMS.search(text):
        raise ValueError('Subscriber message exceeds length or disclosure policy')
    return text, {'outlook': outlook, 'stance': stance,
                  'rejected_editorial_ids': rejected_news+rejected_events,
                  'verified_news_count': len(news), 'verified_event_count': len(events)}

