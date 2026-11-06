import contextlib
import io
import json
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intelligence.central_banks import decisions
from intelligence.core import SYMBOLS, calendar_lines, defi_metric_lines, instant, render
from intelligence.defi import activity, collect_defi, governance_rows, stable_supply
from intelligence.discovery import announcements
from intelligence.runner import main

NOW = instant('2026-11-06T08:00:00Z')


def metric(name='Aave'):
    return {'name': name, 'total24h': 1200000, 'total48hto24h': 1000000,
        'totalDataChart': [[int((NOW-timedelta(hours=8)).timestamp()), 1200000]], 'latestFetchIsOk': True}


def supplies():
    return {'peggedAssets': [{'symbol': s, 'pegType': 'peggedUSD',
        'circulating': {'peggedUSD': 110}, 'circulatingPrevWeek': {'peggedUSD': 100}}
        for s in ('USDT', 'USDC')]}


def vote():
    return {'id': 'proposal-id', 'space': {'id': 'uniswapgovernance.eth'}, 'title': 'Fictional fee proposal',
        'start': int((NOW-timedelta(days=2)).timestamp()), 'end': int((NOW+timedelta(hours=4)).timestamp()), 'state': 'active'}


class CentralBankTests(unittest.TestCase):
    def test_fed_second_day_and_new_york_dst_to_uk(self):
        raw = b'<h4>2026 FOMC Meetings</h4><div>March</div><div>17-18*</div><div>December</div><div>8-9</div>'
        rows = decisions(raw, 'Fed', instant('2026-03-18T08:00:00Z'))
        self.assertEqual(rows[0]['event_at'], '2026-03-18T18:00:00+00:00')
        self.assertEqual(rows[0]['priority'], 0)
        self.assertEqual(decisions(raw, 'Fed', instant('2026-03-17T08:00:00Z')), [])

    def test_boe_uses_official_year_sections_and_noon_uk(self):
        raw = b'<h2>2026 confirmed dates</h2><table><tr><td>Thursday 17 December</td></tr></table><h2>2027 confirmed dates</h2><p>Thursday 4 February</p>'
        rows = decisions(raw, 'BoE', instant('2026-12-17T08:00:00Z'))
        self.assertEqual(rows[0]['event_at'], '2026-12-17T12:00:00+00:00')

    def test_ecb_skips_nonpolicy_and_first_day(self):
        raw = b'<dl><dt>16/12/2026</dt><dd>monetary policy meeting (Day 1)</dd><dt>17/12/2026</dt><dd>monetary policy meeting (Day 2), followed by press conference</dd><dt>18/12/2026</dt><dd>non-monetary policy meeting (Day 2)</dd></dl>'
        rows = decisions(raw, 'ECB', instant('2026-12-17T08:00:00Z'))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['event_at'], '2026-12-17T13:15:00+00:00')

    def test_changed_or_expired_calendars_are_unavailable_not_quiet(self):
        for source in ('Fed', 'BoE', 'ECB'):
            with self.assertRaises(ValueError):
                decisions(b'<p>Calendar currently unavailable</p>', source, NOW)
        with self.assertRaises(ValueError):
            decisions(b'<h4>2025 FOMC Meetings</h4><div>January</div><div>28-29</div>', 'Fed', NOW)

    def test_expected_source_coverage_and_decision_priority(self):
        cal = {'checked_at': NOW.isoformat(), 'expected_sources': ['BLS','BEA','Fed','BoE','ECB'],
            'sources_ok': ['BLS','BEA'], 'events': [
                {'name':'US CPI','event_at':(NOW+timedelta(hours=1)).isoformat(),'relevance':'Inflation. '},
                {'name':'Fed rate decision','event_at':(NOW+timedelta(hours=10)).isoformat(),'relevance':'Rates.','priority':0}]}
        lines, limited = calendar_lines({'calendar': cal}, NOW)
        self.assertTrue(limited)
        self.assertIn('Fed rate decision', lines[0])


