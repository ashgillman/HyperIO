"""Cumulative DVH cursor calculations and a dependency-free Tk plot tab."""
from bisect import bisect_right
import math


def cursor_point(structure, dose_cgy, prescription_cgy=None):
    """Interpolate the calculated curve; prescription is a display normalization."""
    if not math.isfinite(dose_cgy) or dose_cgy < 0:
        raise ValueError('dose must be finite and nonnegative')
    if prescription_cgy is not None and (not math.isfinite(prescription_cgy) or prescription_cgy <= 0):
        raise ValueError('prescription dose must be finite and positive')
    curve = structure['dvh_curve']
    doses, volumes = curve['dose_cgy'], curve['volume_percent']
    index = bisect_right(doses, dose_cgy)
    if index == 0:
        volume = 100.
    elif index == len(doses):
        volume = volumes[-1] if dose_cgy == doses[-1] else 0.
    else:
        fraction = (dose_cgy - doses[index - 1]) / (doses[index] - doses[index - 1])
        volume = volumes[index - 1] + fraction * (volumes[index] - volumes[index - 1])
    return {'dose_cgy': dose_cgy,
            'dose_percent': dose_cgy / prescription_cgy * 100 if prescription_cgy else None,
            'volume_percent': volume, 'volume_cm3': volume / 100 * structure['volume_cm3']}


