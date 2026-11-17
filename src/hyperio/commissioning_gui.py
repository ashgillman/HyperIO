"""Desktop worksheet editor for the MPPG 5.b commissioning test matrix."""
from __future__ import annotations

from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from tkinter import BooleanVar, StringVar, Tk, Toplevel, filedialog, messagebox, ttk
from tkinter.font import nametofont
import webbrowser

from .commissioning import (
    FIELDS, GROUP_NOTES, SOURCE_URL, TESTS, case_fields, load_worksheet, make_case, save_worksheet,
)


APP_TITLE = 'HyperIO · MPPG commissioning'
FILE_TYPES = [('Commissioning worksheet', '*.json'), ('All files', '*')]
STATIC_COLUMNS = (
    'name', 'shape', 'field_x_cm', 'field_y_cm', 'ssd_cm', 'mu', 'depths_cm',
    'field_plane', 'beam', 'machine', 'incidence_deg', 'cone', 'reference',
)
PLAN_COLUMNS = ('name', 'beam', 'technique', 'phantom', 'reference', 'detector')
COLUMN_WIDTHS = {
    'name': 155, 'field_x_cm': 84, 'field_y_cm': 84, 'ssd_cm': 84, 'mu': 65,
    'incidence_deg': 145, 'reference': 175, 'detector': 155,
}


def display_value(value):
    if isinstance(value, list):
        return ', '.join(str(item) for item in value)
    return str(value)