class DefiTests(unittest.TestCase):
    def test_activity_compares_reporting_periods_once(self):
        row = activity(metric(), NOW, 'Aave fees')
        self.assertAlmostEqual(row['change_pct'], 20)
        for change in ({'total24h': float('nan')}, {'total48hto24h': 0}, {'latestFetchIsOk': False},
                       {'name': 'Other'}, {'totalDataChart': [[int((NOW-timedelta(days=4)).timestamp()),1]]}):
            with self.assertRaises(ValueError):
                activity({**metric(), **change}, NOW, 'Aave fees')

    def test_supply_is_scoped_nominal_supply_not_a_price_return(self):
        rows = stable_supply(supplies(), NOW)
        self.assertAlmostEqual(rows[0]['change_7d'], 10)
        bad = supplies(); bad['peggedAssets'].append(bad['peggedAssets'][0])
        with self.assertRaises(ValueError):
            stable_supply(bad, NOW)

    def test_votes_must_be_active_in_allowed_space_and_closing_soon(self):
        self.assertEqual(len(governance_rows([vote()], NOW)), 1)
        for changes in ({'state':'closed'}, {'end':int((NOW-timedelta(seconds=1)).timestamp())},
                        {'start':int((NOW+timedelta(hours=1)).timestamp())},
                        {'space':{'id':'impersonator.eth'}}, {'end':int((NOW+timedelta(days=2)).timestamp())}):
            self.assertFalse(governance_rows([{**vote(), **changes}], NOW))

    def test_collection_is_partial_when_one_source_fails(self):
        def get(url):
            if 'dailyRevenue' in url: raise TimeoutError()
            return supplies() if 'stablecoins' in url else metric()
        result = collect_defi(NOW, get, lambda now: [])
        self.assertEqual(result['unavailable'], ['revenue'])
        self.assertEqual(len(result['activity']), 2)
        self.assertEqual(len(result['stablecoins']), 2)

    def test_public_copy_avoids_flow_and_execution_claims(self):
        data = collect_defi(NOW, lambda url: supplies() if 'stablecoins' in url else metric(), lambda now: governance_rows([vote()], now))
        lines, note = defi_metric_lines({'defi_metrics': data}, NOW)
        self.assertIn('Supply change is not exchange inflow', '\n'.join(lines))
        self.assertIn('not an executed change', '\n'.join(lines))
        self.assertIn('do not imply token-holder returns', note)
        self.assertNotIn('Snapshot', '\n'.join(lines))

    def test_stale_extended_data_is_not_reused(self):
        lines, note = defi_metric_lines({'defi_metrics': {'checked_at':(NOW-timedelta(hours=1)).isoformat()}}, NOW)
        self.assertFalse(lines)
        self.assertIn('unavailable', note)

    def test_full_edition_with_expanded_data_stays_within_telegram_budget(self):
        data = collect_defi(NOW, lambda url: supplies() if 'stablecoins' in url else metric(), lambda now: governance_rows([vote()], now))
        snap = {'mode':'live','as_of':NOW.isoformat(),'failures':{}, 'markets':{s:{'stance':'up'} for s in SYMBOLS},
                'defi':[{'name':'Aave','change_7d':8}], 'defi_metrics':data}
        text, _ = render(snap, {}, NOW)
        self.assertIn('Aave fees', text)
        self.assertLessEqual(len(text.encode('utf-16-le'))//2, 3900)


class ResearchTests(unittest.TestCase):
    def test_date_only_announcements_remain_unverified_and_do_not_invent_a_time(self):
        raw = b'<a href="/example">Example upgrade November 06, 2026</a><a href="https://evil.test/post">Bad November 06, 2026</a>'
        rows = announcements(raw, NOW)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'unverified_candidate')
        self.assertNotIn('published_at', rows[0])
        self.assertFalse(announcements(raw, NOW-timedelta(days=1)))

    def test_private_research_cli_cannot_publish(self):
        with patch.object(sys, 'argv', ['runner','--research','--deliver','--publish-now']), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit): main()
        output = io.StringIO()
        with patch.object(sys, 'argv', ['runner','--research']), patch('intelligence.runner.collect', return_value={'news_candidates':[]}), patch('intelligence.runner.Delivery', side_effect=AssertionError('Send')), contextlib.redirect_stdout(output):
            main()
        self.assertEqual(json.loads(output.getvalue())['news_candidates'], [])


if __name__ == '__main__': unittest.main()
