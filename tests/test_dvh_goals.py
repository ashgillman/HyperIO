import pytest

from hyperio.dvh_goals import (load_catalogue, library_paths, parse_point,
                               overlay_points, matching_groups, regimens, marker)


def test_bundled_libraries_and_tcc_relative_goals():
    paths = {p.stem: p for p in library_paths()}
    assert {'TCC', 'eviq'} <= paths.keys()
    page, = load_catalogue(paths['TCC'])['protocols']
    group, = matching_groups(page, regimens(page)[0], 'Boost_PTV_7000')
    assert len(group['recommendations']) == 7
    assert not matching_groups(page, regimens(page)[0], 'Rectum')
    assert overlay_points(group, 10, '%') == []
    points = overlay_points(group, 10, '%', 7000)
    assert points[0]['dose_cgy'] == 7350
    assert points[0]['volume'] == 2
    assert points[1]['qualifier'] == 'action'
    assert overlay_points(group, 10, 'cm³', 7000)[0]['volume'] == .2


def test_regimen_selects_all_matching_organs_without_crossing_prescriptions():
    page = {'groups': [dict(organ='Rectum', regimen=r, structure_patterns=['*rect*'])
                       for r in ['20#', '39-40#']]}
    assert regimens(page) == ['20#', '39-40#']
    assert matching_groups(page, '39-40#', 'RECTUM')[0]['regimen'] == '39-40#'


@pytest.mark.parametrize('text,direction', [('V95% >= 98%', '^'), ('V107% <= 2%', 'v'),
    ('D2% <= 105%', '<'), ('D98% >= 95%', '>')])
def test_directional_markers(text, direction):
    assert marker(parse_point(text)) == direction


def test_invalid_relative_volume_and_tampered_point(tmp_path):
    assert parse_point('D101% <= 105%') is None
    path = tmp_path / 'bad.json'
    path.write_text('{"schema_version":1,"protocols":[{"groups":[{"recommendations":'
                    '[{"text":"D2% <= 105%","point":{"dose_percent":999}}]}]}]}')
    with pytest.raises(ValueError):
        load_catalogue(path)


def test_selected_structure_statistics_do_not_require_a_cursor():
    from hyperio.dvh_plot import structure_summary
    summary = structure_summary(dict(structure='PTV', volume_cm3=12.5,
        min_dose_cgy=6500., mean_dose_cgy=7000., max_dose_cgy=7350.))
    assert summary == 'PTV  |  Volume: 12.5 cm³  |  Min: 6500 cGy  |  Mean: 7000 cGy  |  Max: 7350 cGy'


@pytest.mark.parametrize('names,shown,active,expected_shown,expected_active', [
    (['Local_contour_name'], [False], 0, [False], 0),
    (['Rectum', 'Bladder'], [False, True], 1, [True, False], 0),
    (['Rectum_A', 'Rectum_B', 'Bladder'], [False, False, True], 2, [True, True, False], 0),
    (['Rectum_A', 'Rectum_B', 'Bladder'], [False, False, True], 1, [True, True, False], 1),
])
def test_goal_selection_filters_only_when_structures_match(names, shown, active, expected_shown, expected_active):
    from hyperio.dvh_plot import DVHPlot

    class Variable:
        def __init__(self, value):
            self.value = value
        def get(self):
            return self.value
        def set(self, value):
            self.value = value

    plot = DVHPlot.__new__(DVHPlot)
    group = dict(organ='Rectum', regimen='20#', structure_patterns=['*Rectum*'],
                 recommendations=[dict(text='V20 Gy <= 30%', point=parse_point('V20 Gy <= 30%'))])
    plot.rows = [dict(structure=name, volume_cm3=10) for name in names]
    plot.goal_pages = [dict(groups=[group])]
    plot.goal_groups = [group]
    plot.active = Variable(active)
    plot.goal_protocol = Variable(0)
    plot.goal_group = Variable(0)
    plot.goal_regimen = Variable('20#')
    plot.goal_apply = Variable(True)
    plot.volume_unit = Variable('%')
    plot.visible = [Variable(value) for value in shown]
    plot.prescription = lambda: None
    plot.draw = lambda: None
    plot.goal_target_changed()
    assert [v.get() for v in plot.visible] == expected_shown
    assert plot.active.get() == expected_active
    points = plot.goal_points()
    assert len(points) == 1
    assert points[0]['dose_cgy'] == 2000
    assert points[0]['volume'] == 30
    # Selecting another plan structure resumes automatic matching.
    plot.match_goal_structure()
    if not any('Rectum' in name for name in names):
        assert plot.goal_points() == []


@pytest.mark.parametrize('qualifier,expected', [
    ('', 'black'), ('Unspecified', 'black'), ('Ideal', '#ff7f0e'),
    (' tolerance ', '#ff7f0e'), ('Acceptable', '#d62728'), ('ACTION', '#d62728'),
])
def test_goal_colours_follow_explicit_qualifiers(qualifier, expected):
    from hyperio.dvh_goals import goal_colour
    assert goal_colour({'qualifier': qualifier}) == expected
