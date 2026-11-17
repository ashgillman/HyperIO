"""Tk application for inspecting and exporting DVHs from saved Monaco dose."""
from pathlib import Path

from ..dvh_export import (HEADERS, batch_export_dvh, calculate_for_export, display_rows,
                           export_dvh_csv, export_dvh_xlsx, safe_filename_component)
from ..plan_discovery import discover_plans
from .common import PlanSourceWindow, grid_scrollable_table, launch, show_message


def select_batch_plans(parent, plans):
    """Return checked plans in source order, or None when the dialog is cancelled."""
    import tkinter as tk
    from tkinter import ttk

    dialog = tk.Toplevel(parent)
    dialog.title('Select plans for batch export')
    dialog.transient(parent)
    dialog.columnconfigure(0, weight=1)
    dialog.rowconfigure(1, weight=1)
    width = min(800, max(320, parent.winfo_screenwidth() - 80))
    height = min(500, max(240, parent.winfo_screenheight() - 100))
    dialog.geometry(f'{width}x{height}')
    ttk.Label(dialog, text='Tick the plans to export.', padding=12).grid(row=0, column=0, sticky='w')

    host = ttk.Frame(dialog, padding=(12, 0, 12, 0))
    host.grid(row=1, column=0, sticky='nsew')
    host.columnconfigure(0, weight=1)
    host.rowconfigure(0, weight=1)
    canvas = tk.Canvas(host, highlightthickness=0)
    canvas.grid(row=0, column=0, sticky='nsew')
    scroll = ttk.Scrollbar(host, orient='vertical', command=canvas.yview)
    scroll.grid(row=0, column=1, sticky='ns')
    canvas.configure(yscrollcommand=scroll.set)
    choices = ttk.Frame(canvas)
    window = canvas.create_window((0, 0), window=choices, anchor='nw')
    choices.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=event.width))
    selections = [tk.BooleanVar(master=dialog, value=True) for plan in plans]
    result = None

    def update_selection():
        count = sum(variable.get() for variable in selections)
        count_label.configure(text=f'{count} of {len(plans)} plans selected')
        proceed.configure(state='normal' if count else 'disabled')

    for plan, variable in zip(plans, selections):
        ttk.Checkbutton(choices, text=plan['label'], variable=variable,
                        command=update_selection).pack(anchor='w', fill='x', pady=3)

    def set_all(value):
        for variable in selections:
            variable.set(value)
        update_selection()

    def accept():
        nonlocal result
        selected = [plan for plan, variable in zip(plans, selections) if variable.get()]
        if selected:
            result = selected
            dialog.destroy()

    actions = ttk.Frame(dialog, padding=12)
    actions.grid(row=3, column=0, sticky='ew')
    ttk.Button(actions, text='Select all', command=lambda: set_all(True)).pack(side='left')
    ttk.Button(actions, text='Clear all', command=lambda: set_all(False)).pack(side='left', padx=8)
    count_label = ttk.Label(dialog, padding=(12, 8, 12, 0))
    count_label.grid(row=2, column=0, sticky='w')
    proceed = ttk.Button(actions, text='Continue…', command=accept)
    proceed.pack(side='right')
    ttk.Button(actions, text='Cancel', command=dialog.destroy).pack(side='right', padx=8)
    dialog.protocol('WM_DELETE_WINDOW', dialog.destroy)
    dialog.bind('<Escape>', lambda event: dialog.destroy())
    update_selection()
    dialog.wait_visibility()
    dialog.grab_set()
    proceed.focus_set()
    parent.wait_window(dialog)
    return result


