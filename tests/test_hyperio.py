from pathlib import Path
import json
import zipfile

import pytest

from hyperio import (HypDocument, FormatError, StructureMetadataWarning, inspect_export,
                     compare_settings, snapshot, diff_snapshots, study_structure_value)


HYP = (b"000610b6\r\n!VOIDEF\r\n    name=Patient\r\n!END\r\n"
       b"!DOSEGRIDSIZE    1\r\n!MCVARIANCE    0.01\r\n"
       b"!MCSEGMENTVARIANCE    0.005\r\n!DOSETOMEDIUM    1\r\n"
       b"!FORCEWATER    0\r\n!UNKNOWN   opaque\r\n")


def test_hyp_retains_raw_bytes_and_independent_fields():
    doc = HypDocument(HYP, "test.hyp")
    assert doc.to_bytes() == HYP
    assert doc.get("MCVARIANCE").value == 0.01
    assert doc.get("MCSEGMENTVARIANCE").value == 0.005
    assert doc.get("MCVARPERPLAN") is None
    assert doc.get("DOSEGRIDSIZE").line == 5
    assert doc.get("DOSEGRIDSIZE").unit == "mm (inferred)"
    assert doc.directives["UNKNOWN"][0].raw == "opaque"


def test_edit_is_a_copy_preserving_unknowns_whitespace_and_line_endings():
    original = HypDocument(HYP)
    edited = original.with_value("DOSEGRIDSIZE", 2)
    assert original.to_bytes() == HYP
    assert edited.to_bytes() == HYP.replace(b"!DOSEGRIDSIZE    1", b"!DOSEGRIDSIZE    2")
    assert edited.get("DOSEGRIDSIZE").value == 2


@pytest.mark.parametrize("payload", [b"1.#INF", b"-1.#IND", b"nan", b"-nan(ind)", b"bogus"])
def test_nonfinite_or_invalid_numeric_value_is_not_a_setting(payload):
    with pytest.raises(FormatError):
        HypDocument(b"000610b6\n!MCVARIANCE " + payload + b"\n").get("MCVARIANCE")


def test_missing_duplicate_and_future_versions_do_not_get_defaults():
    doc = HypDocument(HYP + b"!DOSEGRIDSIZE 2\n")
    with pytest.raises(FormatError, match="multiple"):
        doc.get("DOSEGRIDSIZE")
    with pytest.raises(FormatError, match="version"):
        HypDocument(HYP.replace(b"000610b6", b"ffffffff")).get("DOSEGRIDSIZE")
    with pytest.raises(FormatError):
        HypDocument(HYP).with_value("MCVARPERPLAN", True)
    with pytest.raises(FormatError):
        HypDocument(HYP).with_value("UNKNOWN", 1)


@pytest.mark.parametrize("key,value", [("DOSETOMEDIUM", 2), ("DOSEGRIDSIZE", float("nan")),
                                      ("DOSEGRIDSIZE", True), ("MCVARIANCE", "1\n!FORCEWATER 1")])
def test_edit_rejects_invalid_or_injected_values(key, value):
    with pytest.raises((ValueError, FormatError)):
        HypDocument(HYP).with_value(key, value)


def test_comparison_requires_explicit_expectations_and_reports_missing():
    settings = HypDocument(HYP).settings()
    results = compare_settings(settings, {"DOSEGRIDSIZE": 1, "MCVARIANCE": 0.02,
                                          "MCVARPERPLAN": False})
    assert [r["status"] for r in results] == ["match", "mismatch", "unknown"]
    assert results[0]["source"]["line"] == 5
    with pytest.raises(ValueError):
        compare_settings(settings, {"DOSEGRIDZSIE": 1})
    with pytest.raises(ValueError):
        compare_settings(settings, {"DOSETOMEDIUM": 2})


