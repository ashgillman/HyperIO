"""Source-linked MPPG 5.b commissioning worksheets and case-file validation."""
from __future__ import annotations

from dataclasses import dataclass
import json
from math import isfinite
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import UUID, uuid4


SOURCE_URL = 'https://doi.org/10.1002/acm2.13641'
PROTOCOL = {'id': 'AAPM MPPG 5.b', 'year': 2022, 'doi': '10.1002/acm2.13641'}
SCHEMA_VERSION = 1

MODELLING = 'Photon modelling'
STATIC = 'Basic photon validation'
HETEROGENEITY = 'Photon heterogeneity'
MODULATED = 'IMRT / VMAT'
ELECTRONS = 'Electron validation'
ROUTINE = 'Routine TPS QA'

BASIC_CRITERIA = (
    'High dose: 2% local for one changed parameter, 5% local for multiple changes. '
    'Penumbra: 2 mm DTA. Tail: 3% of maximum field dose up to 5 cm past the field edge.'
)
STATIC_EVIDENCE = (
    'Measured high-dose, penumbra and tail regions at multiple depths and off-axis positions. '
    'Use depths just beyond dmax, at 10–15 cm and at 25–30 cm where applicable.'
)
COMPOSITE_CRITERIA = (
    'Point dose relative to prescription: 2% in low-gradient targets, 3% in high-gradient OARs. '
    'Investigate planar/volumetric failures at 2% local / 2 mm. '
    'For final pretreatment QA, the guideline gives >95% at 3% global / 2 mm with a 10% threshold.'
)


@dataclass(frozen=True)
class TestSpec:
    group: str
    title: str
    source: str
    setup: str
    evidence: str
    criteria: str
    kind: str = 'photon'


