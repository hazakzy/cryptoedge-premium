"""Telegram delivery in memory only. No database, files or automatic uncertain retries."""
import json
import urllib.error
import urllib.request
from datetime import timedelta


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def telegram(token, channel, text):
    body = json.dumps({'chat_id': channel, 'text': text,
        'link_preview_options': {'is_disabled': True}}).encode()
    request = urllib.request.Request('https://api.telegram.org/bot'+token+'/sendMessage',
        data=body, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=15) as response:
            return json.loads(response.read(100_000))
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read(100_000))
        except (ValueError, UnicodeError):
            return {'ok': False, 'error_code': exc.code}


class Delivery:
    def __init__(self, text, channel, now, expires):
        self.text, self.channel = text, channel
        self.expires, self.next_at = expires, now
        self.state, self.message_id = 'pending', None

    def dispatch(self, token, now, sender=None):
        if self.state != 'pending':
            return None
        if now >= self.expires:
            self.state, self.text = 'expired', ''
            return self.state
        if now < self.next_at:
            return None
        self.state = 'sending'  # Claim first, including if interrupted during the call.
        try:
            response = (sender or telegram)(token, self.channel, self.text)
            if response.get('ok') and response.get('result', {}).get('message_id'):
                self.state, self.message_id = 'sent', response['result']['message_id']
            elif response.get('error_code') == 429:
                delay = max(1, min(86400, int(response.get('parameters', {}).get('retry_after', 60))))
                self.state, self.next_at = 'pending', now+timedelta(seconds=delay)
            elif response.get('error_code') in (400, 401, 403, 404):
                self.state = 'failed'
            else:
                self.state = 'uncertain'
        except Exception:
            self.state = 'uncertain'
        if self.state != 'pending':
            self.text = ''
        return self.state
