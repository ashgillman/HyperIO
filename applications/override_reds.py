"""Launch the RED preset application directly from a HyperIO checkout."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from hyperio.gui import red_main

if __name__ == '__main__':
    raise SystemExit(red_main())
