"""Experimental sampled DVHs from native dose and contour data.

Monaco's help documents trilinear dose interpolation, a separate DVH lattice
and dose binning. It does not specify every contour-boundary or bin convention.
This module exposes its reconstruction policies and retains numerical results
even when they do not exactly reproduce the screenshot reference.
"""
from __future__ import annotations

import math
from pathlib import PurePosixPath

from .core import Export, FormatError, inspect_export, _numbers
from .contours import contour_slice
from .dose import native_dose


class DVH:
    """Raw dose statistics plus an explicit interval-binned cumulative curve.

    Dx is interpolated on the binned curve, not taken from np.percentile.
    Samples occupy [k*w, (k+1)*w) intervals and cumulative counts are placed at
    (k+0.5)*w. This convention reproduces the supplied reference quantiles;
    the vendor help documents intervals but does not specify their coordinates.
    """
    def __init__(self, samples_cgy, *, resolution_mm=1, bin_width_cgy=1):
        import numpy as np
        samples = np.array(samples_cgy, dtype=float, copy=True)
        if samples.ndim != 1 or not len(samples) or not np.isfinite(samples).all() or (samples < 0).any():
            raise ValueError('DVH requires nonempty finite nonnegative dose samples')
        if not math.isfinite(resolution_mm) or not math.isfinite(bin_width_cgy) or resolution_mm <= 0 or bin_width_cgy <= 0:
            raise ValueError('DVH resolution and bin width must be positive')
        samples.flags.writeable = False
        self.samples_cgy = samples
        self.resolution_mm = float(resolution_mm)
        self.bin_width_cgy = float(bin_width_cgy)
        indices = np.floor(samples / bin_width_cgy).astype(int)
        self.counts = np.r_[np.bincount(indices), 0]
        self.cumulative_counts = np.cumsum(self.counts[::-1])[::-1]
        self.dose_axis_cgy = (np.arange(len(self.counts)) + .5) * bin_width_cgy

    @property
    def curve(self):
        """JSON-safe cumulative curve, including the full-volume origin."""
        return {'dose_cgy': [0., *self.dose_axis_cgy.tolist()],
                'volume_percent': [100., *(self.cumulative_counts / len(self.samples_cgy) * 100).tolist()]}

    @property
    def statistics(self):
        return {'volume_cm3': len(self.samples_cgy) * self.resolution_mm ** 3 / 1000,
                'min_dose_cgy': float(self.samples_cgy.min()),
                'max_dose_cgy': float(self.samples_cgy.max()),
                'mean_dose_cgy': float(self.samples_cgy.mean())}

    def volume_at_dose(self, dose_cgy, *, absolute=False):
        """Return Vdose in percent, or cm³ with absolute=True, from the curve."""
        import numpy as np
        if not math.isfinite(dose_cgy):
            raise ValueError('dose must be finite')
        count = float(np.interp(dose_cgy, self.dose_axis_cgy, self.cumulative_counts,
                                left=len(self.samples_cgy), right=0))
        return count * self.resolution_mm ** 3 / 1000 if absolute else count / len(self.samples_cgy) * 100

    def dose_at_volume(self, volume_percent):
        """Return Dx by linear inversion of the cumulative histogram.

        Endpoints use raw extrema; interior values use the binned curve,
        bounded by the raw range so a wide bin cannot create a larger maximum.
        """
        import numpy as np
        if not math.isfinite(volume_percent) or not 0 <= volume_percent <= 100:
            raise ValueError('relative volume must be between 0 and 100 percent')
        if volume_percent == 0:
            return float(self.samples_cgy.max())
        if volume_percent == 100:
            return float(self.samples_cgy.min())
        dose = np.interp(len(self.samples_cgy) * volume_percent / 100,
                         self.cumulative_counts[::-1], self.dose_axis_cgy[::-1])
        return float(np.clip(dose, self.samples_cgy.min(), self.samples_cgy.max()))

    def heterogeneity_index(self, high_dose_ref_percent=5, min_dose_ref_percent=95):
        """Monaco help's configurable Dhigh/Dlow form, default D5%/D95%."""
        denominator = self.dose_at_volume(min_dose_ref_percent)
        return self.dose_at_volume(high_dose_ref_percent) / denominator if denominator else None


