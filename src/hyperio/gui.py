"""Compatibility entry points for the RED and DVH desktop applications."""
from .desktop.common import show_message as show_message
from .desktop.dvh import main as dvh_main, select_batch_plans as select_batch_plans
from .desktop.red import main as red_main


def _launch(mode):
    return red_main() if mode == 'red' else dvh_main()
