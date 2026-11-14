"""Stateless daily Intelligence worker. Telegram is the publication archive."""
import argparse
import json
from urllib.parse import urlparse
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from .core import UTC, UK, SYMBOLS, collect, instant, render
from .delivery import Delivery

ROOT = Path(__file__).resolve().parents[1]
FEEDS = ['https://www.federalreserve.gov/feeds/press_monetary.xml',
         'https://blog.ethereum.org/feed.xml']


def flag(env, key):
    value = env.get(key, 'false').lower()
    if value not in ('true', 'false'):
        raise ValueError('Boolean settings must be true or false')
    return value == 'true'


def settings(env=None):
    env = os.environ if env is None else env
    clock = env.get('INTELLIGENCE_DAILY_TIME', '08:00')
    if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', clock):
        raise ValueError('Invalid daily time')
    channel = env.get('INTELLIGENCE_CHANNEL_ID', '@cryptoedgelab')
    if not re.fullmatch(r'@[A-Za-z0-9_]{5,32}|-100\d{5,}', channel):
        raise ValueError('Use a public channel handle or numeric channel ID')
    mapping = json.loads(env.get('INTELLIGENCE_MARKET_MAPPING', '{}'))
    editorial = json.loads(env.get('INTELLIGENCE_EDITORIAL_JSON', '{"news":[],"events":[]}'))
    if not isinstance(mapping, dict) or not isinstance(editorial, dict):
        raise ValueError('Invalid JSON settings')
    if any(not isinstance(editorial.get(kind, []), list) or
           any(not isinstance(item, dict) for item in editorial.get(kind, [])) for kind in ('news', 'events', 'defi', 'tokens')):
        raise ValueError('Invalid editorial records')
    flow = flag(env, 'INTELLIGENCE_ORDER_FLOW_ENABLED')
    if flow and (not env.get('COINALYZE_API_KEY') or set(mapping) != set(SYMBOLS)):
        raise ValueError('Enabled order flow requires credentials and complete mapping')
    headline_feeds = tuple(dict.fromkeys(
        env.get('INTELLIGENCE_HEADLINE_FEEDS', '').split()))
    if len(headline_feeds) > 5 or any(
        urlparse(url).scheme != 'https' or not urlparse(url).hostname
        or urlparse(url).username or urlparse(url).password for url in headline_feeds
    ):
        raise ValueError('Set up to five public HTTPS headline feeds')
    return {'headline_feeds': headline_feeds, 'clock': clock, 'channel': channel, 'mapping': mapping, 'editorial': editorial,
        'order_flow': flow, 'enabled': flag(env, 'INTELLIGENCE_PUBLICATION_ENABLED'),
        'rights': flag(env, 'INTELLIGENCE_DATA_RIGHTS_CONFIRMED'),
        'token': env.get('TELEGRAM_BOT_TOKEN', '')}


def target(now, clock):
    hour, minute = map(int, clock.split(':'))
    return now.astimezone(UK).replace(hour=hour, minute=minute, second=0, microsecond=0, fold=0).astimezone(UTC)


def schedule_due(now, clock):
    at = target(now, clock)
    return at.astimezone(UK).strftime('%H:%M') == clock and timedelta(0) <= now-at < timedelta(minutes=20)


def prepare(config, now, fixture=None):
    snapshot = json.loads(Path(fixture).read_text(encoding='utf-8')) if fixture else collect(
        now, FEEDS, config['mapping'], order_flow_enabled=config['order_flow'],
        headline_feeds=config.get('headline_feeds', ()))
    text, assessment = render(snapshot, config['editorial'], now)
    complete = (snapshot.get('mode') == 'live' and not snapshot.get('failures') and
        set(snapshot.get('markets', {})) == set(SYMBOLS) and bool(snapshot.get('defi')) and
        (not config['order_flow'] or set(snapshot.get('order_flow', {})) == set(SYMBOLS)))
    status = {'outlook': assessment['outlook'], 'complete': complete,
        'verified_news': assessment['verified_news_count'], 'failures': len(snapshot.get('failures', {}))}
    status['defi_unavailable'] = len(snapshot.get('defi_metrics', {}).get('unavailable', []))
    status['calendar_unavailable'] = len(snapshot.get('calendar', {}).get('unavailable', []))
    status['research_candidates'] = len(snapshot.get('news_candidates', []))
    return text, status, instant(snapshot['as_of'])+timedelta(minutes=20)


