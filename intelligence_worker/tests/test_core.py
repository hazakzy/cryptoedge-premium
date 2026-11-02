import json
import os
import sys
import unittest
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intelligence.core import (SYMBOLS, candles, defi_observations, editorial_items, feed_candidates,
                               instant, private_order_flow, render)
from intelligence.runner import schedule_due
NOW = instant('2026-11-01T08:00:00Z')

def snapshot():
    return {'version': 1, 'mode': 'live', 'as_of': NOW.isoformat(),
            'markets': {s: {'stance': 'up'} for s in SYMBOLS},
            'order_flow': {s: {} for s in SYMBOLS},
            'defi': [{'name': 'Aave', 'change_7d': 8}],
            'news_candidates': [{'title': 'UNVERIFIED BUY NOW', 'source': 'secret-provider'}],
            'failures': {}}


def news():
    return {'id': 'n1', 'status': 'verified', 'reviewed_by': 'editor',
            'source_url': 'https://example.org/original',
            'verified_at': NOW.isoformat(), 'published_at': (NOW-timedelta(hours=1)).isoformat(),
            'valid_from': (NOW-timedelta(hours=1)).isoformat(),
            'valid_until': (NOW+timedelta(hours=6)).isoformat(),
            'subscriber_copy': 'A confirmed protocol update deserves attention; market confirmation is still required.'}


class RenderTests(unittest.TestCase):
    def test_private_source_and_discovery_not_published(self):
        item = snapshot()
        item['private_provider'] = 'Coinalyze'
        text, assessment = render(item, {}, NOW)
        self.assertNotIn('Coinalyze', text)
        self.assertNotIn('UNVERIFIED', text)
        self.assertNotIn('08:00 UTC', text)
        self.assertEqual(assessment['verified_news_count'], 0)


    def test_stale_and_future_snapshots_fail(self):
        for offset in (timedelta(minutes=-21), timedelta(seconds=1)):
            item = snapshot()
            item['as_of'] = (NOW+offset).isoformat()
            with self.assertRaises(ValueError):
                render(item, {}, NOW)


    def test_verified_original_copy_and_private_sources(self):
        text, a = render(snapshot(), {'news': [news()]}, NOW)
        self.assertIn('confirmed protocol update', text)
        self.assertNotIn('example.org', text)
        self.assertEqual(a['verified_news_count'], 1)


    def test_bad_editorial_is_omitted_and_audited(self):
        for changes in ({'status': 'rumor'}, {'source_url': ''}, {'reviewed_by': ''},
                        {'subscriber_copy': 'Nansen says buy'}, {'subscriber_copy': 'CVD positive'},
                        {'verified_at': (NOW-timedelta(days=2)).isoformat()},
                        {'published_at': (NOW+timedelta(seconds=1)).isoformat()},
                        {'subscriber_copy': 'Get it at https://secret.test'},
                        {'subscriber_copy': 'x\nGKC BUY NOW'}):
            row = {**news(), **changes}
            accepted, rejected = editorial_items({'news': [row]}, 'news', NOW)
            self.assertFalse(accepted)
            self.assertEqual(rejected, ['n1'])


    def test_event_uk_summer_time_without_suffix(self):
        summer = instant('2026-07-01T07:00:00Z')
        row = {**news(), 'verified_at': summer.isoformat(),
               'valid_from': summer.isoformat(), 'valid_until': (summer+timedelta(days=1)).isoformat(),
               'event_at': (summer+timedelta(hours=2)).isoformat()}
        accepted, _ = editorial_items({'events': [row]}, 'events', summer)
        self.assertTrue(accepted[0].startswith('01 Jul 10:00'))
        self.assertNotIn('BST', accepted[0])


    def test_incomplete_coverage_is_visible(self):
        item = snapshot()
        item['markets'].pop('BTCUSDT')
        item['failures'] = {'BTCUSDT': 'TimeoutError'}
        text, a = render(item, {}, NOW)
        self.assertIn('Assessment limited', text)
        self.assertNotIn('TimeoutError', text)
        self.assertEqual(a['stance'], 'unavailable')


    def test_defi_does_not_equate_tvl_to_token_upside(self):
        text, _ = render(snapshot(), {}, NOW)
        self.assertIn('Price effects and token value capture still need review', text)



