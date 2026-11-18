"""Independent RED output tabs; each preview is rebuilt from the source bytes."""
from .application_io import load_red_mapping, prepare_red_output
from .core import plan_metadata
from .ct_red import calibration_picker_directory, find_calibration
from .desktop.common import grid_scrollable_table
from .experiments import _positive_ed


class REDOutputs:
    def __init__(self, host, changed, calculate=None):
        import tkinter as tk
        from tkinter import filedialog, ttk
        self.tk, self.ttk, self.filedialog = tk, ttk, filedialog
        self.changed = changed
        self.calculate = calculate
        self.plans = []
        self.tabs = []
        self.notebook = ttk.Notebook(host)
        self.notebook.grid(row=0, column=0, sticky='nsew')
        self.add_output()

    def add_output(self):
        tk, ttk = self.tk, self.ttk
        frame = ttk.Frame(self.notebook, padding=8)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)
        number = len(self.tabs) + 1
        name = tk.StringVar()
        preset, status, input_plan = tk.StringVar(), tk.StringVar(), tk.StringVar()
        calibration = tk.StringVar()
        tab = dict(frame=frame, name=name, preset=preset, status=status, input=input_plan,
                   calibration=calibration, manual={}, ct_red={}, generation=0)
        self.tabs.append(tab)
        ttk.Label(frame, text='Input plan').grid(row=0, column=0, sticky='w')
        combo = ttk.Combobox(frame, textvariable=input_plan, state='readonly',
                             values=[plan['label'] for plan in self.plans])
        combo.grid(row=0, column=1, columnspan=2, sticky='ew', padx=8)
        tab['plan_box'] = combo
        if self.plans:
            selected = self.current()['plan_box'].current() if len(self.tabs) > 1 else 0
            combo.current(max(0, selected))
        ttk.Label(frame, text='Output plan name').grid(row=1, column=0, sticky='w')
        ttk.Entry(frame, textvariable=name).grid(row=1, column=1, sticky='ew', padx=8)
        ttk.Label(frame, text='Blank: replace input plan in export').grid(row=1, column=2, sticky='w')
        ttk.Label(frame, text='RED preset').grid(row=2, column=0, sticky='w', pady=8)
        ttk.Entry(frame, textvariable=preset, state='readonly').grid(row=2, column=1, sticky='ew', padx=8)
        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=2)
        ttk.Button(buttons, text='Choose CSV / TSV…', command=lambda: self.choose_preset(tab)).pack(side='left')
        ttk.Button(buttons, text='Clear preset', command=lambda: preset.set('')).pack(side='left', padx=8)
        ttk.Label(frame, text='CT calibration').grid(row=3, column=0, sticky='w')
        ttk.Entry(frame, textvariable=calibration, state='readonly').grid(row=3, column=1, sticky='ew', padx=8)
        ct_buttons = ttk.Frame(frame)
        ct_buttons.grid(row=3, column=2)
        ttk.Button(ct_buttons, text='Choose calibration…', command=lambda: self.choose_calibration(tab)).pack(side='left')
        ttk.Button(ct_buttons, text='Calculate CT mean RED', command=lambda: self.request_ct_red(tab)).pack(side='left', padx=8)
        ttk.Label(frame, textvariable=status, wraplength=1000).grid(row=4, column=0, columnspan=3, sticky='w', pady=(0, 8))
        table_host = ttk.Frame(frame)
        table_host.grid(row=5, column=0, columnspan=3, sticky='nsew')
        table_host.columnconfigure(0, weight=1)
        table_host.rowconfigure(0, weight=1)
        headers = ['Structure', 'Current mode', 'Current RED', 'New RED', 'Resulting mode', 'CT mean RED']
        table = ttk.Treeview(table_host, columns=list(range(len(headers))), show='headings')
        tab['table'] = table
        for index, title in enumerate(headers):
            table.heading(index, text=title)
            table.column(index, width=240 if index == 0 else 145, stretch=False)
        grid_scrollable_table(table)
        table.bind('<Double-1>', lambda event: self.edit_cell(tab, event))
        table.tag_configure('changed', background='#DCE6F1')
        self.notebook.add(frame, text=name.get() or f'Output {number}')
        self.notebook.select(frame)
        name.trace_add('write', lambda *_: self.refresh(tab))
        preset.trace_add('write', lambda *_: self.refresh(tab))
        input_plan.trace_add('write', lambda *_: self.reset_manual(tab))
        calibration.trace_add('write', lambda *_: self.clear_ct_red(tab))
        self.select_plan_calibration(tab)
        self.refresh(tab)

    def remove_output(self):
        if len(self.tabs) > 1:
            tab = self.current()
            self.tabs.remove(tab)
            self.notebook.forget(tab['frame'])
            tab['frame'].destroy()
            self.changed()

    def current(self):
        return next(tab for tab in self.tabs if str(tab['frame']) == self.notebook.select())

    def choose_preset(self, tab):
        path = self.filedialog.askopenfilename(title='Choose RED preset',
            filetypes=[('RED presets', '*.csv *.tsv'), ('All files', '*.*')])
        if path:
            tab['preset'].set(path)

    def choose_calibration(self, tab):
        # Monaco uses arbitrary calibration suffixes. Older macOS Tk treats
        # DICOM3.* as a literal extension, which can abort the native dialog.
        path = self.filedialog.askopenfilename(title='Choose DICOM3 calibration or library ZIP',
                                               initialdir=str(calibration_picker_directory()))
        if path:
            tab['calibration'].set(path)

    def clear_ct_red(self, tab):
        tab['generation'] += 1
        tab['ct_red'] = {}
        self.refresh(tab)

    def request_ct_red(self, tab):
        index = tab['plan_box'].current()
        calibration = tab['calibration'].get()
        if index < 0 or not self.plans or not calibration or calibration.startswith('?? '):
            tab['status'].set('Choose an input plan and CT calibration first.')
            return
        if self.calculate:
            self.calculate(tab, self.plans[index], calibration)

    def set_ct_red(self, tab, generation, result):
        if tab not in self.tabs or tab['generation'] != generation:
            return False
        tab['ct_red'] = result
        self.refresh(tab)
        return True

    def set_plans(self, plans):
        self.plans = plans
        for tab in self.tabs:
            tab['frame'].destroy()
        self.tabs.clear()
        self.add_output()

    def reset_manual(self, tab):
        tab['manual'].clear()
        self.select_plan_calibration(tab)

    def select_plan_calibration(self, tab):
        index = tab['plan_box'].current()
        plan = self.plans[index] if 0 <= index < len(self.plans) else {}
        curve_name = plan.get('ct_to_ed_name')
        path = find_calibration(curve_name)
        if path:
            tab['calibration'].set(str(path))
        else:
            tab['calibration'].set(f'?? {curve_name} ??' if curve_name else '')

    def edit_cell(self, tab, event):
        table = tab['table']
        row, column = table.identify_row(event.y), table.identify_column(event.x)
        if not row:
            return
        if column == '#6':
            values = table.item(row, 'values')
            result = tab['ct_red'].get(values[0])
            if result is not None:
                try:
                    _positive_ed(result['mean_red'])
                except ValueError as exc:
                    tab['status'].set(f'Cannot copy CT mean RED: {exc}')
                    return
                tab['manual'].setdefault(values[0], {})['red'] = str(result['mean_red'])
                self.refresh(tab)
            return
        if column not in ('#4', '#5'):
            return
        box = table.bbox(row, column)
        if not box:
            return
        values = table.item(row, 'values')
        name, field = values[0], 'red' if column == '#4' else 'mode'
        if field == 'red':
            editor = self.ttk.Entry(table)
            editor.insert(0, values[3])
        else:
            editor = self.ttk.Combobox(table, values=('none', 'forced', 'filled'), state='readonly')
            editor.set(values[4])
        editor.place(x=box[0], y=box[1], width=box[2], height=box[3])
        editor.focus_set()
        finished = False

        def finish(commit=True):
            nonlocal finished
            if finished:
                return
            value = editor.get().strip()
            if commit and field == 'red' and value:
                try:
                    _positive_ed(float(value))
                except ValueError as exc:
                    tab['status'].set(f'Invalid RED: {exc}')
                    editor.focus_set()
                    return
            finished = True
            editor.destroy()
            if commit:
                tab['manual'].setdefault(name, {})[field] = value or None
                self.refresh(tab)

        editor.bind('<Return>', lambda _event: finish())
        editor.bind('<FocusOut>', lambda _event: finish())
        editor.bind('<Escape>', lambda _event: finish(False))
        if field == 'mode':
            editor.bind('<<ComboboxSelected>>', lambda _event: finish())

    def refresh(self, tab):
        table = tab['table']
        table.delete(*table.get_children())
        tab['result'] = None
        self.notebook.tab(tab['frame'], text=tab['name'].get() or 'Replace input plan')
        try:
            index = tab['plan_box'].current()
            if index < 0 or not self.plans:
                tab['status'].set('Choose a patient folder or ZIP, then select an input plan.')
                return
            selected = self.plans[index]
            if selected.get('error'):
                raise ValueError(selected['error'])
            data = selected['data']
            mapping = load_red_mapping(tab['preset'].get()) if tab['preset'].get() else {}
            for structure, manual in tab['manual'].items():
                base = mapping.get(structure)
                value = {'mode': 'forced', 'red': base} if base is not None else {}
                value.update(manual)
                if value.get('red') is not None:
                    value['red'] = float(value['red'])
                mapping[structure] = value
            name = tab['name'].get() or selected['name']
            _, changes, missing = prepare_red_output(data, mapping, name)
            self.notebook.tab(tab['frame'], text=tab['name'].get() or selected['name'] + ' (replace)')
            for record in plan_metadata(data, '<selected-plan>')['density_overrides']:
                match = record['name'] in mapping
                value = mapping.get(record['name'])
                red = value.get('red') if isinstance(value, dict) else value
                mode = value.get('mode') if isinstance(value, dict) else ('forced' if match else None)
                table.insert('', 'end', values=[record['name'], record['mode'], record['uniform_ed'],
                    red if red is not None else '', mode or record['mode'],
                    f"{tab['ct_red'][record['name']]['mean_red']:.4f}" if record['name'] in tab['ct_red'] else ''],
                    tags=('changed',) if match else ())
            tab['result'] = dict(member=selected['member'], name=tab['name'].get(), mapping=mapping)
            text = f'{len(changes)} structure(s) have updates.' if mapping else 'No updates: retain the source RED settings.'
            if missing:
                text += ' Unmatched preset entries: ' + ', '.join(missing)
            tab['status'].set(text)
        except Exception as exc:
            tab['status'].set(f'Cannot save this output: {exc}')
        finally:
            self.changed()

    def prepared(self):
        outputs = []
        for tab in self.tabs:
            self.refresh(tab)
            if tab['result'] is None:
                raise ValueError(tab['status'].get())
            outputs.append(tab['result'])
        return outputs