def _lattice_axis(lower, upper, origin, spacing):
    """Select integer lattice indices; preserve the native grid origin's phase."""
    import numpy as np
    first = math.ceil((lower - origin) / spacing - 1e-10)
    last = math.floor((upper - origin) / spacing + 1e-10)
    return origin + np.arange(first, last + 1) * spacing


def _structure_samples(grid, slices, structure_index, resolution_mm, boundary, max_samples):
    """Hold each native contour over its nearest-slice slab; union its polygons.

    This is a declared reconstruction policy, not a documented Monaco rule.
    In particular, WC vertices are rounded text coordinates and inclusion of
    points exactly on their boundaries measurably changes small volumes.
    """
    import numpy as np
    from shapely import Polygon, union_all, contains_xy, intersects_xy
    include = {'include': intersects_xy, 'exclude': contains_xy}[boundary]
    sample_groups, total_points = [], 0
    for slice_index, section in enumerate(slices):
        records = [p for p in section['polygons'] if p['structure_index'] == structure_index]
        if not records:
            continue
        polygons = [Polygon(record['points_xz_mm']) for record in records]
        if any(not polygon.is_valid or polygon.area <= 0 for polygon in polygons):
            raise FormatError(f'{section["source"]["file"]}: invalid contour polygon')
        geometry = union_all(polygons)
        min_x, min_z, max_x, max_z = geometry.bounds
        x_values = _lattice_axis(min_x, max_x, grid.origin_xyz_mm[0], resolution_mm)
        z_values = _lattice_axis(min_z, max_z, grid.origin_xyz_mm[2], resolution_mm)
        x_mesh, z_mesh = np.meshgrid(x_values, z_values)
        inside = include(geometry, x_mesh, z_mesh)
        x_inside, z_inside = x_mesh[inside], z_mesh[inside]
        y = section['y_mm']
        previous_y = slices[slice_index - 1]['y_mm'] if slice_index else y - (slices[1]['y_mm'] - y)
        next_y = slices[slice_index + 1]['y_mm'] if slice_index + 1 < len(slices) else y + (y - previous_y)
        lower_y, upper_y = (previous_y + y) / 2, (y + next_y) / 2
        y_values = _lattice_axis(lower_y, upper_y, grid.origin_xyz_mm[1], resolution_mm)
        # Slabs are [lower, upper), so a point on the midpoint is sampled once.
        y_values = y_values[y_values < upper_y - 1e-10]
        total_points += len(x_inside) * len(y_values)
        if total_points > max_samples:
            raise ValueError('structure sampling exceeds max_samples')
        for sample_y in y_values:
            points = np.column_stack((x_inside, np.full(len(x_inside), sample_y), z_inside))
            values = grid.sample(points, outside='nan')
            sample_groups.append(values[np.isfinite(values)])
    if not sample_groups or not sum(len(group) for group in sample_groups):
        raise ValueError('structure has no sampled points inside the dose grid')
    return np.concatenate(sample_groups), total_points


def _goal_value(goal, histogram, high_ref, min_ref):
    """Evaluate supported primary goal quantities; never reuse screenshot values."""
    raw, kind = goal['raw'], goal['goal_type']
    if kind in (1, 2, 3, 4):
        return histogram.statistics[{1: 'min_dose_cgy', 2: 'max_dose_cgy', 3: 'mean_dose_cgy', 4: 'mean_dose_cgy'}[kind]]
    if kind in (5, 7):
        return histogram.dose_at_volume(float(raw['Volume']))
    if kind in (6, 8):
        percentage = float(raw['Volume']) / 1000 / histogram.statistics['volume_cm3'] * 100
        return histogram.dose_at_volume(percentage) if 0 <= percentage <= 100 else None
    if kind in (9, 10, 11, 12):
        return histogram.volume_at_dose(float(raw['Dose']), absolute=kind in (10, 12))
    if kind == 13:
        return histogram.heterogeneity_index(high_ref, min_ref) if high_ref is not None and min_ref is not None else None
    return None  # No independently established Monaco CI formula for GoalType 14.


