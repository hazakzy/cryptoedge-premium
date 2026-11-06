"""Original-source announcement metadata for private editorial review only."""
import hashlib
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


def announcements(raw, now):
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
        if not now.date()-timedelta(days=2) <= date <= now.date() or url in seen:
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