class DataTests(unittest.TestCase):
    def test_defi_uses_explicit_child_scopes_and_rejects_empty_coverage(self):
        rows = [{'slug': slug, 'name': slug, 'tvl': 100, 'change_7d': 6}
                for slug in ('aave-v3', 'uniswap-v3', 'hyperliquid-bridge')]
        selected = defi_observations(rows+[{'slug': 'aave-v2', 'tvl': 1000}])
        self.assertEqual(len(selected), 3)
        with self.assertRaises(ValueError):
            defi_observations([])
        with self.assertRaises(ValueError):
            defi_observations(rows+[rows[0]])


    def bars(self):
        end = int(NOW.timestamp()*1000)
        return [[str(end-i*3600000), '100', '102', '98', str(100+i/100), '10', '1000'] for i in range(151)]


    def test_unfinished_candle_is_excluded(self):
        rows = self.bars()
        rows[0][4] = '1000000'
        result = candles(rows, NOW, 1)
        self.assertEqual(result['last_close'], 100.01)
        self.assertEqual(result['closed_at'], NOW.isoformat())


    def test_candle_gap_duplicates_staleness_rejected(self):
        rows = self.bars()
        for broken in (rows[2:], rows[:20]+rows[21:], rows+[rows[10]]):
            with self.assertRaises(ValueError):
                candles(broken, NOW, 1)


    def test_news_feed_dates_and_discovery_only(self):
        xml = b'<rss><channel><item><title>Announcement</title><link>https://example.org/a</link><pubDate>Sun, 01 Nov 2026 07:00:00 GMT</pubDate></item><item><title>Future</title><link>https://example.org/b</link><pubDate>Sun, 01 Nov 2026 09:00:00 GMT</pubDate></item></channel></rss>'
        rows = feed_candidates(xml, 'official-feed', NOW)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'unverified_candidate')


    def test_orderflow_missing_access_fails(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            private_order_flow({}, NOW)


    def test_orderflow_closed_delta_and_missing_interval(self):
        mapping = {s: {'spot': [s+'_SPOT'], 'futures': [s+'_PERP']} for s in SYMBOLS}
        end = int(NOW.timestamp())
        def fake_fetch(url, headers):
            from urllib.parse import parse_qs, urlparse
            market = parse_qs(urlparse(url).query)['symbols'][0]
            if 'ohlcv-history' in url:
                return json.dumps([{'symbol': market, 'history': [{'t': end-3600, 'v': 100, 'bv': 60}]}]).encode()
            return json.dumps([{'symbol': market, 'value': 0.01, 'update': end-60}]).encode()
        with patch.dict(os.environ, {'COINALYZE_API_KEY': 'not-a-real-key'}), patch('intelligence.core.fetch', side_effect=fake_fetch):
            result = private_order_flow(mapping, NOW)
        self.assertEqual(result['BTCUSDT']['spot'][0]['delta_in_provider_volume_units'], 20)
        with patch.dict(os.environ, {'COINALYZE_API_KEY': 'not-a-real-key'}), patch('intelligence.core.fetch', return_value=b'[]'):
            with self.assertRaises(ValueError):
                private_order_flow(mapping, NOW)



class ScheduleTests(unittest.TestCase):
    def test_nonexistent_spring_clock_is_skipped(self):
        self.assertFalse(schedule_due(instant('2026-03-29T01:35:00Z'), '01:30'))


    def test_uk_daily_time_across_clock_changes(self):
        for date, utc in [('2026-03-28', '08:00'), ('2026-03-29', '07:00'),
                          ('2026-10-24', '07:00'), ('2026-10-25', '08:00')]:
            now = instant(date+'T'+utc+':00Z')
            self.assertTrue(schedule_due(now, '08:00'))
            self.assertFalse(schedule_due(now-timedelta(seconds=1), '08:00'))
            self.assertFalse(schedule_due(now+timedelta(minutes=20), '08:00'))


    def test_repeated_autumn_hour_not_double_window(self):
        self.assertTrue(schedule_due(instant('2026-10-25T00:05:00Z'), '01:00'))
        self.assertFalse(schedule_due(instant('2026-10-25T01:05:00Z'), '01:00'))


