"""Tk desktop front ends, shared by Windows and macOS launchers.

Imports of Tk and numerical/export dependencies are deferred until needed.
Workers send results through a queue; all Tk calls stay on the main thread.
"""
from __future__ import annotations

from pathlib import Path
import queue
import threading

from .application_io import discover_plans, load_red_mapping, apply_red_mapping, save_plan_copy
from .core import Export, plan_metadata
from .dvh_export import HEADERS, display_rows, export_dvh_csv, export_dvh_xlsx


def _launch(mode):
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as exc:
        raise SystemExit('These applications require Python with Tk support. '
                         'See applications/README.md for Windows and macOS setup.') from exc

    class Application:
        def __init__(self, root):
            self.root = root
            self.is_red = mode == 'red'
            root.title('HyperIO — RED preset overrides' if self.is_red else 'HyperIO — DVH exporter')
            root.geometry('1250x760')
            root.minsize(850, 450)
            root.columnconfigure(0, weight=1)
            root.rowconfigure(2, weight=1)
            self.source = None
            self.plans = []
            self.selected = None
            self.data = None
            self.result = None
            self.busy = False
            self.messages = queue.Queue()
            self.controls = []
            self.directory = tk.StringVar()
            self.plan = tk.StringVar()
            self.preset = tk.StringVar()
            self.boundary = tk.StringVar(value='include')
            self.export_format = tk.StringVar(value='xlsx')
            self.status = tk.StringVar(value='Choose a patient-set directory or ZIP archive to begin.')

            controls = ttk.Frame(root, padding=12)
            controls.grid(row=0, column=0, sticky='ew')
            controls.columnconfigure(1, weight=1)
            ttk.Label(controls, text='Patient set').grid(row=0, column=0, sticky='w')
            ttk.Entry(controls, textvariable=self.directory, state='readonly').grid(row=0, column=1, sticky='ew', padx=8)
            self.button(controls, 'Choose directory…', self.choose_directory).grid(row=0, column=2)
            self.button(controls, 'Choose ZIP…', self.choose_zip).grid(row=0, column=3, padx=(8, 0))
            ttk.Label(controls, text='Plan').grid(row=1, column=0, sticky='w', pady=8)
            self.plan_box = ttk.Combobox(controls, textvariable=self.plan, state='readonly')
            self.plan_box.grid(row=1, column=1, sticky='ew', padx=8)
            self.plan_box.bind('<<ComboboxSelected>>', self.select_plan)
            self.controls.append((self.plan_box, 'readonly'))
            self.load_button = self.button(controls, 'Load plan' if self.is_red else 'Calculate DVH', self.load)
            self.load_button.grid(row=1, column=2)
            if self.is_red:
                ttk.Label(controls, text='RED preset').grid(row=2, column=0, sticky='w')
                ttk.Entry(controls, textvariable=self.preset, state='readonly').grid(row=2, column=1, sticky='ew', padx=8)
                self.button(controls, 'Choose CSV / TSV…', self.choose_preset).grid(row=2, column=2)
            else:
                ttk.Label(controls, text='Contour boundary').grid(row=2, column=0, sticky='w')
                boundary_box = ttk.Combobox(controls, textvariable=self.boundary, values=['include', 'exclude'], state='readonly', width=15)
                boundary_box.grid(row=2, column=1, sticky='w', padx=8)
                boundary_box.bind('<<ComboboxSelected>>', self.invalidate)
                self.controls.append((boundary_box, 'readonly'))
                ttk.Label(controls, text='Export format').grid(row=3, column=0, sticky='w', pady=(8, 0))
                format_box = ttk.Combobox(controls, textvariable=self.export_format, values=['xlsx', 'csv'], state='readonly', width=15)
                format_box.grid(row=3, column=1, sticky='w', padx=8, pady=(8, 0))
                self.controls.append((format_box, 'readonly'))

            actions = ttk.Frame(root, padding=(12, 0, 12, 8))
            actions.grid(row=1, column=0, sticky='ew')
            if self.is_red:
                self.button(actions, 'Preview preset', self.preview).pack(side='left')
            self.save_button = self.button(actions, 'Save modified plan copy…' if self.is_red else 'Export spreadsheet…', self.save)
            self.save_button.pack(side='left', padx=(8, 0))
            ttk.Label(actions, textvariable=self.status, wraplength=850).pack(side='left', padx=12)

            host = ttk.Frame(root, padding=(12, 0, 12, 8))
            host.grid(row=2, column=0, sticky='nsew')
            host.columnconfigure(0, weight=1)
            host.rowconfigure(0, weight=1)
            headers = ['Structure', 'Current mode', 'Current RED', 'Preset RED', 'Resulting mode'] if self.is_red else HEADERS
            self.table = ttk.Treeview(host, columns=list(range(len(headers))), show='headings')
            for index, name in enumerate(headers):
                self.table.heading(index, text=name)
                self.table.column(index, width=240 if index == 0 or name == 'Dosimetric Criterion' else 145, stretch=False)
            self.table.grid(row=0, column=0, sticky='nsew')
            vertical = ttk.Scrollbar(host, orient='vertical', command=self.table.yview)
            horizontal = ttk.Scrollbar(host, orient='horizontal', command=self.table.xview)
            vertical.grid(row=0, column=1, sticky='ns')
            horizontal.grid(row=1, column=0, sticky='ew')
            self.table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
            self.table.tag_configure('changed', background='#DCE6F1')
            note = ('Preset matches use exact structure names and force the plan-level RED. '
                    'Save creates a separate plan file. Studyset defaults and saved dose are unchanged. '
                    'Native density editing remains experimental and requires Monaco load/save/recalculation review.'
                    if self.is_red else
                    'DVHs are reconstructed from saved native dose, using the enabled structures and saved sampling settings. '
                    'Contour and bin conventions remain provisional; saved dose freshness is unknown. '
                    'Monaco conformity index is unavailable and is exported blank.')
            ttk.Label(root, text=note, wraplength=1100, padding=12).grid(row=3, column=0, sticky='ew')
            self.update_actions()
            root.after(100, self.poll)

        def button(self, parent, label, command):
            widget = ttk.Button(parent, text=label, command=command)
            self.controls.append((widget, 'normal'))
            return widget

        def update_actions(self):
            self.load_button.configure(state='normal' if self.selected and not self.busy else 'disabled')
            self.save_button.configure(state='normal' if self.result is not None and not self.busy else 'disabled')

        def clear_table(self):
            self.table.delete(*self.table.get_children())

        def invalidate(self, event=None):
            self.result = None
            self.clear_table()
            self.status.set('Settings changed. Load the plan again to calculate the DVH.')
            self.update_actions()

        def work(self, operation, success, message):
            if self.busy:
                return
            self.busy = True
            self.status.set(message)
            for widget, state in self.controls:
                widget.configure(state='disabled')

            def run():
                try:
                    self.messages.put((success, operation(), None))
                except Exception as exc:
                    self.messages.put((success, None, exc))
            threading.Thread(target=run, daemon=True).start()

        def poll(self):
            try:
                success, value, error = self.messages.get_nowait()
            except queue.Empty:
                pass
            else:
                self.busy = False
                for widget, state in self.controls:
                    widget.configure(state=state)
                if error is not None:
                    self.status.set(f'Failed: {error}')
                    messagebox.showerror('HyperIO', str(error))
                else:
                    try:
                        success(value)
                    except Exception as exc:
                        self.result = None
                        self.status.set(f'Failed: {exc}')
                        messagebox.showerror('HyperIO', str(exc))
                self.update_actions()
            self.root.after(100, self.poll)

        def choose_directory(self):
            path = filedialog.askdirectory(title='Choose a patient set or a directory containing patient sets')
            if path:
                self.open_source(path)

        def choose_zip(self):
            path = filedialog.askopenfilename(title='Choose a Monaco patient-set ZIP archive',
                                             filetypes=[('ZIP archives', '*.zip'), ('All files', '*.*')])
            if path:
                self.open_source(path)

        def open_source(self, path):
            if not path:
                return
            self.source = Path(path)
            self.directory.set(path)
            self.selected = self.data = self.result = None
            self.plans = []
            self.plan.set('')
            self.plan_box.configure(values=[])
            self.clear_table()
            self.work(lambda: discover_plans(path), self.found_plans, 'Scanning patient sets…')

        def found_plans(self, plans):
            self.plans = plans
            self.plan_box.configure(values=[plan['label'] for plan in plans])
            self.status.set(f'Found {len(plans)} plan(s). Select a plan.' if plans else 'No Monaco plans found in this source.')
            if len(plans) == 1:
                self.plan_box.current(0)
                self.select_plan()

        def select_plan(self, event=None):
            self.selected = self.plans[self.plan_box.current()]
            self.data = self.result = None
            self.clear_table()
            self.status.set(self.selected.get('error') or 'Plan selected. Load it to continue.')
            self.update_actions()

        def load(self):
            if not self.selected:
                return
            self.result = self.data = None
            self.clear_table()
            selected, source = self.selected, self.source
            if selected.get('error'):
                messagebox.showerror('Unreadable plan', selected['error'])
                self.update_actions()
                return
            if self.is_red:
                def read():
                    with Export(source) as export:
                        return export.read(selected['member'])
                self.work(read, self.loaded_red, 'Loading plan density table…')
            else:
                boundary = self.boundary.get()
                def calculate():
                    from .dvh import calculate_plan_dvh
                    result = calculate_plan_dvh(source, selected['name'], plan_path=selected['path'], boundary=boundary)
                    result['plan_path'] = selected['path']
                    # Follow the saved display order, rather than alphabetic calculation order.
                    from .core import inspect_export
                    plan = next(p for p in inspect_export(source)['plans'] if p['path'] == selected['path'])
                    order = {c['structure']: i for i, c in enumerate(plan['isodose_settings']['structures'])}
                    result['structures'].sort(key=lambda row: order[row['structure']])
                    return result
                self.work(calculate, self.loaded_dvh, 'Calculating DVH statistics from saved dose…')

        def loaded_red(self, data):
            self.data = data
            self.preview()

        def choose_preset(self):
            path = filedialog.askopenfilename(title='Choose RED preset', filetypes=[('RED presets', '*.csv *.tsv'), ('All files', '*.*')])
            if path:
                self.preset.set(path)
                self.result = None
                self.clear_table()
                if self.data is not None:
                    self.preview()
                self.update_actions()

        def preview(self):
            self.result = None
            self.clear_table()
            try:
                if self.data is None:
                    self.status.set('Load a plan before previewing a preset.')
                    return
                mapping = load_red_mapping(self.preset.get()) if self.preset.get() else {}
                edited, changes, missing = apply_red_mapping(self.data, mapping)
                for record in plan_metadata(self.data, '<selected-plan>')['density_overrides']:
                    match = record['name'] in mapping
                    self.table.insert('', 'end', values=[record['name'], record['mode'], record['uniform_ed'],
                                      mapping.get(record['name'], ''), 'forced' if match else record['mode']],
                                      tags=('changed',) if match else ())
                self.result = edited if changes else None
                text = f'{len(changes)} matching structure(s) will receive forced REDs.'
                if missing:
                    text += ' Unmatched preset entries: ' + ', '.join(missing)
                if not mapping:
                    text = 'Plan loaded. Choose a RED preset to preview changes.'
                self.status.set(text)
            except Exception as exc:
                messagebox.showerror('Invalid preset', str(exc))
                self.status.set(f'Failed: {exc}')
            finally:
                self.update_actions()

        def loaded_dvh(self, result):
            self.result = result
            for row in display_rows(result):
                self.table.insert('', 'end', values=['' if value is None else f'{value:.3f}' if isinstance(value, float) else value for value in row])
            self.status.set(f'Calculated {len(result["structures"])} structures. Ready to export.')

        def save(self):
            if self.result is None:
                return
            extension = '.' + self.export_format.get()
            path = filedialog.asksaveasfilename(
                title='Save modified plan copy' if self.is_red else 'Export DVH spreadsheet',
                initialfile='plan.RED-overridden' if self.is_red else 'DVH' + extension,
                defaultextension='' if self.is_red else extension,
                filetypes=[('Plan copy', '*.*')] if self.is_red else [('Spreadsheet', '*' + extension)])
            if not path:
                return
            if self.is_red:
                original = self.source if self.source.is_file() else self.source / self.selected['member']
                operation = lambda: save_plan_copy(self.result, original, path)
            else:
                exporter = export_dvh_xlsx if self.export_format.get() == 'xlsx' else export_dvh_csv
                operation = lambda: exporter(self.result, path, source=self.source)
            self.work(operation, lambda _: self.status.set(f'Saved {path}'), 'Saving…')

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise SystemExit(f'Unable to open the desktop GUI: {exc}') from exc
    Application(root)
    root.mainloop()
    return 0


def red_main():
    return _launch('red')


def dvh_main():
    return _launch('dvh')
