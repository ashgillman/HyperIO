"""Launch the MPPG commissioning application from a HyperIO checkout."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from hyperio.commissioning_gui import main

if __name__ == '__main__':
    raise SystemExit(main())