class DVHWindow(PlanSourceWindow):
    title = 'HyperIO — DVH explorer / exporter'

    def build_source_options(self, controls):
        tk, ttk = self.tk, self.ttk
        self.selected = self.result = None
        self.plan = tk.StringVar()
        self.boundary = tk.StringVar(value='include')
        ttk.Label(controls, text='Plan').grid(row=1, column=0, sticky='w', pady=8)
        self.plan_box = ttk.Combobox(controls, textvariable=self.plan, state='readonly')
        self.plan_box.grid(row=1, column=1, sticky='ew', padx=8)
        self.plan_box.bind('<<ComboboxSelected>>', self.select_plan)
        self.controls.append((self.plan_box, 'readonly'))
        self.load_button = self.button(controls, 'Calculate DVH', self.load)
        self.load_button.grid(row=1, column=2)
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

    def build_actions(self, actions):
        self.save_button = self.button(actions, 'Export spreadsheet…', self.save)
        self.save_button.pack(side='left', padx=(8, 0))
        self.batch_button = self.button(actions, 'Batch export XLSX…', self.batch_export)
        self.batch_button.pack(side='left', padx=(8, 0))
        self.ttk.Label(actions, textvariable=self.status, wraplength=850).pack(side='left', padx=12)

    def build_content(self, host):
        from ..dvh_plot import DVHPlot

        ttk = self.ttk
        notebook = ttk.Notebook(host)
        notebook.grid(row=0, column=0, sticky='nsew')
        table_host = ttk.Frame(notebook)
        table_host.columnconfigure(0, weight=1)
        table_host.rowconfigure(0, weight=1)
        plot_host = ttk.Frame(notebook)
        notebook.add(table_host, text='Statistics')
        notebook.add(plot_host, text='DVH plot')
        self.plot = DVHPlot(plot_host)

        self.table = ttk.Treeview(table_host, columns=list(range(len(HEADERS))), show='headings')
        for index, name in enumerate(HEADERS):
            self.table.heading(index, text=name)
            width = 240 if index == 0 or name == 'Dosimetric Criterion' else 145
            self.table.column(index, width=width, stretch=False)
        grid_scrollable_table(self.table)
        self.table.tag_configure('changed', background='#DCE6F1')

    def update_actions(self):
        super().update_actions()
        self.load_button.configure(state='normal' if self.selected and not self.busy else 'disabled')
        self.batch_button.configure(state='normal' if self.plans and not self.busy else 'disabled')
        self.save_button.configure(state='normal' if self.result is not None and not self.busy else 'disabled')

    def discard_result(self):
        self.result = None

    def reset_source_view(self):
        self.selected = self.result = None
        self.clear_table()
        self.plan.set('')
        self.plan_box.configure(values=[])

    def clear_table(self):
        self.table.delete(*self.table.get_children())
        self.plot.set_result()

    @staticmethod
    def discover(source):
        return discover_plans(source, lazy=True)

    def found_plans(self, plans):
        self.plans = plans
        self.plan_box.configure(values=[plan['label'] for plan in plans])
        self.status.set(f'Found {len(plans)} plan(s). Select a plan.' if plans else 'No Monaco plans found in this source.')
        if len(plans) == 1:
            self.plan_box.current(0)
            self.select_plan()

    def invalidate(self, event=None):
        self.result = None
        self.clear_table()
        self.status.set('Settings changed. Load the plan again to calculate the DVH.')
        self.update_actions()

    def select_plan(self, event=None):
        self.selected = self.plans[self.plan_box.current()]
        self.result = None
        self.clear_table()
        self.status.set(self.selected.get('error') or 'Plan selected. Load it to continue.')
        self.update_actions()

    def load(self):
        if not self.selected:
            return
        self.result = None
        self.clear_table()
        selected, source = self.selected, self.source
        if selected.get('error'):
            show_message(self.root, 'Unreadable plan', selected['error'])
            self.update_actions()
            return
        boundary = self.boundary.get()
        self.work(lambda: calculate_for_export(source, selected, boundary),
                  self.loaded_dvh, 'Calculating DVH statistics from saved dose…')

    def loaded_dvh(self, result):
        self.result = result
        self.plot.set_result(result)
        for row in display_rows(result):
            values = ['' if value is None else f'{value:.3f}' if isinstance(value, float) else value
                      for value in row]
            self.table.insert('', 'end', values=values)
        self.status.set(f'Calculated {len(result["structures"])} structures. Ready to export.')
        if result.get('structure_failures'):
            self.status.set(self.status.get() + f' {len(result["structure_failures"])} structure(s) failed.')
        if result.get('diagnostics'):
            self.status.set(self.status.get() + f' WARN: {len(result["diagnostics"])} warning(s).')
            self.show_error('DVH warnings', '\n'.join(
                f"{row['severity']}: {row['message']}" for row in result['diagnostics']))

    def batch_export(self):
        plans = select_batch_plans(self.root, self.plans)
        if not plans:
            return
        destination = self.filedialog.askdirectory(parent=self.root, title='Choose a folder for the DVH spreadsheets')
        if not destination:
            return
        source, boundary = self.source, self.boundary.get()
        self.work(lambda: batch_export_dvh(source, plans, destination, boundary=boundary),
                  self.batch_finished, 'Calculating and exporting DVHs…')

    def batch_finished(self, outcomes):
        self.batch_outcomes = outcomes
        failures = [item for item in outcomes if item['error']]
        count = len(outcomes) - len(failures)
        summary = f'Exported {count} of {len(outcomes)} plans.'
        warned = sum(bool(item.get('diagnostics')) and not item['error'] for item in outcomes)
        if warned or failures:
            summary += f' WARN: {warned} exported with warnings. ERROR: {len(failures)} failed.'
        self.status.set(summary)
        if failures or warned:
            details = []
            for item in outcomes:
                if item['error']:
                    details.append(f"ERROR — {item['path']}: {item['error']}")
                elif item.get('diagnostics'):
                    details.append(f"WARN — {item['path']}: exported successfully")
                else:
                    details.append(f"INFO — {item['path']}: exported successfully")
                details.extend(f"  {row['severity']}: {row['message']}"
                               for row in item.get('diagnostics', []))
            details = '\n'.join(details)
            self.show_error('Batch export results', summary + '\n\n' + details)
        else:
            self.messagebox.showinfo('Batch export results', summary)

    def save(self):
        if self.result is None:
            return
        selected_type = self.tk.StringVar(value='Excel workbook')
        path = self.filedialog.asksaveasfilename(
            title='Export DVH spreadsheet',
            initialfile=safe_filename_component(self.selected['name']),
            defaultextension='.xlsx',
            typevariable=selected_type,
            filetypes=[('Excel workbook', '*.xlsx'), ('CSV (comma-separated)', '*.csv')])
        if not path:
            return
        suffix = Path(path).suffix.lower()
        if suffix not in ('.xlsx', '.csv'):
            show_message(self.root, 'Unsupported export format', 'Choose an .xlsx or .csv filename.')
            return
        exporter = export_dvh_csv if suffix == '.csv' else export_dvh_xlsx
        operation = lambda: exporter(self.result, path, source=self.source)
        self.work(operation, lambda _: self.status.set(f'Saved {path}'), 'Saving…')


def main():
    return launch(DVHWindow)
