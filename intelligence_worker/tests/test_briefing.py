import json
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intelligence.briefing import calendar_events, spot_movers
from intelligence.core import SYMBOLS, calendar_lines, collect, editorial_items, instant, mover_lines, render

NOW = instant('2026-11-04T08:00:00Z')


def ics(start='DTSTART:20261104T133000Z', title='Consumer Price Index', extra=''):
    return ('BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:test\r\n'+start+'\r\nSUMMARY:'+title+
            '\r\n'+extra+'\r\nEND:VEVENT\r\nEND:VCALENDAR').encode()


def payload():
    rows = [{'symbol': symbol+'USDT', 'price24hPcnt': str(change),
             'turnover24h': '15000000', 'lastPrice': '10'}
            for symbol, change in [('AAA', .2), ('BBB', .1), ('CCC', .05),
                                  ('DDD', -.1), ('EEE', -.2), ('FFF', -.05)]]
    return {'retCode': 0, 'time': int(NOW.timestamp()*1000), 'result': {'category': 'spot', 'list': rows}}


def snapshot():
    return {'mode': 'live', 'as_of': NOW.isoformat(), 'failures': {},
        'markets': {s: {'stance': 'mixed'} for s in SYMBOLS},
        'defi': [{'name': 'Aave', 'change_7d': 8}],
        'calendar': {'checked_at': NOW.isoformat(), 'sources_ok': ['BLS', 'BEA'], 'unavailable': [],
            'events': calendar_events(ics(), 'BLS', NOW)}, 'movers': spot_movers(payload(), NOW)}


def editorial(kind='news'):
    item = {'id': 'one', 'status': 'verified', 'reviewed_by': 'editor',
        'source_url': 'https://example.org/release', 'verified_at': NOW.isoformat(),
        'published_at': (NOW-timedelta(hours=1)).isoformat(),
        'valid_from': NOW.isoformat(), 'valid_until': (NOW+timedelta(hours=20)).isoformat(),
        'subscriber_copy': 'An independently reviewed protocol announcement.',
        'impact_copy': 'Activity may change, but token value capture still needs confirmation.', 'affected_assets': ['ETH']}
    if kind == 'events':
        item.update(event_at=(NOW+timedelta(hours=5)).isoformat(), subscriber_copy='US CPI', previous='2.4%', forecast='2.5%')
    return item


class CalendarTests(unittest.TestCase):
    def test_utc_and_eastern_events_convert_to_uk_with_dst(self):
        rows = calendar_events(ics(), 'BLS', NOW)
        lines, limited = calendar_lines({'calendar': {'checked_at': NOW.isoformat(), 'events': rows,
            'sources_ok': ['BLS', 'BEA']}}, NOW)
        self.assertIn('04 Nov 13:30', lines[0])
        self.assertFalse(limited)
        # US and UK clocks change on different dates: 08:30 New York is 12:30 UK on March 20.
        march = instant('2026-03-20T08:00:00Z')
        rows = calendar_events(ics('DTSTART;TZID=America/New_York:20260320T083000'), 'BLS', march)
        self.assertEqual(rows[0]['event_at'], '2026-03-20T12:30:00+00:00')

    def test_folded_bea_title_and_cancelled_all_day_floating_dates(self):
        rows = calendar_events(ics(title='Personal Income and Outlays\\, October\r\n  2026'), 'BEA', NOW)
        self.assertEqual(rows[0]['name'], 'US income / spending / PCE')
        for start, extra in [('DTSTART;VALUE=DATE:20261104', ''), ('DTSTART:20261104T083000', ''),
                             ('DTSTART:20261104T133000Z', 'STATUS:CANCELLED')]:
            with self.assertRaises(ValueError):
                calendar_events(ics(start, extra=extra), 'BLS', NOW)

    def test_stale_calendar_is_not_a_quiet_calendar(self):
        with self.assertRaises(ValueError):
            calendar_events(ics('DTSTART:20251104T133000Z'), 'BLS', NOW)
        text, _ = render({**snapshot(), 'calendar': {}}, {}, NOW)
        self.assertIn('Some calendar inputs unavailable', text)
        self.assertIn('Calendar coverage is incomplete', text)

    def test_latest_cancelled_revision_and_nonheadline_jobs_are_not_promoted(self):
        text = ics().decode().replace('END:VCALENDAR', '')
        text += 'BEGIN:VEVENT\nUID:test\nSEQUENCE:1\nSTATUS:CANCELLED\nDTSTART:20261104T133000Z\nSUMMARY:Consumer Price Index\nEND:VEVENT\n'
        text += 'BEGIN:VEVENT\nUID:other\nDTSTART:20261105T133000Z\nSUMMARY:Employment Situation of Veterans\nEND:VEVENT\nEND:VCALENDAR'
        self.assertEqual(calendar_events(text.encode(), 'BLS', NOW), [])

    def test_elapsed_schedule_does_not_claim_a_verified_result(self):
        early = calendar_events(ics('DTSTART:20261104T073000Z')[:-len(b'END:VCALENDAR')]+
            b'BEGIN:VEVENT\nDTSTART:20261105T133000Z\nSUMMARY:Consumer Price Index\nEND:VEVENT\nEND:VCALENDAR', 'BLS', NOW)
        lines, _ = calendar_lines({'calendar': {'checked_at': NOW.isoformat(), 'events': early}}, NOW)
        self.assertIn('Scheduled time passed; result unverified', lines[0])


