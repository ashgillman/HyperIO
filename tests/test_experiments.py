"""Validation files are experimental candidates until Monaco review is recorded."""
from pathlib import Path
import json
import zipfile

import pytest

from hyperio import FormatError, HypDocument
from hyperio.experiments import edit_plan_density, edit_static_aperture, build_validation_batch


def plan_bytes():
    return (b"00d5101a\r\n\r\nExample\r\nunknown\r\nPHANTOM\r\n1\r\nStudy\r\n"
            b"2\r\nPatient\r\n2,2,1,1,2\r\nInsert\r\n2,1,1,1,9\r\n")


def tel_bytes():
    lines = [b"00d5101d", b""] + [b"0"] * 170
    start = 2
    values = {0: b"2", 2: b"10x10", 3: b"Machine", 4: b"Unit", 5: b"0,0,0",
              7: b"0,0,0,0,0,0,0,0,0,0,0", 8: b"DRP", 9: b"0,0,0,0,0,0", 10: b"6,-1",
              13: b"5181,6", 16: b"100,100,0,0", 18: b"100,100,0,0",
              22: b"0,0,0,0,0,0,0,0,0", 26: b"1,2,3,1,2,3,0,100"}
    for offset, value in values.items():
        lines[start + offset] = value
    pairs = [(-50, 50) if 28 <= i <= 51 else (-20, 20) for i in range(80)]
    flat = [n for pair in pairs for n in pair]
    for j in range(16):
        lines[start + 151 + j] = ",".join(str(n) for n in flat[j * 10:j * 10 + 10]).encode()
    return b"\r\n".join(lines) + b"\r\n"


def test_plan_density_edits_only_targeted_tokens_and_preserves_source():
    source = plan_bytes()
    edited = edit_plan_density(source, "Insert", uniform_ed=1.1)
    assert source == plan_bytes()
    assert edited == source.replace(b"2,1,1,1,9", b"2,1,1.1000000000000001,1,9")
    assert edit_plan_density(source, "Insert", mode=1) == source.replace(b"2,1,1,1,9", b"1,1,1,1,9")
    with pytest.raises(FormatError):
        edit_plan_density(source, "Missing", uniform_ed=1.1)
    for bad in (0, -1, float('nan'), 16, True):
        with pytest.raises(ValueError):
            edit_plan_density(source, "Insert", uniform_ed=bad)


def test_aperture_probe_changes_two_header_rows_only():
    source = tel_bytes()
    edited = edit_static_aperture(source, "2", "rectangle-header")
    assert edited == source.replace(b"100,100,0,0", b"80,60,0,0")
    assert source == tel_bytes()


def test_leaf_probe_changes_exactly_eight_pairs_in_one_bank():
    source = tel_bytes()
    edited = edit_static_aperture(source, "2", "leaf-notch")
    before = source.splitlines()
    after = edited.splitlines()
    vals_before = [float(n) for row in before[153:169] for n in row.split(b",")]
    vals_after = [float(n) for row in after[153:169] for n in row.split(b",")]
    changes = [i for i, (a, b) in enumerate(zip(vals_before, vals_after)) if a != b]
    assert changes == [2 * i + 1 for i in range(36, 44)]
    assert all(vals_after[i] == 10 for i in changes)
    assert after[:153] == before[:153]
    assert after[169:] == before[169:]
    with pytest.raises(FormatError):
        edit_static_aperture(source.replace(b"100,100,0,0", b"70,70,0,0"), "2", "leaf-notch")


REFERENCE = Path(__file__).resolve().parents[1] / "reference/1~ZZZELEKTAONEHETERO.zip"


