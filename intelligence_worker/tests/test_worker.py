import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intelligence.core import collect, instant, render, SYMBOLS
from intelligence.delivery import Delivery
from intelligence.runner import Worker, main, prepare, settings

NOW = instant('2026-11-02T08:00:00Z')


def config():
    return settings({'INTELLIGENCE_PUBLICATION_ENABLED':'true', 'INTELLIGENCE_DATA_RIGHTS_CONFIRMED':'true',
        'TELEGRAM_BOT_TOKEN':'not-a-real-token'})


def snapshot():
    return {'mode':'live', 'as_of':NOW.isoformat(), 'markets':{s:{'stance':'up'} for s in SYMBOLS},
        'defi':[{'name':'Aave', 'change_7d':8}], 'failures':{}}


def produced(c, now):
    return 'Full original brief', {'complete':True, 'outlook':'Mixed', 'failures':0}, now+timedelta(minutes=20)


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.item = Delivery('brief', '@cryptoedgelab', NOW, NOW+timedelta(minutes=20))

    def test_success_is_not_resent(self):
        sender = lambda *_:{'ok':True, 'result':{'message_id':5}}
        self.assertEqual(self.item.dispatch('token', NOW, sender), 'sent')
        self.assertEqual(self.item.message_id, 5)
        self.assertIsNone(self.item.dispatch('token', NOW, lambda *_:self.fail('Duplicate')))
        self.assertEqual(self.item.text, '')

    def test_timeout_or_unknown_response_is_held(self):
        def timeout(*_):
            raise TimeoutError('secret must never reach logs')
        self.assertEqual(self.item.dispatch('token', NOW, timeout), 'uncertain')
        self.assertIsNone(self.item.dispatch('token', NOW, lambda *_:self.fail('Uncertain retry')))

    def test_server_error_is_not_blindly_retried(self):
        self.assertEqual(self.item.dispatch('token', NOW, lambda *_:{'ok':False,'error_code':500}), 'uncertain')

    def test_crash_claim_stays_held(self):
        def crash(*_):
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.item.dispatch('token', NOW, crash)
        self.assertEqual(self.item.state, 'sending')
        self.assertIsNone(self.item.dispatch('token', NOW, lambda *_:self.fail('Crash retry')))

    def test_rate_limit_retries_only_when_due(self):
        self.assertEqual(self.item.dispatch('token', NOW, lambda *_:{'error_code':429,'parameters':{'retry_after':60}}), 'pending')
        self.assertIsNone(self.item.dispatch('token', NOW+timedelta(seconds=59), lambda *_:self.fail('Early retry')))
        self.assertEqual(self.item.dispatch('token', NOW+timedelta(seconds=60), lambda *_:{'ok':True,'result':{'message_id':6}}), 'sent')

    def test_expired_messages_never_send(self):
        self.assertEqual(self.item.dispatch('token', NOW+timedelta(minutes=20), lambda *_:self.fail('Stale send')), 'expired')

    def test_permanent_rejections_are_not_retried(self):
        self.assertEqual(self.item.dispatch('token', NOW, lambda *_:{'error_code':403}), 'failed')
        self.assertIsNone(self.item.dispatch('token', NOW, lambda *_:self.fail('Rejected retry')))


