"""Native Tk checks for the batch export plan chooser."""
import pytest


@pytest.mark.parametrize('action', ['export', 'cancel', 'close'])
def test_batch_plan_selection_defaults_and_confirmation(action):
    from hyperio.gui import select_batch_plans

    tk = pytest.importorskip('tkinter')
    from tkinter import ttk

    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f'Tk display unavailable: {error}')
    root.update()
    plans = [dict(label='Patient / Plan A'), dict(label='Patient / Plan B')]
    observed = []

    def interact():
        dialog = next(child for child in root.winfo_children() if isinstance(child, tk.Toplevel))
        if not dialog.winfo_viewable():
            root.after(100, interact)
            return

        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        widgets = list(descendants(dialog))
        checks = [widget for widget in widgets if isinstance(widget, ttk.Checkbutton)]
        buttons = {widget.cget('text'): widget for widget in widgets if isinstance(widget, ttk.Button)}
        observed.append([bool(widget.instate(['selected'])) for widget in checks])
        buttons['Clear all'].invoke()
        observed.append(buttons['Continue…'].instate(['disabled']))
        buttons['Select all'].invoke()
        checks[0].invoke()
        observed.append(not buttons['Continue…'].instate(['disabled']))
        if action == 'close':
            dialog.tk.call(dialog.protocol('WM_DELETE_WINDOW'))
        else:
            buttons['Continue…' if action == 'export' else 'Cancel'].invoke()

    try:
        root.after(100, interact)
        result = select_batch_plans(root, plans)
        assert observed == [[True, True], True, True]
        assert result == ([plans[1]] if action == 'export' else None)
        if result:
            assert result[0] is plans[1]
    finally:
        root.destroy()
