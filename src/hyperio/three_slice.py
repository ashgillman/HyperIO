"""Legacy three-slice format fixture; below the documented TPS loading minimum.

Retained for local packaging regression tests, not exposed by the current CLI.
"""
from __future__ import annotations

import difflib
import json
from pathlib import Path
import shutil
import tempfile

from .experiments import (build_named_validation_batch, _sha, _save_json,
                          _write_review_material)

SLICE_POSITIONS = (-600.5, -599.5, -598.5)
STUDY = '1~zzzInputOutputAG/1~SemiflexWater'
PLAN = '1~zzzInputOutputAG/plan/RefHeteroSq6X'


def crop_study_records(info: bytes, index: bytes) -> tuple[bytes, bytes]:
    """Reduce observed count, contour bounds and explicit native slice index.

    The bounds interpretation is a candidate mapping, pending TPS save/reopen.
    Native CT headers and matching WC contour coordinates remain unchanged.
    """
    rows = info.splitlines(keepends=True)
    if rows[0].strip() != b'00271016' or rows[6].strip() != b'311,0,0':
        raise ValueError('three-slice profile requires the observed 311-slice info layout')
    bounds = rows[3].strip().split(b',')
    if len(bounds) != 6:
        raise ValueError('unexpected study bounds layout')
    bounds[1], bounds[4] = b'-600.5', b'-598.5'
    rows[3] = b','.join(bounds) + b'\r\n'
    rows[6] = b'3,0,0\r\n'
    entries = index.splitlines()
    count = int(entries[0])
    if len(entries) < 1 + 2 * count:
        raise ValueError('truncated native slice index')
    pairs = [(entries[1+2*i], entries[2+2*i]) for i in range(count)]
    selected = [(name, position) for name, position in pairs if float(position) in SLICE_POSITIONS]
    if len(selected) != 3 or {float(p) for _, p in selected} != set(SLICE_POSITIONS):
        raise ValueError('index does not contain all three unique requested slices')
    for name, position in selected:
        if name != b'T.' + position + b'.CT':
            raise ValueError('slice filename and coordinate disagree')
    return b''.join(rows), b'3\n' + b''.join(n+b'\n'+p+b'\n' for n,p in selected) + b'\n'