@pytest.mark.skipif(not REFERENCE.exists(), reason="supplied archive is local only")
def test_batch_has_exact_manifests_pending_reviews_and_pristine_controls(tmp_path):
    destination = tmp_path / "batch"
    result = build_validation_batch(REFERENCE, destination)
    assert len(result["cases"]) >= 12
    assert (destination / "REVIEW.md").exists()
    review = json.loads((destination / "review-results.json").read_text())
    assert all(row["review_status"] == "not_reviewed" and row["load_result"] is None for row in review["cases"])
    with zipfile.ZipFile(REFERENCE) as source:
        for case in result["cases"]:
            manifest = json.loads((destination / "cases" / case["id"] / "manifest.json").read_text())
            payload = destination / "cases" / case["id"] / "payload"
            actual = {p.relative_to(payload).as_posix() for p in payload.rglob("*") if p.is_file()}
            assert actual == set(manifest["files"])
            changed = set()
            for name in actual:
                data = (payload / name).read_bytes()
                original = source.read(name)
                if data != original:
                    changed.add(name)
                assert data == original or name in manifest["changed_files"]
            assert changed == set(manifest["changed_files"])
            if case["id"] == "V00-original":
                assert not changed
                assert not manifest["omitted_files"]
            else:
                assert not any(p.name == "dose.1" or ".dose." in p.name or p.suffix == ".xlog"
                               for p in payload.rglob("*") if p.is_file())
                assert len(manifest["omitted_files"]) == 5
    (destination / "review-results.json").write_text('{"human": "keep this"}')
    with pytest.raises(FileExistsError):
        build_validation_batch(REFERENCE, destination)
    assert (destination / "review-results.json").read_text() == '{"human": "keep this"}'


def test_named_identity_changes_records_and_paths_without_touching_binary():
    from hyperio.experiments import named_patient_record, named_patient_path
    old = b'00081017\r\nZZZElektaONEHetero^AG\r\nZZZELEKTAONEHETERO\r\n'
    assert named_patient_record('demographic.ZZZELEKTAONEHETERO', old) == (
        b'00081017\r\nzzPHYS^Ash\r\nzzzInputOutputAG\r\n')
    binary = b'\x00ZZZELEKTAONEHETERO\xff'
    assert named_patient_record('T.1.CT', binary) == binary
    assert named_patient_path('1~ZZZELEKTAONEHETERO/demographic.ZZZELEKTAONEHETERO') == (
        '1~zzzInputOutputAG/demographic.zzzInputOutputAG')


@pytest.mark.skipif(not REFERENCE.exists(), reason='supplied archive is local only')
def test_named_batch_identity_and_manifests(tmp_path):
    from hyperio.experiments import build_named_validation_batch
    import hashlib
    dest = tmp_path / 'named'
    result = build_named_validation_batch(REFERENCE, dest)
    assert len(result['cases']) == 17
    assert result['patient_id'] == 'zzzInputOutputAG'
    assert result['patient_name'] == 'zzPHYS, Ash'
    baseline = dest / 'baseline' / '1~zzzInputOutputAG'
    assert (baseline / 'demographic.zzzInputOutputAG').exists()
    assert b'zzPHYS^Ash' in (baseline / 'demographic.zzzInputOutputAG').read_bytes()
    assert b'ZZZELEKTAONEHETERO' not in (baseline / '1~SemiflexWater/info').read_bytes()
    for case in result['cases']:
        folder = dest / 'cases' / case['id']
        manifest = json.loads((folder / 'manifest.json').read_text())
        for name, record in manifest['files'].items():
            data = (folder / 'payload' / name).read_bytes()
            assert hashlib.sha256(data).hexdigest() == record['sha256']
        plan = folder / 'payload/1~zzzInputOutputAG/plan/RefHeteroSq6X/plan'
        assert plan.read_bytes().splitlines()[4] == b'zzzInputOutputAG'
    baseline_manifest = json.loads((dest / 'baseline-manifest.json').read_text())
    actual = {p.relative_to(dest / 'baseline').as_posix() for p in (dest / 'baseline').rglob('*') if p.is_file()}
    assert actual == set(baseline_manifest['files'])
    with zipfile.ZipFile(REFERENCE) as archive:
        for name, record in baseline_manifest['files'].items():
            data = (dest / 'baseline' / name).read_bytes()
            assert hashlib.sha256(data).hexdigest() == record['sha256']
            if name.endswith(('.CT', '.WC')):
                assert data == archive.read(record['source_path'])
    for case_id, key, value in [('V14-force-water', 'FORCEWATER', True),
                                ('V15-mode-zero', 'MCVARPERPLAN', False),
                                ('V16-mode-one', 'MCVARPERPLAN', True)]:
        hyp = next((dest / 'cases' / case_id / 'payload').rglob('*.hyp'))
        assert HypDocument.read(hyp).get(key).value == value
    assert all(c['review_status'] == 'not_reviewed' for c in json.loads((dest / 'review-results.json').read_text())['cases'])
    with pytest.raises(FileExistsError):
        build_named_validation_batch(REFERENCE, dest)