class CommissioningApp:
    def __init__(self, root):
        self.root = root
        self.path = None
        self.cases = {}
        self.dirty = False
        self.test_id = next(iter(TESTS))

        root.title(APP_TITLE)
        root.geometry('1180x730')
        root.minsize(900, 620)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        self.title_font = nametofont('TkDefaultFont').copy()
        self.title_font.configure(size=20, weight='bold')
        self.heading_font = nametofont('TkDefaultFont').copy()
        self.heading_font.configure(size=13, weight='bold')

        header = ttk.Frame(root, padding=(16, 12))
        header.grid(row=0, column=0, sticky='ew')
        ttk.Label(header, text='MPPG 5.b commissioning', font=self.title_font).grid(row=0, column=0, sticky='w')
        ttk.Label(
            header, text='AAPM · 2022     |     TPS dose-calculation worksheet',
        ).grid(row=1, column=0, sticky='w', pady=(3, 0))
        header.columnconfigure(0, weight=1)
        files = ttk.Frame(header)
        files.grid(row=0, column=1, rowspan=2)
        for text, command in (
            ('New', self.new), ('Open…', self.open), ('Save', self.save),
            ('Save as…', lambda: self.save(as_new=True)),
            ('Export JSON…', self.export),
            ('Build Monaco patient…', self.build_monaco),
        ):
            ttk.Button(files, text=text, command=command).pack(side='left', padx=(5, 0))

        content = ttk.Panedwindow(root, orient='horizontal')
        content.grid(row=1, column=0, sticky='nsew', padx=16)
        sidebar = ttk.Frame(content, padding=(0, 0, 10, 0), width=305)
        detail = ttk.Frame(content, padding=(10, 0, 0, 0), width=810)
        content.add(sidebar, weight=0)
        content.add(detail, weight=1)
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(1, weight=1)
        ttk.Label(sidebar, text='Guideline tests', font=self.heading_font).grid(row=0, column=0, sticky='w', pady=(0, 7))
        self.tests = ttk.Treeview(sidebar, columns=('count',), show='tree headings', selectmode='browse')
        self.tests.heading('#0', text='Test')
        self.tests.heading('count', text='In', anchor='center')
        self.tests.column('#0', width=260, minwidth=190)
        self.tests.column('count', width=32, stretch=False, anchor='center')
        self.tests.grid(row=1, column=0, sticky='nsew')
        nav_scroll = ttk.Scrollbar(sidebar, orient='vertical', command=self.tests.yview)
        nav_scroll.grid(row=1, column=1, sticky='ns')
        self.tests.configure(yscrollcommand=nav_scroll.set)
        for test_id, spec in TESTS.items():
            if not self.tests.exists(spec.group):
                self.tests.insert('', 'end', iid=spec.group, text=spec.group, open=True)
            self.tests.insert(spec.group, 'end', iid=test_id, text=f'{test_id}  {spec.title}')
        ttk.Button(
            sidebar, text='Open AAPM guideline', command=lambda: webbrowser.open(SOURCE_URL),
        ).grid(row=2, column=0, sticky='w', pady=(8, 0))

        detail.columnconfigure(0, weight=1)
        detail.rowconfigure(2, weight=1)
        self.detail_title = ttk.Label(detail, font=self.heading_font)
        self.detail_title.grid(row=0, column=0, sticky='w')
        guidance = ttk.LabelFrame(detail, text='Guideline reference', padding=(9, 6))
        guidance.grid(row=1, column=0, sticky='ew', pady=(7, 9))
        guidance.columnconfigure(1, weight=1)
        self.guidance_labels = []
        for row, label in enumerate(('Setup', 'Evidence', 'Criteria')):
            ttk.Label(guidance, text=label).grid(row=row, column=0, sticky='nw', padx=(0, 10), pady=2)
            description = ttk.Label(guidance, justify='left', wraplength=540)
            description.grid(row=row, column=1, sticky='ew', pady=2)
            self.guidance_labels.append(description)
        guidance.bind('<Configure>', self.resize_guidance)

        table = ttk.Frame(detail)
        table.grid(row=2, column=0, sticky='nsew')
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self.rows = ttk.Treeview(table, show='headings', selectmode='browse')
        self.rows.grid(row=0, column=0, sticky='nsew')
        vertical = ttk.Scrollbar(table, orient='vertical', command=self.rows.yview)
        horizontal = ttk.Scrollbar(table, orient='horizontal', command=self.rows.xview)
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        self.rows.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.rows.bind('<<TreeviewSelect>>', self.update_controls)
        self.rows.bind('<Double-1>', self.edit_clicked)
        self.rows.bind('<Return>', lambda event: self.edit_case())
        self.rows.bind('<space>', lambda event: self.toggle_case())

        bar = ttk.Frame(detail, padding=(0, 8, 0, 0))
        bar.grid(row=3, column=0, sticky='ew')
        ttk.Button(bar, text='Add case…', command=self.add_case).pack(side='left')
        self.row_buttons = []
        for text, command in (
            ('Edit…', self.edit_case), ('Duplicate…', self.duplicate_case),
            ('Exclude', self.toggle_case), ('Remove', self.remove_case),
        ):
            button = ttk.Button(bar, text=text, command=command)
            button.pack(side='left', padx=(6, 0))
            self.row_buttons.append(button)
        self.case_status = ttk.Label(detail, padding=(0, 7, 0, 0))
        self.case_status.grid(row=4, column=0, sticky='w')

        self.footer = ttk.Label(root, padding=(16, 9), anchor='w')
        self.footer.grid(row=2, column=0, sticky='ew')
        self.tests.bind('<<TreeviewSelect>>', self.select_test)
        self.tests.selection_set(self.test_id)
        self.refresh()

    def resize_guidance(self, event):
        for label in self.guidance_labels:
            label.configure(wraplength=max(140, event.width - 100))

    def select_test(self, event):
        selection = self.tests.selection()
        if selection and selection[0] in TESTS:
            self.test_id = selection[0]
            self.refresh_table()

    def refresh(self, selected_id=None):
        for test_id in TESTS:
            count = sum(case['included'] for case in self.cases.get(test_id, ()))
            self.tests.set(test_id, 'count', str(count) if count else '–')
        self.refresh_table(selected_id)
        self.update_title()

    def update_title(self):
        name = self.path.name if self.path else 'Untitled worksheet'
        marker = ' *' if self.dirty else ''
        self.root.title(f'{APP_TITLE} — {name}{marker}')
        self.footer.configure(text=f'{name}{marker}     |     Planning worksheet · guideline criteria for reference')

    def refresh_table(self, selected_id=None):
        spec = TESTS[self.test_id]
        self.detail_title.configure(text=f'{self.test_id}  {spec.title}   ·   {spec.source}')
        group_note = GROUP_NOTES.get(spec.group)
        setup = f'{spec.setup} {group_note}' if group_note else spec.setup
        for label, description in zip(self.guidance_labels, (setup, spec.evidence, spec.criteria)):
            label.configure(text=description)

        fields = case_fields(self.test_id)
        possible = STATIC_COLUMNS if 'mu' in fields else PLAN_COLUMNS
        columns = tuple(key for key in possible if key in fields)
        self.rows.configure(columns=('included', *columns))
        self.rows.heading('included', text='Included')
        self.rows.column('included', width=70, stretch=False, anchor='center')
        for key in columns:
            self.rows.heading(key, text=FIELDS[key].label)
            self.rows.column(key, width=COLUMN_WIDTHS.get(key, 112), minwidth=60, stretch=False)
        self.rows.delete(*self.rows.get_children())
        rows = self.cases.get(self.test_id, ())
        for case in rows:
            cells = [display_value(case['values'].get(key, '')) for key in columns]
            self.rows.insert('', 'end', iid=case['id'], values=('Yes' if case['included'] else 'No', *cells))
        if selected_id and self.rows.exists(selected_id):
            self.rows.selection_set(selected_id)
            self.rows.focus(selected_id)
            self.rows.see(selected_id)
        count = sum(case['included'] for case in rows)
        status = f'{count} included / {len(rows)} total · Double-click a case to edit its full setup.'
        self.case_status.configure(text=status if rows else 'No cases for this test. Use Add case to start.')
        self.update_controls()

    def selected_case(self):
        selection = self.rows.selection()
        return next(
            (case for case in self.cases.get(self.test_id, ()) if case['id'] in selection), None,
        )

    def update_controls(self, event=None):
        case = self.selected_case()
        for button in self.row_buttons:
            button.configure(state='normal' if case else 'disabled')
        self.row_buttons[2].configure(text='Include' if case and not case['included'] else 'Exclude')

    def mark_changed(self, selected_id=None):
        self.dirty = True
        self.refresh(selected_id)

    def add_case(self):
        self.case_editor()

    def edit_case(self):
        case = self.selected_case()
        if case:
            self.case_editor(case)

    def edit_clicked(self, event):
        row = self.rows.identify_row(event.y)
        if row:
            self.rows.selection_set(row)
            self.edit_case()

    def duplicate_case(self):
        case = self.selected_case()
        if case:
            self.case_editor(case, duplicate=True)

    def toggle_case(self):
        case = self.selected_case()
        if case:
            case['included'] = not case['included']
            self.mark_changed(case['id'])

    def remove_case(self):
        case = self.selected_case()
        if case and messagebox.askyesno('Remove case', f"Remove {case['values']['name']}?", parent=self.root):
            self.cases[self.test_id].remove(case)
            self.mark_changed()

    def case_editor(self, case=None, *, duplicate=False):
        test_id = self.test_id
        spec = TESTS[test_id]
        initial = dict(case['values']) if case else {}
        if duplicate:
            initial['name'] += ' (copy)'
        dialog = Toplevel(self.root)
        dialog.title(f'{test_id} · {spec.title}')
        dialog.transient(self.root)
        frame = ttk.Frame(dialog, padding=14)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)
        ttk.Label(frame, text=f'{test_id}  {spec.title}', font=self.heading_font).grid(
            row=0, column=0, columnspan=4, sticky='w',
        )
        ttk.Label(frame, text='Enter local values. A case name is required. Separate depths by commas.').grid(
            row=1, column=0, columnspan=4, sticky='w', pady=(2, 8),
        )
        values = {}
        first_entry = None
        keys = case_fields(test_id)
        for index, key in enumerate(keys):
            field = FIELDS[key]
            row, pair = divmod(index, 2)
            col = 2 * pair
            row += 2
            ttk.Label(frame, text=field.label).grid(row=row, column=col, sticky='w', padx=(0, 6), pady=3)
            value = StringVar(dialog, value=display_value(initial.get(key, '')))
            values[key] = value
            if field.choices:
                entry = ttk.Combobox(frame, textvariable=value, values=('', *field.choices), state='readonly', width=19)
            else:
                entry = ttk.Entry(frame, textvariable=value, width=22)
            entry.grid(row=row, column=col + 1, sticky='ew', padx=(0, 14 if pair == 0 else 0))
            if first_entry is None:
                first_entry = entry

        included = BooleanVar(dialog, value=case['included'] if case else True)
        controls = ttk.Frame(frame, padding=(0, 10, 0, 0))
        controls.grid(row=(len(keys) + 1) // 2 + 2, column=0, columnspan=4, sticky='ew')
        ttk.Checkbutton(controls, text='Include in case export', variable=included).pack(side='left')

        def apply():
            try:
                result = make_case(
                    test_id, {key: value.get() for key, value in values.items()},
                    included=included.get(), case_id=case['id'] if case and not duplicate else None,
                )
            except ValueError as error:
                messagebox.showerror('Check case fields', str(error), parent=dialog)
                return
            rows = self.cases.setdefault(test_id, [])
            if case and not duplicate:
                rows[rows.index(case)] = result
            else:
                rows.append(result)
            self.mark_changed(result['id'])
            dialog.destroy()

        ttk.Button(controls, text='Apply case', command=apply).pack(side='right')
        ttk.Button(controls, text='Cancel', command=dialog.destroy).pack(side='right', padx=6)
        dialog.bind('<Escape>', lambda event: dialog.destroy())
        dialog.bind('<Return>', lambda event: apply())
        dialog.wait_visibility()
        dialog.grab_set()
        first_entry.focus_set()

    def confirm_discard(self):
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel(
            'Unsaved worksheet', 'Save changes to the current worksheet?', parent=self.root,
        )
        return self.save() if answer else answer is False

    def new(self):
        if self.confirm_discard():
            self.set_document(None, {})

    def open(self):
        chosen = filedialog.askopenfilename(parent=self.root, title='Open worksheet', filetypes=FILE_TYPES)
        if chosen and self.confirm_discard():
            path = Path(chosen)
            try:
                cases = load_worksheet(path)
            except (OSError, ValueError) as error:
                messagebox.showerror('Cannot open worksheet', str(error), parent=self.root)
                return
            self.set_document(path, cases)

    def set_document(self, path, cases):
        self.path = path
        self.cases = cases
        self.dirty = False
        self.refresh()

    def choose_output(self, title, name):
        chosen = filedialog.asksaveasfilename(
            parent=self.root, title=title, filetypes=FILE_TYPES, defaultextension='.json', initialfile=name,
        )
        return Path(chosen) if chosen else None

    def write(self, path, *, included_only=False):
        try:
            if included_only and self.path and path.resolve() == self.path.resolve():
                raise ValueError('Choose a different filename for the included-case export.')
            save_worksheet(path, self.cases, included_only=included_only)
        except (OSError, ValueError) as error:
            messagebox.showerror('Cannot write worksheet', str(error), parent=self.root)
            return False
        return True

    def save(self, *, as_new=False):
        path = self.path
        if not path or as_new:
            path = self.choose_output('Save worksheet', path.name if path else 'commissioning.json')
        if not path or not self.write(path):
            return False
        self.path = path
        self.dirty = False
        self.update_title()
        return True

    def export(self):
        if not any(case['included'] for rows in self.cases.values() for case in rows):
            messagebox.showinfo('No included cases', 'Include at least one case to export.', parent=self.root)
            return
        path = self.choose_output('Export included cases', 'commissioning-included.json')
        if path and self.write(path, included_only=True):
            self.footer.configure(text=f'Exported included cases to {path.name}')

    def build_monaco(self):
        from .commissioning_native import list_native_templates

        rows = [
            (test_id, case) for test_id, cases in self.cases.items() for case in cases
            if case['included'] and TESTS[test_id].kind != 'manual'
        ]
        if not rows:
            messagebox.showinfo('No plan cases', 'Include at least one case with a TPS plan.', parent=self.root)
            return
        chosen = filedialog.askdirectory(parent=self.root, title='Choose the native Monaco phantom patient folder')
        if not chosen:
            return
        source = Path(chosen)
        try:
            templates = list_native_templates(source)
        except (OSError, ValueError) as error:
            messagebox.showerror('Cannot open Monaco patient', str(error), parent=self.root)
            return
        if not templates:
            messagebox.showinfo(
                'No supported templates', 'Choose a native phantom patient with a readable saved plan.',
                parent=self.root,
            )
            return
        self.monaco_assignments(source, templates, rows)

    def monaco_assignments(self, source, templates, rows):
        from .commissioning_native import build_native_patient

        dialog = Toplevel(self.root)
        dialog.title('Build native Monaco patient')
        dialog.transient(self.root)
        dialog.geometry('840x560')
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(2, weight=1)
        description = (
            'Choose a matching plan from a saved Monaco phantom patient. Each assigned case becomes a new plan. '
            'The selected template supplies the studyset, beam geometry, machine and MU. '
            'Worksheet calculation settings are applied where supported.'
        )
        ttk.Label(dialog, text=description, wraplength=790, justify='left', padding=12).grid(sticky='ew')
        identity = ttk.Frame(dialog, padding=(12, 0, 12, 8))
        identity.grid(sticky='ew')
        patient_id, patient_name = StringVar(dialog), StringVar(dialog, value='Commissioning^MPPG')
        for label, value in (('New patient ID', patient_id), ('Patient name (Last^First)', patient_name)):
            ttk.Label(identity, text=label).pack(side='left', padx=(0, 5))
            ttk.Entry(identity, textvariable=value, width=22).pack(side='left', padx=(0, 12))

        table = ttk.Treeview(dialog, columns=('case', 'template'), show='headings', selectmode='browse')
        table.heading('case', text='Included worksheet case')
        table.heading('template', text='Monaco template')
        table.grid(row=2, column=0, sticky='nsew', padx=(12, 0))
        scroll = ttk.Scrollbar(dialog, orient='vertical', command=table.yview)
        scroll.grid(row=2, column=1, sticky='ns', padx=(0, 12))
        table.configure(yscrollcommand=scroll.set)
        case_by_id = {case['id']: (test_id, case) for test_id, case in rows}
        assignments = {}
        for case_id, (test_id, case) in case_by_id.items():
            table.insert('', 'end', iid=case_id, values=(f"{test_id}   {case['values']['name']}", ''))

        selector = ttk.Frame(dialog, padding=(12, 8))
        selector.grid(sticky='ew')
        ttk.Label(selector, text='Template for selected row').pack(side='left', padx=(0, 8))
        choice = StringVar(dialog)
        combo = ttk.Combobox(selector, textvariable=choice, values=('', *templates), state='readonly', width=34)
        combo.pack(side='left')
        setup = ttk.Label(dialog, wraplength=790, justify='left', padding=(12, 0, 12, 5))
        setup.grid(sticky='ew')
        confirmed = BooleanVar(dialog, value=False)

        def show_assignment(event):
            selected = table.selection()
            if selected:
                case_id = selected[0]
                choice.set(assignments.get(case_id, ''))
                test_id, case = case_by_id[case_id]
                values = case['values']
                output_name = self.monaco_case(test_id, case, choice.get())['name']
                fields = [
                    f'{FIELDS[key].label} {display_value(value)}' for key, value in values.items()
                    if key not in {'name', 'notes', 'reference', 'detector', 'depths_cm'}
                ]
                setup.configure(text=' · '.join([output_name, *fields]))

        def assign(event):
            selected = table.selection()
            if selected:
                assignments[selected[0]] = choice.get()
                table.set(selected[0], 'template', choice.get())
                confirmed.set(False)

        table.bind('<<TreeviewSelect>>', show_assignment)
        combo.bind('<<ComboboxSelected>>', assign)
        table.selection_set(rows[0][1]['id'])
        ttk.Label(
            dialog, text='Blank assignments stay in the worksheet. CT-to-density verification has no plan.',
            padding=(12, 0, 12, 6),
        ).grid(sticky='w')

        controls = ttk.Frame(dialog, padding=(12, 0, 12, 12))
        controls.grid(sticky='ew')
        ttk.Checkbutton(
            controls, text='I checked that each assigned template matches its case setup.', variable=confirmed,
        ).pack(side='left')

        def start():
            selected = [
                self.monaco_case(test_id, case, assignments[case_id])
                for case_id, (test_id, case) in case_by_id.items() if assignments.get(case_id)
            ]
            if not selected or not confirmed.get() or not patient_id.get().strip():
                messagebox.showerror(
                    'Complete assignments', 'Assign at least one template, confirm the setup, and enter a new patient ID.',
                    parent=dialog,
                )
                return
            destination = filedialog.askdirectory(parent=dialog, title='Choose a staging folder for the new patient')
            if not destination:
                return
            arguments = (source, Path(destination), patient_id.get().strip(), patient_name.get().strip(), selected)
            results = Queue()

            def worker():
                try:
                    results.put((build_native_patient(*arguments), None))
                except Exception as error:
                    results.put((None, error))

            def poll():
                try:
                    result, error = results.get_nowait()
                except Empty:
                    dialog.after(100, poll)
                    return
                dialog.protocol('WM_DELETE_WINDOW', dialog.destroy)
                build.configure(state='normal', text='Build patient…')
                if error is not None:
                    messagebox.showerror('Monaco export failed', str(error), parent=dialog)
                    return
                dialog.destroy()
                self.footer.configure(text=f"Built {result['patient_path']}")
                unassigned = len(rows) - len(result['plans'])
                remaining = f'{unassigned} included case(s) had no template assignment.\n\n' if unassigned else ''
                output_message = (
                    f"Built {len(result['plans'])} plan(s) in\n{result['patient_path']}\n\n"
                    f'{remaining}'
                    'Copy this patient folder into the target Monaco Installation/Clinic folder. '
                    'Open and verify the plans in Monaco before calculating.'
                )
                messagebox.showinfo(
                    'Monaco patient staged',
                    output_message,
                    parent=self.root,
                )

            build.configure(state='disabled', text='Building…')
            dialog.protocol('WM_DELETE_WINDOW', lambda: None)
            Thread(target=worker, daemon=True).start()
            dialog.after(100, poll)

        build = ttk.Button(controls, text='Build patient…', command=start)
        build.pack(side='right')
        dialog.wait_visibility()
        dialog.grab_set()

    @staticmethod
    def monaco_case(test_id, case, template):
        values = case['values']
        settings = {}
        if 'dose_grid_mm' in values:
            settings['DOSEGRIDSIZE'] = values['dose_grid_mm']
        if 'mc_uncertainty_pct' in values:
            fraction = values['mc_uncertainty_pct'] / 100
            settings.update(MCVARIANCE=fraction, MCSEGMENTVARIANCE=fraction)
        if 'mc_uncertainty_mode' in values:
            settings['MCVARPERPLAN'] = values['mc_uncertainty_mode'] == 'Per Calculation'
        return {
            'name': f"MPPG{test_id.replace('.', '_')}_{case['id'][:8]}",
            'template': template, 'confirmed': True, 'settings': settings,
            'test_id': test_id, 'case_id': case['id'], 'values': values,
        }

    def close(self):
        if self.confirm_discard():
            self.root.destroy()


def main():
    root = Tk()
    CommissioningApp(root)
    root.mainloop()
    return 0
