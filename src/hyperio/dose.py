"""Physical sampling of dose arrays and the observed native Monaco dose layout.

The native reader is deliberately separate from metadata inspection: decoding
arrays requires the optional analysis dependencies and is a larger operation.
Coordinates here are native Monaco (x,y,z) millimetres, not DICOM LPS.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from io import BytesIO
import math

from .core import FormatError, _numbers


@dataclass
class DoseGrid:
    """Dose in cGy on a regular native grid with array order (y,z,x).

    ``origin_xyz_mm`` is the first grid-node centre, not the outer voxel edge.
    Public sampling coordinates always use (x,y,z), independently of array order.
    """
    values_cgy: object
    origin_xyz_mm: tuple
    spacing_xyz_mm: tuple
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        import numpy as np
        values = np.array(self.values_cgy, dtype=float, copy=True)
        if values.ndim != 3 or min(values.shape) < 2 or not np.isfinite(values).all():
            raise ValueError('dose array must be finite and have at least two nodes per axis')
        origin = np.asarray(self.origin_xyz_mm, dtype=float)
        spacing = np.asarray(self.spacing_xyz_mm, dtype=float)
        if origin.shape != (3,) or spacing.shape != (3,) or not np.isfinite(origin).all() or not np.isfinite(spacing).all() or (spacing <= 0).any():
            raise ValueError('grid origin/spacing must contain three finite values with positive spacing')
        values.flags.writeable = False
        self.values_cgy = values
        self.origin_xyz_mm = tuple(origin.tolist())
        self.spacing_xyz_mm = tuple(spacing.tolist())

    @property
    def maximum_xyz_mm(self):
        y_count, z_count, x_count = self.values_cgy.shape
        counts_xyz = (x_count, y_count, z_count)
        return tuple(origin + spacing * (count - 1)
                     for origin, spacing, count in zip(self.origin_xyz_mm, self.spacing_xyz_mm, counts_xyz))

    def sample(self, points_xyz_mm, *, outside='raise'):
        """Trilinearly interpolate at physical coordinates using SciPy.

        Samples outside the grid raise by default; ``outside='nan'`` makes that
        condition explicit in returned values rather than silently extrapolating.
        """
        import numpy as np
        from scipy.ndimage import map_coordinates
        if outside not in ('raise', 'nan'):
            raise ValueError('outside must be raise or nan')
        points = np.asarray(points_xyz_mm, dtype=float)
        if points.ndim < 1 or points.shape[-1] != 3 or not np.isfinite(points).all():
            raise ValueError('sampling points must be finite (...,3) native coordinates')
        indices_xyz = (points.reshape(-1, 3) - self.origin_xyz_mm) / self.spacing_xyz_mm
        upper_xyz = np.array(self.values_cgy.shape)[[2, 0, 1]] - 1
        valid = ((indices_xyz >= -1e-10) & (indices_xyz <= upper_xyz + 1e-10)).all(axis=1)
        if outside == 'raise' and not valid.all():
            raise ValueError('sampling point is outside the dose grid')
        # Permit roundoff at a node boundary, but never clamp an exterior dose.
        indices_xyz = np.clip(indices_xyz, 0, upper_xyz)
        values = map_coordinates(self.values_cgy, indices_xyz[:, [1, 2, 0]].T, order=1,
                                 mode='constant', cval=float('nan'), prefilter=False)
        values[~valid] = np.nan
        values = values.reshape(points.shape[:-1])
        return float(values) if values.ndim == 0 else values


def native_dose(data: bytes, source: str = '<memory>', *, max_voxels=25_000_000) -> DoseGrid:
    """Read the observed 00d5301e and 00be301e full-grid profiles using unlzw3.

    The newer profile has 39 text header lines; Unity's older profile has 38,
    omitting the timestamp after the magic. Both have five length-prefixed compressed
    blocks. Four leading zero placeholders precede a full big-endian uint32
    array. Non-placeholder leading blocks are not yet interpreted.
    For the Unity profile, multiply the first scale by the second scalar.
    Scaling/order have DRP and screenshot evidence for the supplied VMAT case;
    they are not declared validated for every Monaco export with this magic.
    """
    import numpy as np
    from unlzw3 import unlzw
    stream = BytesIO(data)
    try:
        version = stream.readline(4096).decode('ascii').rstrip('\r\n')
        header_count = {'00d5301e': 39, '00be301e': 38}.get(version)
        if header_count is None:
            raise FormatError(f'{source}: unsupported native dose header profile {version!r}')
        header = [version] + [stream.readline(4096).decode('ascii').rstrip('\r\n')
                              for _ in range(header_count - 1)]
    except UnicodeDecodeError as exc:
        raise FormatError(f'{source}: invalid native dose text header') from exc
    # Use offsets relative to the format record, retaining the actual raw header.
    offset = 1 if version == '00d5301e' else 0
    if header[1 + offset] != '0,2' or header[7 + offset] != '5':
        raise FormatError(f'{source}: unsupported native dose header profile')
    geometry = _numbers(header[8 + offset], 10)
    scales = _numbers(header[4 + offset], 2)
    if geometry is None or scales is None or geometry[0] != 0:
        raise FormatError(f'{source}: unsupported native dose geometry/scaling')
    base_scale, secondary_factor = scales
    if (_numbers(header[5 + offset], 1) != [1]
            or (version != '00be301e' and secondary_factor != 1)):
        raise FormatError(f'{source}: non-unit secondary dose scaling fields are not yet mapped')
    effective_scale = base_scale * secondary_factor
    if min(base_scale, secondary_factor, effective_scale) <= 0 or not math.isfinite(effective_scale):
        raise FormatError(f'{source}: dose scale factors and their product must be finite and positive')
    counts_xzy = geometry[7:10]
    if any(count != int(count) or count < 2 for count in counts_xzy):
        raise FormatError(f'{source}: invalid dose grid dimensions')
    voxel_count = math.prod(int(count) for count in counts_xzy)
    if voxel_count > max_voxels:
        raise FormatError(f'{source}: dose grid exceeds max_voxels')
    extents_xzy = geometry[1:4]
    if any(extent <= 0 for extent in extents_xzy):
        raise FormatError(f'{source}: invalid dose grid extent')
    payloads = []
    for block_index in range(5):
        length_text = stream.readline(32)
        try:
            length = int(length_text)
        except ValueError as exc:
            raise FormatError(f'{source}: invalid/truncated compressed block length') from exc
        if length <= 0 or length > len(data) - stream.tell():
            raise FormatError(f'{source}: truncated compressed block {block_index}')
        payloads.append(stream.read(length))
    # These are compressed four-byte zero placeholders, not dose subgrids.
    if any(payload != b'\x00\x02\x02\x00' for payload in payloads[:-1]):
        raise FormatError(f'{source}: non-placeholder leading dose blocks are not yet supported')
    try:
        # Native streams omit the .Z wrapper. Restore magic + 16-bit block-mode
        # flags and delegate all code-width/reset/padding behavior to unlzw3.
        decoded = unlzw(b'\x1f\x9d\x90' + payloads[-1])
    except (ValueError, IndexError) as exc:
        raise FormatError(f'{source}: invalid compressed dose payload: {exc}') from exc
    if len(decoded) != voxel_count * 4:
        raise FormatError(f'{source}: decoded dose size disagrees with grid geometry')
    x_count, z_count, y_count = (int(count) for count in counts_xzy)
    values = np.frombuffer(decoded, dtype='>u4').reshape(y_count, z_count, x_count).astype(float) * effective_scale
    # The header orders coordinates (x,z,y). Convert geometry to public xyz;
    # extent spans the first to last grid-node centres, so there are n-1 gaps.
    centre_xyz = np.array(geometry[4:7])[[0, 2, 1]]
    extents_xyz = np.array(extents_xzy)[[0, 2, 1]]
    counts_xyz = np.array(counts_xzy)[[0, 2, 1]]
    metadata = {
        'file': source, 'sha256': hashlib.sha256(data).hexdigest(), 'raw_header': header,
        'format_version': version,
        'codec': 'unlzw3 (.Z header adapter)', 'scale_cgy_per_count': effective_scale,
        'base_scale_cgy_per_count': base_scale, 'secondary_scale_factor': secondary_factor,
        'decoded_payload_sha256': hashlib.sha256(decoded).hexdigest(),
        'compressed_payload_bytes': len(payloads[-1]), 'unparsed_trailer_hex': stream.read().hex(),
        'interpretation': 'fixture-supported full-grid mapping; dose freshness not established',
    }
    return DoseGrid(values, tuple(centre_xyz - extents_xyz / 2),
                    tuple(extents_xyz / (counts_xyz - 1)), metadata)