# Paraphrased guidance. Examples are displayed as text and never assigned to a case.
TESTS = {
    '5.1': TestSpec(MODELLING, 'Reference dose per MU', 'Table 4',
        'Use the local absolute calibration geometry for each configured photon beam.',
        'Compare TPS dose per MU at the calibration point with the calibrated output.',
        '0.5% under reference calibration conditions.'),
    '5.2': TestSpec(MODELLING, 'Planning vs modelling module', 'Table 4',
        'If the TPS has a beam-modelling module, choose a large measured field '
        '(the guideline example exceeds 30 × 30 cm²). Repeat for each algorithm.',
        'Compare dose at several points or profiles between the two TPS modules.',
        'Agreement within statistical, grid and material-definition uncertainty.'),
    '5.3': TestSpec(MODELLING, 'Commissioning data spot checks', 'Table 4',
        'Choose nonreference field sizes, depths and off-axis positions.',
        'Compare clinical-module PDDs, output factors or off-axis factors with commissioning data.',
        '2%, using local differences for curves such as PDD.'),
    '5.4': TestSpec(STATIC, 'Small static MLC fields', 'Tables 5–6',
        'Use the smallest static non-SRS, non-IMRT MLC apertures expected clinically.',
        STATIC_EVIDENCE, BASIC_CRITERIA),
    '5.5': TestSpec(STATIC, 'MLC blocking and overtravel', 'Tables 5–6',
        'Use a large, extensively blocked aperture to challenge MLC transmission, overtravel and output.',
        STATIC_EVIDENCE, BASIC_CRITERIA),
    '5.6': TestSpec(STATIC, 'Off-axis and primary collimator', 'Tables 5–6',
        'Use a large off-axis aperture and consider diagonal profiles or collimator rotation.',
        STATIC_EVIDENCE, BASIC_CRITERIA),
    '5.7': TestSpec(STATIC, 'SSD and field divergence', 'Tables 5–6',
        'Use an SSD different from that used for modelling. An asymmetric field at the minimum SSD is an example.',
        STATIC_EVIDENCE, BASIC_CRITERIA),
    '5.8': TestSpec(STATIC, 'Oblique surface incidence', 'Tables 5–6',
        'Challenge oblique incidence. The guideline gives a 10 × 10 cm² example and recommends aiming for at least 20°.',
        STATIC_EVIDENCE, BASIC_CRITERIA),
    '5.9': TestSpec(STATIC, 'Nonphysical wedges', 'Tables 5–6',
        'If used clinically, test each nonphysical wedge angle with a large field (over 15 cm in the example).',
        'Measure the modified dose distribution. An array can be used.',
        BASIC_CRITERIA),
    '6.1': TestSpec(HETEROGENEITY, 'CT-to-density verification', 'Table 7',
        'Use the acquired density phantom scans for all clinical dose-calculation scanners, including applicable on-board systems.',
        'Compare TPS electron or mass densities with known material values spanning air, lung, water and dense bone.',
        'Table 7 gives no numeric tolerance for this test.', 'manual'),
    '6.2': TestSpec(HETEROGENEITY, 'Dose beyond lung material', 'Table 7',
        'Use a low-density slab phantom for each energy. The guideline gives a 5 × 5 cm² example.',
        'Measure and compare the central-axis dose ratio on either side of the heterogeneity, away from buildup/builddown.',
        '3% agreement for the dose comparison.'),
    '7.1': TestSpec(MODULATED, 'Small-field PDD', 'Table 8',
        'Use a static MLC-defined aperture, for example below 2 × 2 cm², at a clinically relevant SSD.',
        'Acquire PDD with a suitable small-field detector, such as a diode or plastic scintillator.',
        'Record the local PDD comparison method. Table 9 describes composite-plan criteria.'),
    '7.2': TestSpec(MODULATED, 'Small-field output', 'Table 8',
        'Use static small square and rectangular MLC apertures, down to 2 × 2 cm² and preferably smaller. '
        'Set jaws to represent modulated delivery.',
        'Measure output factors at a clinically relevant depth with an appropriate small-field detector.',
        'Aim for optimal agreement. Section 7.2 notes that 2% can be difficult for fields of 3 × 3 cm² or smaller.'),
    '7.3': TestSpec(MODULATED, 'TG-119 cases', 'Tables 8–9',
        'Plan both the mock head-and-neck and C-shape cases for the applicable delivery techniques and energies.',
        'Deliver the plans to a QA phantom. Record point or distribution comparisons and patient-specific QA results.',
        COMPOSITE_CRITERIA, 'plan'),
    '7.4': TestSpec(MODULATED, 'Representative clinical cases', 'Tables 8–9',
        'Use at least two representative image sets. Validate each delivery modality and energy separately.',
        'Optimise, deliver and measure in an appropriate phantom. Examine the locations and causes of disagreement.',
        COMPOSITE_CRITERIA, 'plan'),
    '7.5': TestSpec(MODULATED, 'External end-to-end review', 'Tables 8–9',
        'Arrange anthropomorphic end-to-end tests. Section 7.1 recommends two external validations and discusses '
        'head-and-neck and heterogeneous thorax testing.',
        'Acquire images, plan and deliver to the phantom, and submit dosimeters for external review. '
        'If external evaluation is unavailable, arrange independent physicist peer review of end-to-end results.',
        'Aim for 5% of prescription dose in the low-gradient target region.', 'plan'),
    '8.1': TestSpec(ELECTRONS, 'Electron reference dose per MU', 'Table 10',
        'Use the locally calibrated cone, SSD and reference depth.',
        'Compare calculated dose per MU at the calibration point with measured output.',
        '0.5% under reference calibration conditions.', 'electron'),
    '8.2': TestSpec(ELECTRONS, 'Shaped electron fields', 'Table 10',
        'Test custom cutouts at both standard and extended SSD for each energy.',
        'Measure depth-dose and profiles. Preserve lateral scatter equilibrium for the test cutout.',
        '3% of central-ray normalisation dose in high-dose, low-gradient regions. '
        '3 mm DTA for central-axis PDD beyond buildup.', 'electron'),
    '8.3': TestSpec(ELECTRONS, 'Electron surface obliquity', 'Table 10',
        'Use a homogeneous phantom, reference cone and nominal clinical SSD at oblique incidence for each energy.',
        'Measure depth-dose or profiles to evaluate depth-dose and penumbra effects.',
        '5% in the high-dose, low-gradient region.', 'electron'),
    '8.4': TestSpec(ELECTRONS, 'Electron heterogeneity', 'Table 10',
        'Use a heterogeneous phantom at nominal clinical SSD with the reference cone.',
        'Compare with a heterogeneity-corrected manual calculation or chamber measurement. Review the dose distribution qualitatively.',
        'Dose disagreement should stay within 7%.', 'electron'),
    '9': TestSpec(ROUTINE, 'Baseline plans for recalculation', 'Section 9',
        'Select reference plans during commissioning for each configured photon beam and electron energy. '
        'Include representative static/wedge and modulated photon plans as applicable. '
        'For electrons, use heterogeneous anatomy with surface curvature and consider extended distance and bolus.',
        'Keep the reference plan and dose. Recalculate annually or after upgrades and compare to baseline. '
        'Maintain TPS file integrity checks separately.',
        '1% / 1 mm agreement with the reference dose calculation.', 'plan'),
}