class MoverTests(unittest.TestCase):
    def test_ranking_signs_liquidity_and_stable_filters(self):
        data = payload()
        for symbol, turnover in [('USDCUSDT', '999999999'), ('BTC3LUSDT', '999999999'), ('TINYUSDT', '100')]:
            data['result']['list'].append({'symbol': symbol, 'price24hPcnt': '5', 'turnover24h': turnover, 'lastPrice': '1'})
        movers = spot_movers(data, NOW)
        self.assertEqual([r['symbol'] for r in movers['gainers']], ['AAA', 'BBB', 'CCC'])
        self.assertEqual([r['symbol'] for r in movers['losers']], ['EEE', 'DDD', 'FFF'])
        self.assertEqual(movers['gainers'][0]['change_pct'], 20)
        self.assertEqual(movers['eligible_count'], 6)

    def test_stale_nan_duplicate_and_nonspot_payloads_are_rejected(self):
        for mutate in [lambda p: p.update(time=int((NOW-timedelta(minutes=6)).timestamp()*1000)),
                       lambda p: p['result'].update(category='linear'),
                       lambda p: p['result']['list'][0].update(price24hPcnt='nan'),
                       lambda p: p['result']['list'].append(p['result']['list'][0])]:
            data = payload(); mutate(data)
            with self.assertRaises(ValueError):
                spot_movers(data, NOW)

    def test_never_fills_losers_with_positive_performers(self):
        data = payload()
        for row in data['result']['list']:
            row['price24hPcnt'] = '.1'
        movers = spot_movers(data, NOW)
        lines = mover_lines({'movers': movers}, NOW)
        self.assertIn('Top 3 losers: No qualifying losers.', lines)
        self.assertIn('Fewer than three qualifying losers in this snapshot.', lines)

    def test_stale_or_missing_rankings_are_explicitly_unavailable(self):
        self.assertIn('unavailable', mover_lines({}, NOW)[0])
        self.assertIn('unavailable', mover_lines(snapshot(), NOW+timedelta(minutes=6))[0])


