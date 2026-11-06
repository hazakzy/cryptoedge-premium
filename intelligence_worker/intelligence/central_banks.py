"""Selected scheduled decisions from official central-bank calendars."""
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

UTC = timezone.utc
UK = ZoneInfo('Europe/London')
SOURCES = {
    'Fed': 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm',
    'BoE': 'https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates',
    'ECB': 'https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html',
}
MONTHS = 'January February March April May June July August September October November December'.split()
MONTH = '|'.join(MONTHS)


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1
        if tag in ('h2', 'h3', 'h4', 'div', 'tr', 'td', 'dt', 'dd', 'p', 'br'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip-1)
        if tag in ('h2', 'h3', 'h4', 'div', 'tr', 'td', 'dt', 'dd', 'p'):
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def decisions(raw, source, now):
    parser = VisibleText()
    parser.feed(raw.decode('utf-8-sig'))
    text = '\n'.join(' '.join(line.split()) for line in ''.join(parser.parts).splitlines() if line.strip())
    dates = []
    if source == 'Fed':
        sections = re.split(r'(\d{4}) FOMC Meetings', text)
        for index in range(1, len(sections), 2):
            year, body = int(sections[index]), sections[index+1]
            for match in re.finditer(r'(?m)^('+MONTH+r')\n(\d{1,2})(?:[-–](\d{1,2}))?\*?$', body):
                dates.append(datetime(year, MONTHS.index(match[1])+1, int(match[3] or match[2]),
                                      14, 0, tzinfo=ZoneInfo('America/New_York')))
        label, relevance = 'Fed rate decision', 'Rates and guidance may move yields, the dollar and crypto.'
    elif source == 'BoE':
        sections = re.split(r'(\d{4}) confirmed dates', text, flags=re.I)
        for index in range(1, len(sections), 2):
            year, body = int(sections[index]), sections[index+1]
            for match in re.finditer(r'\b(?:Monday|Tuesday|Wednesday|Thursday|Friday)\s+(\d{1,2})\s+('+MONTH+r')\b', body):
                dates.append(datetime(year, MONTHS.index(match[2])+1, int(match[1]), 12, 0, tzinfo=UK))
        label, relevance = 'BoE rate decision', 'Rates and guidance may move sterling and risk appetite.'
    elif source == 'ECB':
        # Only Day 2 monetary-policy meetings; non-policy meetings and Day 1 are excluded.
        for match in re.finditer(r'(\d{2}/\d{2}/\d{4})\n([^\n]+)', text):
            if 'monetary policy meeting' in match[2] and '(Day 2)' in match[2] and 'non-monetary' not in match[2]:
                dates.append(datetime.strptime(match[1], '%d/%m/%Y').replace(hour=14, minute=15, tzinfo=ZoneInfo('Europe/Berlin')))
        label, relevance = 'ECB rate decision', 'Rates and guidance may move the euro, yields and risk appetite.'
    else:
        raise ValueError('Unknown calendar source')
    if not dates or max(dates).astimezone(UTC) < now:
        raise ValueError('No current or future official schedule parsed')
    result = []
    for when in sorted(set(dates)):
        when = when.astimezone(UTC)
        if when.astimezone(UK).date() == now.astimezone(UK).date() or now <= when <= now+timedelta(hours=24):
            result.append({'name': label, 'event_at': when.isoformat(), 'relevance': relevance,
                           'source': source, 'priority': 0})
    return result
