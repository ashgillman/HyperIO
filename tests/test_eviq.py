"""Synthetic layouts exercise eviQ extraction without distributing protocol text."""
import json

import pytest

from hyperio.eviq import parse_protocol, parse_point, overlay_points, load_catalogue, update_catalogue
from hyperio.eviq import discover_protocols


def test_reader_retries_transient_timeouts(monkeypatch):
    from hyperio import eviq
    reader = eviq.SiteReader.__new__(eviq.SiteReader)
    attempts = []
    def read(url):
        attempts.append(url)
        if len(attempts) < 3:
            raise TimeoutError('temporary timeout')
        return 'success'
    monkeypatch.setattr(reader, '_read_once', read)
    monkeypatch.setattr(eviq.time, 'sleep', lambda seconds: None)
    assert reader._read('example') == 'success'
    assert len(attempts) == 3


def test_default_catalogue_uses_bundled_snapshot_unless_local_refresh_exists(tmp_path, monkeypatch):
    from hyperio import eviq
    local = tmp_path / 'local.json'
    monkeypatch.setattr(eviq, 'DEFAULT_CATALOGUE', local)
    assert eviq.default_catalogue_path() == eviq.BUNDLED_CATALOGUE
    local.write_text('{}')
    assert eviq.default_catalogue_path() == local


HTML = '''<h1>Example protocol</h1><div data-section-name="Organs at risk">
<table><thead><tr><th rowspan="2">Organ</th><th colspan="2">Constraint</th>
<th rowspan="2">Notes</th></tr><tr><th>5 fractions</th><th>20 fractions</th></tr></thead>
<tbody><tr><th>Example organ</th><td><p>Ideal:</p><ul><li>V20 Gy &lt;30%</li></ul>
Acceptable:<ul><li>D0.1 cc ≤25 Gy</li><li>Mean dose &lt;10 Gy</li></ul></td>
<td>V30 Gy &lt;40%</td><td>Contour entire organ.</td></tr>
<tr><th>Other</th><td colspan="2">V10 Gy &lt;50%</td><td>Shared.</td></tr></tbody></table>
<p>Consider prior treatment.</p></div><h2>History</h2><p>V99 Gy &lt;1%</p>'''


def test_extract_preserves_regimens_qualifiers_notes_and_unparsed():
    page = parse_protocol(HTML, 'https://www.eviq.org.au/radiation-oncology/test/123-example')
    groups = page['groups']
    assert len(groups) == 4
    assert groups[0]['regimen'] == 'Constraint / 5 fractions'
    assert groups[1]['regimen'] == 'Constraint / 20 fractions'
    assert groups[0]['notes'] == 'Contour entire organ.'
    records = groups[0]['recommendations']
    assert records[0]['qualifier'] == 'Ideal'
    assert records[1]['qualifier'] == 'Acceptable'
    assert records[2]['status'] == 'manual_review'
    assert records[1]['point']['volume_unit'] == 'cm3'
    assert all(r['point']['dose_cgy'] != 9900 for g in groups for r in g['recommendations'] if r['point'])
    assert 'Consider prior treatment.' in page['section_text']


@pytest.mark.parametrize('text', ['Dmax <30 Gy', 'Mean <20 Gy', 'D1 cc <54 Gy EQD2',
    'V20 Gy <30% or V30 Gy <20%', 'V20 Gy <30% if previously treated',
    'V20 Gy <130%', 'V20 Gy <30-40%', 'D95% >95%'])
def test_ambiguous_or_nonphysical_points_are_review_only(text):
    assert parse_point(text) is None


def test_points_and_axis_conversions():
    assert parse_point('V20 Gy <30%')['dose_cgy'] == 2000
    p = parse_point('D0.1 cm³ ≤2500 cGy')
    assert (p['dose_cgy'], p['volume'], p['operator']) == (2500, .1, '<=')
    group = {'recommendations': [{'point': p, 'text': 'small volume'}]}
    assert overlay_points(group, 2, '%')[0]['volume'] == 5
    group['recommendations'][0]['point'] = parse_point('V20 Gy <30%')
    assert overlay_points(group, 2, 'cm³')[0]['volume'] == pytest.approx(.6)


def test_update_fresh_inventory_atomic_failure_and_removed_pages(tmp_path):
    url = 'https://www.eviq.org.au/radiation-oncology/test/123-example'
    output = tmp_path / 'catalogue.json'
    update_catalogue([url], output, fetch=lambda u: HTML, delay=0)
    assert len(load_catalogue(output)['protocols']) == 1
    before = output.read_bytes()
    def broken(url):
        raise OSError('network unavailable')
    with pytest.raises(OSError):
        update_catalogue([url], output, fetch=broken, delay=0)
    assert output.read_bytes() == before
    with pytest.raises(ValueError, match='No protocols'):
        update_catalogue([], output, fetch=broken, delay=0)
    assert output.read_bytes() == before