GROUP_NOTES = {
    STATIC: 'Apply 5.4–5.8 to each unique open and hard-wedged beam. Add 5.9 for nonphysical wedges.',
    MODULATED: 'Track each applicable delivery technique and configured beam. FFF is a distinct beam.',
}


@dataclass(frozen=True)
class Field:
    label: str
    kind: str = 'text'
    choices: tuple[str, ...] = ()


FIELDS = {
    'name': Field('Case name'),
    'machine': Field('Machine'),
    'beam': Field('Energy / beam'),
    'model': Field('TPS / algorithm / model'),
    'technique': Field('Technique'),
    'phantom': Field('Phantom / CT'),
    'shape': Field('Field shape', choices=(
        'Square', 'Rectangle', 'Circle', 'Asymmetric jaws', 'Custom MLC', 'Electron cutout', 'Other',
    )),
    'field_x_cm': Field('Field X (cm)', 'positive'),
    'field_y_cm': Field('Field Y (cm)', 'positive'),
    'field_plane': Field('Field-size plane', choices=('Isocentre', 'Phantom surface', 'Applicator plane')),
    'ssd_cm': Field('SSD (cm)', 'positive'),
    'sad_cm': Field('SAD (cm)', 'positive'),
    'mu': Field('MU', 'positive'),
    'depths_cm': Field('Depths (cm)', 'depths'),
    'gantry_deg': Field('Gantry (°)', 'angle'),
    'collimator_deg': Field('Collimator (°)', 'angle'),
    'incidence_deg': Field('Surface incidence (°)', 'incidence'),
    'modifier': Field('Wedge / bolus / modifier'),
    'cone': Field('Applicator / cone'),
    'aperture': Field('Jaw / leaf / cutout details'),
    'image_spacing': Field('Image spacing XYZ (mm)', 'spacing'),
    'dose_grid_mm': Field('Dose grid (mm)', 'positive'),
    'mc_uncertainty_pct': Field('MC uncertainty (%)', 'percent'),
    'mc_uncertainty_mode': Field('MC uncertainty mode', choices=('Per Control Point', 'Per Calculation')),
    'reference': Field('Plan / evidence reference'),
    'detector': Field('Detector / method'),
    'notes': Field('Notes / local rationale'),
}

IDENTITY = ('name', 'machine', 'beam', 'model', 'technique', 'phantom')
GEOMETRY = (
    'shape', 'field_x_cm', 'field_y_cm', 'field_plane', 'ssd_cm', 'sad_cm', 'mu',
    'depths_cm', 'gantry_deg', 'collimator_deg', 'incidence_deg', 'modifier', 'aperture',
)
CALCULATION = ('image_spacing', 'dose_grid_mm', 'mc_uncertainty_pct', 'mc_uncertainty_mode')
EVIDENCE = ('reference', 'detector', 'notes')


def case_fields(test_id: str) -> tuple[str, ...]:
    kind = TESTS[test_id].kind
    if kind == 'manual':
        return ('name', 'phantom', 'model', *EVIDENCE)
    if kind == 'plan':
        return (*IDENTITY, *CALCULATION, *EVIDENCE)
    extra = ('cone',) if kind == 'electron' else ()
    return (*IDENTITY, *GEOMETRY, *extra, *CALCULATION, *EVIDENCE)


def _numbers(value, field):
    if isinstance(value, str):
        if field.kind == 'spacing':
            value = value.replace('×', ',').replace('x', ',')
        value = value.split(',')
    if not isinstance(value, list) or not value:
        raise ValueError(f'{field.label} must contain numbers separated by commas.')
    return [_number(item, field) for item in value]


def _number(value, field):
    try:
        if type(value) not in (int, float, str):
            raise ValueError
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f'{field.label} must contain numbers.') from None
    if not isfinite(number):
        raise ValueError(f'{field.label} must contain finite numbers.')
    return number