class DVHPlot:
    """Tk Canvas plot, with independent visibility and active-curve controls."""

    COLORS = ('#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
              '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf')

    def __init__(self, parent):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.rows, self.visible = [], []
        self.point_dose = None
        self.pinned = False
        self.active = tk.IntVar(value=-1)
        self.rx = tk.StringVar()
        self.dose_unit = tk.StringVar(value='cGy')
        self.volume_unit = tk.StringVar(value='%')
        self.readout = tk.StringVar(value='Calculate a DVH to view curves.')
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        tools = ttk.Frame(parent, padding=8)
        tools.grid(row=0, column=0, columnspan=2, sticky='ew')
        toolbar = tools
        tools = ttk.Frame(toolbar)
        tools.pack(fill='x')
        ttk.Label(tools, text='Prescription (Gy)').pack(side='left')
        ttk.Entry(tools, textvariable=self.rx, width=12).pack(side='left', padx=6)
        for label, variable, values in [('Dose', self.dose_unit, ['cGy', '% Rx']),
                                         ('Volume', self.volume_unit, ['%', 'cm³'])]:
            ttk.Label(tools, text=label).pack(side='left', padx=(12, 4))
            ttk.Combobox(tools, textvariable=variable, values=values,
                         state='readonly', width=8).pack(side='left')
        ttk.Button(tools, text='Track cursor', command=self.track).pack(side='left', padx=12)
        self.build_eviq_controls(toolbar)
        self.canvas = tk.Canvas(parent, background='white', highlightthickness=0, width=600, height=350)
        self.canvas.grid(row=1, column=0, sticky='nsew')
        side = ttk.Frame(parent, padding=8)
        side.grid(row=1, column=1, sticky='ns')
        ttk.Label(side, text='Show    Select structure').pack(anchor='w')
        scroll = tk.Canvas(side, width=250, highlightthickness=0)
        scrollbar = ttk.Scrollbar(side, orient='vertical', command=scroll.yview)
        scrollbar.pack(side='right', fill='y')
        scroll.pack(side='left', fill='both', expand=True)
        scroll.configure(yscrollcommand=scrollbar.set)
        self.list = ttk.Frame(scroll)
        scroll.create_window((0, 0), window=self.list, anchor='nw')
        self.list.bind('<Configure>', lambda e: scroll.configure(scrollregion=scroll.bbox('all')))
        ttk.Label(parent, textvariable=self.readout, padding=8, wraplength=1000).grid(row=2, column=0, columnspan=2, sticky='w')
        ttk.Label(parent, text='Select a structure on the right, then move over the plot. Click to pin a point; Track cursor resumes movement.',
                  padding=8, wraplength=1000).grid(row=3, column=0, columnspan=2, sticky='w')
        self.canvas.bind('<Configure>', lambda e: self.draw())
        self.canvas.bind('<Motion>', self.motion)
        self.canvas.bind('<Button-1>', self.click)
        for variable in (self.rx, self.dose_unit, self.volume_unit):
            variable.trace_add('write', lambda *args: self.draw())

    def set_result(self, result=None):
        self.rows = result['structures'] if result else []
        self.point_dose = None
        self.pinned = False
        for child in self.list.winfo_children():
            child.destroy()
        self.visible = []
        for index, row in enumerate(self.rows):
            visible = self.tk.BooleanVar(value=True)
            self.visible.append(visible)
            self.ttk.Checkbutton(self.list, variable=visible, command=self.draw).grid(row=index, column=0)
            self.tk.Label(self.list, text='━', fg=self.COLORS[index % len(self.COLORS)]).grid(row=index, column=1)
            self.ttk.Radiobutton(self.list, text=row['structure'], variable=self.active,
                                 value=index, command=self.select).grid(row=index, column=2, sticky='w')
        self.active.set(0 if self.rows else -1)
        self.eviq_apply.set(False)
        self.draw()

    def select(self):
        self.point_dose = None
        self.pinned = False
        self.eviq_apply.set(False)
        self.draw()

    def build_eviq_controls(self, parent):
        from .eviq import default_catalogue_path
        tk, ttk = self.tk, self.ttk
        self.eviq_pages = []
        self.eviq_groups = []
        self.eviq_protocol = tk.StringVar()
        self.eviq_group = tk.StringVar()
        self.eviq_apply = tk.BooleanVar(value=False)
        controls = ttk.Frame(parent)
        controls.pack(fill='x', pady=(8, 0))
        ttk.Button(controls, text='Load eviQ JSON…', command=self.load_eviq).pack(side='left')
        self.protocol_box = ttk.Combobox(controls, textvariable=self.eviq_protocol, state='readonly', width=55)
        self.protocol_box.pack(side='left', padx=6, fill='x', expand=True)
        self.protocol_box.bind('<<ComboboxSelected>>', self.eviq_protocol_changed)
        ttk.Button(controls, text='Open source', command=self.open_eviq_source).pack(side='left')
        line = ttk.Frame(parent)
        line.pack(fill='x', pady=4)
        self.group_box = ttk.Combobox(line, textvariable=self.eviq_group, state='readonly', width=65)
        self.group_box.pack(side='left', fill='x', expand=True)
        self.group_box.bind('<<ComboboxSelected>>', self.eviq_group_changed)
        ttk.Checkbutton(line, text='Overlay on selected structure', variable=self.eviq_apply,
                        command=self.draw).pack(side='left', padx=6)
        self.eviq_details = tk.Text(parent, height=4, wrap='word', state='disabled')
        self.eviq_details.pack(fill='x')
        self.set_eviq_details('Load a catalogue generated by hyperio-eviq-update. Select protocol and organ/regimen, '
                              'then select the corresponding plan structure and enable the overlay. '
                              'Review fractionation, definitions and source; points are not clinical approval.')
        catalogue_path = default_catalogue_path()
        if catalogue_path.is_file():
            self.load_eviq(catalogue_path)

    def set_eviq_details(self, text):
        self.eviq_details.configure(state='normal')
        self.eviq_details.delete('1.0', 'end')
        self.eviq_details.insert('1.0', text)
        self.eviq_details.configure(state='disabled')

    def load_eviq(self, path=None):
        from tkinter import filedialog, messagebox
        from .eviq import load_catalogue
        path = path or filedialog.askopenfilename(title='Load eviQ criteria catalogue', filetypes=[('JSON', '*.json')])
        if not path:
            return
        try:
            catalogue = load_catalogue(path)
            pages = catalogue['protocols']
            labels = [f'{i + 1}. {p["title"]}' for i, p in enumerate(pages)]
        except (OSError, ValueError, KeyError, TypeError) as error:
            messagebox.showerror('Cannot load eviQ criteria', str(error))
            return
        self.eviq_pages = pages
        self.eviq_updated = catalogue.get('generated_at', 'unknown')
        self.protocol_box.configure(values=labels)
        self.eviq_protocol.set('')
        self.eviq_groups = []
        self.group_box.configure(values=[])
        self.eviq_group.set('')
        self.eviq_apply.set(False)
        self.set_eviq_details(f'Catalogue retrieved {self.eviq_updated}. Select a protocol; review the current source before use.')
        if hasattr(self, 'canvas'):
            self.draw()

    def eviq_protocol_changed(self, event=None):
        index = self.protocol_box.current()
        self.eviq_groups = self.eviq_pages[index]['groups'] if index >= 0 else []
        self.group_box.configure(values=[f'{i + 1}. {g["organ"]} | {g["regimen"]}'
                                         for i, g in enumerate(self.eviq_groups)])
        self.eviq_group.set('')
        self.eviq_apply.set(False)
        page = self.eviq_pages[index] if index >= 0 else {}
        self.set_eviq_details('Select an organ/regimen. ' + ' '.join(page.get('warnings', [])))
        self.draw()

    def eviq_group_changed(self, event=None):
        self.eviq_apply.set(False)
        index = self.group_box.current()
        if index >= 0:
            group = self.eviq_groups[index]
            page = self.eviq_pages[self.protocol_box.current()]
            lines = [f'Adapted from eviQ / Cancer Institute NSW | ID {page.get("protocol_id", "?")} '
                     f'| {page.get("version") or "version unavailable"} | Retrieved {self.eviq_updated} | {page["url"]}',
                     f'{group["organ"]} | {group["regimen"]} | {group["notes"]}']
            for record in group['recommendations']:
                status = 'point' if record.get('point') else 'manual review, no point'
                lines.append(f'{record.get("qualifier", "")}: {record["text"]} [{status}]')
            lines.append('Verify prescription, fractionation, contour definitions and conditional notes in the source. '
                         'Open circles mark limits, not measured dose or approval. No EQD2 conversion is performed.')
            self.set_eviq_details('\n'.join(lines))
        self.draw()

    def open_eviq_source(self):
        import webbrowser
        from .eviq import protocol_url
        index = self.protocol_box.current()
        if index >= 0:
            url = self.eviq_pages[index]['url']
            if protocol_url(url):
                webbrowser.open(url)

    def eviq_points(self):
        from .eviq import overlay_points
        index, group_index = self.active.get(), self.group_box.current()
        if not self.eviq_apply.get() or index < 0 or group_index < 0 or index >= len(self.rows):
            return []
        return overlay_points(self.eviq_groups[group_index], self.rows[index]['volume_cm3'], self.volume_unit.get())

    def track(self):
        self.pinned = False
        self.draw()

    def prescription(self):
        """Return the prescription entered in Gy as cGy for plot calculations."""
        try:
            value = float(self.rx.get()) * 100
            return value if math.isfinite(value) and value > 0 else None
        except ValueError:
            return None

    def draw(self):
        c = self.canvas
        c.delete('all')
        self.bounds = (75, 20, max(100, c.winfo_width() - 25), max(60, c.winfo_height() - 55))
        left, top, right, bottom = self.bounds
        rx = self.prescription()
        if self.dose_unit.get() == '% Rx' and rx is None:
            self.readout.set('Enter a finite, positive prescription dose in Gy to plot relative dose.')
            return
        shown = [i for i, visible in enumerate(self.visible) if visible.get()]
        points = self.eviq_points() if self.active.get() in shown else []
        self.xmax = max((self.rows[i]['dvh_curve']['dose_cgy'][-1] for i in shown), default=1.)
        self.ymax = 100. if self.volume_unit.get() == '%' else max((self.rows[i]['volume_cm3'] for i in shown), default=1.)
        self.xmax = max(self.xmax, *(p['dose_cgy'] for p in points), 1.)
        self.ymax = max(self.ymax, *(p['volume'] for p in points), 1e-9)
        self.ymax = max(self.ymax, 1e-9)
        def xy(dose, volume):
            return left + dose / self.xmax * (right - left), bottom - volume / self.ymax * (bottom - top)
        c.create_line(left, top, left, bottom, right, bottom, fill='#444444')
        for tick in range(6):
            fraction = tick / 5
            x, y = left + fraction * (right - left), bottom - fraction * (bottom - top)
            c.create_line(left, y, right, y, fill='#eeeeee')
            c.create_text(left - 8, y, text=f'{fraction * self.ymax:.3g}', anchor='e')
            dose = fraction * self.xmax
            c.create_text(x, bottom + 15, text=f'{dose / rx * 100 if self.dose_unit.get() == "% Rx" else dose:.4g}')
        c.create_text((left + right) / 2, bottom + 38, text=f'Dose ({self.dose_unit.get()})')
        c.create_text(18, (top + bottom) / 2, text=f'Volume ({self.volume_unit.get()})', angle=90)
        for index in shown:
            row = self.rows[index]
            curve = row['dvh_curve']
            scale = 1 if self.volume_unit.get() == '%' else row['volume_cm3'] / 100
            coordinates = [v for dose, volume in zip(curve['dose_cgy'], curve['volume_percent']) for v in xy(dose, volume * scale)]
            c.create_line(*coordinates, fill=self.COLORS[index % len(self.COLORS)], width=3 if index == self.active.get() else 1.5)
        for number, point in enumerate(points, 1):
            x, y = xy(point['dose_cgy'], point['volume'])
            color = self.COLORS[self.active.get() % len(self.COLORS)]
            c.create_oval(x - 6, y - 6, x + 6, y + 6, outline=color, width=2)
            c.create_text(x - 8, y - 8, text=f'{number}: {point["qualifier"]} {point["text"]}',
                          anchor='se', fill=color, font=('TkDefaultFont', 8))
        index = self.active.get()
        if index not in shown:
            self.readout.set('Select a visible structure to inspect its DVH.' if self.rows else 'Calculate a DVH to view curves.')
            return
        row = self.rows[index]
        if self.point_dose is None:
            self.readout.set(f'{row["structure"]}: move the cursor over the plot to inspect a point.')
            return
        point = cursor_point(row, self.point_dose, rx)
        x, y = xy(point['dose_cgy'], point['volume_percent'] if self.volume_unit.get() == '%' else point['volume_cm3'])
        if left <= x <= right:
            c.create_line(x, top, x, bottom, dash=(3, 3), fill='#888888')
            c.create_line(left, y, right, y, dash=(3, 3), fill='#888888')
            c.create_oval(x - 4, y - 4, x + 4, y + 4, outline=self.COLORS[index % len(self.COLORS)], width=2)
        relative = f' ({point["dose_percent"]:.3f}% Rx)' if rx else ''
        self.readout.set(f'{row["structure"]}  |  Dose: {point["dose_cgy"]:.3f} cGy{relative}  |  '
                         f'Volume: {point["volume_cm3"]:.4f} cm³ ({point["volume_percent"]:.3f}%)'
                         + ('  |  Pinned' if self.pinned else ''))

    def motion(self, event, force=False):
        if self.pinned and not force:
            return
        if not self.rows or not hasattr(self, 'xmax'):
            return
        if self.dose_unit.get() == '% Rx' and self.prescription() is None:
            return
        left, top, right, bottom = self.bounds
        if left <= event.x <= right and top <= event.y <= bottom:
            self.point_dose = (event.x - left) / (right - left) * self.xmax
            self.draw()

    def click(self, event):
        self.motion(event, force=True)
        self.pinned = self.point_dose is not None
        self.draw()
