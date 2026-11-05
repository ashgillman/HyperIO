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


def test_application_log_buttons_export_both_reports(tmp_path, monkeypatch):
    import json
    tk = pytest.importorskip('tkinter')
    from tkinter import filedialog, ttk
    from hyperio.gui import dvh_main
    from test_hyperio import synthetic_export
    source = tmp_path / 'source'
    synthetic_export(source)
    full, anonymous = tmp_path / 'full.json', tmp_path / 'anonymous.json'
    monkeypatch.setattr(filedialog, 'askopenfilename', lambda **kwargs: str(source))
    destinations = iter([str(full), str(anonymous)])
    monkeypatch.setattr(filedialog, 'asksaveasfilename', lambda **kwargs: next(destinations))
    original_tk = tk.Tk
    failures = []

    def create_root():
        root = original_tk()
        root.withdraw()
        step = 0

        def buttons(parent):
            result = {}
            for child in parent.winfo_children():
                if isinstance(child, ttk.Button):
                    result[str(child['text'])] = child
                result.update(buttons(child))
            return result

        def tick():
            nonlocal step
            try:
                widgets = buttons(root)
                if step == 0:
                    assert widgets['Export full logs…'].instate(['disabled'])
                    widgets['Choose ZIP…'].invoke()
                    step = 1
                elif step == 1 and not widgets['Export full logs…'].instate(['disabled']):
                    widgets['Export full logs…'].invoke()
                    step = 2
                elif step == 2 and full.exists() and not widgets['Export anonymised full logs…'].instate(['disabled']):
                    widgets['Export anonymised full logs…'].invoke()
                    step = 3
                elif step == 3 and anonymous.exists():
                    root.quit()
                    return
                root.after(20, tick)
            except Exception as exc:
                failures.append(exc)
                root.quit()

        root.after(0, tick)
        root.after(5000, root.quit)
        return root

    monkeypatch.setattr(tk, 'Tk', create_root)
    try:
        dvh_main()
        assert not failures, failures
        assert json.loads(full.read_text())['anonymised'] is False
        assert json.loads(anonymous.read_text())['anonymised'] is True
        assert 'PHANTOM' not in anonymous.read_text()
    finally:
        if tk._default_root:
            tk._default_root.destroy()
