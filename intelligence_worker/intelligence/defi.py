"""Small public DeFi observations and governance metadata, held only in memory."""
import json
import math
import urllib.request
from datetime import datetime, timedelta, timezone
from .delivery import NoRedirect

UTC = timezone.utc
BASE = 'https://api.llama.fi'
SPACES = {'uniswapgovernance.eth': 'Uniswap'}


def finite(value):
    if isinstance(value, bool):
        raise ValueError('Boolean is not a metric')
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('Invalid metric')
    return result


def activity(payload, now, name):
    if payload.get('disabled') or payload.get('latestFetchIsOk') is False:
        raise ValueError('Unavailable metric')
    chart = payload.get('totalDataChart', [])
    stamp = max(int(row[0]) for row in chart)
    age = now-datetime.fromtimestamp(stamp, UTC)
    if not -timedelta(minutes=5) <= age <= timedelta(hours=48):
        raise ValueError('Stale or future source reporting period')
    current, previous = finite(payload['total24h']), finite(payload['total48hto24h'])
    if current < 0 or previous <= 0:
        raise ValueError('Missing comparable reporting periods')
    if name != 'Covered DEX volume' and payload.get('name') != 'Aave':
        raise ValueError('Unexpected protocol scope')
    return {'name': name, 'value': current, 'change_pct': finite(100*(current/previous-1)),
            'period_at': datetime.fromtimestamp(stamp, UTC).isoformat(), 'fetched_at': now.isoformat()}


def stable_supply(payload, now):
    rows = payload['peggedAssets']
    result = []
    for symbol in ('USDT', 'USDC'):
        matches = [row for row in rows if row.get('symbol') == symbol and row.get('pegType') == 'peggedUSD']
        if len(matches) != 1:
            raise ValueError('Missing or duplicated stablecoin scope')
        row = matches[0]
        current = finite(row['circulating']['peggedUSD'])
        previous = finite(row['circulatingPrevWeek']['peggedUSD'])
        if current <= 0 or previous <= 0:
            raise ValueError('Invalid circulating supply')
        result.append({'symbol': symbol, 'supply': current, 'change_7d': finite(100*(current/previous-1)),
                       'fetched_at': now.isoformat()})
    return result


def governance(now):
    query = '''query {
      space(id: "uniswapgovernance.eth") { id name verified }
      proposals(first: 20, orderBy: "created", orderDirection: desc,
        where: {space_in: ["uniswapgovernance.eth"], state: "active"}) {
          id title start end state space { id }
        }
    }'''
    request = urllib.request.Request('https://hub.snapshot.org/graphql',
        data=json.dumps({'query': query}).encode(),
        headers={'Content-Type': 'application/json', 'User-Agent': 'CryptoEdgeLab/1.0'})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=15) as response:
        payload = json.loads(response.read(200_000))
    if payload.get('errors') or payload.get('data', {}).get('space', {}).get('verified') is not True:
        raise ValueError('Unverified governance space')
    return governance_rows(payload['data']['proposals'], now)


def governance_rows(rows, now):
    result = []
    for row in rows:
        space = row['space']['id']
        start, end = (datetime.fromtimestamp(int(row[k]), UTC) for k in ('start', 'end'))
        if space not in SPACES or row['state'] != 'active' or not start <= now < end:
            continue
        if end > now+timedelta(hours=24):
            continue
        if not isinstance(row['title'], str) or not 1 <= len(row['title']) <= 100:
            continue
        result.append({'protocol': SPACES[space], 'title': row['title'], 'ends_at': end.isoformat(),
            'id': row['id'], 'space': space, 'fetched_at': now.isoformat(), 'status': 'active_vote'})
    return sorted(result, key=lambda row: row['ends_at'])[:2]


def collect_defi(now, get_json, vote_fetch=None):
    result = {'checked_at': now.isoformat(), 'activity': [], 'stablecoins': [], 'votes': [], 'unavailable': []}
    suffix = '?excludeTotalDataChart=false&excludeTotalDataChartBreakdown=true'
    sources = [('dex_volume', BASE+'/overview/dexs'+suffix, 'Covered DEX volume'),
        ('fees', BASE+'/summary/fees/aave?dataType=dailyFees', 'Aave fees'),
        ('revenue', BASE+'/summary/fees/aave?dataType=dailyRevenue', 'Aave revenue')]
    for key, url, name in sources:
        try:
            result['activity'].append(activity(get_json(url), now, name))
        except Exception:
            result['unavailable'].append(key)
    try:
        result['stablecoins'] = stable_supply(get_json('https://stablecoins.llama.fi/stablecoins?includePrices=false'), now)
    except Exception:
        result['unavailable'].append('stablecoin_supply')
    try:
        result['votes'] = (vote_fetch or governance)(now)
    except Exception:
        result['unavailable'].append('governance')
    return result
