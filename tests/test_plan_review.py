"""Examples: read review metadata directly from bytes, without a full export.

Run with ``python3 -m pytest tests/test_plan_review.py -v``.
These examples need no private patient files or optional DICOM dependencies.

Use ``cost_functions(hyp_bytes, source_name)`` for optimisation records, or
``HypDocument(hyp_bytes, source_name).cost_functions()`` when retaining a
byte-preserving document. Use ``isodose_settings(xml_bytes, source_name)`` and
``dvh_parameters(xml_bytes, source_name)`` for the review XML documents.

The small documents below deliberately use different names, dose values and
margin values from the screenshot fixture. They illustrate the public return
values and unknown/error behavior independently of that one returned patient.
Source names are optional, but supplying one makes provenance useful to callers.
"""
import json

import pytest

from hyperio import (FormatError, HypDocument, cost_functions, dose_reference_points,
                     dvh_parameters, inspect_export, isodose_settings)


def objective(kind='pa', extra='', margins=''):
    """Build one minimal objective in the observed .hyp block grammar.

    Extra scalar properties and nested margin blocks can be supplied separately
    to illustrate extensions and error cases without editing a patient archive.
    """
    return f'''000610b6
!VOIDEF
 name=Different organ
 !COSTFUNCTION
  type={kind}
  status=1
  manual=0
  multicriterial=0
  weight=0.2
  refdose=24
  thresholddose=1
  exponent=4
  isoconstraint=35
  isoeffect=12.75
  relativeimpact=0.3
{extra}{margins} !END
!END
!PROTON_RBE_MODEL_ID
'''.encode()


def xml_settings(goals='', refs='', extra=''):
    """Build one version-5 structure with independent goal and reference lists."""
    return f'''<XmlFileIo><Metadata><Version>5</Version></Metadata><Data>
<IsodoseSettings><DoseStructureParametersList><DoseStructureParameter>
<StructureName>Another target</StructureName><Enabled>1</Enabled>
<HighDoseRef>2</HighDoseRef><MinDoseRef>98</MinDoseRef><PrescribedDose>4800</PrescribedDose>
<RefDoseList>{refs}</RefDoseList><DoseGoalList>{goals}</DoseGoalList>
{extra}</DoseStructureParameter></DoseStructureParametersList></IsodoseSettings>
</Data></XmlFileIo>'''.encode()


def test_public_objectives_retain_per_target_margins_and_native_provenance():
    """Access each target margin and inspect native tokens alongside UI units.

    The single ``shrink_margin_cm`` convenience field is None when target
    margins differ; the complete list still supplies both values in mm.
    """
    margins = '''  !SHRINKMARGINTARGET
   shrinkmargintarget=Target A
   targetmargin=2
  !END
  !SHRINKMARGINTARGET
   shrinkmargintarget=Target B
   targetmargin=7
  !END
'''
    rows = cost_functions(objective(margins=margins), 'different.hyp')
    row = rows[0]
    assert row['structure'] == 'Different organ'
    assert row['reference_dose_cgy'] == 2400
    assert row['isoeffect'] == 12.75
    assert row['effect_unit'] == '%'
    assert row['shrink_margin_cm'] is None
    assert [(m['structure'], m['margin_mm']) for m in row['shrink_margin_targets']] == [('Target A', 2), ('Target B', 7)]
    assert row['shrink_margin_targets'][0]['fields']['targetmargin']['unit'] == 'mm'
    assert row['fields']['refdose']['raw'] == '24'
    assert row['fields']['refdose']['unit'] == 'Gy'
    assert row['fields']['refdose']['file'] == 'different.hyp'
    assert HypDocument(objective(), 'different.hyp').cost_functions()[0]['structure'] == 'Different organ'


def test_unknown_objectives_preserve_literal_data_without_inventing_units():
    """Inspect unfamiliar objective properties while leaving their units unknown."""
    row = cost_functions(objective('future', extra='  vendor_parameter=uninterpreted\n'))[0]
    assert row['type_code'] == 'future'
    assert row['cost_function'] is None
    assert row['effect_unit'] is None
    assert row['isoeffect'] is None
    assert row['raw']['vendor_parameter'] == 'uninterpreted'
    assert row['diagnostics']


def test_absent_objective_values_are_unknown_and_duplicates_are_errors():
    """Distinguish missing values from contradictory or malformed records.

    Missing optional values remain None. Duplicate properties, incomplete
    blocks and invalid booleans raise the public FormatError exception.
    """
    row = cost_functions(b'000610b6\n!VOIDEF\nname=X\n!COSTFUNCTION\ntype=qp\n!END\n!END\n')[0]
    assert row['isoeffect'] is None
    assert row['manual'] is None
    assert row['status'] is None
    with pytest.raises(FormatError, match='duplicate'):
        cost_functions(objective(extra='  weight=0.5\n'))
    with pytest.raises(FormatError, match='incomplete'):
        cost_functions(b'000610b6\n!VOIDEF\nname=X\n')
    with pytest.raises(FormatError, match='boolean'):
        cost_functions(objective().replace(b'manual=0', b'manual=2'))


