"""Error details remain readable and copyable even for long batch reports."""
import pytest


def test_message_dialog_retains_and_copies_complete_report():
    tk = pytest.importorskip('tkinter')
    from tkinter import ttk
    from hyperio.gui import show_message
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f'Tk display unavailable: {error}')
    try:
        root.withdraw()
        message = 'Exported 0 of 11 plans.\n\n' + 'Unsupported version — details\n' * 200
        dialog = show_message(root, 'Batch export results', message)
        root.update_idletasks()
        def descendants(parent):
            for child in parent.winfo_children():
                yield child
                yield from descendants(child)
        widgets = list(descendants(dialog))
        text = next(w for w in widgets if isinstance(w, tk.Text))
        assert text.get('1.0', 'end-1c') == message
        assert str(text['state']) == 'disabled'
        text.tag_add('sel', '1.0', '1.8')
        text.event_generate('<<Copy>>')
        assert root.clipboard_get() == 'Exported'
        next(w for w in widgets if isinstance(w, ttk.Button) and w['text'] == 'Copy all').invoke()
        assert root.clipboard_get() == message
        assert dialog.resizable() == (1, 1)
        dialog.destroy()
    finally:
        root.destroy()
