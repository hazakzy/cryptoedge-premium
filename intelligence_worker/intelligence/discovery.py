"""Original-source announcement metadata for private editorial review only."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from xml.etree import ElementTree
import re
from datetime import datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

UNISWAP_BLOG = 'https://blog.uniswap.org/'


class BlogLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.href, self.parts = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.href = dict(attrs).get('href')
            self.parts = []

    def handle_data(self, data):
        if self.href:
            self.parts.append(data.strip())

    def handle_endtag(self, tag):
        if tag == 'a' and self.href:
            self.links.append((self.href, ' '.join(self.parts)))
            self.href, self.parts = None, []


def announcements(raw, now, days=2):
    parser = BlogLinks()
    parser.feed(raw.decode('utf-8-sig'))
    result, seen = [], set()
    for href, text in parser.links:
        url = urljoin(UNISWAP_BLOG, href)
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname != 'blog.uniswap.org' or not parsed.path.strip('/'):
            continue
        match = re.search(r'([A-Z][a-z]+ \d{1,2}, \d{4})', text)
        if not match:
            continue
        try:
            date = datetime.strptime(match[1], '%B %d, %Y').date()
        except ValueError:
            continue
        if not now.date()-timedelta(days=days) <= date <= now.date() or url in seen:
            continue
        title = ' '.join((text[:match.start()] or text[match.end():]).split())[:300]
        if not title:
            continue
        seen.add(url)
        result.append({'id': hashlib.sha256(url.encode()).hexdigest()[:16], 'url': url,
            'title': title, 'published_date': date.isoformat(), 'source': UNISWAP_BLOG,
            'category': 'protocol_announcement', 'status': 'unverified_candidate'})
    # Date-only publication metadata is intentionally NOT converted into a fabricated timestamp.
    return result[:10]


DEFI_BLOG_FEEDS = {'Lido': 'https://blog.lido.fi/rss/'}

RELEASE_REPOS = {
    'defi': {'Aave': 'aave/aave-v3-origin', 'Morpho': 'morpho-org/morpho-blue',
             'Pendle': 'pendle-finance/pendle-core-v2-public'},
    'tokens': {'BTC': 'bitcoin/bitcoin', 'ETH': 'ethereum/go-ethereum',
               'SOL': 'anza-xyz/agave', 'XRP': 'XRPLF/rippled'},
}
ATOM = '{http://www.w3.org/2005/Atom}'


def collect_official_updates(now, fetch, uniswap, parse_feed):
    """Read project releases on roundup days, with a four-day overlap for late editions."""

    def releases(source):
        subject, repo = source
        result = []
        try:
            feed = ElementTree.fromstring(fetch(f'https://github.com/{repo}/releases.atom'))
        except (OSError, ValueError, ElementTree.ParseError):
            return result
        for entry in feed.findall(ATOM+'entry'):
            title = ' '.join((entry.findtext(ATOM+'title') or '').split())
            link = entry.find(ATOM+'link')
            url = link.get('href', '') if link is not None else ''
            prefix = f'https://github.com/{repo}/releases/tag/'
            try:
                updated = datetime.fromisoformat(entry.findtext(ATOM+'updated', '').replace('Z', '+00:00'))
                fresh = now-timedelta(days=4) < updated <= now
            except (TypeError, ValueError):
                continue
            if title and url.startswith(prefix) and fresh:
                result.append((updated, {'copy': f'{subject}: Release entry updated {updated:%d %b} — {title[:95]}',
                                         'url': url}))
        return result

    def blog_announcements(source):
        subject, url = source
        try:
            rows = parse_feed(fetch(url), url, now, hours=96)
            return [row for row in rows if urlparse(row['url']).hostname == urlparse(url).hostname]
        except (OSError, ValueError, ElementTree.ParseError):
            return []

    dated_defi = [(row['published_date'], {'copy': 'Uniswap: '+row['title'][:150], 'url': row['url']})
                  for row in uniswap]
    result = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for kind, repos in RELEASE_REPOS.items():
            rows = [row for batch in pool.map(releases, repos.items()) for row in batch]
            if kind == 'defi':
                dated_defi.extend((updated.date().isoformat(), item) for updated, item in rows)
            else:
                result[kind] = [item for _, item in sorted(rows, key=lambda row: row[0], reverse=True)]
        for subject, rows in zip(DEFI_BLOG_FEEDS, pool.map(blog_announcements, DEFI_BLOG_FEEDS.items())):
            dated_defi.extend((row['published_at'][:10], {'copy': subject+': '+row['title'][:150], 'url': row['url']})
                              for row in rows)
    result['defi'] = [item for _, item in sorted(dated_defi, key=lambda row: row[0], reverse=True)]
    return result
