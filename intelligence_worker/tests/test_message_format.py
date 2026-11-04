import json
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intelligence.delivery import telegram
from intelligence.formatting import telegram_html


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.tags = [], []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, attrs))


class TelegramFormattingTests(unittest.TestCase):
    def test_html_preserves_text_and_escapes_editorial_markup(self):
        text = 'CRYPTOEDGELAB — DAILY MARKET BRIEF\n\nTOP GAINERS & LOSERS — 24H\n• <script>alert("x")</script> & <b>untrusted</b> 🔵\n  Why it matters: A < B & C > D'
        parser = PlainText()
        parser.feed(telegram_html(text))
        self.assertEqual(''.join(parser.parts), text)
        self.assertTrue(parser.tags)
        self.assertTrue(all(tag == 'b' and not attrs for tag, attrs in parser.tags))

    def test_actual_telegram_payload_enables_html_without_changing_channel(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"ok":true,"result":{"message_id":1}}'
        opener = MagicMock()
        opener.open.return_value = response
        with patch('intelligence.delivery.urllib.request.build_opener', return_value=opener):
            result = telegram('fake-token', '@cryptoedgelab', 'WATCHLIST\n• BTC: Wait & confirm.')
        payload = json.loads(opener.open.call_args.args[0].data)
        self.assertEqual(payload['chat_id'], '@cryptoedgelab')
        self.assertEqual(payload['parse_mode'], 'HTML')
        self.assertIn('<b>WATCHLIST</b>', payload['text'])
        self.assertIn('Wait &amp; confirm.', payload['text'])
        self.assertTrue(result['ok'])
