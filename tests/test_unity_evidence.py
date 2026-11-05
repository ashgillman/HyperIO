"""Optional end-to-end regression against the supplied Unity phantom capture.

Set HYPERIO_UNITY_EXAMPLE to its local ZIP path; vendor data is not distributed.
These checks establish reconstruction consistency, not independent TPS DVH agreement.
"""
import os
from pathlib import Path

import pytest

SOURCE = Path(os.environ.get('HYPERIO_UNITY_EXAMPLE', 'reference/1~cellIrrad.zip'))


@pytest.mark.skipif(not SOURCE.is_file(), reason='local Unity phantom archive is not distributed')
def test_cellirrad_batch_exports_saved_doses_and_reports_missing_doses(tmp_path, monkeypatch):
    pytest.importorskip('numpy')
    pytest.importorskip('shapely')
    pytest.importorskip('unlzw3')
    openpyxl = pytest.importorskip('openpyxl')
    from hyperio.application_io import discover_plans
    from hyperio.core import inspect_export
    from hyperio import dvh_export

    report = inspect_export(SOURCE)
    assert len(report['plans']) == 5
    assert all(not p['diagnostics'] for p in report['plans'])
    assert all(not s['diagnostics'] for s in report['studysets'])
    results = {}
    calculate = dvh_export.calculate_for_export

    def retain_result(source, plan, boundary):
        result = calculate(source, plan, boundary)
        results[plan['name']] = result
        return result

    monkeypatch.setattr(dvh_export, 'calculate_for_export', retain_result)
    outcomes = dvh_export.batch_export_dvh(SOURCE, discover_plans(SOURCE), tmp_path)
    exported = {Path(o['path']).name: o for o in outcomes if not o['error']}
    assert set(exported) == {'Cells1', 'CraneR', 'WaterandAir'}
    failures = {Path(o['path']).name: o['error'] for o in outcomes if o['error']}
    assert failures == {'CellTesting': 'plan has no saved dose.1', 'test': 'plan has no saved dose.1'}
    expected_structures = {'Cells1': {'target vol. 23', 'target vol. 4'},
                           'CraneR': {'cells', 'well plate ACTUAL'},
                           'WaterandAir': {'target vol. 2'}}
    for name, outcome in exported.items():
        result = results[name]
        assert result['dose_grid']['format_version'] == '00be301e'
        assert {s['structure'] for s in result['structures']} == expected_structures[name]
        # All five beams in each capture share a DRP; compare the plan dose
        # with the sum of separately saved beam doses at that physical point.
        references = result['dose_reference_point_samples']
        assert len(references) == 5
        expected_dose = sum(p['saved_beam_dose_cgy'] for p in references)
        for point in references:
            assert point['sampled_dose_cgy'] == pytest.approx(expected_dose, abs=.001)
        book = openpyxl.load_workbook(outcome['output'], data_only=True)
        try:
            rows = list(book['DVH Statistics'].iter_rows(min_row=4, values_only=True))
            for structure in result['structures']:
                assert structure['volume_cm3'] > 0
                assert 0 <= structure['min_dose_cgy'] <= structure['mean_dose_cgy'] <= structure['max_dose_cgy']
                row = next(row for row in rows if row[0] == structure['structure'])
                assert row[1] == pytest.approx(structure['volume_cm3'])
                assert row[4] == pytest.approx(structure['mean_dose_cgy'])
            assert '00be301e' in book['Provenance']['B6'].value
        finally:
            book.close()
    assert len(list(tmp_path.glob('*.xlsx'))) == 3
