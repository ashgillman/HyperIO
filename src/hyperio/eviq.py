"""Refreshable, source-linked eviQ OAR catalogue and conservative DVH points.

Only complete, unambiguous physical-dose Vx/Dx expressions become plot points.
All other wording remains available for manual review.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urljoin, urlsplit
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser


from .dvh_goals import load_catalogue, overlay_points, parse_point as parse_goal_point


ROOT = 'https://www.eviq.org.au'
AGENT = 'HyperIO-eviQ/1.0'
DEFAULT_CATALOGUE = Path.home() / '.hyperio' / 'eviq.json'
BUNDLED_CATALOGUE = Path(__file__).parent / 'data' / 'dvh' / 'eviq.json'
NUMBER = r'(?:\d+(?:\.\d*)?|\.\d+)'
UNIT = r'(?:%|cc|cm3|cm³)'
OP = r'(?:<=|>=|<|>|=)'


def default_catalogue_path():
    """Prefer an explicit local refresh, otherwise use the versioned snapshot."""
    return DEFAULT_CATALOGUE if DEFAULT_CATALOGUE.is_file() else BUNDLED_CATALOGUE


def clean(text):
    return ' '.join(text.replace('\u200b', '').split())


def parse_point(text):
    """eviQ extraction currently supports physical dose only."""
    point = parse_goal_point(text)
    return point if point is not None and 'dose_cgy' in point else None


def _soup(html):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, 'html.parser')


def _grid(table):
    """Expand row/column spans while keeping the original cell identities."""
    grid, occupied = [], {}
    for y, row in enumerate(table.find_all('tr')):
        if row.find_parent('table') is not table:
            continue
        line, x = [], 0
        for cell in row.find_all(['th', 'td'], recursive=False):
            while (y, x) in occupied:
                x += 1
            for dy in range(int(cell.get('rowspan', 1))):
                for dx in range(int(cell.get('colspan', 1))):
                    occupied[y + dy, x + dx] = cell
            x += int(cell.get('colspan', 1))
        if occupied:
            line = [occupied.get((y, i)) for i in range(max(i for j, i in occupied if j == y) + 1)]
        grid.append(line)
    return grid


def _lines(cell):
    # Remove superscript reference labels, never the surrounding recommendation.
    clone = _soup(str(cell))
    for ref in clone.select('a.reference-link, sup'):
        ref.decompose()
    for tag in clone.find_all(['p', 'li', 'ul', 'ol', 'br', 'div']):
        tag.insert_before('\n')
        tag.insert_after('\n')
    return [clean(line) for line in clone.get_text().splitlines() if clean(line)]


def parse_protocol(html, url):
    soup = _soup(html)
    title = soup.find('h1') or soup.title
    page = dict(url=url, title=clean(title.get_text(' ', strip=True)) if title else url,
                sha256=hashlib.sha256(html.encode()).hexdigest(), groups=[], warnings=[])
    page['protocol_id'] = re.search(r'/(\d+)-', url).group(1) if re.search(r'/(\d+)-', url) else None
    versions = [clean(h.get_text()) for h in soup.select('.histoty-title')]
    page['version'] = versions[0] if versions else None
    for label in soup.find_all('strong', string=re.compile(r'^ID:\s*\d+$')):
        page['protocol_id'] = re.search(r'\d+', label.get_text()).group()
        version = re.search(r'\bv\.(\d+)', label.parent.get_text(' ', strip=True))
        if version:
            page['version'] = 'Version ' + version.group(1)
        break
    page['dates'] = {clean(dt.get_text()).rstrip(':'): clean(dt.find_next_sibling('dd').get_text())
                     for dt in soup.find_all('dt') if dt.find_next_sibling('dd') is not None}
    section = soup.find(attrs={'data-section-name': re.compile(r'^Organs at risk$', re.I)})
    if section is None:
        page['warnings'].append('Organs at risk section not found; no points extracted.')
        page['section_text'] = ''
        return page
    page['section_text'] = clean(section.get_text(' ', strip=True))
    # The complete local source snapshot retains version/date, prescriptions and references.
    for table_index, table in enumerate(section.find_all('table')):
        if table.find_parent('table'):
            continue
        if not clean(table.get_text()):
            continue
        grid = _grid(table)
        header_count = 0
        for row in grid:
            if row and all(c is not None and c.name == 'th' and c.get('scope') != 'row' for c in row):
                header_count += 1
            else:
                break
        # eviQ sometimes uses scope=row on the Organ column heading.
        if table.thead:
            header_count = len(table.thead.find_all('tr'))
        if not header_count:
            page['warnings'].append(f'Table {table_index + 1}: unsupported header layout; retained in section_text.')
            continue
        headers = []
        for x in range(max(map(len, grid[:header_count]))):
            cells = []
            for row in grid[:header_count]:
                if x < len(row) and row[x] is not None and all(row[x] is not c for c in cells):
                    cells.append(row[x])
            headers.append(' / '.join(clean(c.get_text(' ', strip=True)) for c in cells))
        for row_index, row in enumerate(grid[header_count:]):
            if not row or row[0] is None:
                continue
            organ = clean(row[0].get_text(' ', strip=True))
            notes = ' '.join(clean(c.get_text(' ', strip=True)) for x, c in enumerate(row)
                             if c is not None and x < len(headers) and re.search(r'notes|information|contour', headers[x], re.I))
            for x, cell in enumerate(row[1:], 1):
                if cell is None or x >= len(headers) or re.search(r'notes|information|contour', headers[x], re.I):
                    continue
                records, qualifier, pending_metric = [], '', ''
                for line in _lines(cell):
                    if line.endswith(':'):
                        qualifier = line[:-1]
                        continue
                    expression = line
                    # Some eviQ cells put a Dx heading above Optimal/Mandatory limits.
                    metric = re.fullmatch(rf'(D\s*{NUMBER}\s*{UNIT})', line, re.I)
                    described = re.fullmatch(rf'Near maximum dose\s*\((D\s*{NUMBER}\s*{UNIT})\)', line, re.I)
                    if metric or described:
                        pending_metric = (metric or described).group(1)
                    else:
                        labelled = re.fullmatch(r'(Ideal|Acceptable|Optimal|Mandatory)\s*:?\s*(.*)', line, re.I)
                        if labelled:
                            qualifier, expression = labelled.groups()
                        if pending_metric and re.fullmatch(rf'[<>=≤≥]+\s*{NUMBER}\s*(cGy|Gy)\.?', expression, re.I):
                            expression = pending_metric + ' ' + expression
                        else:
                            pending_metric = ''
                    point = parse_point(expression)
                    records.append(dict(text=line, point_expression=expression, qualifier=qualifier, point=point,
                                        status='parsed' if point else 'manual_review'))
                if not records:
                    continue
                key = f'{url}#{table_index}:{row_index}:{x}'
                page['groups'].append(dict(id=key, organ=organ, structure_patterns=[f'*{organ}*'],
                                           regimen=headers[x], notes=notes,
                                           recommendations=records))
    if not page['groups']:
        page['warnings'].append('No supported OAR table rows; inspect source and section_text.')
    return page


def protocol_url(url):
    parsed = urlsplit(url)
    return (parsed.scheme == 'https' and parsed.netloc == 'www.eviq.org.au'
            and bool(re.fullmatch(r'/radiation-oncology/(?:[^/]+/)*\d+-[^/]+', parsed.path, re.I)))


class SiteReader:
    """Sequential, rate-limited HTTPS reads with robots enforcement and local snapshots."""

    def __init__(self, cache, delay=1.):
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.delay, self.last = max(1., delay), 0.
        self.robot = RobotFileParser()
        self.robot.parse(self._read(ROOT + '/robots.txt').splitlines())
        self.delay = max(self.delay, self.robot.crawl_delay(AGENT) or self.robot.crawl_delay('*') or 0)

    def _read(self, url):
        for attempt in range(3):
            try:
                return self._read_once(url)
            except (OSError, HTTPError) as error:
                if isinstance(error, HTTPError) and error.code != 429 and error.code < 500:
                    raise
                if attempt == 2:
                    raise
                time.sleep(2 ** (attempt + 1))

    def _read_once(self, url):
        time.sleep(max(0., self.delay - (time.monotonic() - self.last)))
        try:
            request = Request(url, headers={'User-Agent': AGENT})
            with urlopen(request, timeout=60) as response:
                if urlsplit(response.url).netloc != 'www.eviq.org.au':
                    raise ValueError('Unexpected redirect outside eviQ')
                if urlsplit(response.url).path.lower().startswith('/login'):
                    raise ValueError(f'eviQ requires login for {url}; public catalogue update stopped')
                data = response.read()
                encoding = ('utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff'))
                            else response.headers.get_content_charset() or 'utf-8-sig')
                return data.decode(encoding)
        finally:
            self.last = time.monotonic()

    def __call__(self, url):
        if not self.robot.can_fetch(AGENT, url):
            raise ValueError(f'robots.txt disallows {url}')
        html = self._read(url)
        digest = hashlib.sha256(html.encode()).hexdigest()
        (self.cache / f'{digest}.html').write_text(html, encoding='utf-8')
        return html


def discover_protocols(fetch, start=ROOT + '/radiation-oncology', max_pages=2000):
    """Walk only radiation-oncology categories; do not crawl protocol subpages/history."""
    queue, seen, protocols = [start], set(), set()
    while queue:
        url = queue.pop(0)
        if url in seen:
            continue
        if len(seen) >= max_pages:
            raise ValueError('Discovery page limit reached; catalogue was not replaced.')
        seen.add(url)
        html = fetch(url)
        # eviQ renders many category listings client-side from an embedded JSON tree.
        # Decode the JSON data only; never execute the surrounding JavaScript.
        for script in _soup(html).find_all('script'):
            source = script.string or script.get_text()
            for match in re.finditer(r'\bdata\s*:\s*(\{\s*"AliasPath")', source):
                listing, _ = json.JSONDecoder().raw_decode(source[match.start(1):])
                listed_protocols = set()
                def walk(node):
                    for page in node.get('Pages', []):
                        if re.search(r'discontinued|superseded|archived', page.get('Title', ''), re.I):
                            continue
                        candidate = urljoin(ROOT, page['AliasPath']).lower().rstrip('/')
                        if protocol_url(candidate):
                            listed_protocols.add(candidate)
                    for category in node.get('Categories', []):
                        walk(category)
                walk(listing)
                if listing.get('AliasPath', '').lower().rstrip('/') == '/radiation-oncology':
                    return sorted(listed_protocols)
                protocols.update(listed_protocols)
        for link in _soup(html).find_all('a', href=True):
            target = urlsplit(urljoin(url, link['href']))
            candidate = target._replace(path=target.path.lower(), query='', fragment='').geturl().rstrip('/')
            if target.scheme != 'https' or target.netloc != 'www.eviq.org.au':
                continue
            if protocol_url(candidate):
                protocols.add(candidate)
            elif (target.path.lower().startswith('/radiation-oncology')
                  and not re.search(r'/\d+-', target.path)
                  and candidate not in seen and candidate not in queue):
                queue.append(candidate)
    return sorted(protocols)


def update_catalogue(urls, destination, *, fetch, delay=0):
    """Replace only after every requested protocol succeeds; old files survive failures."""
    urls = sorted(set(urls))
    if not urls:
        raise ValueError('No protocols discovered; catalogue was not replaced.')
    protocols, identities = [], {}
    for url in urls:
        if not protocol_url(url):
            raise ValueError(f'Not an eviQ radiation oncology protocol URL: {url}')
        page = parse_protocol(fetch(url), url)
        identity = page['protocol_id'] or url
        if identity in identities:
            identities[identity].setdefault('aliases', []).append(url)
        else:
            identities[identity] = page
            protocols.append(page)
        if delay:
            time.sleep(delay)
    catalogue = dict(schema_version=1, generated_at=datetime.now(timezone.utc).isoformat(),
                     source='eviQ / Cancer Institute NSW', protocols=protocols,
                     attribution='Adapted from eviQ Cancer Treatments Online, Cancer Institute NSW. '
                                 'Extraction by HyperIO; no endorsement implied.',
                     source_terms=ROOT + '/copyright',
                     scope='OAR tables only; conservative physical-dose Vx/Dx points; manual review required')
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destination.parent, delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(catalogue, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write('\n')
    try:
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return catalogue


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_CATALOGUE)
    parser.add_argument('--cache', type=Path, default=DEFAULT_CATALOGUE.parent / 'eviq-sources')
    parser.add_argument('--url', action='append', help='Update only these protocol URLs; repeat as needed')
    parser.add_argument('--max-pages', type=int, default=2000)
    parser.add_argument('--verbose', action='store_true', help='Print each URL as it is fetched')
    args = parser.parse_args(argv)
    try:
        reader = SiteReader(args.cache)
        def fetch(url):
            if args.verbose:
                print(f'Fetching {url}', flush=True)
            return reader(url)
        print('Discovering eviQ protocols…' if not args.url else 'Using selected eviQ protocols…', flush=True)
        urls = args.url or discover_protocols(fetch, max_pages=args.max_pages)
        print(f'Refreshing {len(urls)} protocols…', flush=True)
        catalogue = update_catalogue(urls, args.output, fetch=fetch)
    except (OSError, ValueError, ImportError) as error:
        parser.exit(1, f'Update failed; previous catalogue retained: {error}\n')
    groups = [g for p in catalogue['protocols'] for g in p['groups']]
    records = [r for g in groups for r in g['recommendations']]
    print(f'{len(catalogue["protocols"])} protocols from {len(urls)} URLs, {len(groups)} organ/regimen groups, '
          f'{sum(r["point"] is not None for r in records)} points, '
          f'{sum(r["point"] is None for r in records)} manual-review records: {args.output}')
    for page in catalogue['protocols']:
        for warning in page['warnings']:
            print(f'WARNING {page["url"]}: {warning}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
