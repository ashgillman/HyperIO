"""Build temporary synthetic fixtures rather than depending on current import packages."""
from pathlib import Path
import pytest


@pytest.fixture(scope='session')
def zero_ct_candidate(tmp_path_factory):
    pytest.importorskip('pydicom')
    pytest.importorskip('numpy')
    from hyperio.blank_ct import build_blank_ct
    source=Path(__file__).resolve().parents[1]/'reference/1~ZZZELEKTAONEHETERO.zip'
    if not source.exists():
        pytest.skip('supplied CT metadata template is local only')
    dest=tmp_path_factory.mktemp('zero-ct-fixture')/'candidate'
    build_blank_ct(source,dest)
    return dest