class WorkerTests(unittest.TestCase):
    def test_single_daily_send_in_running_process(self):
        worker = Worker(config(), NOW-timedelta(minutes=1), sending=True)
        calls=[]
        def sender(*args):
            calls.append(args)
            return {'ok':True,'result':{'message_id':8}}
        self.assertEqual(worker.tick(NOW, produced, sender)['delivery'], 'sent')
        self.assertIsNone(worker.tick(NOW+timedelta(minutes=1), lambda *_:self.fail('Recollect'), sender))
        self.assertEqual(len(calls), 1)

    def test_restart_at_or_after_schedule_skips_day_without_disk_receipts(self):
        for offset in (0, 1, 1200, 3600):
            worker=Worker(config(), NOW+timedelta(seconds=offset), sending=True)
            self.assertIsNone(worker.tick(NOW+timedelta(seconds=offset+1), lambda *_:self.fail('Restart duplicate')))

    def test_next_day_can_send_after_restart_suppression(self):
        worker=Worker(config(), NOW, sending=True)
        event=worker.tick(NOW+timedelta(days=1), produced, lambda *_:{'ok':True,'result':{'message_id':2}})
        self.assertEqual(event['delivery'], 'sent')

    def test_incomplete_data_holds_delivery_and_can_recover_in_window(self):
        worker=Worker(config(), NOW-timedelta(minutes=1), sending=True)
        bad=lambda c,t:('partial', {'complete':False}, t+timedelta(minutes=20))
        self.assertEqual(worker.tick(NOW, bad, lambda *_:self.fail('Incomplete send'))['held'], 'incomplete_collection')
        self.assertEqual(worker.tick(NOW+timedelta(minutes=1), produced,
            lambda *_:{'ok':True,'result':{'message_id':4}})['delivery'], 'sent')

    def test_disabled_publication_cannot_start_sender(self):
        with self.assertRaises(ValueError):
            Worker(settings({}), NOW, sending=True)

    def test_preview_does_not_create_a_delivery(self):
        worker=Worker(settings({}), NOW-timedelta(seconds=1))
        self.assertEqual(worker.tick(NOW, produced, lambda *_:self.fail('Preview sent'))['mode'], 'preview')
        self.assertIsNone(worker.delivery)

    def test_live_processing_does_not_open_or_write_files(self):
        with patch('intelligence.runner.collect', return_value=snapshot()), patch('builtins.open', side_effect=AssertionError('File access')), patch('pathlib.Path.open', side_effect=AssertionError('File access')):
            text, status, _=prepare(config(), NOW)
        self.assertTrue(status['complete'])
        self.assertIn('TOP GAINERS & LOSERS', text)
        self.assertNotIn('GKC', text)
        self.assertNotIn('CRYPTOEDGE STATUS', text)

    def test_fixture_cli_cannot_send(self):
        with patch.object(sys, 'argv', ['runner','--fixture','fake.json','--deliver','--publish-now']), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main()

    def test_manual_send_needs_explicit_publish_now(self):
        with patch.object(sys, 'argv', ['runner','--deliver']), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main()

    def test_error_logs_do_not_expose_settings_or_credentials(self):
        output=io.StringIO()
        with patch.object(sys, 'argv', ['runner','--check']), patch('intelligence.runner.prepare', side_effect=ValueError('secret-token-in-url')), contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit):
                main()
        self.assertEqual(json.loads(output.getvalue()), {'worker_error':'ValueError'})

    def test_optional_orderflow_is_not_called_by_default(self):
        rows=[{'slug':s,'name':s,'tvl':1,'change_7d':0} for s in ('aave-v3','uniswap-v3','hyperliquid-bridge')]
        with patch('intelligence.core.market', return_value={'stance':'up'}), patch('intelligence.core.get_json', return_value=rows), patch('intelligence.core.private_order_flow', side_effect=AssertionError('Unused provider')):
            item=collect(NOW, [])
        self.assertEqual(item['failures'], {})
        self.assertNotIn('order_flow', item)

    def test_settings_reject_bad_time_channel_and_optional_flow_without_mapping(self):
        for env in ({'INTELLIGENCE_DAILY_TIME':'25:00'}, {'INTELLIGENCE_CHANNEL_ID':'https://bad'},
                    {'INTELLIGENCE_ORDER_FLOW_ENABLED':'true'}, {'INTELLIGENCE_PUBLICATION_ENABLED':'yes'},
                    {'INTELLIGENCE_EDITORIAL_JSON':'{"news":[1]}'}):
            with self.assertRaises(ValueError):
                settings(env)

    def test_unverified_news_and_no_calendar_are_disclosed(self):
        text, _=render(snapshot(), {}, NOW)
        self.assertIn('No verified material catalyst', text)
        self.assertIn('Calendar coverage is incomplete', text)