def test_snapshot_diff_detects_content_without_timestamp_noise(tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.mkdir()
    new.mkdir()
    (old / "a").write_bytes(b"same")
    (new / "a").write_bytes(b"same")
    (old / "b").write_bytes(b"before")
    (new / "b").write_bytes(b"after")
    (new / "c").write_bytes(b"new")
    changes = diff_snapshots(snapshot(old), snapshot(new))
    assert [(c["path"], c["status"]) for c in changes] == [("b", "changed"), ("c", "added")]
    assert changes[0]["text_diff"]


def test_snapshot_refuses_duplicate_zip_members_and_unsafe_paths(tmp_path):
    for names in [("a", "a"), ("../escape",), ("/absolute",)]:
        zpath = tmp_path / "bad.zip"
        with zipfile.ZipFile(zpath, "w") as z:
            import warnings
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Duplicate name:", category=UserWarning)
                for n in names:
                    z.writestr(n, "x")
        with pytest.raises(FormatError):
            snapshot(zpath)


def test_missing_hyp_keeps_plan_visible_with_diagnostic(tmp_path):
    plan_dir = tmp_path / "patient" / "plan" / "Example"
    plan_dir.mkdir(parents=True)
    (plan_dir / "plan").write_text("unknown\n")
    report = inspect_export(tmp_path)
    assert len(report["plans"]) == 1
    assert report["plans"][0]["diagnostics"]
    assert report["plans"][0]["settings"] == {}


REFERENCE = Path(__file__).resolve().parents[1] / "reference/1~ZZZELEKTAONEHETERO.zip"


@pytest.mark.skipif(not REFERENCE.exists(), reason="local supplied archive is not distributed")
def test_supplied_archive_six_plans_and_density_overrides():
    report = inspect_export(REFERENCE)
    assert report["file_count"] == 5735
    assert len(report["plans"]) == 6
    assert len(report["studysets"]) == 6
    for plan in report["plans"]:
        assert not plan["diagnostics"]
        assert plan["settings"]["DOSEGRIDSIZE"]["value"] == 1
        assert plan["settings"]["MCVARPERPLAN"] is None
        expected_uncertainty = 0.005 if plan["name"].endswith("6F") else 0.01
        assert plan["settings"]["MCVARIANCE"]["value"] == expected_uncertainty
        assert plan["settings"]["MCSEGMENTVARIANCE"]["value"] == expected_uncertainty
        assert len(plan["calculation_logs"]) == 1
        assert len(plan["calculation_logs"][0]["completion_events"]) == 1
        assert plan["calculation_logs"][0]["per_segment_percent"][0]["value"] == 100 * expected_uncertainty
        assert len(plan["beams"]) == 3
        assert [b["description"] for b in plan["beams"]] == ["3x3", "5x5", "10x10"]
        assert all(b["algorithm_code"] == 6 for b in plan["beams"])
        insert = next(s for s in plan["density_overrides"] if s["name"] == "Insert")
        expected_ed = 1.606 if plan["name"].startswith("HD") else 0.283 if plan["name"].startswith("LD") else 1
        assert insert["uniform_ed"] == pytest.approx(expected_ed)
        assert insert["mode"] == "forced"
        study = next(s for s in report["studysets"] if s["name"] == plan["studyset"])
        assert study["ct_to_ed_name"]["value"] == "RoutineSep21"
    json.dumps(report, allow_nan=False)


def synthetic_export(root):
    """Independent tiny files exercise arities and links without vendor assets."""
    patient = root / "1~PHANTOM"
    plan_dir = patient / "plan" / "Test"
    study_dir = patient / "1~Study"
    plan_dir.mkdir(parents=True)
    study_dir.mkdir()
    (plan_dir / "plan").write_text("00d5101a\n\nTest\nunknown\nPHANTOM\n1\nStudy\n"
                                   "1\nInsert\n2,1,0.3,1,1\n")
    (plan_dir / "phantom.hyp").write_bytes(HYP + b"!BEAMS\n!BEAMDEF\n!END\n!END\n")
    beam = ["0"] * 35
    for index, value in {0: "1", 2: "Test field", 3: "Arbitrary model", 4: "Unit",
                         5: "0,0,0", 7: ",".join(["0"] * 11), 8: "DRP", 9: "0,0,0,0,0,0",
                         10: "6,-1", 13: "5181,6", 22: ",".join(["0"] * 9),
                         26: "1,2,3,1,2,3,0,100", 34: '0,0,0,0,123.4,100,0,1'}.items():
        beam[index] = value
    (plan_dir / "tel.1").write_text("00d5101d\n" + "\n".join(beam) + "\n")
    (study_dir / "info").write_text("00271016\n0\nCalibrationName\nPHANTOM\nStudy\n" + "0\n" * 13)
    (study_dir / "contournames").write_text("00131027\n1\nInsert\n1,0.3,2,1,19700101.1,0,1,1\n"
                                           "\n1,2,3,4,5,6\n")
    return plan_dir, study_dir


def test_directory_and_zip_have_identical_semantics(tmp_path):
    synthetic_export(tmp_path / "export")
    zpath = tmp_path / "export.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        for p in (tmp_path / "export").rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(tmp_path / "export"))
    directory = inspect_export(tmp_path / "export")
    zipped = inspect_export(zpath)
    assert directory["plans"] == zipped["plans"]
    assert directory["studysets"] == zipped["studysets"]
    assert not directory["plans"][0]["diagnostics"]
    assert not directory["studysets"][0]["diagnostics"]
    assert directory["plans"][0]["beams"][0]["machine_id"] == "Arbitrary model"
    assert directory["studysets"][0]["ct_to_ed_name"]["value"] == "CalibrationName"


def test_ambiguous_density_table_and_hyp_are_diagnostics(tmp_path):
    plan_dir, _ = synthetic_export(tmp_path)
    with (plan_dir / "plan").open("a") as f:
        f.write("1\nOther\n2,1,1,1,1\n")
    (plan_dir / "extra.hyp").write_bytes(HYP)
    plan = inspect_export(tmp_path)["plans"][0]
    assert any("density table" in d for d in plan["diagnostics"])
    assert any("found 2" in d for d in plan["diagnostics"])


def test_cli_checks_unknowns_mismatches_and_invalid_profiles(tmp_path, capsys):
    from hyperio.cli import main
    synthetic_export(tmp_path / "export")
    profile = tmp_path / "profile.json"
    profile.write_text('{"DOSETOMEDIUM": true}')
    assert main(["check", str(tmp_path / "export"), str(profile)]) == 0
    assert json.loads(capsys.readouterr().out)["plans"][0]["checks"][0]["status"] == "match"
    for expected, status in [('{"MCVARPERPLAN": false}', "unknown"), ('{"DOSEGRIDSIZE": 2}', "mismatch")]:
        profile.write_text(expected)
        assert main(["check", str(tmp_path / "export"), str(profile)]) == 1
        assert json.loads(capsys.readouterr().out)["plans"][0]["checks"][0]["status"] == status
    profile.write_text('{"DOSEGRIDZSIE": 1}')
    assert main(["check", str(tmp_path / "export"), str(profile)]) == 2
    assert "unknown expectation" in capsys.readouterr().err


def test_empty_exports_cannot_pass_audit(tmp_path, capsys):
    from hyperio.cli import main
    source = tmp_path / "empty"
    source.mkdir()
    profile = tmp_path / "profile.json"
    profile.write_text('{"DOSETOMEDIUM": true}')
    assert main(["check", str(source), str(profile)]) == 1
    capsys.readouterr()


def test_snapshot_hashes_binary_and_reports_removed_and_newline_changes(tmp_path):
    root = tmp_path / "export"
    root.mkdir()
    (root / "dose.1").write_bytes(b"\x00\xff\x10")
    (root / "plan").write_bytes(b"a\r\n")
    before = snapshot(root)
    assert "text" not in before["files"]["dose.1"]
    (root / "plan").write_bytes(b"a\n")
    after = snapshot(root)
    del after["files"]["dose.1"]
    assert [(c["path"], c["status"]) for c in diff_snapshots(before, after)] == [
        ("dose.1", "removed"), ("plan", "changed")]


def test_settings_inside_known_blocks_are_not_global_settings():
    doc = HypDocument(b"000610b6\n!VOIDEF\n!DOSEGRIDSIZE 1\n!END\n")
    with pytest.raises(FormatError, match="scope"):
        doc.get("DOSEGRIDSIZE")


def test_studyset_link_failure_is_reported(tmp_path):
    plan_dir, _ = synthetic_export(tmp_path)
    p = plan_dir / "plan"
    p.write_text(p.read_text().replace("\nStudy\n", "\nMissing\n"))
    assert any("linked studyset" in d for d in inspect_export(tmp_path)["plans"][0]["diagnostics"])


def test_edit_preserves_unknown_bytes_and_missing_final_newline():
    data = b"000610b6\r\n!UNKNOWN  \x81\xff\r\n!DOSEGRIDSIZE\t1  "
    edited = HypDocument(data).with_value("DOSEGRIDSIZE", 2)
    assert edited.to_bytes() == data.replace(b"\t1  ", b"\t2  ")


def test_incomplete_beam_parsing_is_a_diagnostic(tmp_path):
    plan_dir, _ = synthetic_export(tmp_path)
    hyp = plan_dir / "phantom.hyp"
    hyp.write_bytes(hyp.read_bytes() + b"!BEAMS\n!BEAMDEF\n!END\n!END\n")
    assert any("beam definition count" in d for d in inspect_export(tmp_path)["plans"][0]["diagnostics"])


def test_log_values_are_separate_from_requested_settings():
    from hyperio.logs import calculation_log
    data = (b'\xef\xbb\xbf<Log>\n<Time>capture time</Time>\n'
            b'<Message>History density: 10526.8 mcStdDev: 0.01 oversampling: 1</Message>\n</Log>'
            b'<Log>\n<Message># For the entire calculation: 0.69 percent #</Message>\n</Log>'
            b'<Log>\n<Message># For each segment (control point): 1 percent #</Message>\n</Log>'
            b'<Log>\n<Message>Dose Calculation Completed</Message>\n</Log>')
    result = calculation_log(data, "RxA.xlog")
    assert result["mc_stddev"][0]["value"] == 0.01
    assert result["entire_calculation_percent"][0]["value"] == 0.69
    assert result["per_segment_percent"][0]["value"] == 1
    assert result["mc_stddev"][0]["line"] == 3
    assert len(result["completion_events"]) == 1
    with pytest.raises(FormatError):
        calculation_log(b"<Log><Message>truncated", "bad.xlog")


def test_unsupported_tel_reports_version_without_spurious_beam_mismatch(tmp_path):
    plan_dir, _ = synthetic_export(tmp_path)
    (plan_dir / 'tel.1').write_bytes(b'ffffffff\n')
    diagnostics = inspect_export(tmp_path)['plans'][0]['diagnostics']
    assert any("unsupported tel.1 version 'ffffffff'" in d for d in diagnostics)
    assert not any('beam definition count' in d for d in diagnostics)


def test_unity_metadata_uses_observed_record_shapes(tmp_path):
    plan_dir, study_dir = synthetic_export(tmp_path)
    for path, old, new in [(plan_dir / 'plan', '00d5101a', '00be101a'),
                            (plan_dir / 'tel.1', '00d5101d', '00be101d'),
                            (study_dir / 'info', '00271016', '00241016'),
                            (study_dir / 'contournames', '00131027', '00121027')]:
        path.write_text(path.read_text().replace(old, new, 1))
    report = inspect_export(tmp_path)
    assert not report['plans'][0]['diagnostics']
    assert not report['studysets'][0]['diagnostics']
    assert report['plans'][0]['beams'][0]['isocentre_raw'] == [1, 2, 3]
    assert report['plans'][0]['dose_reference_points'][0]['saved_beam_dose_cgy'] == 123.4
    assert report['studysets'][0]['ct_to_ed_name']['value'] == 'CalibrationName'
    assert report['studysets'][0]['structures'][0]['uniform_ed'] == .3


def test_contournames_trailing_repeats_keep_primary_structures(tmp_path):
    from hyperio.diagnostics import classify_dvh_diagnostics

    _, study_dir = synthetic_export(tmp_path)
    fixture = Path(__file__).parent / 'fixtures' / 'monaco' / 'contournames'
    (study_dir / 'contournames').write_bytes(fixture.read_bytes())

    with pytest.warns(StructureMetadataWarning, match='conflicting contournames definitions') as warnings:
        report = inspect_export(tmp_path, plan_path='1~PHANTOM/plan/Test')
    assert len(warnings) == 1
    diagnostics = classify_dvh_diagnostics(report['plans'][0]['diagnostics'])
    assert [row['severity'] for row in diagnostics] == ['WARN']
    study = report['studysets'][0]
    assert len(study['structures']) == 53
    by_name = {record['name']: record for record in study['structures']}
    assert len(by_name) == len({record['index'] for record in study['structures']}) == 53
    for name, index, density, layer, repeat_layer, repeat_line in [
        ('FemHead_L', 53, 1.226016, 7, 2, 1179),
        ('FemHead_R', 54, 1.206814, 6, 1, 1197),
    ]:
        record = by_name[name]
        assert (record['index'], record['uniform_ed'], record['layer']) == (index, density, layer)
        assert record['conflicting_fields'] == ['uniform_ed', 'layer']
        repeat, = record['repeated_records']
        assert (repeat['name'], repeat['index']) == (name, index)
        assert (repeat['uniform_ed'], repeat['layer'], repeat['source']['line']) == (1, repeat_layer, repeat_line)
        with pytest.warns(StructureMetadataWarning, match="uniform_ed.*using the first record"):
            assert study_structure_value(record, 'uniform_ed') == density
        assert study_structure_value(record, 'index') == index
    for name in ('DCAV', 'Rectum+SpaceOAR'):
        record = by_name[name]
        assert len(record['repeated_records']) == 1
        assert record['conflicting_fields'] == []


@pytest.mark.parametrize('count,name,index', [
    (2, 'Insert', 1),  # a repeat before the declared set is complete
    (1, 'Other', 1),   # index collision
    (1, 'Insert', 2),  # name collision
    (1, 'Other', 2),   # extra unique structure
])
def test_contournames_rejects_inconsistent_structure_tables(tmp_path, count, name, index):
    _, study_dir = synthetic_export(tmp_path)
    (study_dir / 'contournames').write_text(
        f'00121027\n{count}\nInsert\n1,0.3,2,1,19700101.1,0,1,1\n\n1,2,3,4,5,6\n'
        f'{name}\n{index},1,1,1,19700101.1,0,1,1\n\n1,2,3,4,5,6\n'
    )

    report = inspect_export(tmp_path)
    assert report['plans'][0]['diagnostics']


@pytest.mark.parametrize('scoped', [False, True])
def test_linked_studyset_diagnostics_retain_path_and_all_causes(tmp_path, scoped):
    _, study_dir = synthetic_export(tmp_path)
    (study_dir / 'info').unlink()
    (study_dir / 'contournames').write_text('ffffffff\n')
    kwargs = {'plan_path': '1~PHANTOM/plan/Test'} if scoped else {}
    report = inspect_export(tmp_path, **kwargs)
    assert report['plans'][0]['diagnostics'] == [
        'linked studyset 1~PHANTOM/1~Study: missing info',
        'linked studyset 1~PHANTOM/1~Study: unsupported contournames version',
    ]
