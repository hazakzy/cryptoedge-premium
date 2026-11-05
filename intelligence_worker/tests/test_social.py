import contextlib
import io
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intelligence.core import SYMBOLS, instant, render
from intelligence.runner import Worker, main, settings
from intelligence.social import XDelivery, publish_x, x_summary

NOW = instant('2026-11-03T08:00:00Z')


def brief(stance='mixed', mode='live'):
    return render({'mode': mode, 'as_of': NOW.isoformat(), 'failures': {},
        'markets': {s: {'stance': stance} for s in SYMBOLS}, 'defi': []}, {}, NOW)[0]


def config():
    return settings({'INTELLIGENCE_PUBLICATION_ENABLED': 'true',
        'INTELLIGENCE_DATA_RIGHTS_CONFIRMED': 'true', 'TELEGRAM_BOT_TOKEN': 'fake',
        'INTELLIGENCE_X_ENABLED': 'true', 'INTELLIGENCE_X_HANDLE': '@cryptoedge',
        'BUFFER_API_KEY': 'private-fake', 'BUFFER_X_CHANNEL_ID': 'channel-id'})


def produced(c, now):
    return brief(), {'complete': True}, NOW+timedelta(minutes=20)


class SocialTests(unittest.TestCase):
    def test_all_outlooks_fit_standard_x_length_and_link_to_actual_edition(self):
        for stance in ('up', 'down', 'mixed', 'flat'):
            text = x_summary(brief(stance), '@cryptoedgelab', 123)
            link = 'https://t.me/cryptoedgelab/123'
            self.assertTrue(text.isascii())
            self.assertLessEqual(len(text)-len(link)+23, 280)
            self.assertIn(link, text)
            self.assertIn('03 Nov 2026 | 08:00', text)
            self.assertIn('not an entry signal', text)
            self.assertNotIn('UTC', text)

    def test_demo_is_labelled_and_incomplete_assessment_is_held(self):
        self.assertIn('DEMO - FICTIONAL', x_summary(brief(mode='demonstration'), '@cryptoedgelab'))
        for text in (brief()+'\nCoverage is incomplete', brief().replace('Mixed; wait for confirmation', 'Assessment limited')):
            with self.assertRaises(ValueError):
                x_summary(text, '@cryptoedgelab')

    def test_expiry_and_uncertain_send_never_retry(self):
        item = XDelivery(brief(), NOW+timedelta(minutes=20))
        sender = Mock(side_effect=TimeoutError('secret-key'))
        self.assertEqual(item.dispatch(config(), NOW, 1, sender), 'uncertain')
        self.assertIsNone(item.dispatch(config(), NOW, 1, sender))
        sender.assert_called_once()
        self.assertEqual(item.brief, '')
        item = XDelivery(brief(), NOW)
        self.assertEqual(item.dispatch(config(), NOW, 1, Mock(side_effect=AssertionError)), 'expired')

    def test_buffer_validates_destination_then_uses_share_now(self):
        destination = {'channel': {'id': 'channel-id', 'name': 'CryptoEdge', 'service': 'twitter',
            'isDisconnected': False, 'isLocked': False, 'isQueuePaused': False}}
        request = Mock(side_effect=[destination, {'createPost': {'post': {'id': 'post-id'}}}])
        self.assertEqual(publish_x('token', 'channel-id', '@cryptoedge', 'text', request), 'accepted')
        payload = request.call_args.args[2]['input']
        self.assertEqual(payload['mode'], 'shareNow')
        self.assertFalse(payload['saveToDraft'])
        self.assertEqual(payload['assets'], [])
        for changes in ({'service': 'instagram'}, {'name': 'another'}, {'isLocked': True},
                        {'isDisconnected': True}, {'isQueuePaused': True}):
            request = Mock(return_value={'channel': {**destination['channel'], **changes}})
            with self.assertRaises(ValueError):
                publish_x('token', 'channel-id', '@cryptoedge', 'text', request)
            request.assert_called_once()

    def test_buffer_mutation_errors_are_not_reported_as_accepted(self):
        destination = {'channel': {'id': 'channel-id', 'name': 'cryptoedge', 'service': 'twitter',
            'isDisconnected': False, 'isLocked': False, 'isQueuePaused': False}}
        with self.assertRaises(ValueError):
            publish_x('token', 'channel-id', 'cryptoedge', 'text', Mock(side_effect=[
                destination, {'createPost': {'message': 'Queue full'}}]))

    def test_x_runs_once_only_after_successful_telegram_send(self):
        worker = Worker(config(), NOW-timedelta(minutes=1), sending=True)
        x_sender = Mock(return_value='accepted')
        event = worker.tick(NOW, produced, lambda *_: {'ok': True, 'result': {'message_id': 8}}, x_sender)
        self.assertEqual(event['delivery'], 'sent')
        self.assertEqual(event['x_delivery'], 'accepted')
        self.assertIn('https://t.me/cryptoedgelab/8', x_sender.call_args.args[3])
        self.assertIsNone(worker.tick(NOW+timedelta(minutes=1), produced, None, x_sender))
        x_sender.assert_called_once()

    def test_no_x_on_preview_disabled_failed_or_incomplete_telegram(self):
        for reply in ({'error_code': 403}, {'error_code': 500},
                      {'error_code': 429, 'parameters': {'retry_after': 60}}):
            worker = Worker(config(), NOW-timedelta(minutes=1), sending=True)
            x_sender = Mock(side_effect=AssertionError('Should not send'))
            worker.tick(NOW, produced, lambda *_: reply, x_sender)
            x_sender.assert_not_called()
        for sending, cfg in ((False, config()), (True, {**config(), 'x_enabled': False})):
            worker = Worker(cfg, NOW-timedelta(minutes=1), sending=sending)
            x_sender = Mock()
            worker.tick(NOW, produced, lambda *_: {'ok': True, 'result': {'message_id': 8}}, x_sender)
            x_sender.assert_not_called()
        worker = Worker(config(), NOW-timedelta(minutes=1), sending=True)
        x_sender = Mock()
        worker.tick(NOW, lambda *_: ('partial', {'complete': False}, NOW), Mock(), x_sender)
        x_sender.assert_not_called()

    def test_telegram_rate_limit_then_success_posts_x_once(self):
        worker = Worker(config(), NOW-timedelta(minutes=1), sending=True)
        telegram = Mock(side_effect=[{'error_code': 429, 'parameters': {'retry_after': 60}},
                                    {'ok': True, 'result': {'message_id': 9}}])
        x_sender = Mock(return_value='accepted')
        worker.tick(NOW, produced, telegram, x_sender)
        x_sender.assert_not_called()
        event = worker.tick(NOW+timedelta(minutes=1), produced, telegram, x_sender)
        self.assertEqual(event['x_delivery'], 'accepted')
        x_sender.assert_called_once()

    def test_x_failure_does_not_resend_telegram_or_leak_secrets(self):
        worker = Worker(config(), NOW-timedelta(minutes=1), sending=True)
        telegram = Mock(return_value={'ok': True, 'result': {'message_id': 7}})
        x_sender = Mock(side_effect=TimeoutError('private-fake'))
        event = worker.tick(NOW, produced, telegram, x_sender)
        self.assertEqual(event['delivery'], 'sent')
        self.assertEqual(event['x_delivery'], 'uncertain')
        self.assertNotIn('private-fake', str(event))
        worker.tick(NOW+timedelta(minutes=1), produced, telegram, x_sender)
        telegram.assert_called_once()
        x_sender.assert_called_once()

    def test_missing_x_settings_hold_x_but_allow_telegram(self):
        self.assertFalse(settings({})['x_enabled'])
        cfg = {**config(), 'buffer_token': ''}
        worker = Worker(cfg, NOW-timedelta(minutes=1), sending=True)
        x_sender = Mock()
        event = worker.tick(NOW, produced, lambda *_: {'ok': True, 'result': {'message_id': 8}}, x_sender)
        self.assertEqual(event['delivery'], 'sent')
        self.assertEqual(event['x_delivery'], 'held_config')
        x_sender.assert_not_called()

    def test_draft_cli_never_delivers(self):
        with patch.object(sys, 'argv', ['runner', '--x-draft', '--worker']), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main()


if __name__ == '__main__':
    unittest.main()
