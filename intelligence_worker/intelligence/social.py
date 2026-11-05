"""Optional X summary through Buffer. No paid X API, SDK, database or disk writes."""
import json
import re
import urllib.request

from .delivery import NoRedirect


def x_summary(brief, channel, message_id=None):
    if not re.fullmatch(r'@[A-Za-z0-9_]{5,32}', channel):
        raise ValueError('X summaries require a public Telegram handle')
    lines = brief.splitlines()
    stamp = lines[1]
    if not re.fullmatch(r'\d{2} [A-Za-z]{3} \d{4} \| \d{2}:\d{2}', stamp):
        raise ValueError('Missing edition timestamp')
    outlook = next(line.removeprefix('MARKET OUTLOOK: ') for line in lines
                   if line.startswith('MARKET OUTLOOK: '))
    notes = {
        'Cautiously bullish': 'BTC continuation watch while support holds.',
        'Cautiously bearish': 'BTC structure is weak; recovery through resistance challenges the view.',
        'Mixed; wait for confirmation': 'BTC direction is unsettled. Wait for confirmation.',
        'Neutral': 'BTC has no clear directional preference.',
    }
    if outlook not in notes or 'Coverage is incomplete' in brief:
        raise ValueError('Incomplete assessment cannot promote an X outlook')
    link = 'https://t.me/'+channel[1:]
    if message_id is not None:
        if type(message_id) is not int or message_id <= 0:
            raise ValueError('Invalid Telegram message ID')
        link += '/'+str(message_id)
    demo = 'DEMO - FICTIONAL\n' if 'DEMONSTRATION' in brief else ''
    text = (demo+'CryptoEdge Morning Intelligence\n'+stamp+'\n\n'+notes[outlook]+
            '\nResearch watch, not an entry signal.\n\nFull free brief + separate BTC signals:\n'+link)
    # Fixed ASCII copy and one URL: X transforms the URL to 23 characters.
    if not text.isascii() or len(text)-len(link)+23 > 280:
        raise ValueError('X summary exceeds standard post length')
    return text


def buffer_request(token, query, variables):
    request = urllib.request.Request('https://api.buffer.com',
        data=json.dumps({'query': query, 'variables': variables}).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer '+token})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=15) as response:
        result = json.loads(response.read(100_000))
    if result.get('errors') or not isinstance(result.get('data'), dict):
        raise ValueError('Buffer request rejected')
    return result['data']


def publish_x(token, channel_id, handle, text, request=None):
    request = request or buffer_request
    # Confirm the configured destination is the connected X account, not another network.
    data = request(token, '''query Destination($input: ChannelInput!) {
        channel(input: $input) { id name service isDisconnected isLocked isQueuePaused }
    }''', {'input': {'id': channel_id}})
    channel = data['channel']
    if (channel['id'] != channel_id or channel['service'] != 'twitter' or
        channel['name'].lstrip('@').lower() != handle.lstrip('@').lower() or
        any(channel[k] for k in ('isDisconnected', 'isLocked', 'isQueuePaused'))):
        raise ValueError('Buffer X destination unavailable or mismatched')
    result = request(token, '''mutation PublishSummary($input: CreatePostInput!) {
        createPost(input: $input) {
            ... on PostActionSuccess { post { id } }
            ... on MutationError { message }
        }
    }''', {'input': {'channelId': channel_id, 'text': text, 'assets': [],
        'needsApproval': False, 'saveToDraft': False,
        'schedulingType': 'automatic', 'mode': 'shareNow'}})
    if not result.get('createPost', {}).get('post', {}).get('id'):
        raise ValueError('Buffer did not accept the post')
    # Acceptance is not proof of publication on X. Verify in Buffer / X.
    return 'accepted'


class XDelivery:
    def __init__(self, brief, expires):
        self.brief, self.expires, self.state = brief, expires, 'pending'

    def dispatch(self, config, now, message_id, sender=None):
        if self.state != 'pending':
            return None
        self.state = 'sending'  # Claim before network IO; never retry an uncertain mutation.
        try:
            if (not config['buffer_token'] or not config['buffer_channel'] or
                not re.fullmatch(r'@?[A-Za-z0-9_]{1,15}', config['x_handle']) or
                not config['channel'].startswith('@')):
                self.state = 'held_config'
            elif now >= self.expires:
                self.state = 'expired'
            else:
                text = x_summary(self.brief, config['channel'], message_id)
                result = (sender or publish_x)(config['buffer_token'], config['buffer_channel'],
                                               config['x_handle'], text)
                self.state = 'accepted' if result == 'accepted' else 'uncertain'
        except Exception:
            self.state = 'uncertain'
        finally:
            self.brief = ''
        return self.state