def build_three_slice_batch(source: str | Path, destination: str | Path) -> dict:
    """Each case contains its own three-slice patient; no overlay installation."""
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(f'refusing to overwrite existing batch: {destination}')
    source = Path(source)
    if source.is_dir() and (source.resolve() == destination.resolve() or source.resolve() in destination.resolve().parents):
        raise ValueError('output must be outside the source export')
    with tempfile.TemporaryDirectory(prefix='hyperio-three-slice-') as temporary:
        staging = Path(temporary)/'named'
        result = build_named_validation_batch(source, staging)
        baseline = staging/'baseline'
        study = baseline/STUDY
        info, index = crop_study_records((study/'info').read_bytes(),
                                         (study/'1~SemiflexWater/index.dat').read_bytes())
        selected_names = {f'T.{p:.1f}' for p in SLICE_POSITIONS}
        common = {}
        base_manifest = json.loads((staging/'baseline-manifest.json').read_text())['files']
        for path in baseline.rglob('*'):
            if not path.is_file():
                continue
            name = path.relative_to(baseline).as_posix()
            # Plan files come from the no-dose case, never from the saved-dose baseline.
            if name.startswith(PLAN+'/'):
                continue
            if path.suffix in ('.CT', '.WC') and path.stem not in selected_names:
                continue
            if path.name.endswith('.CT.DCM') and 'T.'+path.name[:-7] not in selected_names:
                continue
            common[name] = path.read_bytes()
        common[STUDY+'/info'] = info
        common[STUDY+'/1~SemiflexWater/index.dat'] = index
        for position in SLICE_POSITIONS:
            stem = f'T.{position:.1f}'
            ct = common[STUDY+'/'+stem+'.CT']
            wc = common[STUDY+'/'+stem+'.WC']
            if float(ct.split(b'\n',6)[5]) != position:
                raise ValueError('native CT header does not match selected slice')
            if float(wc.splitlines()[5].split(b',')[2]) != position:
                raise ValueError('native contour origin does not match selected slice')
        cases = json.loads(json.dumps([c for c in result['cases'] if c['id'] != 'V00-original']))
        cases[0].update(id='V00-three-slice-control', title='Three-slice patient, no saved dose control',
            expected_observation='Patient zzzInputOutputAG / zzPHYS, Ash with three consecutive native CT slices, matching WC contours, and original parameter settings. No saved dose or historical calculation log.',
            review_checks=['Confirm patient identity, SemiflexWater studyset and three axial slices.',
                           'Check all three beam shapes and baseline calculation settings before trying other cases.'])
        result.update(profile='supplied-static-three-slice-v1', cases=cases,
            ct_slice_positions_mm=list(SLICE_POSITIONS), slice_count=3,
            payload_policy='each case is a standalone patient directory; one case at a time',
            dose_policy='no source dose payload or historical calculation log in any case',
            minimum_slice_requirement='user-reported hypothesis; unverified in TPS')
        destination.mkdir(parents=True)
        for case in cases:
            original_id = 'V01-no-dose-control' if case['id']=='V00-three-slice-control' else case['id']
            source_case = staging/'cases'/original_id
            source_manifest = json.loads((source_case/'manifest.json').read_text())
            data = dict(common)
            for path in (source_case/'payload'/PLAN).iterdir():
                if path.is_file():
                    data[PLAN+'/'+path.name] = path.read_bytes()
            # ED studyset probes override only contournames in the shared three-slice data.
            contour = STUDY+'/contournames'
            data[contour] = (source_case/'payload'/contour).read_bytes()
            case_dir = destination/'cases'/case['id']
            records = {}
            for name, content in sorted(data.items()):
                target = case_dir/'payload'/name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                provenance = source_manifest['files'].get(name, base_manifest.get(name))
                records[name] = dict(provenance, sha256=_sha(content), size=len(content))
                if name in (STUDY+'/info', STUDY+'/1~SemiflexWater/index.dat'):
                    records[name]['content'] = 'three-slice metadata edit'
            _save_json(case_dir/'manifest.json', {'schema_version':1,'case':case,
                'source_archive_sha256':result['source_archive_sha256'],'files':records,
                'omitted_files':source_manifest['omitted_files'],
                'slice_positions_mm':list(SLICE_POSITIONS),'monaco_validation':'not_reviewed',
                'source_slice_count':311,'removed_slice_count':308,
                'image_policy':'three native CT/WC and matching source DICOM cache files retained byte-identically',
                'metadata_policy':'info slice count and candidate contour bounds plus native index reduced to three; source plan grid/status/checksum metadata retained pending TPS review'})
            diffs = (source_case/'changes.diff').read_text()
            for name, modified in [(STUDY+'/info',info),(STUDY+'/1~SemiflexWater/index.dat',index)]:
                before = (baseline/name).read_bytes()
                diffs += ''.join(difflib.unified_diff(before.decode('cp1252').splitlines(True),
                    modified.decode('cp1252').splitlines(True),fromfile='named-full-study/'+name,tofile='three-slice/'+name))
            (case_dir/'changes.diff').write_text(diffs)
            (case_dir/'INSTRUCTIONS.md').write_text(f'# {case["id"]}: {case["title"]}\n\n'
                'Load the entire `payload/1~zzzInputOutputAG/` patient directory for this case.\n'
                'It includes three CT slices and matching contours; no baseline merge is required.\n'
                'Use one case at a time, closing the patient before replacing its complete directory.\n\n'
                +case['expected_observation']+'\n\n'+ '\n'.join('- [ ] '+s for s in case['review_checks'])+'\n\n'
                'Record initial load, save/reopen and any calculation separately in REVIEW.md.\n')
        _write_review_material(destination,result)
        (destination/'README.md').write_text('''# Batch 001: standalone three-slice patient cases

Patient ID: `zzzInputOutputAG`.
Name: `zzPHYS, Ash` (native demographic representation `zzPHYS^Ash`).
Every case has its own complete `payload/1~zzzInputOutputAG/` folder with exactly three native CT slices, three matching WC contour files and three matching source DICOM cache files.
There is no separate baseline directory to merge.

## Load sequence

1. Start with `cases/V00-three-slice-control/payload/1~zzzInputOutputAG/`.
2. Restore that whole patient directory using your native Monaco data workflow.
3. Confirm the identity, open studyset `SemiflexWater`, then plan `RefHeteroSq6X`.
4. Confirm three slices appear; record exact messages and screenshot the initial views and settings.
5. If the control loads, test subsequent cases one at a time by replacing the whole validation patient directory while it is closed.
   Do not merge a case into an earlier patient copy, because stale files could survive.
6. Record results in `REVIEW.md` or `review-results.json`, with returned native saves under `roundtrips/<case-id>/`.
   Keep initial load, save/reopen and recalculation captures separate.

## What changed in this rebuilt batch

The source studyset had 311 CT slices.
This batch retains three consecutive source slices at -600.5, -599.5 and -598.5 mm, near the original plan isocentre.
Native CT, matching WC contours and source DICOM cache bytes are unchanged.
The native slice index and info slice-count record now specify three, and candidate longitudinal contour bounds are reduced to the retained positions.
Cached DICOM files retain their source metadata; load the native patient rather than importing these as a new DICOM patient.
The native demographic, plan and studyset patient references use the requested identity.

No case contains source dose payloads or historical calculation logs.
The old saved-dose V00 and duplicate no-dose V01 have been replaced with one V00-three-slice-control.
The remaining V02-V16 cases retain their parameter probes: uncertainty fields/mode, dose grid, density settings, dose deposition, force-water and aperture representation.
Plan grid, checksum and status metadata are retained from the fixture; their normalization and consistency after cropping remain TPS review questions.
The three-slice minimum is a user-reported hypothesis, not a verified Monaco requirement.
This thin slab tests loading and displayed settings/geometry; it does not reproduce the full phantom's dose geometry.

Each manifest inventories every payload file with its hash and source path.
All review fields have been reset to not_reviewed.
Python checks establish packaging consistency only; TPS load/save/calculation behavior remains unvalidated.
''')
        _save_json(destination/'batch.json',result)
        return result