def _field_value(value, field):
    if field.kind == 'text':
        if not isinstance(value, str):
            raise ValueError(f'{field.label} must be text.')
        value = value.strip()
        if field.choices and value not in field.choices:
            raise ValueError(f'For {field.label}, choose one of the listed options.')
        return value
    if field.kind in ('depths', 'spacing'):
        values = _numbers(value, field)
        if field.kind == 'spacing' and (len(values) != 3 or min(values) <= 0):
            raise ValueError(f'{field.label} requires three positive values in XYZ order.')
        if field.kind == 'depths' and min(values) < 0:
            raise ValueError(f'{field.label} must be nonnegative.')
        return values
    number = _number(value, field)
    if field.kind == 'positive' and number <= 0:
        raise ValueError(f'{field.label} must be greater than zero.')
    if field.kind == 'percent' and not 0 < number <= 100:
        raise ValueError(f'{field.label} must be greater than zero and at most 100.')
    if field.kind == 'angle' and not 0 <= number < 360:
        raise ValueError(f'{field.label} must be at least 0 and less than 360.')
    if field.kind == 'incidence' and not 0 <= number < 90:
        raise ValueError(f'{field.label} must be at least 0 and less than 90.')
    return number


def make_case(test_id, values, *, included=True, case_id=None):
    """Normalise worksheet fields without supplying local clinical settings."""
    allowed = case_fields(test_id)
    if not isinstance(values, dict) or values.keys() - set(allowed):
        raise ValueError(f'Test {test_id} has unknown or invalid case fields.')
    if type(included) is not bool:
        raise ValueError('Case included must be true or false.')
    if case_id is None:
        case_id = uuid4().hex
    try:
        if not isinstance(case_id, str) or UUID(case_id).hex != case_id:
            raise ValueError
    except ValueError:
        raise ValueError('Case ID must be a UUID in compact lowercase form.') from None
    cleaned = {
        key: _field_value(values[key], FIELDS[key])
        for key in allowed
        if key in values and values[key] is not None
        and not (isinstance(values[key], str) and not values[key].strip())
    }
    if not cleaned.get('name'):
        raise ValueError('Enter a case name.')
    if ('field_x_cm' in cleaned or 'field_y_cm' in cleaned) and 'field_plane' not in cleaned:
        raise ValueError('Select a field-size plane when recording field dimensions.')
    if cleaned.get('shape') == 'Square' and {'field_x_cm', 'field_y_cm'} <= cleaned.keys():
        if cleaned['field_x_cm'] != cleaned['field_y_cm']:
            raise ValueError('A square field requires equal X and Y dimensions.')
    return {'id': case_id, 'included': included, 'values': cleaned}


def _validate_cases(cases):
    if not isinstance(cases, dict) or cases.keys() - TESTS.keys():
        raise ValueError('Worksheet cases must be grouped under known MPPG test IDs.')
    checked = {}
    seen = set()
    for test_id in TESTS:
        if test_id not in cases:
            continue
        rows = cases[test_id]
        if not isinstance(rows, list):
            raise ValueError(f'Test {test_id} must contain a list of cases.')
        checked[test_id] = []
        for row in rows:
            if not isinstance(row, dict) or row.keys() != {'id', 'included', 'values'} or row['id'] is None:
                raise ValueError(f'Test {test_id} contains an invalid case record.')
            case = make_case(test_id, row['values'], included=row['included'], case_id=row['id'])
            if case['id'] in seen:
                raise ValueError(f'Duplicate case ID in test {test_id}.')
            seen.add(case['id'])
            checked[test_id].append(case)
    return checked


def load_worksheet(path: Path):
    document = json.loads(path.read_text(encoding='utf-8'))
    if (
        not isinstance(document, dict)
        or document.keys() != {'schema_version', 'protocol', 'cases'}
        or type(document['schema_version']) is not int
        or document['schema_version'] != SCHEMA_VERSION
        or document['protocol'] != PROTOCOL
    ):
        raise ValueError('Expected an AAPM MPPG 5.b worksheet with schema version 1.')
    return _validate_cases(document['cases'])


def save_worksheet(path: Path, cases, *, included_only=False):
    checked = _validate_cases(cases)
    if included_only:
        checked = {
            test_id: [case for case in rows if case['included']]
            for test_id, rows in checked.items()
        }
        checked = {test_id: rows for test_id, rows in checked.items() if rows}
        if not checked:
            raise ValueError('Include at least one case to export.')
    document = {'schema_version': SCHEMA_VERSION, 'protocol': PROTOCOL, 'cases': checked}
    data = json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    temporary = None
    try:
        with NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(data)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