def test_nonfinite_saved_optimizer_results_are_json_safe_and_explicit():
    """Serialize an uncalculated effect without treating its native NaN as zero."""
    row = cost_functions(objective().replace(b'isoeffect=12.75', b'isoeffect=-1.#IND'))[0]
    assert row['isoeffect'] is None
    assert row['fields']['isoeffect']['raw'] == '-1.#IND'
    assert row['fields']['isoeffect']['special_value'] == 'not_a_number'
    json.dumps(row, allow_nan=False)


@pytest.mark.parametrize('kind,metric,operator,limit,unit', [
    (1, 'Dmin', '>=', 5100, 'cGy'), (2, 'Dmax', '<=', 5100, 'cGy'),
    (3, 'Dmean', '>=', 5100, 'cGy'), (4, 'Dmean', '<=', 5100, 'cGy'),
    (5, 'D3%', '>=', 5100, 'cGy'), (6, 'D0.003cm3', '>=', 5100, 'cGy'),
    (7, 'D3%', '<=', 5100, 'cGy'), (8, 'D0.003cm3', '<=', 5100, 'cGy'),
    (9, 'V5100cGy', '>=', 3, '%'), (10, 'V5100cGy', '>=', .003, 'cm3'),
    (11, 'V5100cGy', '<=', 3, '%'), (12, 'V5100cGy', '<=', .003, 'cm3'),
    (13, 'HI', '<=', 1.2, None), (14, 'CI', '>=', 1.2, None),
])
def test_all_dose_goal_types_use_correct_quantity_and_units(kind, metric, operator, limit, unit):
    """Read the GoalType-dependent bound, including absolute volumes and indices.

    Native absolute volumes are mm³ and the public limits are cm³.
    HI/CI use Index, while dose goals use Dose; all raw fields remain available.
    These synthetic cases exercise the mapped type table, not TPS dose results.
    """
    goals = f'<DoseGoal><GoalType>{kind}</GoalType><Dose>5100</Dose><Volume>3</Volume><Index>1.2</Index><Tolerance>0</Tolerance></DoseGoal>'
    row = isodose_settings(xml_settings(goals), 'isodosesettings.xml')['dose_goals'][0]
    assert (row['metric'], row['operator'], row['limit'], row['limit_unit']) == (metric, operator, limit, unit)
    assert row['source']['file'] == 'isodosesettings.xml'
    assert 'DoseGoal[1]' in row['source']['path']


def test_index_configuration_reference_requests_and_infinite_mean_bounds_are_preserved():
    """Read editable HI reference percentages and a relative-volume cursor request.

    Additional goal bounds remain in raw XML form, so an infinite upper bound
    is preserved even though the primary definition is a lower mean-dose goal.
    """
    goals = '<DoseGoal><GoalType>3</GoalType><Dose>4000</Dose><Volume>-1</Volume><Index>0</Index><Tolerance>20</Tolerance><MeanDoseMaximum>INF</MeanDoseMaximum></DoseGoal>'
    refs = '<RefDose><RefType>1</RefType><RefValue>2</RefValue></RefDose>'
    parsed = isodose_settings(xml_settings(goals, refs))
    s = parsed['structures'][0]
    assert s['high_dose_ref_percent'] == 2
    assert s['min_dose_ref_percent'] == 98
    assert s['prescribed_dose_cgy'] == 4800
    assert s['reference_doses'][0]['raw'] == {'RefType': '1', 'RefValue': '2'}
    assert s['reference_doses'][0]['quantity'] == 'relative_volume'
    assert s['reference_doses'][0]['value'] == 2
    assert s['reference_doses'][0]['unit'] == '%'
    assert parsed['dose_goals'][0]['raw']['MeanDoseMaximum'] == 'INF'
    json.dumps(parsed, allow_nan=False)


def test_xml_namespaces_missing_settings_and_unsupported_goals():
    """Read either XML namespace style and retain future goal types as unknown."""
    data = xml_settings('<DoseGoal><GoalType>99</GoalType><Vendor>keep</Vendor></DoseGoal>')
    data = data.replace(b'<XmlFileIo>', b'<XmlFileIo xmlns="urn:example">')
    row = isodose_settings(data)['dose_goals'][0]
    assert row['goal_type'] == 99
    assert row['metric'] is None and row['limit'] is None
    assert row['raw']['Vendor'] == 'keep'
    assert row['diagnostics']
    assert dvh_parameters(b'<XmlFileIo><Data><DvhParams><Resolution>2</Resolution></DvhParams></Data></XmlFileIo>')['bin_width_cgy'] is None
    with pytest.raises(FormatError):
        dvh_parameters(b'<broken>')
    with pytest.raises(FormatError):
        dvh_parameters(b'<XmlFileIo><Data><DvhParams><Resolution>0</Resolution></DvhParams></Data></XmlFileIo>')


