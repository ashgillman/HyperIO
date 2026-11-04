"""Independent RED output tabs; each preview is rebuilt from the source bytes."""
from .application_io import load_red_mapping, prepare_red_output
from .core import plan_metadata


class REDOutputs:
    def __init__(self, host, changed):
        import tkinter as tk
        from tkinter import filedialog, ttk
        self.tk, self.ttk, self.filedialog = tk, ttk, filedialog
        self.changed = changed
        self.plans = []
        self.tabs = []
        self.notebook = ttk.Notebook(host)
        self.notebook.grid(row=0, column=0, sticky='nsew')
        self.add_output()

    def add_output(self):
        tk, ttk = self.tk, self.ttk
        frame = ttk.Frame(self.notebook, padding=8)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(4, weight=1)
        number = len(self.tabs) + 1
        name = tk.StringVar()
        preset, status, input_plan = tk.StringVar(), tk.StringVar(), tk.StringVar()
        tab = dict(frame=frame, name=name, preset=preset, status=status, input=input_plan)
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
        ttk.Label(frame, textvariable=status, wraplength=1000).grid(row=3, column=0, columnspan=3, sticky='w', pady=(0, 8))
        table_host = ttk.Frame(frame)
        table_host.grid(row=4, column=0, columnspan=3, sticky='nsew')
        table_host.columnconfigure(0, weight=1)
        table_host.rowconfigure(0, weight=1)
        headers = ['Structure', 'Current mode', 'Current RED', 'Preset RED', 'Resulting mode']
        table = ttk.Treeview(table_host, columns=list(range(len(headers))), show='headings')
        tab['table'] = table
        for index, title in enumerate(headers):
            table.heading(index, text=title)
            table.column(index, width=240 if index == 0 else 145, stretch=False)
        table.grid(row=0, column=0, sticky='nsew')
        vertical = ttk.Scrollbar(table_host, orient='vertical', command=table.yview)
        horizontal = ttk.Scrollbar(table_host, orient='horizontal', command=table.xview)
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        table.tag_configure('changed', background='#DCE6F1')
        self.notebook.add(frame, text=name.get() or f'Output {number}')
        self.notebook.select(frame)
        name.trace_add('write', lambda *_: self.refresh(tab))
        preset.trace_add('write', lambda *_: self.refresh(tab))
        input_plan.trace_add('write', lambda *_: self.refresh(tab))
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

    def set_plans(self, plans):
        self.plans = plans
        for tab in self.tabs:
            tab['frame'].destroy()
        self.tabs.clear()
        self.add_output()

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
            name = tab['name'].get() or selected['name']
            _, changes, missing = prepare_red_output(data, mapping, name)
            self.notebook.tab(tab['frame'], text=tab['name'].get() or selected['name'] + ' (replace)')
            for record in plan_metadata(data, '<selected-plan>')['density_overrides']:
                match = record['name'] in mapping
                table.insert('', 'end', values=[record['name'], record['mode'], record['uniform_ed'],
                    mapping.get(record['name'], ''), 'forced' if match else record['mode']],
                    tags=('changed',) if match else ())
            tab['result'] = dict(member=selected['member'], name=tab['name'].get(), mapping=mapping)
            text = f'{len(changes)} matching structure(s) will receive forced REDs.' if mapping else 'No preset: retain the source RED settings.'
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
