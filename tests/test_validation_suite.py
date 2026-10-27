"""Stable catalogue and one patient containing combined native plan candidates."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import zipfile

import pytest
from hyperio.core import inspect_export
from hyperio.validation_suite import build_suite, record_review, _wc_polygons

ROOT=Path(__file__).resolve().parents[1]
CATALOGUE=ROOT/'validation/catalogue.json'
SOURCE=ROOT/'reference/1~ZZZELEKTAONEHETERO.zip'
RETURN=ROOT/'reference/native-zero-ct/1~zzzInputOutputAG2.zip'


def test_catalogue_has_stable_ids_and_combines_component_checks():
    c=json.loads(CATALOGUE.read_text())
    assert len(c['profiles'])==7
    assert len({p['plan'] for p in c['profiles']})==7
    ids=[t['id'] for t in c['tests']]
    assert len(ids)==len(set(ids)) and len(ids)>=20
    for t in c['tests']:
        assert t['revision']>=1
        assert set(t['profiles'])<=set(p['id'] for p in c['profiles'])
    assert any(len(p['settings'])>=5 and p['density'] for p in c['profiles'])


@pytest.mark.skipif(not SOURCE.exists() or not RETURN.exists(),reason='private native fixtures local only')
def test_suite_has_intact_CT_controls_and_seven_independent_plans(tmp_path):
    out=tmp_path/'generated'
    r=build_suite(SOURCE,RETURN,out,CATALOGUE)
    patient=out/'native/1~zzzInputOutputAGsuite'
    assert patient.exists()
    assert len(list((patient/'plan').iterdir()))==7
    report=inspect_export(out/'native')
    assert {p['name'] for p in report['plans']}=={p['plan'] for p in json.loads(CATALOGUE.read_text())['profiles']}
    assert {s['name'] for s in report['studysets']}=={'CT1','Phantom','Density'}
    assert all(not p['diagnostics'] and p['patient_id']=='zzzInputOutputAGsuite' for p in report['plans'])
    assert all(not s['diagnostics'] for s in report['studysets'])
    with zipfile.ZipFile(RETURN) as z:
        for study in ['CT1','Phantom','Density']:
            folder=patient/f'1~{study}'
            assert len(list(folder.glob('*.CT')))==100
            assert len(list(folder.glob('*.WC')))==100
            assert len(list((folder/'DCMData').glob('*.CT.DCM')))==100
            for path in folder.glob('*.CT'):
                assert path.read_bytes()==z.read('1~zzzInputOutputAG2/1~CT1/'+path.name)
        for path in (patient/'1~CT1').glob('*.WC'):
            assert path.read_bytes()==z.read('1~zzzInputOutputAG2/1~CT1/'+path.name)
    assert not any(p.name in ('.editlock','.dirlock','.templock','dose.1') or '.dose.' in p.name or p.suffix=='.xlog'
                   for p in patient.rglob('*'))
    plans={p['name']:p for p in report['plans']}
    assert plans['Reference']['studyset']=='Phantom'
    assert plans['Density-Conflict']['studyset']=='Density'
    assert plans['Calculation-A']['settings']['MCVARIANCE']['value']==.02
    assert plans['Calculation-A']['settings']['MCSEGMENTVARIANCE']['value']==.03
    assert plans['Calculation-A']['settings']['MCVARPERPLAN']['value'] is False
    assert plans['Calculation-B']['settings']['MCVARPERPLAN']['value'] is True
    assert plans['Reference']['settings']['MCVARPERPLAN'] is None
    assert plans['Calculation-B']['settings']['FORCEWATER']['value'] is True
    for name,expected in [('Density-Conflict',1.1),('Density-Aligned',1.2)]:
        assert next(d for d in plans[name]['density_overrides'] if d['name']=='Insert')['uniform_ed']==expected
    study=next(s for s in report['studysets'] if s['name']=='Density')
    assert next(s for s in study['structures'] if s['name']=='Insert')['uniform_ed']==1.2
    assert r['contour_transfer']['nonempty_target_slices']>50
    assert r['contour_transfer']['empty_outside_source_slices']>0
    for path in (patient/'1~Phantom').glob('*.WC'):
        polygons=_wc_polygons(path.read_bytes())
        y=float(path.name[2:-3])
        assert -849.5<=y<=-349.5
        for structure,points in polygons:
            assert structure in (2,3,4,5,6,7,8,10,11)
            assert all(-250.0635<=x<=249.9365 and -250.0638<=z<=249.9362 for x,z in points)
    assert (patient/'1~Phantom/contournames').read_bytes()!=(patient/'1~Density/contournames').read_bytes()
    for record in r['files']:
        file=out/'native'/record['path']
        assert hashlib.sha256(file.read_bytes()).hexdigest()==record['sha256']
    review=json.loads((out/'review.json').read_text())
    assert review['run_manifest_sha256']==hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest()
    assert all(o['status']=='not_reviewed' for o in review['observations'])
    assert {o['profile_id'] for o in review['observations']}=={'patient',*[p['id'] for p in json.loads(CATALOGUE.read_text())['profiles']]}
    with pytest.raises(FileExistsError):
        build_suite(SOURCE,RETURN,out,CATALOGUE)


def test_recording_results_appends_preserves_scope_and_is_idempotent(tmp_path):
    review={'schema_version':1,'suite_id':'hyperio-tps','run_id':'example',
            'observations':[{'test_id':'CALC-GRID','test_revision':1,'profile_id':'calculation-a',
                             'phase':'initial','status':'pass','actual':'Grid spacing displayed as 0.20 cm',
                             'evidence':['screen.png']}]}
    path=tmp_path/'review.json';path.write_text(json.dumps(review))
    events=tmp_path/'events.jsonl'
    assert record_review(path,CATALOGUE,events)==1
    before=events.read_bytes()
    assert record_review(path,CATALOGUE,events)==0
    assert events.read_bytes()==before
    review['run_id']='next';review['observations'][0]['status']='fail';review['observations'][0]['actual']='Grid changed to 0.10 cm on reopen'
    review['observations'][0]['phase']='save_reopen'
    path.write_text(json.dumps(review))
    assert record_review(path,CATALOGUE,events)==1
    rows=[json.loads(line) for line in events.read_text().splitlines()]
    assert len(rows)==2 and rows[0]['status']=='pass' and rows[1]['status']=='fail'
    assert rows[0]['phase']=='initial' and rows[1]['phase']=='save_reopen'
    bad=deepcopy(review);bad['observations'][0]['test_id']='INVENTED';path.write_text(json.dumps(bad))
    with pytest.raises(ValueError):record_review(path,CATALOGUE,events)
    assert len(events.read_text().splitlines())==2
    bad=deepcopy(review);bad['observations'][0]['profile_id']='density-aligned';path.write_text(json.dumps(bad))
    with pytest.raises(ValueError):record_review(path,CATALOGUE,events)
    assert len(events.read_text().splitlines())==2