def test_inspect_and_cli_expose_review_data_for_arbitrary_plan_names(tmp_path, capsys):
    """Use the same records through inspect_export() and the inspect CLI.

    A malformed optional file produces a plan diagnostic and None for that
    component; the successfully parsed objectives remain available.
    """
    from test_hyperio import synthetic_export
    from hyperio.cli import main
    plan, _ = synthetic_export(tmp_path)
    (plan / 'phantom.hyp').write_bytes(objective() + b'!BEAMS\n!BEAMDEF\n!END\n!END\n')
    (plan / 'isodosesettings.xml').write_bytes(xml_settings())
    (plan / 'dvhparam.xml').write_bytes(b'<XmlFileIo><Data><DvhParams><Resolution>2</Resolution><BinWidth>5</BinWidth></DvhParams></Data></XmlFileIo>')
    parsed = inspect_export(tmp_path)['plans'][0]
    assert parsed['cost_functions'][0]['reference_dose_cgy'] == 2400
    assert parsed['isodose_settings']['structures'][0]['structure'] == 'Another target'
    assert parsed['dvh_parameters']['resolution_mm'] == 2
    assert parsed['dose_reference_points'][0]['description'] == 'Test field'
    assert main(['inspect', str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)['plans'][0]['cost_functions'] == parsed['cost_functions']
    (plan / 'dvhparam.xml').write_bytes(b'bad XML')
    parsed = inspect_export(tmp_path)['plans'][0]
    assert parsed['dvh_parameters'] is None
    assert parsed['cost_functions']
    assert any('dvhparam.xml' in d for d in parsed['diagnostics'])


def test_drp_records_are_anchored_to_beams_and_validate_arity(tmp_path):
    """Read multiple DRPs by beam identity despite different absolute line numbers.

    The source coordinate record remains in mm and xyz_cm is converted to cm.
    Zero saved dose stays numeric zero; unsupported layouts raise FormatError.
    """
    from test_hyperio import synthetic_export
    plan, _ = synthetic_export(tmp_path)
    data = (plan / 'tel.1').read_bytes()
    second = data.split(b'\n', 1)[1].replace(b'Test field', b'Unrelated second beam')
    second = second.replace(b'DRP\n0,0,0,0,0,0\n', b'DRP\n0,12,-34,56,0,1\n', 1)
    second = second.replace(b'123.4,100,0,1', b'0,100,0,1')
    parsed = dose_reference_points(data + b'\n' * 7 + second, 'tel.1')
    assert len(parsed) == 2
    assert parsed[0]['saved_beam_dose_cgy'] == 123.4
    assert parsed[1]['xyz_cm'] == [1.2, -3.4, 5.6]
    assert parsed[1]['saved_beam_dose_cgy'] == 0  # no UI dash or total-dose inference
    assert parsed[1]['coordinates']['raw'] == '0,12,-34,56,0,1'
    assert parsed[1]['saved_beam_dose']['file'] == 'tel.1'
    with pytest.raises(FormatError, match='DRP'):
        dose_reference_points(data.replace(b'0,0,0,0,123.4,100,0,1', b'0,0,0'), 'tel.1')
    with pytest.raises(FormatError, match='version'):
        dose_reference_points(data.replace(b'00d5101d', b'future00'), 'tel.1')


def test_unknown_sentinels_versions_and_duplicate_xml_fields():
    """Inspect unset XML tokens without turning them into valid numeric settings."""
    data = xml_settings(refs='<RefDose><RefType>0</RefType><RefValue>-1</RefValue></RefDose>')
    data = data.replace(b'<Enabled>1</Enabled>', b'<Enabled>-1</Enabled>')
    data = data.replace(b'<PrescribedDose>4800</PrescribedDose>', b'<PrescribedDose>-1</PrescribedDose>')
    row = isodose_settings(data)['structures'][0]
    assert row['enabled'] is None
    assert row['prescribed_dose_cgy'] is None
    assert row['reference_doses'][0]['value'] is None
    assert row['raw']['Enabled'] == '-1'
    with pytest.raises(FormatError, match='version'):
        isodose_settings(data.replace(b'<Version>5', b'<Version>99'))
    with pytest.raises(FormatError, match='duplicate'):
        isodose_settings(xml_settings(extra='<Enabled>0</Enabled>'))


@pytest.mark.parametrize('kind,unit,scale', [
    ('po', 'cGy', 100), ('qp', 'cGy', 100), ('o_q', 'cGy', 100),
    ('se', 'cGy', 100), ('pa', '%', 1), ('o_v', '%', 1), ('u_v', '%', 1),
    ('mxd', 'cGy', 100), ('u_q', 'cGy', 100), ('conf', None, 1),
])
def test_objective_units_follow_type_instead_of_fixture_values(kind, unit, scale):
    """Interpret native effect values using the objective's mapped units.

    The same native number becomes cGy for dose effects, stays percent for
    volume effects, and stays dimensionless for Conformality.
    """
    row = cost_functions(objective(kind))[0]
    assert row['effect_unit'] == unit
    assert row['isoeffect'] == 12.75 * scale
    assert row['isoconstraint'] == 35 * scale
