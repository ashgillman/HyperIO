"""Persistent test identities, combined native candidates and append-only results."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import difflib
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile
from zoneinfo import ZoneInfo

from .core import Export, FormatError, HypDocument, inspect_export
from .experiments import (edit_plan_density, edit_static_aperture, _edit_study_density,
                          _hash_path, _sha, _save_json)

SOURCE_PLAN = '1~ZZZELEKTAONEHETERO/plan/RefHeteroSq6X'
SOURCE_STUDY = '1~ZZZELEKTAONEHETERO/1~SemiflexWater'
RETURN_ROOT = '1~zzzInputOutputAG2'
RETURN_STUDY = RETURN_ROOT + '/1~CT1'


def _catalogue(path):
    c = json.loads(Path(path).read_text())
    if c['schema_version'] != 1 or c['suite_id'] != 'hyperio-tps':
        raise ValueError('unsupported validation catalogue')
    profiles = c['profiles']
    if len({p['id'] for p in profiles}) != len(profiles) or len({p['plan'] for p in profiles}) != len(profiles):
        raise ValueError('duplicate profile or plan identity')
    if len({t['id'] for t in c['tests']}) != len(c['tests']):
        raise ValueError('duplicate stable test ID')
    for p in profiles:
        if any(x in p['plan'] for x in '/\\') or p['plan'] in ('.','..'):
            raise ValueError('unsafe plan folder name')
        if p['studyset'] not in ('Phantom','Density'):
            raise ValueError('unsupported suite studyset')
    for t in c['tests']:
        if not set(t['profiles']) <= {p['id'] for p in profiles} or t['revision'] < 1:
            raise ValueError('invalid test revision or profile reference')
    if any(x in c['patient_id'] for x in '/\\') or len(c['patient_id']) > 32:
        raise ValueError('unsafe patient identity')
    return c


def _replace_record(data, old, new):
    old, new = old.encode('ascii'), new.encode('ascii')
    rows = data.splitlines(keepends=True)
    for i, row in enumerate(rows):
        value = row.rstrip(b'\r\n')
        if value == old:
            rows[i] = new + row[len(value):]
    return b''.join(rows)


def _wc_polygons(data):
    """Read the fixture's leading polygon records; leave marker records untouched."""
    rows = data.decode('cp1252').splitlines()
    if rows[0] != '00091013':
        raise FormatError('unsupported contour file header')
    i, polygons = 7, []
    while i + 1 < len(rows):
        try:
            count, structure = int(rows[i]), int(rows[i+1])
        except ValueError:
            break
        if count <= 0 or structure <= 0:
            break
        if count > 10000:
            raise FormatError('unexpected contour point count')
        i += 2
        values = []
        while len(values) < 2*count and i < len(rows):
            values.extend(float(x) for x in rows[i].split(','))
            i += 1
        if len(values) != 2*count:
            raise FormatError('contour point count disagrees with polygon records')
        polygons.append((structure, list(zip(values[::2], values[1::2]))))
    return polygons