def test_missing_section_is_reported_and_invalid_catalogue_rejected(tmp_path):
    assert parse_protocol('<h1>Example</h1>', 'https://www.eviq.org.au/radiation-oncology/123-example')['warnings']
    path = tmp_path / 'bad.json'
    path.write_text(json.dumps({'schema_version': 999, 'protocols': []}))
    with pytest.raises(ValueError):
        load_catalogue(path)


def test_stereotactic_metric_heading_inheritance_stops_at_dmax():
    html = HTML.replace('V20 Gy &lt;30%',
        'Near maximum dose (D0.035 cc)</li><li>Optimal ≤10 Gy</li><li>Mandatory ≤15 Gy</li>'
        '<li>Dmax</li><li>Optimal ≤20 Gy')
    records = parse_protocol(html, 'example')['groups'][0]['recommendations']
    assert records[1]['point']['volume'] == .035
    assert records[1]['point']['dose_cgy'] == 1000
    assert records[2]['point']['dose_cgy'] == 1500
    assert records[4]['point'] is None


def test_discovery_accepts_official_mixed_case_links_and_ignores_subpages():
    pages = {
        'https://www.eviq.org.au/radiation-oncology': '<a href="/Radiation-oncology/Breast">Breast</a>',
        'https://www.eviq.org.au/radiation-oncology/breast':
            '<a href="/Radiation-oncology/Breast/123-Example">Protocol</a>'
            '<a href="/Radiation-oncology/Breast/123-Example/patient-information">Patient</a>'
            '<a href="https://other.test/radiation-oncology/456-other">Other</a>',
    }
    assert discover_protocols(pages.__getitem__) == ['https://www.eviq.org.au/radiation-oncology/breast/123-example']


def test_metadata_and_merged_headers_remain_source_linked():
    html = '<h4 class="histoty-title">Version 8</h4><dl><dt>Last reviewed:</dt><dd>1 January 2026</dd></dl>' + HTML
    page = parse_protocol(html, 'https://www.eviq.org.au/radiation-oncology/test/123-example')
    assert page['protocol_id'] == '123'
    assert page['version'] == 'Version 8'
    assert page['dates']['Last reviewed'] == '1 January 2026'
    assert [g['regimen'] for g in page['groups'][2:]] == [
        'Constraint / 5 fractions', 'Constraint / 20 fractions']


def test_discovery_reads_client_side_json_tree_and_skips_discontinued():
    listing = {'AliasPath': '/radiation-oncology', 'Categories': [{'Pages': [
        {'AliasPath': '/radiation-oncology/example/123-current', 'Title': 'Current'},
        {'AliasPath': '/radiation-oncology/example/124-old', 'Title': 'Old DISCONTINUED'}]}]}
    html = '<script>setup({data: ' + json.dumps(listing) + ', other: true});</script>'
    assert discover_protocols(lambda url: html) == ['https://www.eviq.org.au/radiation-oncology/example/123-current']


def test_refresh_drops_protocols_not_in_new_inventory(tmp_path):
    a = 'https://www.eviq.org.au/radiation-oncology/test/123-example'
    b = 'https://www.eviq.org.au/radiation-oncology/test/124-other'
    path = tmp_path / 'catalogue.json'
    update_catalogue([a, b], path, fetch=lambda u: HTML)
    assert len(load_catalogue(path)['protocols']) == 2
    update_catalogue([a], path, fetch=lambda u: HTML)
    assert [p['url'] for p in load_catalogue(path)['protocols']] == [a]


def test_eviq_utf16_robots_is_decoded_and_enforced(tmp_path, monkeypatch):
    import io
    from email.message import Message
    from hyperio import eviq
    class Response(io.BytesIO):
        url = 'https://www.eviq.org.au/robots.txt'
        headers = Message()
    data = 'User-agent: *\nDisallow: /blocked\n'.encode('utf-16')
    monkeypatch.setattr(eviq, 'urlopen', lambda *args, **kwargs: Response(data))
    reader = eviq.SiteReader(tmp_path)
    with pytest.raises(ValueError, match='robots.txt disallows'):
        reader('https://www.eviq.org.au/blocked')


def test_redirect_aliases_use_actual_protocol_id_and_are_deduplicated(tmp_path):
    a = 'https://www.eviq.org.au/radiation-oncology/test/123-example'
    b = 'https://www.eviq.org.au/radiation-oncology/test/124-redirect-id-123'
    html = '<p><strong>ID: 123</strong> v.4</p>' + HTML
    catalogue = update_catalogue([a, b], tmp_path / 'catalogue.json', fetch=lambda u: html)
    page, = catalogue['protocols']
    assert page['protocol_id'] == '123'
    assert page['version'] == 'Version 4'
    assert page['aliases'] == [b]
