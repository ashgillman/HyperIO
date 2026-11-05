import json

from hyperio.diagnostics import build_diagnostic_report
from test_hyperio import synthetic_export


def test_full_report_retains_underlying_study_errors_and_session_failures(tmp_path):
    _, study = synthetic_export(tmp_path)
    (study / 'info').write_text('12341016\nPRIVATE NAME\n')
    report = build_diagnostic_report(tmp_path, events=[{'error': 'PRIVATE ERROR'}])
    assert report['events'] == [{'error': 'PRIVATE ERROR'}]
    assert report['inspection']['studysets'][0]['diagnostics'] == ['unsupported info version']
    assert any(row['version'] == '12341016' for row in report['files'])


def test_anonymised_report_uses_allowlist_even_for_unrecognised_errors(tmp_path):
    plan, study = synthetic_export(tmp_path)
    (study / 'info').write_text('12341016\nPRIVATE NAME\n')
    (plan / 'tel.1').write_text('SECRET PATIENT\n')
    report = build_diagnostic_report(
        tmp_path, anonymised=True,
        events=[{'error': 'PRIVATE ERROR', 'traceback': '/Users/PRIVATE/person'}],
        outcomes=[{'path': '1~PHANTOM/plan/Test', 'output': None,
                   'error': 'unknown structure names: [PRIVATE STRUCTURE]'}])
    text = json.dumps(report)
    for private in ('PHANTOM', 'Study', 'Test', 'Insert', 'PRIVATE', 'SECRET', str(tmp_path),
                    'CalibrationName', 'Arbitrary model', '19700101'):
        assert private not in text
    assert 'unsupported_info_version' in text
    assert '12341016' in text
    assert 'unknown_structure_names' in text
    assert report['events'] == [{'error_codes': ['unclassified_error_details_withheld']}]
    assert report['plans'][0]['id'] == 'plan_001'
    assert report['plans'][0]['studyset_id'] == 'studyset_001'


def test_anonymised_inspection_failure_withholds_exception_text(tmp_path, monkeypatch):
    import hyperio.diagnostics as diagnostics
    def fail(*args, **kwargs):
        raise ValueError('PRIVATE NAME /Users/secret')
    monkeypatch.setattr(diagnostics, 'inspect_export', fail)
    report = build_diagnostic_report(tmp_path, anonymised=True)
    assert 'PRIVATE' not in json.dumps(report)
    assert report['inspection_error_codes'] == ['unclassified_error_details_withheld']


def test_report_writes_json_and_limits_xml_version_to_numeric_metadata(tmp_path):
    from hyperio.diagnostics import export_diagnostic_report
    plan, _ = synthetic_export(tmp_path / 'source')
    (plan / 'dvhparam.xml').write_text(
        '<XmlFileIo><Metadata><Version>97</Version></Metadata><Private>SECRET</Private></XmlFileIo>')
    target = tmp_path / 'report.json'
    export_diagnostic_report(tmp_path / 'source', target, anonymised=True)
    report = json.loads(target.read_text())
    assert 'SECRET' not in target.read_text()
    assert next(row for row in report['files'] if row['kind'] == 'dvhparam.xml')['version'] == '97'