def _contours(original, returned):
    """Nearest-slice transfer of fixture polygons in physical native coordinates.

    Image data stay byte-identical. Transfer is an explicit unvalidated TPS test.
    The source is sampled only inside its image extent; no end slices are extended.
    """
    candidates = [(float(PurePosixPath(n).name[2:-3]), n) for n in original.sizes
                  if str(PurePosixPath(n).parent) == SOURCE_STUDY and n.endswith('.WC')]
    if len(candidates) != 311:
        raise FormatError('contour transfer requires the supplied 311-slice source')
    low, high = min(y for y,_ in candidates), max(y for y,_ in candidates)
    targets = sorted(n for n in returned.sizes if str(PurePosixPath(n).parent) == RETURN_STUDY and n.endswith('.WC'))
    if len(targets) != 100:
        raise FormatError('expected all 100 returned contour files')
    result, transfers, xs, ys, zs = {}, [], [], [], []
    empty = nonempty = 0
    for n in targets:
        base = returned.read(n)
        y = float(PurePosixPath(n).name[2:-3])
        record = {'target_file':PurePosixPath(n).name, 'target_position_mm':y,
                  'returned_empty_WC_sha256':_sha(base)}
        if not low <= y <= high:
            result[PurePosixPath(n).name] = base
            record['source_file'] = None
            record['policy'] = 'retain returned empty slice outside source image range'
            empty += 1
        else:
            sy, source = min(candidates, key=lambda item:(abs(item[0]-y),item[0]))
            raw = original.read(source)
            polygons = _wc_polygons(raw)
            a, b = raw.splitlines(keepends=True), base.splitlines(keepends=True)
            if a[0].strip()!=b[0].strip() or len(a)<7 or len(b)<7:
                raise FormatError('incompatible source/target contour headers')
            # Keep source polygon bounds and records, but use target CT origin,
            # orientation and image description for the new physical slice.
            for i in (1,3,5,6):
                a[i] = b[i]
            data = b''.join(a)
            result[PurePosixPath(n).name] = data
            record.update(source_file=source, source_position_mm=sy, source_sha256=_sha(raw),
                          policy='nearest source slice; transverse polygon coordinates retained')
            record['polygon_count'] = len(polygons)
            for _,points in polygons:
                xs.extend(p[0] for p in points)
                zs.extend(p[1] for p in points)
            if polygons:
                ys.append(y)
                nonempty += 1
        record['output_sha256'] = _sha(result[PurePosixPath(n).name])
        transfers.append(record)
    if not xs or not ys or not zs:
        raise FormatError('source has no transferable contours')
    bounds = [min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)]
    return result, {'method':'nearest longitudinal source slice, no extrapolation',
                    'status':'candidate_transfer_requires_TPS_geometry_review',
                    'nonempty_target_slices':nonempty,'empty_outside_source_slices':empty,
                    'source_image_extent_mm':[low,high], 'candidate_contour_bounds_native_mm':bounds,
                    'slice_records':transfers}


def _settings(data, changes):
    doc = HypDocument(data)
    for key,value in changes.items():
        if key == 'MCVARPERPLAN' and doc.get(key) is None:
            anchor = doc.get('MCSEGMENTVARIANCE')
            rows = doc.to_bytes().splitlines(keepends=True)
            ending = b'\r\n' if rows[anchor.line-1].endswith(b'\r\n') else b'\n'
            rows.insert(anchor.line,b'!MCVARPERPLAN    '+str(int(value)).encode()+ending)
            doc = HypDocument(b''.join(rows))
        else:
            doc = doc.with_value(key,value)
    return doc.to_bytes()


def _diff(old, new, source, target):
    return ''.join(difflib.unified_diff(old.decode('cp1252').splitlines(True),
                                      new.decode('cp1252').splitlines(True),fromfile=source,tofile=target))


def _review(c, run_id):
    observations = []
    for t in c['tests']:
        if t['group'] == 'historical':
            continue
        for profile in t['profiles'] or ['patient']:
            observations.append({'test_id':t['id'],'test_revision':t['revision'],
                'profile_id':profile,'phase':t['phase'],'expected':t['expected'],
                'status':'not_reviewed','actual':None,'messages':[],'evidence':[]})
    return {'schema_version':1,'suite_id':c['suite_id'],'run_id':run_id,
            'reviewer':None,'monaco_version_build':None,'observed_at':None,
            'patient_id_as_installed':None,'observations':observations}


def _review_markdown(review, c):
    lines = ['# TPS suite review', '',
             'Import/restore the native patient once; collect each group while its studyset/plan is open.',
             'Record individual failures even when several tests share the same plan.',
             'Fill this worksheet or review.json; record results into the perpetual event log afterwards.',
             '', 'Reviewer: ', 'Monaco build: ', 'Installed patient ID: ', 'Observed at / timezone: ',
             '', 'Status choices: not_reviewed, pass, fail, blocked, not_applicable, observation.',
             'An earlier successful CT import is historical evidence; this fresh native restoration still needs review.']
    locations = [('patient','Patient and CT1 image control')] + [(p['id'],p['plan']+' / '+p['studyset']) for p in c['profiles']]
    for profile,title in locations:
        lines += ['', '## '+title, '', '| Test | Phase | Expected check | Status | Actual / evidence |',
                  '|---|---|---|---|---|']
        for o in review['observations']:
            if o['profile_id']==profile:
                lines.append(f"| {o['test_id']} | {o['phase']} | {o['expected']} | not_reviewed | |")
    return '\n'.join(lines)+'\n'