def publication_ready(config):
    if not config['enabled'] or not config['rights'] or not config['token']:
        raise ValueError('Publication requires explicit enablement, permitted data use and a bot token')


class Worker:
    def __init__(self, config, started, sending=False):
        self.config, self.sending, self.delivery = config, sending, None
        if sending:
            publication_ready(config)
        # No disk receipts: never resume today's scheduled send after its time on restart.
        self.day = started.astimezone(UK).date() if started >= target(started, config['clock']) else None

    def tick(self, now, producer=None, sender=None):
        day = now.astimezone(UK).date()
        event = None
        if day != self.day and schedule_due(now, self.config['clock']):
            text, status, expires = (producer or prepare)(self.config, now)
            event = {'edition_date': day.isoformat(), **status, 'mode': 'preview'}
            if not self.sending:
                self.day = day
            elif status['complete']:
                self.delivery = Delivery(text, self.config['channel'], now, expires)
                self.day = day
                event['mode'] = 'publication'
            else:
                event['held'] = 'incomplete_collection'
        if self.delivery:
            state = self.delivery.dispatch(self.config['token'], now, sender)
            if state:
                event = {**(event or {}), 'delivery': state}
        return event


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', action='store_true', help='Run the daily scheduler')
    parser.add_argument('--deliver', action='store_true', help='Permit Telegram sends; requires private environment settings')
    parser.add_argument('--publish-now', action='store_true', help='Explicit one-off send; check Telegram first to avoid duplicates')
    parser.add_argument('--check', action='store_true', help='Collect and report coverage without printing the brief')
    parser.add_argument('--research', action='store_true', help='Private research queue and coverage; never publishes')
    parser.add_argument('--fixture', help='Preview a fictional snapshot; cannot send')
    parser.add_argument('--at', help='Offset-aware fixture time only')
    args = parser.parse_args()
    if args.research and (args.worker or args.deliver or args.publish_now or args.check or args.fixture or args.at):
        parser.error('--research is a live read-only diagnostic')
    if args.at and not args.fixture:
        parser.error('--at requires --fixture')
    if args.deliver and (args.fixture or args.check):
        parser.error('A fixture or check cannot deliver')
    if args.publish_now != (args.deliver and not args.worker):
        parser.error('One-off delivery requires --publish-now; worker delivery uses --worker --deliver')
    if args.worker and (args.fixture or args.at or args.check or args.publish_now):
        parser.error('Worker cannot use preview overrides')
    try:
        config = settings()
        now = instant(args.at) if args.at else datetime.now(UTC)
        if args.research:
            snapshot = collect(now, FEEDS, config['mapping'], order_flow_enabled=config['order_flow'],
                               headline_feeds=config['headline_feeds'])
            print(json.dumps({k: snapshot.get(k) for k in ('as_of', 'news_candidates', 'defi_review_candidates', 'research_unavailable',
                'defi_metrics', 'calendar', 'failures')}), flush=True)
            return
        if args.worker:
            worker = Worker(config, now, args.deliver)
            print(json.dumps({'service': 'cryptoedge-intelligence', 'storage': 'memory_only',
                'mode': 'publication' if args.deliver else 'preview', 'daily_time': config['clock'],
                'today_suppressed_after_start': worker.day is not None}), flush=True)
            while True:
                try:
                    event = worker.tick(datetime.now(UTC))
                    if event:
                        print(json.dumps(event), flush=True)
                except Exception as exc:
                    print(json.dumps({'worker_error': type(exc).__name__}), flush=True)
                time.sleep(60)
        else:
            if args.deliver:
                publication_ready(config)
            text, status, expires = prepare(config, now, args.fixture)
            if args.deliver:
                if not status['complete']:
                    raise ValueError('Incomplete collection; publication held')
                delivery = Delivery(text, config['channel'], now, expires)
                status['delivery'] = delivery.dispatch(config['token'], datetime.now(UTC))
            elif not args.check:
                print(text)
            print(json.dumps(status), flush=True)
    except Exception as exc:
        # Exception messages and request URLs can contain credentials. Report type only.
        print(json.dumps({'worker_error': type(exc).__name__}), flush=True)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
