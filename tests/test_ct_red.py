from zipfile import ZipFile

import pytest

from hyperio.ct_red import read_calibration


@pytest.mark.parametrize('platform,env,expected', [
    ('win32', {'LOCALAPPDATA': '/local'}, '/local/HyperIO/data/cttoed'),
    ('win32', {}, '/home/test/AppData/Local/HyperIO/data/cttoed'),
    ('darwin', {}, '/home/test/Library/Application Support/HyperIO/data/cttoed'),
    ('linux', {'XDG_DATA_HOME': '/xdg'}, '/xdg/hyperio/data/cttoed'),
    ('linux', {'XDG_DATA_HOME': 'relative'}, '/home/test/.local/share/hyperio/data/cttoed'),
])
def test_calibration_directory_order(monkeypatch, platform, env, expected):
    from pathlib import Path
    from hyperio import ct_red
    monkeypatch.setattr(ct_red.sys, 'platform', platform)
    monkeypatch.setattr(ct_red.Path, 'home', lambda: Path('/home/test'))
    monkeypatch.delenv('LOCALAPPDATA', raising=False)
    monkeypatch.delenv('XDG_DATA_HOME', raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert ct_red.calibration_directories() == [Path(expected),
        Path('/home/test/.config/hyperio/data/cttoed'), Path('/home/test/.hyperio/data/cttoed')]


def test_find_calibration_exact_order_and_picker(monkeypatch, tmp_path):
    from hyperio import ct_red
    first, second = tmp_path / 'first', tmp_path / 'second'
    monkeypatch.setattr(ct_red, 'calibration_directories', lambda: [first, second])
    second.mkdir()
    (second / 'DICOM3.Scanner').write_text('not read')
    (second / 'DICOM3.scanner').write_text('not read')
    assert ct_red.find_calibration('Scanner') == second / 'DICOM3.Scanner'
    assert ct_red.find_calibration('SCANNER') is None
    assert ct_red.find_calibration('../Scanner') is None
    assert ct_red.calibration_picker_directory() == second
    first.mkdir()
    (first / 'DICOM3.Scanner').write_text('not read')
    assert ct_red.find_calibration('Scanner') == first / 'DICOM3.Scanner'


def test_picker_creates_first_available_directory(monkeypatch, tmp_path):
    from hyperio import ct_red
    blocked = tmp_path / 'file'
    blocked.write_text('x')
    fallback = tmp_path / 'fallback' / 'cttoed'
    monkeypatch.setattr(ct_red, 'calibration_directories', lambda: [blocked / 'cttoed', fallback])
    assert ct_red.calibration_picker_directory() == fallback
    assert fallback.is_dir()


def test_red_plan_discovery_reads_linked_curve_from_folder_and_zip(tmp_path):
    from hyperio.application_io import load_red_plans
    from test_hyperio import synthetic_export
    source = tmp_path / 'source'
    _, study = synthetic_export(source)
    archive = tmp_path / 'patient.zip'
    with ZipFile(archive, 'w') as zipped:
        for path in source.rglob('*'):
            if path.is_file():
                zipped.write(path, path.relative_to(source))
    assert load_red_plans(source)[0]['ct_to_ed_name'] == 'CalibrationName'
    assert load_red_plans(archive)[0]['ct_to_ed_name'] == 'CalibrationName'
    (study / 'info').write_text('00271016\n0\n')
    assert load_red_plans(source)[0]['ct_to_ed_name'] is None


@pytest.mark.parametrize('header,comment,flag', [
    ('0000100f', '', ''),
    ('00bc100f', 'Calibration note', '0\n'),
    ('00d5100f', '', '0\n'),
])
def test_read_ct_to_ed_table(tmp_path, header, comment, flag):
    path = tmp_path / 'DICOM3.Example'
    path.write_text(f'{header}\n{comment}\n{flag}3\n-1000, 0\n100\n0.001, 1.05, 1.04\n')
    assert read_calibration(path, expected_name='Example') == (
        [-1000, 0, 100], [0.001, 1.05, 1.04])
    with pytest.raises(ValueError, match='selects Another'):
        read_calibration(path, expected_name='Another')


def test_zip_calibration_requires_exact_unique_name(tmp_path):
    path = tmp_path / 'curves.zip'
    curve = '0000100f\n\n2\n-1000, 0\n0.001, 1\n'
    with ZipFile(path, 'w') as archive:
        archive.writestr('clinic/DICOM3.Example', curve)
        archive.writestr('other/DICOM3.example', curve)
    assert read_calibration(path, expected_name='Example') == ([-1000, 0], [0.001, 1])
    with pytest.raises(ValueError, match='found 0'):
        read_calibration(path, expected_name='EXAMPLE')
    with ZipFile(path, 'a') as archive:
        archive.writestr('other/DICOM3.Example', curve)
    with pytest.raises(ValueError, match='found 2'):
        read_calibration(path, expected_name='Example')