def build_suite(source, native_return, destination, catalogue):
    """Generate one combined native patient without overwriting a previous run."""
    source,native_return,destination,catalogue=map(Path,(source,native_return,destination,catalogue))
    if destination.exists():
        raise FileExistsError(f'refusing to overwrite a generated suite or review: {destination}')
    for fixture in (source,native_return):
        if fixture.is_dir() and (fixture.resolve()==destination.resolve() or fixture.resolve() in destination.resolve().parents):
            raise ValueError('generated suite must be outside fixture directories')
    c = _catalogue(catalogue)
    pid = c['patient_id']
    root = '1~'+pid
    payload, provenance, patches = {}, {}, {}
    with Export(native_return) as ret, Export(source) as original:
        ret_report=inspect_export(native_return)
        if len(ret_report['studysets'])!=1 or ret_report['studysets'][0]['name']!='CT1' or ret_report['studysets'][0]['diagnostics']:
            raise FormatError('expected the returned native CT1 studyset without reader diagnostics')
        if len([n for n in ret.sizes if n.startswith(RETURN_STUDY+'/') and n.endswith('.CT')])!=100:
            raise FormatError('the imported 100-slice native baseline is required')
        contour_files, transfer = _contours(original,ret)
        source_contours=original.read(SOURCE_STUDY+'/contournames')
        source_report=inspect_export(source)
        source_plan=next(p for p in source_report['plans'] if p['path']==SOURCE_PLAN)
        if source_plan['diagnostics']:
            raise FormatError('source plan has reader diagnostics')
        for key,expected in {'DOSEGRIDSIZE':1,'MCVARIANCE':0.01,'MCSEGMENTVARIANCE':0.01,
                             'DOSETOMEDIUM':True,'FORCEWATER':False}.items():
            if not source_plan['settings'].get(key) or source_plan['settings'][key]['value']!=expected:
                raise FormatError(f'source fixture differs from the catalogue baseline at {key}')
        if source_plan['settings'].get('MCVARPERPLAN') is not None:
            raise FormatError('catalogue absence control requires absent source MCVARPERPLAN')
        baseline_study=next(s for s in source_report['studysets'] if s['path']==SOURCE_STUDY)
        insert=next(s for s in baseline_study['structures'] if s['name']=='Insert')
        if insert['uniform_ed']!=1 or insert['mode']!='forced':
            raise FormatError('density profiles require source Insert forced ED 1.0')
        def put(name,data,source_name,old,kind):
            payload[name]=data
            provenance[name]={'source_path':source_name,'source_sha256':_sha(old),
                              'change':kind if old!=data else 'source-identical'}
        # Patient-level files only; never transfer editing locks from the return.
        for n in sorted(ret.sizes):
            if str(PurePosixPath(n).parent)!=RETURN_ROOT or PurePosixPath(n).name.startswith('.'):
                continue
            raw=ret.read(n)
            data=_replace_record(raw,'zzzInputOutputAG2',pid)
            if PurePosixPath(n).name.startswith('demographic.'):
                data=_replace_record(data,'zzPHYS^Ash',c['patient_name'])
            name=PurePosixPath(n).name.replace('demographic.zzzInputOutputAG2','demographic.'+pid)
            put(root+'/'+name,data,n,raw,'local patient identity')
        for study in ('CT1','Phantom','Density'):
            diffparts=[]
            for n in sorted(ret.sizes):
                if not n.startswith(RETURN_STUDY+'/'):
                    continue
                rel=n[len(RETURN_STUDY)+1:]
                if PurePosixPath(rel).name in ('.dirlock','.editlock','.templock'):
                    continue
                raw=ret.read(n,limit=ret.sizes[n])
                data=raw
                old=raw
                source_name=n
                kind='source-identical'
                rel=rel.replace('1~CT1/','1~'+study+'/')
                if PurePosixPath(n).name=='info':
                    data=_replace_record(_replace_record(raw,'zzzInputOutputAG2',pid),'CT1',study)
                    if study!='CT1':
                        rows=data.splitlines(keepends=True)
                        rows[3]=','.join(format(v,'.10g') for v in transfer['candidate_contour_bounds_native_mm']).encode()+b'\r\n'
                        data=b''.join(rows)
                    kind='native patient/studyset references and candidate contour bounds'
                elif study!='CT1' and n.endswith('/contournames'):
                    source_name=SOURCE_STUDY+'/contournames'
                    old=source_contours
                    data=source_contours.replace(b'SemiflexWater',study.encode())
                    if study=='Density':
                        data=_edit_study_density(data,insert['source']['line'],1.2)
                    kind='source phantom structure table, local studyset name and optional ED 1.2'
                elif study!='CT1' and n.endswith('.WC'):
                    data=contour_files[PurePosixPath(n).name]
                    kind='sampled source phantom contours; see contour-transfer.json'
                name=root+'/1~'+study+'/'+rel
                put(name,data,source_name,old,kind)
                if data!=old and PurePosixPath(n).name in ('info','contournames'):
                    diffparts.append(_diff(old,data,source_name,name))
            patches['studyset-'+study]='\n'.join(diffparts)
        omitted=[]
        plan_names=sorted(n for n in original.sizes if str(PurePosixPath(n).parent)==SOURCE_PLAN)
        for p in c['profiles']:
            diffs=[]
            for n in plan_names:
                base=PurePosixPath(n).name
                if base=='dose.1' or '.dose.' in base or base.lower().endswith('.xlog'):
                    if n not in omitted:omitted.append(n)
                    continue
                raw=original.read(n)
                data=raw
                if base=='plan':
                    rows=data.splitlines(keepends=True)
                    for i,value in ((2,p['plan']),(4,pid),(6,p['studyset'])):
                        rows[i]=value.encode()+b'\r\n'
                    data=edit_plan_density(b''.join(rows),'Insert',**p['density'])
                elif base.lower().endswith('.hyp'):
                    data=_settings(raw,p['settings'])
                    # The reference reader expects the patient-specific .hyp filename.
                    base=pid+'.hyp'
                elif base=='tel.1' and p['aperture']:
                    data=edit_static_aperture(raw,'2',p['aperture'])
                name=root+'/plan/'+p['plan']+'/'+base
                put(name,data,n,raw,'plan identity/studyset association or explicit profile mutation')
                if data!=raw:
                    diffs.append(_diff(raw,data,n,name))
            patches['plan-'+p['id']]='\n'.join(diffs)
    destination.mkdir(parents=True)
    for name,data in payload.items():
        target=destination/'native'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
    report=inspect_export(destination/'native')
    if len(report['plans'])!=len(c['profiles']) or any(p['diagnostics'] for p in report['plans']) or any(s['diagnostics'] for s in report['studysets']):
        raise FormatError('generated suite read-back failed; preserve output for diagnosis')
    # Ensure local native plan identities and both settings file and studyset exist.
    for p in report['plans']:
        if p['patient_id']!=pid or not (destination/'native'/p['path']/(pid+'.hyp')).exists():
            raise FormatError('native patient/plan settings identity mismatch')
    records=[{'path':name,'size':len(data),'sha256':_sha(data),**provenance[name]} for name,data in sorted(payload.items())]
    catalogue_sha=_hash_path(catalogue)
    payload_sha=_sha(json.dumps(records,sort_keys=True).encode())
    generator_identity={p.name:_hash_path(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
    run_id='hyperio-tps-'+_sha((catalogue_sha+payload_sha+json.dumps(generator_identity,sort_keys=True)).encode())[:16]
    result={'schema_version':1,'suite_id':c['suite_id'],'run_id':run_id,
        'catalogue_sha256':catalogue_sha,'catalogue_revision':c['catalogue_revision'],
        'patient_id':pid,'patient_name':c['patient_name'],'native_patient_directory':root,
        'plan_count':len(c['profiles']),'studysets':['CT1','Phantom','Density'],
        'sources':{'source_plan_archive':str(source),'source_plan_archive_sha256':_hash_path(source) if source.is_file() else None,
                   'returned_native_archive':str(native_return),'returned_native_archive_sha256':_hash_path(native_return) if native_return.is_file() else None},
        'profiles':c['profiles'],'files':records,'omitted_source_dose_and_logs':omitted,
        'contour_transfer':{k:v for k,v in transfer.items() if k!='slice_records'},
        'validation_status':'local_structure_and_byte_checks_passed_TPS_restore_pending',
        'limits':['Source plan grid/checksum/status/normalization and plan_comment document metadata are retained and unvalidated for the new CT/studyset and cloned plans.',
                  'Studysets are local copies of the same images and intentionally share original image UIDs, as observed in the supplied multi-studyset phantom archive.',
                  'Phantom contours are nearest-slice transferred from the supplied fixture; geometry acceptance is a first-class test.',
                  'Grouped settings can interact; record coupled changes and split a focused follow-up only if needed.',
                  'The imported CT contained no plan, so Reference is a transplanted plan control, not a previously TPS-accepted plan on this CT.'],
        'generator_sha256':generator_identity}
    _save_json(destination/'manifest.json',result)
    _save_json(destination/'catalogue.json',c)
    _save_json(destination/'contour-transfer.json',transfer)
    _save_json(destination/'reader-check.json',report)
    patchdir=destination/'changes';patchdir.mkdir()
    for name,data in patches.items():(patchdir/(name+'.diff')).write_text(data)
    review=_review(c,run_id)
    review['run_manifest_sha256']=_hash_path(destination/'manifest.json')
    review['generator_sha256']=generator_identity
    _save_json(destination/'review.json',review)
    (destination/'REVIEW.md').write_text(_review_markdown(review,c))
    (destination/'README.md').write_text(_instructions(c,run_id))
    (destination/'roundtrips').mkdir()
    archive=destination/'HyperIO-TPS-tests.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(destination.rglob('*')):
            if p.is_file() and p!=archive:
                z.write(p,'HyperIO-TPS-tests/'+p.relative_to(destination).as_posix())
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise FormatError('generated suite ZIP failed CRC check')
    archive.with_suffix('.zip.sha256').write_text(_hash_path(archive)+'  '+archive.name+'\n')
    return result


def _instructions(c,run_id):
    table='\n'.join('| '+p['plan']+' | '+p['studyset']+' | '+p['purpose']+' |' for p in c['profiles'])
    return f'''# HyperIO TPS validation suite

Run identity: `{run_id}`.
Restore/import the **one native patient folder** `native/1~{c['patient_id']}/` using your normal Monaco native-data workflow.
Do not use the DICOM import browser for this native patient package.
Patient ID: `{c['patient_id']}`; Name: `zzPHYS, Ash`.
It is separate from zzzInputOutputAG and your imported zzzInputOutputAG2.
If you choose another local ID, record it in the review and return the entire native patient rather than renaming individual files outside Monaco.

## One restoration, combined observations

1. Open CT1 without a plan first: it is the returned 100-slice, 5 mm, 500 mm zero-CT image control, with native identity references changed to the suite patient.
2. Open Phantom and inspect Patient/Insert contours, then open Reference.
   If a studyset/plan cannot open, record the exact failure and mark dependent checks blocked; do not interpret failed opening as evidence for an individual setting.
3. Inspect each listed plan once and collect all its initial settings/geometry observations together.
4. Save the reviewed plans, close/reopen the patient once, and collect persistence/independence checks together.
5. Only after geometry and settings review, optionally calculate Reference and retain a separate native/DICOM return for the calculation checks.
   Do not calculate every profile just to inspect settings.

| Plan | Studyset | Combined checks |
|---|---|---|
{table}

CT1 is the intact image control with its original empty contour records.
Phantom adds fixture contours transferred by nearest longitudinal slice onto the returned CT coordinates.
Density has the same images/contours but studyset Insert forced ED 1.2 for the two precedence plans.
Each studyset includes all 100 CT/WC and cached DICOM slices: there are no overlays or three-slice cases.
The local studyset copies share image UIDs because they represent the same images; only their local structure/default-density records differ.
No old dose payloads or calculation logs are supplied.
Source plan grid/checksum/status/normalization and document metadata remain experimental for this transplanted CT; report normalization, stale-state warnings or rejection rather than treating them as accepted.

The .hyp settings filename matches the suite patient ID in every plan directory.
Native patient identity, unique plan names and studyset references are changed together.
Reference retains source beam/settings values but is still a new plan-to-studyset association requiring TPS validation.

## Record results once and keep history

REVIEW.md is grouped by location so opening one plan gives several observations.
review.json is the same run worksheet in structured form.
Each result retains its stable test ID, revision, profile and phase; a save/reopen result does not replace an initial-load result.
Use status not_reviewed, pass, fail, blocked, not_applicable or observation.
Do not mark untested dependent checks passed.
When a field mapping is still an open question, use observation and record the displayed value/mode rather than declaring the mapping validated.
After editing review.json, record it in the perpetual project ledger:

```sh
PYTHONPATH=src python3 -m hyperio record-review PATH_TO_REVIEW_JSON validation/catalogue.json validation/results/events.jsonl
```

A repeated identical import of the review adds no duplicate events.
Later observations append new events, leaving previous results intact.
Keep returned files under roundtrips/<profile-or-patient>/<initial-or-saved-or-recalculated>/ and reference them from the review.
When returning a single patient archive, note which plans were opened/saved/calculated so all applicable tests can use that same return.

catalogue.json is this run's catalogue snapshot.
The perpetual editable catalogue is validation/catalogue.json with its readable list validation/TESTS.org.
manifest.json records all native file hashes, source paths, profile values, generator identity and unresolved assumptions.
changes/ contains text diffs; contour-transfer.json records the source/target slice association for each transferred contour file.
A generated worksheet starts blank; historical CT import success remains in the event ledger and is not erased or applied automatically to this new native restoration.
'''


def record_review(review_path, catalogue_path, event_path):
    """Append completed observations idempotently; never reset previous evidence."""
    review_path,catalogue_path,event_path=map(Path,(review_path,catalogue_path,event_path))
    c=_catalogue(catalogue_path)
    review=json.loads(review_path.read_text())
    if review.get('suite_id')!=c['suite_id'] or not isinstance(review.get('run_id'),str) or not review['run_id']:
        raise ValueError('review suite/run identity missing or incompatible')
    tests={t['id']:t for t in c['tests']}
    profiles={p['id'] for p in c['profiles']}|{'patient','zero-ct-depot'}
    completed=[]
    existing=[]
    if event_path.exists():
        existing=[json.loads(line) for line in event_path.read_text().splitlines() if line.strip()]
    seen={e.get('event_id') for e in existing}
    for o in review['observations']:
        if o.get('test_id') not in tests or o.get('profile_id') not in profiles:
            raise ValueError('unknown stable test or profile identity')
        allowed_profiles=set(tests[o['test_id']]['profiles'] or ['patient'])
        historical_CT=(o['profile_id']=='zero-ct-depot' and o['test_id'] in ('CT-IMPORT','CT-GEOMETRY','CT-ZERO'))
        if o['profile_id'] not in allowed_profiles and not historical_CT:
            raise ValueError('profile is not assigned to this stable test')
        if type(o.get('test_revision')) is not int or not 1<=o['test_revision']<=tests[o['test_id']]['revision']:
            raise ValueError('unknown test revision')
        if o.get('phase') not in ('import','initial','save_reopen','recalculate','export','returned_file_checks'):
            raise ValueError('unknown observation phase')
        status=o.get('status')
        if status=='not_reviewed':continue
        if status not in ('pass','fail','blocked','not_applicable','observation'):
            raise ValueError('unsupported review status; unknown must not become pass')
        if not isinstance(o.get('actual'),str) or not o['actual'].strip():
            raise ValueError('completed observations require the actual result or blocking reason')
        event={'suite_id':c['suite_id'],'run_id':review['run_id'],
               'catalogue_sha256':_hash_path(catalogue_path),'review_source_sha256':_hash_path(review_path),
               'run_manifest_sha256':review.get('run_manifest_sha256'),'generator_sha256':review.get('generator_sha256'),
               'reviewer':review.get('reviewer'),'monaco_version_build':review.get('monaco_version_build'),
               'observed_at':review.get('observed_at'),'patient_id_as_installed':review.get('patient_id_as_installed'),
               **{k:o.get(k) for k in ('test_id','test_revision','profile_id','phase','status','actual','messages','evidence')}}
        # Review-file hash is provenance, not identity: filling another row must not
        # duplicate an unchanged observation already recorded from this worksheet.
        for key in ('run_manifest_sha256','generator_sha256'):
            if event.get(key) is None:event.pop(key,None)
        identity={k:v for k,v in event.items() if k!='review_source_sha256'}
        event_id=_sha(json.dumps(identity,sort_keys=True).encode())
        if event_id in seen:continue
        event['event_id']=event_id
        event['recorded_at']=datetime.now(ZoneInfo('Australia/Brisbane')).isoformat()
        completed.append(event);seen.add(event_id)
    if completed:
        event_path.parent.mkdir(parents=True,exist_ok=True)
        with event_path.open('a',encoding='utf-8') as stream:
            for event in completed:stream.write(json.dumps(event,sort_keys=True)+'\n')
    return len(completed)