def _criterion_result(goal, histogram, high_ref, min_ref):
    actual = _goal_value(goal, histogram, high_ref, min_ref)
    limit, tolerance = goal['limit'], goal['tolerance']
    indicator = None
    # A finite secondary mean-dose bound is a compound goal. Do not silently
    # report a single-bound result as the outcome of the full expression.
    secondary_bound = goal['raw'].get('MeanDoseMaximum', '-1')
    compound_mean = goal['goal_type'] == 3 and secondary_bound not in ('-1', 'INF', '+INF')
    if actual is not None and limit is not None and not compound_mean:
        if goal['operator'] == '>=':
            meets = actual >= limit
            within = tolerance is not None and actual >= limit - tolerance
        else:
            meets = actual <= limit
            within = tolerance is not None and actual <= limit + tolerance
        indicator = 'green' if meets else 'yellow' if within else 'red'
    return {'metric': goal['metric'], 'actual': actual, 'indicator': indicator,
            'goal': goal, 'interpretation': 'reconstructed primary-bound result; not a clinical approval'}


def calculate_plan_dvh(source, plan_name, *, plan_path=None, structures=None, boundary='include',
                       include_conformity=False, max_samples=5_000_000):
    """Reconstruct a plan's DVH statistics from saved dose and WC polygons.

    Only the observed full-grid native dose profile is currently decoded.
    No numerical values from GT fixtures are consulted by this function.
    Policies are returned alongside results so residual differences stay visible.
    Paddick CI is optional and explicitly labelled as a candidate mapping.
    Supply plan_path to select one plan when names repeat across patient sets.
    """
    import numpy as np
    if boundary not in ('include', 'exclude'):
        raise ValueError('boundary must be include or exclude')
    plans = [plan for plan in inspect_export(source)['plans'] if plan['name'] == plan_name
             and (plan_path is None or plan['path'] == plan_path)]
    if len(plans) != 1:
        raise FormatError('expected one uniquely named plan')
    plan = plans[0]
    if plan['diagnostics']:
        raise FormatError('; '.join(plan['diagnostics']))
    parameters, settings = plan['dvh_parameters'], plan['isodose_settings']
    if parameters is None or settings is None or not plan['beams']:
        raise FormatError('plan is missing DVH configuration or beam geometry')
    resolution, bin_width = parameters['resolution_mm'], parameters['bin_width_cgy']
    if resolution is None or bin_width is None:
        raise FormatError('plan is missing DVH resolution or bin width')
    with Export(source) as export:
        dose_member = plan['path'] + '/dose.1'
        if dose_member not in export.sizes:
            raise FormatError('plan has no saved dose.1')
        grid = native_dose(export.read(dose_member, limit=256_000_000), dose_member)
        patient_prefix = PurePosixPath(plan['path']).parent.parent
        study_prefix = str(patient_prefix / ('1~' + plan['studyset']))
        from .core import study_metadata
        study = study_metadata(export, study_prefix)
        if study['diagnostics']:
            raise FormatError('; '.join(study['diagnostics']))
        slices = sorted((contour_slice(export.read(member), member) for member in export.sizes
                         if str(PurePosixPath(member).parent) == study_prefix and member.endswith('.WC')),
                        key=lambda section: section['y_mm'])
    if len(slices) < 2 or len({section['y_mm'] for section in slices}) != len(slices):
        raise FormatError('nearest-slice sampling requires distinct ordered WC slices')
    if any(_numbers(section['raw_header'][6], 6) != [1, 0, 0, 0, 1, 0] for section in slices):
        raise FormatError('oblique WC contour sampling is not yet supported')
    isocentre = np.asarray(plan['beams'][0]['isocentre_raw'])
    alignment = (isocentre - grid.origin_xyz_mm) / resolution
    if not np.allclose(alignment, np.rint(alignment), atol=1e-8, rtol=0):
        raise FormatError('native grid origin is not commensurate with the requested isocentre-aligned DVH lattice')
    requested = set(structures) if structures is not None else {
        row['structure'] for row in settings['structures'] if row['enabled'] is True}
    structures_by_name = {record['name']: record for record in study['structures']}
    configs = {record['structure']: record for record in settings['structures']}
    unknown = requested - structures_by_name.keys()
    if unknown:
        raise ValueError(f'unknown structure names: {sorted(unknown)}')
    results = []
    histograms = {}
    for name in sorted(requested):
        structure_index = structures_by_name[name]['index']
        samples, all_count = _structure_samples(grid, slices, structure_index, resolution, boundary, max_samples)
        histogram = DVH(samples, resolution_mm=resolution, bin_width_cgy=bin_width)
        histograms[name] = histogram
        config = configs.get(name, {})
        high_ref, min_ref = config.get('high_dose_ref_percent'), config.get('min_dose_ref_percent')
        statistics = histogram.statistics
        hi = histogram.heterogeneity_index(high_ref, min_ref) if high_ref is not None and min_ref is not None else None
        goals = [goal for goal in settings['dose_goals'] if goal['structure'] == name]
        criterion_results = [_criterion_result(goal, histogram, high_ref, min_ref) for goal in goals]
        references = []
        for reference in config.get('reference_doses', []):
            value = reference['value']
            if value is None:
                continue
            if reference['quantity'] == 'dose':
                references.append({'dose_cgy': value, 'volume_percent': histogram.volume_at_dose(value),
                                   'volume_cm3': histogram.volume_at_dose(value, absolute=True),
                                   'query': {'quantity': 'dose', 'value': value}})
            elif reference['quantity'] == 'relative_volume':
                references.append({'dose_cgy': histogram.dose_at_volume(value), 'volume_percent': value,
                                   'volume_cm3': value / 100 * statistics['volume_cm3'],
                                   'query': {'quantity': 'relative_volume', 'value': value}})
        results.append({'structure': name, **statistics, 'dvh_curve': histogram.curve, 'heterogeneity_index': hi,
                        'percent_in_volume': len(samples) / all_count * 100,
                        'is_in_ss': not any(p['structure_index'] == structure_index
                                            for section in (slices[0], slices[-1]) for p in section['polygons']),
                        'criterion_results': criterion_results, 'reference_requests': references,
                        'paddick_conformity_index': None})
    if include_conformity:
        # Sample the same lattice throughout the calculated volume. This is an
        # optional, potentially larger operation used only for a CI candidate.
        axes = [_lattice_axis(low, high, low, resolution)
                for low, high in zip(grid.origin_xyz_mm, grid.maximum_xyz_mm)]
        if math.prod(len(axis) for axis in axes) > max_samples:
            raise ValueError('conformity calculation exceeds max_samples')
        x_mesh, z_mesh = np.meshgrid(axes[0], axes[2])
        thresholds = {configs[row['structure']]['prescribed_dose_cgy'] for row in results
                      if configs.get(row['structure'], {}).get('prescribed_dose_cgy') is not None}
        counts = {threshold: 0 for threshold in thresholds}
        for y in axes[1]:
            values = grid.sample(np.column_stack((x_mesh.ravel(), np.full(x_mesh.size, y), z_mesh.ravel())))
            binned = (np.floor(values / bin_width) + .5) * bin_width
            for threshold in thresholds:
                # Match volume_at_dose's linear cumulative curve, including
                # a fractional contribution between adjacent bin midpoints.
                counts[threshold] += float(np.clip(1 + (binned - threshold) / bin_width, 0, 1).sum())
        for row in results:
            threshold = configs.get(row['structure'], {}).get('prescribed_dose_cgy')
            if threshold is None:
                continue
            prescription_volume = counts[threshold] * resolution ** 3 / 1000
            covered = histograms[row['structure']].volume_at_dose(threshold, absolute=True)
            row['paddick_conformity_index'] = covered ** 2 / (row['volume_cm3'] * prescription_volume) if prescription_volume else None
    drp_checks = [{'description': point['description'], 'sampled_dose_cgy': grid.sample(np.asarray(point['xyz_cm']) * 10),
                   'saved_beam_dose_cgy': point['saved_beam_dose_cgy']} for point in plan['dose_reference_points'] or []]
    limitations = ['Contour boundary and histogram conventions remain provisional; inspect residual differences.',
                   'Paddick CI is a candidate mapping, not a documented Monaco formula.',
                   'A decoded saved dose does not establish dose freshness or validity.']
    if grid.metadata.get('format_version') == '00be301e':
        limitations.append('Unity full-grid decoding has CellIrrad beam/plan reference-dose consistency evidence; '
                           'independent Monaco DVH statistics agreement has not been established.')
    return {'plan': plan_name, 'plan_path': plan['path'], 'structures': results, 'dose_grid': grid.metadata,
            'dose_reference_point_samples': drp_checks,
            'sampling': {'resolution_mm': resolution, 'bin_width_cgy': bin_width,
                         'origin_xyz_mm': grid.origin_xyz_mm, 'boundary': boundary,
                         'contours': 'union polygons; nearest-slice slabs [lower,upper)',
                         'dose': 'SciPy trilinear interpolation',
                         'bins': 'half-open dose intervals; cumulative counts at midpoints; linear inversion'},
            'limitations': limitations}
