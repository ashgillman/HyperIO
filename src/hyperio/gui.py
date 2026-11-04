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
from .dvh_export import (HEADERS, display_rows, export_dvh_csv, export_dvh_xlsx,
                         safe_filename_component, calculate_for_export, batch_export_dvh)


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
            root.title('HyperIO — RED preset overrides' if self.is_red else 'HyperIO — DVH explorer / exporter')
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
                advanced = ttk.Menubutton(controls, text='Advanced…')
                advanced.grid(row=1, column=3, padx=(8, 0), sticky='w')
                menu = tk.Menu(advanced, tearoff=False)
                boundary_menu = tk.Menu(menu, tearoff=False)
                for value in ('include', 'exclude'):
                    boundary_menu.add_radiobutton(label=value.capitalize() + ' boundary voxels',
                                                  variable=self.boundary, value=value, command=self.invalidate)
                menu.add_cascade(label='Contour boundary', menu=boundary_menu)
                advanced.configure(menu=menu)
                self.controls.append((advanced, 'normal'))

            actions = ttk.Frame(root, padding=(12, 0, 12, 8))
            actions.grid(row=1, column=0, sticky='ew')
            if self.is_red:
                self.button(actions, 'Preview preset', self.preview).pack(side='left')
            self.save_button = self.button(actions, 'Save modified plan copy…' if self.is_red else 'Export spreadsheet…', self.save)
            self.save_button.pack(side='left', padx=(8, 0))
            if not self.is_red:
                self.batch_button = self.button(actions, 'Batch export XLSX…', self.batch_export)
                self.batch_button.pack(side='left', padx=(8, 0))
            ttk.Label(actions, textvariable=self.status, wraplength=850).pack(side='left', padx=12)

            host = ttk.Frame(root, padding=(12, 0, 12, 8))
            host.grid(row=2, column=0, sticky='nsew')
            host.columnconfigure(0, weight=1)
            host.rowconfigure(0, weight=1)
            self.plot = None
            if not self.is_red:
                notebook = ttk.Notebook(host)
                notebook.grid(row=0, column=0, sticky='nsew')
                table_host = ttk.Frame(notebook)
                table_host.columnconfigure(0, weight=1)
                table_host.rowconfigure(0, weight=1)
                plot_host = ttk.Frame(notebook)
                notebook.add(table_host, text='Statistics')
                notebook.add(plot_host, text='DVH plot')
                from .dvh_plot import DVHPlot
                self.plot = DVHPlot(plot_host)
                host = table_host
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
            if self.is_red:
                note = ('Preset matches use exact structure names and force the plan-level RED. '
                        'Save creates a separate plan file. Studyset defaults and saved dose are unchanged. '
                        'Native density editing remains experimental and requires Monaco load/save/recalculation review.')
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
            if not self.is_red:
                self.batch_button.configure(state='normal' if self.plans and not self.busy else 'disabled')

        def clear_table(self):
            self.table.delete(*self.table.get_children())
            if self.plot is not None:
                self.plot.set_result()

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
                    return calculate_for_export(source, selected, boundary)
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
            self.plot.set_result(result)
            for row in display_rows(result):
                self.table.insert('', 'end', values=['' if value is None else f'{value:.3f}' if isinstance(value, float) else value for value in row])
            self.status.set(f'Calculated {len(result["structures"])} structures. Ready to export.')

        def batch_export(self):
            destination = filedialog.askdirectory(title='Choose a folder for the DVH spreadsheets')
            if not destination:
                return
            source, plans, boundary = self.source, list(self.plans), self.boundary.get()
            self.work(lambda: batch_export_dvh(source, plans, destination, boundary=boundary),
                      self.batch_finished, 'Calculating and exporting DVHs…')

        def batch_finished(self, outcomes):
            failures = [item for item in outcomes if item['error']]
            count = len(outcomes) - len(failures)
            summary = f'Exported {count} of {len(outcomes)} plans.'
            self.status.set(summary)
            if failures:
                details = '\n'.join(f"{item['path']}: {item['error']}" for item in failures)
                messagebox.showwarning('Batch export results', summary + '\n\n' + details)
            else:
                messagebox.showinfo('Batch export results', summary)

        def save(self):
            if self.result is None:
                return
            selected_type = tk.StringVar(value='Excel workbook')
            path = filedialog.asksaveasfilename(
                title='Save modified plan copy' if self.is_red else 'Export DVH spreadsheet',
                initialfile='plan.RED-overridden' if self.is_red else safe_filename_component(self.selected['name']),
                defaultextension='' if self.is_red else '.xlsx',
                typevariable=selected_type,
                filetypes=[('Plan copy', '*.*')] if self.is_red else [('Excel workbook', '*.xlsx'), ('CSV (comma-separated)', '*.csv')])
            if not path:
                return
            if self.is_red:
                original = self.source if self.source.is_file() else self.source / self.selected['member']
                operation = lambda: save_plan_copy(self.result, original, path)
            else:
                suffix = Path(path).suffix.lower()
                if suffix not in ('.xlsx', '.csv'):
                    messagebox.showerror('Unsupported export format', 'Choose an .xlsx or .csv filename.')
                    return
                exporter = export_dvh_csv if suffix == '.csv' else export_dvh_xlsx
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
