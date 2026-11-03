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
        ttk.Label(tools, text='Prescription (Gy)').pack(side='left')
        ttk.Entry(tools, textvariable=self.rx, width=12).pack(side='left', padx=6)
        for label, variable, values in [('Dose', self.dose_unit, ['cGy', '% Rx']),
                                         ('Volume', self.volume_unit, ['%', 'cm³'])]:
            ttk.Label(tools, text=label).pack(side='left', padx=(12, 4))
            ttk.Combobox(tools, textvariable=variable, values=values,
                         state='readonly', width=8).pack(side='left')
        ttk.Button(tools, text='Track cursor', command=self.track).pack(side='left', padx=12)
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
        self.draw()

    def select(self):
        self.point_dose = None
        self.pinned = False
        self.draw()

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
        self.xmax = max((self.rows[i]['dvh_curve']['dose_cgy'][-1] for i in shown), default=1.)
        self.ymax = 100. if self.volume_unit.get() == '%' else max((self.rows[i]['volume_cm3'] for i in shown), default=1.)
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
