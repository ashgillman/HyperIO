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


def structure_summary(row):
    """Show calculated statistics as soon as a structure is selected."""
    parts = [row['structure'], f"Volume: {row['volume_cm3']:.4g} cm³"]
    for label, key in [('Min', 'min_dose_cgy'), ('Mean', 'mean_dose_cgy'), ('Max', 'max_dose_cgy')]:
        value = row.get(key)
        if value is not None and math.isfinite(value):
            parts.append(f'{label}: {value:.4g} cGy')
    return '  |  '.join(parts)


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
        self.canvas = tk.Canvas(parent, background='white', highlightthickness=0, width=600, height=350)
        self.canvas.grid(row=1, column=0, sticky='nsew')
        side = ttk.Frame(parent, padding=8)
        side.grid(row=1, column=1, sticky='ns')
        structures = ttk.Frame(side)
        structures.pack(fill='both', expand=True)
        ttk.Label(structures, text='Show    Select structure').pack(anchor='w')
        scroll = tk.Canvas(structures, width=235, height=100, highlightthickness=0)
        scrollbar = ttk.Scrollbar(structures, orient='vertical', command=scroll.yview)
        scrollbar.pack(side='right', fill='y')
        scroll.pack(side='left', fill='both', expand=True)
        scroll.configure(yscrollcommand=scrollbar.set)
        self.list = ttk.Frame(scroll)
        scroll.create_window((0, 0), window=self.list, anchor='nw')
        self.list.bind('<Configure>', lambda e: scroll.configure(scrollregion=scroll.bbox('all')))
        readout = ttk.Label(parent, textvariable=self.readout, padding=8, wraplength=1000)
        readout.grid(row=2, column=0, columnspan=2, sticky='ew')
        readout.bind('<Configure>', lambda e: readout.configure(wraplength=max(100, e.width - 16)))
        self.build_goal_controls(toolbar)
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
        self.match_goal_structure()
        self.draw()

    def select(self):
        self.point_dose = None
        self.pinned = False
        self.match_goal_structure()
        self.draw()

    def build_goal_controls(self, parent):
        from .dvh_goals import library_paths
        tk, ttk = self.tk, self.ttk
        self.goal_pages, self.goal_groups = [], []
        self.goal_manual = False
        self.goal_protocol = tk.IntVar(value=-1)
        self.goal_group = tk.IntVar(value=-1)
        self.goal_filter = tk.StringVar()
        self.goal_library = tk.StringVar()
        self.goal_regimen = tk.StringVar()
        self.goal_apply = tk.BooleanVar(value=True)
        panel = ttk.LabelFrame(parent, text='DVH goals', padding=6)
        panel.pack(fill='x', pady=(8, 0))
        line = ttk.Frame(panel)
        line.pack(fill='x')
        self.library_paths = library_paths()
        ttk.Label(line, text='Goal library').grid(row=0, column=0, sticky='w')
        self.library_box = ttk.Combobox(line, textvariable=self.goal_library, state='readonly',
                                        values=[p.name for p in self.library_paths], width=20)
        self.library_box.grid(row=0, column=1, sticky='ew', padx=4)
        self.library_box.bind('<<ComboboxSelected>>',
                              lambda e: self.load_goals(self.library_paths[self.library_box.current()]))
        ttk.Label(line, text='Filter protocols').grid(row=0, column=2, sticky='w', padx=(12, 0))
        ttk.Entry(line, textvariable=self.goal_filter, width=25).grid(row=0, column=3, sticky='ew', padx=4)
        ttk.Checkbutton(line, text='Show goals', variable=self.goal_apply, command=self.draw).grid(row=0, column=4, sticky='w', padx=8)
        ttk.Button(line, text='Open source', command=self.open_goal_source).grid(row=0, column=5, sticky='e')
        lists = ttk.Frame(panel)
        lists.pack(fill='x', pady=4)
        lists.columnconfigure(0, weight=3)
        lists.columnconfigure(1, weight=2)
        lists.columnconfigure(2, weight=1)
        self.goal_list_canvases = {}
        def radio_list(label, column, width):
            frame = ttk.LabelFrame(lists, text=label)
            frame.grid(row=0, column=column, sticky='nsew', padx=3)
            canvas = tk.Canvas(frame, width=width, height=95, highlightthickness=0)
            bar = ttk.Scrollbar(frame, orient='vertical', command=canvas.yview)
            bar.pack(side='right', fill='y')
            canvas.pack(side='left', fill='both', expand=True)
            canvas.configure(yscrollcommand=bar.set)
            self.goal_list_canvases[column] = canvas
            content = ttk.Frame(canvas)
            window = canvas.create_window((0, 0), window=content, anchor='nw')
            canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window, width=e.width))
            content.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
            return content
        self.protocol_list = radio_list('1. Protocol', 0, 460)
        self.regimen_list = radio_list('2. Prescription', 1, 300)
        self.target_list = radio_list('3. Structure goals', 2, 180)
        self.goal_filter.trace_add('write', lambda *args: self.filter_protocols())
        # An unobtrusive advanced loader stays below the normal selection flow.
        ttk.Button(panel, text='Advanced: load JSON…', command=self.load_goals).pack(anchor='e', pady=(3, 0))
        if self.library_paths:
            self.library_box.current(0)
            self.load_goals(self.library_paths[0])

    def add_goal_radio(self, parent, text, variable, value, command):
        button = self.tk.Radiobutton(parent, text=text, variable=variable, value=value,
                                     command=command, anchor='w', justify='left', wraplength=300)
        button.pack(fill='x', anchor='w')
        button.bind('<Configure>', lambda e: button.configure(wraplength=max(60, e.width - 30)))

    def load_goals(self, path=None):
        from tkinter import filedialog
        from pathlib import Path
        from .dvh_goals import load_catalogue
        path = path or filedialog.askopenfilename(title='Load DVH goal library', filetypes=[('JSON', '*.json')])
        if not path:
            return
        try:
            catalogue = load_catalogue(path)
        except (OSError, ValueError, KeyError, TypeError) as error:
            from .gui import show_message
            show_message(self.canvas.winfo_toplevel(), 'Cannot load DVH goals', str(error))
            return
        self.goal_library.set(Path(path).name)
        self.goal_pages = catalogue['protocols']
        self.goal_source = catalogue.get('attribution', catalogue.get('source', ''))
        self.goal_protocol.set(0 if len(self.goal_pages) == 1 else -1)
        self.goal_filter.set('')
        self.filter_protocols()
        self.goal_protocol_changed()

    def filter_protocols(self):
        self.goal_list_canvases[0].yview_moveto(0)
        for child in self.protocol_list.winfo_children():
            child.destroy()
        query = self.goal_filter.get().casefold().split()
        for index, page in enumerate(self.goal_pages):
            title = f'{page.get("protocol_id") or ""} {page["title"]}'.strip()
            if all(word in title.casefold() for word in query):
                self.add_goal_radio(self.protocol_list, title, self.goal_protocol, index, self.goal_protocol_changed)

    def goal_protocol_changed(self):
        from .dvh_goals import regimens
        for child in self.regimen_list.winfo_children():
            child.destroy()
        self.goal_list_canvases[1].yview_moveto(0)
        self.goal_regimen.set('')
        index = self.goal_protocol.get()
        if index >= 0:
            prescriptions = regimens(self.goal_pages[index])
            if len(prescriptions) == 1:
                self.goal_regimen.set(prescriptions[0])
            for regimen in prescriptions:
                self.add_goal_radio(self.regimen_list, regimen, self.goal_regimen, regimen, self.goal_regimen_changed)
        self.goal_regimen_changed()

    def goal_regimen_changed(self):
        self.goal_list_canvases[2].yview_moveto(0)
        for child in self.target_list.winfo_children():
            child.destroy()
        index = self.goal_protocol.get()
        self.goal_groups = ([g for g in self.goal_pages[index]['groups']
                             if g['regimen'] == self.goal_regimen.get()] if index >= 0 else [])
        self.goal_group.set(-1)
        for i, group in enumerate(self.goal_groups):
            self.add_goal_radio(self.target_list, group['organ'], self.goal_group, i, self.goal_target_changed)
        self.match_goal_structure()
        if len(self.goal_groups) == 1:
            self.goal_group.set(0)
            self.goal_target_changed()
        if hasattr(self, 'canvas'):
            self.draw()

    def match_goal_structure(self):
        self.goal_manual = False
        from .dvh_goals import matching_groups
        index, protocol = self.active.get(), self.goal_protocol.get()
        matches = (matching_groups(self.goal_pages[protocol], self.goal_regimen.get(),
                                   self.rows[index]['structure'])
                   if protocol >= 0 and 0 <= index < len(self.rows) else [])
        self.goal_group.set(next((i for i, g in enumerate(self.goal_groups) if g in matches), -1))

    def goal_target_changed(self):
        self.goal_manual = True
        from fnmatch import fnmatchcase
        group = self.goal_groups[self.goal_group.get()]
        patterns = group.get('structure_patterns', [group['organ']])
        matches = [i for i, row in enumerate(self.rows) if any(
            fnmatchcase(row['structure'].casefold(), p.casefold()) for p in patterns)]
        if matches:
            matching = set(matches)
            for index, visible in enumerate(self.visible):
                visible.set(index in matching)
            if self.active.get() not in matching:
                self.active.set(matches[0])
                self.point_dose = None
                self.pinned = False
        self.goal_apply.set(True)
        self.draw()

    def open_goal_source(self):
        import webbrowser
        from urllib.parse import urlsplit
        index = self.goal_protocol.get()
        if index >= 0:
            url = self.goal_pages[index].get('url', '')
            if urlsplit(url).scheme == 'https' and urlsplit(url).netloc:
                webbrowser.open(url)

    def goal_points(self):
        from .dvh_goals import overlay_points, matching_groups
        index, protocol = self.active.get(), self.goal_protocol.get()
        if not self.goal_apply.get() or not 0 <= index < len(self.rows) or protocol < 0:
            return []
        row = self.rows[index]
        selected = self.goal_group.get()
        if self.goal_manual and 0 <= selected < len(self.goal_groups):
            groups = [self.goal_groups[selected]]
        else:
            groups = matching_groups(self.goal_pages[protocol], self.goal_regimen.get(), row['structure'])
        return [point for group in groups for point in overlay_points(
            group, row['volume_cm3'], self.volume_unit.get(), self.prescription())]

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
        points = self.goal_points() if self.goal_manual or self.active.get() in shown else []
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
            c.create_line(x, top, x, bottom, fill='#eeeeee')
            c.create_line(x, bottom, x, bottom + 5, fill='#444444', tags='axis-tick')
            c.create_line(left - 5, y, left, y, fill='#444444', tags='axis-tick')
            c.create_text(left - 8, y, text=f'{fraction * self.ymax:.3g}', anchor='e', fill='#222222', tags='axis-value')
            dose = fraction * self.xmax
            c.create_text(x, bottom + 15, text=f'{dose / rx * 100 if self.dose_unit.get() == "% Rx" else dose:.4g}', fill='#222222', tags='axis-value')
        for tick in range(1, 25):
            if tick % 5 == 0:
                continue
            fraction = tick / 25
            x, y = left + fraction * (right - left), bottom - fraction * (bottom - top)
            c.create_line(x, bottom, x, bottom + 3, fill='#777777', tags='axis-tick')
            c.create_line(left - 3, y, left, y, fill='#777777', tags='axis-tick')
        c.create_text((left + right) / 2, bottom + 38, text=f'Dose ({self.dose_unit.get()})', fill='#222222')
        c.create_text(18, (top + bottom) / 2, text=f'Volume ({self.volume_unit.get()})', angle=90, fill='#222222')
        for index in shown:
            row = self.rows[index]
            curve = row['dvh_curve']
            scale = 1 if self.volume_unit.get() == '%' else row['volume_cm3'] / 100
            coordinates = [v for dose, volume in zip(curve['dose_cgy'], curve['volume_percent']) for v in xy(dose, volume * scale)]
            c.create_line(*coordinates, fill=self.COLORS[index % len(self.COLORS)], width=3 if index == self.active.get() else 1.5)
        for number, point in enumerate(points, 1):
            x, y = xy(point['dose_cgy'], point['volume'])
            from .dvh_goals import goal_colour, marker
            color = goal_colour(point)
            direction = marker(point)
            shapes = {'<': [x + 5, y - 6, x - 5, y, x + 5, y + 6],
                      '>': [x - 5, y - 6, x + 5, y, x - 5, y + 6],
                      '^': [x - 6, y + 5, x, y - 5, x + 6, y + 5],
                      'v': [x - 6, y - 5, x, y + 5, x + 6, y - 5]}
            if direction in shapes:
                c.create_polygon(*shapes[direction], fill='white', outline=color, width=2)
            else:
                c.create_oval(x - 6, y - 6, x + 6, y + 6, outline=color, width=2)
            c.create_text(x - 8, y - 8, text=f'{number}: {point["qualifier"]} {point["text"]}',
                          anchor='se', fill=color, font=('TkDefaultFont', 8))
        index = self.active.get()
        if index not in shown:
            self.readout.set('Select a visible structure to inspect its DVH.' if self.rows else 'Calculate a DVH to view curves.')
            return
        row = self.rows[index]
        if self.point_dose is None:
            self.readout.set(structure_summary(row))
            return
        point = cursor_point(row, self.point_dose, rx)
        x, y = xy(point['dose_cgy'], point['volume_percent'] if self.volume_unit.get() == '%' else point['volume_cm3'])
        if left <= x <= right:
            c.create_line(x, top, x, bottom, dash=(3, 3), fill='#888888')
            c.create_line(left, y, right, y, dash=(3, 3), fill='#888888')
            color = self.COLORS[index % len(self.COLORS)]
            c.create_oval(x - 4, y - 4, x + 4, y + 4, outline=color, width=2)
            dose_position = point['dose_percent'] if self.dose_unit.get() == '% Rx' else point['dose_cgy']
            volume_position = point['volume_percent'] if self.volume_unit.get() == '%' else point['volume_cm3']
            # Keep axis positions legible over the regular tick labels without adding a panel.
            for px, py, value, anchor in (
                    (min(right - 24, max(left + 24, x)), bottom + 15, dose_position, 'center'),
                    (left - 8, min(bottom - 8, max(top + 8, y)), volume_position, 'e')):
                label = c.create_text(px, py, text=f'{value:.4g}', anchor=anchor,
                                      fill=color, tags='axis-position')
                background = c.create_rectangle(*c.bbox(label), fill='white', outline=color,
                                                 tags='axis-position')
                c.tag_lower(background, label)
        relative = f' ({point["dose_percent"]:.3f}% Rx)' if rx else ''
        self.readout.set(structure_summary(row) + f'\nCursor  |  Dose: {point["dose_cgy"]:.3f} cGy{relative}  |  '
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
