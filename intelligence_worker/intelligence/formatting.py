"""Readable plain-text previews and escaped Telegram HTML presentation."""
import html
import re
from urllib.parse import urlsplit, urlunsplit

HEADINGS = {
    'MARKET HEADLINES', 'COMING UP — ECONOMIC CALENDAR (UK TIMES)', 'DEFI WATCH',
    'DEFI DEVELOPMENTS', 'TOP TOKEN UPDATES', 'WATCHLIST', 'WHAT CHANGES THE VIEW', 'TOP GAINERS & LOSERS — 24H',
    'Top 3 gainers:', 'Top 3 losers:',
}


def checked_source(value):
    if len(value) > 512 or any(character.isspace() or ord(character) < 32 for character in value):
        raise ValueError('Invalid public source URL')
    url = urlsplit(value)
    if url.scheme != 'https' or not url.hostname or url.username or url.password:
        raise ValueError('Invalid public source URL')
    return urlunsplit((url.scheme, url.netloc.lower(), url.path.rstrip('/'), '', ''))


def visible_text(text):
    return re.sub(r'^  Source: https://[^\s]+$', '  Source', text, flags=re.MULTILINE)


def arrange(text):
    result = []
    for line in text.splitlines():
        if line.startswith(('Top 3 gainers: ', 'Top 3 losers: ')):
            heading, body = line.split(': ', 1)
            result += ['', heading+':']
            if body.startswith('No qualifying'):
                result.append(body)
            else:
                result += [str(i)+'. '+value for i, value in enumerate(body.split(' | '), 1)]
            continue
        if line.startswith('• '):
            # Keep each reviewed item together, with its facts and implications on separate lines.
            for label in ('Why it matters:', 'Watch:', 'Previous:', 'Forecast:', 'Actual:'):
                line = line.replace(' '+label, '\n  '+label)
            line = re.sub(r' (Scheduled; result pending\.|Scheduled time passed; result unverified\.|Released; result verified\.)',
                          r'\n  \1', line)
            result += [line, '']
        elif line.startswith('  Source: ') and result and result[-1] == '':
            result[-1:] = [line, '']
        elif re.match(r'^(BTC|ETH|SOL|XRP|HYPE): ', line):
            result.append('• '+line)
        else:
            result.append(line)
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(result)).strip()


def telegram_html(text):
    result = []
    in_headlines = False
    for index, line in enumerate(text.splitlines()):
        if line in HEADINGS:
            in_headlines = line in {'MARKET HEADLINES', 'DEFI DEVELOPMENTS', 'TOP TOKEN UPDATES'}
        escaped = html.escape(line, quote=False)
        if (index == 0 and line.startswith('CRYPTOEDGELAB')) or line in HEADINGS or line.startswith('MARKET OUTLOOK: '):
            escaped = '<b>'+escaped+'</b>'
        elif in_headlines and line.startswith('  Source: '):
            source = checked_source(line.removeprefix('  Source: '))
            escaped = '  <a href="'+html.escape(source, quote=True)+'">Source</a>'
        elif in_headlines and line.startswith('• '):
            label, separator, copy = escaped.partition(': ')
            escaped = '<b>'+label+('</b>'+separator+copy if separator else '</b>')
        elif line == 'DEMONSTRATION — FICTIONAL DATA':
            escaped = '<b>'+escaped+'</b>'
        elif re.match(r'^• (BTC|ETH|SOL|XRP|HYPE): ', line):
            label, body = line.split(': ', 1)
            escaped = '<b>'+html.escape(label, quote=False)+':</b> '+html.escape(body, quote=False)
        elif re.match(r'^  (Why it matters|Watch|Previous|Forecast|Actual): ', line):
            label, body = line.split(': ', 1)
            escaped = '<b>'+html.escape(label, quote=False)+':</b> '+html.escape(body, quote=False)
        result.append(escaped)
    return '\n'.join(result)
