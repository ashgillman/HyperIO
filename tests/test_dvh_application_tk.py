"""Exercise saved-dose calculation and CSV export through the Tk application."""
import csv
import json

import pytest


def test_dvh_application_calculates_selected_plan_and_exports_csv(tmp_path, monkeypatch):
    tk = pytest.importorskip('tkinter')
    from tkinter import filedialog, ttk
    from hyperio import dvh
    from hyperio.gui import dvh_main
    from test_applications import example_result, plan_bytes

    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f'Tk display unavailable: {error}')
    root.withdraw()
    source = tmp_path / 'export'
    plan = source / 'plan' / 'Example' / 'plan'
    plan.parent.mkdir(parents=True)
    plan.write_bytes(plan_bytes())
    destination = tmp_path / 'dvh.csv'
    provenance = destination.with_suffix('.csv.provenance.json')

    def calculate(path, name, *, plan_path, boundary):
        assert (path, name, plan_path, boundary) == (source, 'Example', 'plan/Example', 'include')
        result = example_result()
        result['structure_order'] = [row['structure'] for row in result['structures']]
        result['structures'][0]['dvh_curve'] = {'dose_cgy': [0, 200], 'volume_percent': [100, 0]}
        return result

    monkeypatch.setattr(dvh, 'calculate_plan_dvh', calculate)
    monkeypatch.setattr(tk, 'Tk', lambda: root)
    monkeypatch.setattr(filedialog, 'askdirectory', lambda **_: str(source))
    monkeypatch.setattr(filedialog, 'asksaveasfilename', lambda **_: str(destination))

    def buttons(widget):
        for child in widget.winfo_children():
            if isinstance(child, ttk.Button):
                yield child['text'], child
            yield from buttons(child)

    step = 0
    failures = []

    def interact():
        nonlocal step
        try:
            controls = dict(buttons(root))
            calculate_button = controls['Calculate DVH']
            save_button = controls['Export spreadsheet…']
            errors = [child.title() for child in root.winfo_children() if isinstance(child, tk.Toplevel)]
            assert not errors, errors
            if step == 0:
                assert calculate_button.instate(['disabled'])
                assert save_button.instate(['disabled'])
                controls['Choose directory…'].invoke()
                step = 1
            elif step == 1 and calculate_button.instate(['!disabled']):
                calculate_button.invoke()
                step = 2
            elif step == 2 and save_button.instate(['!disabled']):
                save_button.invoke()
                step = 3
            elif step == 3 and save_button.instate(['!disabled']) and provenance.exists():
                step = 4
                root.quit()
                return
            root.after(20, interact)
        except Exception as error:
            failures.append(error)
            root.quit()

    try:
        root.after(0, interact)
        root.after(5000, root.quit)
        assert dvh_main() == 0
        assert not failures, failures
        assert step == 4, 'Timed out waiting for the DVH export'
        with destination.open(encoding='utf-8-sig', newline='') as stream:
            assert list(csv.reader(stream))[1][0] == "'=Insert"
        assert json.loads(provenance.read_text())['plan_path'] == 'plan/Example'
    finally:
        root.destroy()