class CatalystAndIntegrationTests(unittest.TestCase):
    def test_verified_catalyst_explains_impact_and_assets(self):
        text, assessment = render(snapshot(), {'news': [editorial()]}, NOW)
        self.assertIn('Why it matters: Activity may change', text)
        self.assertIn('Watch: ETH', text)
        self.assertEqual(assessment['verified_news_count'], 1)
        for change in ({'status': 'rumor'}, {'impact_copy': 'Nansen says buy'}, {'affected_assets': ['secret link']}):
            self.assertFalse(editorial_items({'news': [{**editorial(), **change}]}, 'news', NOW)[0])

    def test_forecast_previous_actual_and_release_status(self):
        row = editorial('events')
        events, _ = editorial_items({'events': [row]}, 'events', NOW)
        self.assertIn('Forecast: 2.5%', events[0])
        self.assertIn('result pending', events[0])
        self.assertFalse(editorial_items({'events': [{**row, 'actual': '2.6%'}]}, 'events', NOW)[0])
        row.update(event_at=(NOW-timedelta(minutes=30)).isoformat(), actual='2.6%')
        events, _ = editorial_items({'events': [row]}, 'events', NOW)
        self.assertIn('Released; result verified', events[0])

    def test_updated_brief_replaces_status_and_stays_bounded(self):
        text, _ = render(snapshot(), {'news': [editorial()], 'events': [editorial('events')]}, NOW)
        self.assertIn('ECONOMIC CALENDAR', text)
        self.assertIn('Top 3 gainers:\n1. AAA +20.00%', text)
        self.assertIn('Top 3 losers:\n1. EEE -20.00%', text)
        self.assertNotIn('CRYPTOEDGE STATUS', text)
        self.assertNotIn('bybit', text.lower())
        self.assertLessEqual(len(text.encode('utf-16-le'))//2, 3900)

    def test_roundups_run_monday_and_friday_with_links_and_deduplication(self):
        from intelligence.formatting import telegram_html

        for offset in (1, 2, 5):
            now = NOW + timedelta(days=offset)
            item = {**snapshot(), 'as_of': now.isoformat(), 'official_updates': {
                'tokens': [{'copy': 'SOL: Client release', 'url': 'https://example.org/sol'}],
                'defi': [{'copy': 'Uniswap: Update', 'url': 'https://example.org/original?utm_source=test'}],
            }}
            news = {**editorial(), 'published_at': now.isoformat(), 'verified_at': now.isoformat(),
                    'valid_from': now.isoformat(), 'valid_until': (now+timedelta(hours=2)).isoformat(),
                    'source_url': 'https://example.org/original'}
            text, _ = render(item, {'news': [news]}, now)
            html = telegram_html(text)
            self.assertEqual('DEFI DEVELOPMENTS' in html, offset in (2, 5))
            self.assertEqual('TOP TOKEN UPDATES' in html, offset in (2, 5))
            self.assertEqual('https://example.org/sol' in html, offset in (2, 5))
            self.assertEqual(html.count('https://example.org/original'), 1)
            self.assertIn('TOP GAINERS &amp; LOSERS', html)

    def test_full_length_editorial_fits_by_omitting_whole_extra_items(self):
        news = [{**editorial(), 'id': str(i), 'source_url': f'https://example.org/news/{i}', 'subscriber_copy': '\U0001f535'*220,
                 'impact_copy': 'y'*120, 'affected_assets': ['ABCDEFGHIJKL']*5} for i in range(3)]
        events = [{**editorial('events'), 'id': str(i), 'subscriber_copy': 'z'*140,
                   'forecast': 'f'*30, 'previous': 'p'*30} for i in range(3)]
        item = snapshot()
        item['markets'] = {s: {'stance': 'up'} for s in SYMBOLS}
        item['defi'] = [{'name': 'A'*60, 'change_7d': 8}, {'name': 'B'*60, 'change_7d': -8}]
        for index, row in enumerate(item['movers']['gainers']+item['movers']['losers']):
            row['symbol'] = 'ABCDEFGHIJKLMNOPQRS'+str(index)
        text, _ = render(item, {'news': news, 'events': events}, NOW)
        self.assertLessEqual(len(text.encode('utf-16-le'))//2, 3900)
        self.assertIn('Additional items omitted', text)
        self.assertIn('Top 3 gainers', text)

    def test_supplementary_outages_do_not_erase_main_assessment(self):
        rows = [{'slug': s, 'name': s, 'tvl': 1, 'change_7d': 0} for s in ('aave-v3','uniswap-v3','hyperliquid-bridge')]
        def fake_json(url):
            if 'llama' in url:
                return rows
            raise TimeoutError()
        with patch('intelligence.core.market', return_value={'stance': 'mixed'}), patch('intelligence.core.get_json', side_effect=fake_json), patch('intelligence.core.fetch', side_effect=TimeoutError()), patch('intelligence.defi.governance', side_effect=TimeoutError()):
            item = collect(NOW, [])
        self.assertFalse(item['failures'])
        text, _ = render(item, {}, NOW)
        self.assertIn('Mixed; wait for confirmation', text)
        self.assertIn('gainers and losers unavailable', text)
        self.assertIn('Some calendar inputs unavailable', text)


if __name__ == '__main__':
    unittest.main()
