"""Legacy three-slice packaging checks; these are not valid TPS loading controls."""
import hashlib
import json
from pathlib import Path

import pytest

from hyperio.experiments import SOURCE_PATIENT_ID
from hyperio.three_slice import crop_study_records, build_three_slice_batch
from hyperio.core import inspect_export


def test_crop_updates_slice_count_bounds_and_native_index():
    info = b'00271016\r\nNo Description\r\n0\r\n-148.7,-749.5,-112.0,151.8,-450.5,61.5\r\n0\r\n16623,-2158,421,0,600,40\r\n311,0,0\r\n'
    index = b'5\nT.-597.5.CT\n-597.5\nT.-598.5.CT\n-598.5\nT.-599.5.CT\n-599.5\nT.-600.5.CT\n-600.5\nT.-601.5.CT\n-601.5\n\n'
    edited, selected = crop_study_records(info, index)
    assert edited.splitlines()[6] == b'3,0,0'
    assert [float(x) for x in edited.splitlines()[3].split(b',')] == [-148.7,-600.5,-112,151.8,-598.5,61.5]
    assert selected == b'3\nT.-598.5.CT\n-598.5\nT.-599.5.CT\n-599.5\nT.-600.5.CT\n-600.5\n\n'
    with pytest.raises(ValueError):
        crop_study_records(info, index.replace(b'T.-599.5.CT', b'T.-999.5.CT'))


REFERENCE = Path(__file__).resolve().parents[1] / 'reference/1~ZZZELEKTAONEHETERO.zip'


@pytest.mark.skipif(not REFERENCE.exists(), reason='supplied archive local only')
def test_three_slice_cases_are_complete_and_reviews_reset(tmp_path):
    dest = tmp_path / 'batch'
    result = build_three_slice_batch(REFERENCE, dest)
    assert len(result['cases']) == 16
    assert result['cases'][0]['id'] == 'V00-three-slice-control'
    for case in result['cases']:
        folder = dest/'cases'/case['id']
        payload = folder/'payload'
        study = payload/'1~zzzInputOutputAG/1~SemiflexWater'
        assert len(list(payload.rglob('*.CT'))) == 3
        assert len(list(payload.rglob('*.WC'))) == 3
        assert len(list(payload.rglob('*.CT.DCM'))) == 3
        assert (study/'1~SemiflexWater/index.dat').read_text().splitlines()[0] == '3'
        assert (study/'info').read_bytes().splitlines()[6] == b'3,0,0'
        assert not any(p.name == 'dose.1' or '.dose.' in p.name or p.suffix == '.xlog' for p in payload.rglob('*'))
        manifest = json.loads((folder/'manifest.json').read_text())
        assert set(manifest['files']) == {p.relative_to(payload).as_posix() for p in payload.rglob('*') if p.is_file()}
        for name, record in manifest['files'].items():
            assert hashlib.sha256((payload/name).read_bytes()).hexdigest() == record['sha256']
        report = inspect_export(payload)
        assert report['plans'][0]['patient_id'] == 'zzzInputOutputAG'
        assert not report['plans'][0]['diagnostics']
        assert not report['studysets'][0]['diagnostics']
    review = json.loads((dest/'review-results.json').read_text())
    assert all(c['review_status'] == 'not_reviewed' and c['load_result'] is None for c in review['cases'])
    with pytest.raises(FileExistsError):
        build_three_slice_batch(REFERENCE, dest)
