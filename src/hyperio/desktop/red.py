"""Tk application for RED overrides in Monaco plan or patient copies."""
from ..application_io import export_red_patient, export_red_plan_copies, load_red_plans
from ..ct_red import calculate_ct_red
from ..red_outputs import REDOutputs
from .common import PlanSourceWindow, launch, show_message


ADD_TO_SOURCE = 'Add to source folder'


class REDWindow(PlanSourceWindow):
    title = 'HyperIO — RED overrides'

    def build_source_options(self, controls):
        ttk = self.ttk
        self.output_format = self.tk.StringVar(value='Folder')
        ttk.Label(controls, text='Save as').grid(row=1, column=0, sticky='w', pady=8)
        self.output_box = ttk.Combobox(controls, textvariable=self.output_format,
                                      values=('Folder', 'ZIP'), state='readonly', width=22)
        self.output_box.grid(row=1, column=1, sticky='w', padx=8)
        self.controls.append((self.output_box, 'readonly'))

    def build_actions(self, status_host):
        ttk = self.ttk
        actions = ttk.Frame(status_host)
        actions.pack(fill='x')
        self.button(actions, 'Add output', lambda: self.red_outputs.add_output()).pack(side='left')
        self.button(actions, 'Remove output', lambda: self.red_outputs.remove_output()).pack(side='left', padx=(8, 0))
        self.button(actions, 'Preview output', self.preview).pack(side='left', padx=(8, 0))
        self.save_button = self.button(actions, 'Save patient…', self.save)
        self.save_button.pack(side='left', padx=(8, 0))
        ttk.Label(status_host, textvariable=self.status, wraplength=1100).pack(fill='x', pady=(8, 0))

    def build_content(self, host):
        self.red_outputs = REDOutputs(host, self.update_actions, self.calculate_ct_mean)
        note = ('Double-click New RED or Resulting mode to edit a structure. Presets use exact names and force the plan-level RED. '
                'CT mean RED is experimental and ignores overrides; double-click to copy it without changing mode. '
                'Folder and ZIP save a complete patient copy. Blank names replace the input plan in that copy. '
                'Add to source folder requires a new plan name on every tab. '
                'Studyset defaults and saved dose are unchanged; dose must be recalculated after RED edits. '
                'Native density editing remains experimental and requires Monaco load/save/recalculation review.')
        self.ttk.Label(self.root, text=note, wraplength=1100, padding=12).grid(row=3, column=0, sticky='ew')

    def update_actions(self):
        super().update_actions()
        self.save_button.configure(state='normal' if self.plans and not self.busy else 'disabled')

    def reset_source_view(self):
        folder_source = self.source is not None and self.source.is_dir()
        formats = ('Folder', 'ZIP', ADD_TO_SOURCE) if folder_source else ('Folder', 'ZIP')
        self.output_box.configure(values=formats)
        if self.output_format.get() not in formats:
            self.output_format.set('Folder')
        self.red_outputs.set_plans([])

    @staticmethod
    def discover(source):
        return load_red_plans(source)

    def found_plans(self, plans):
        self.plans = plans
        self.red_outputs.set_plans(plans)
        self.status.set(f'Found {len(plans)} plan(s). Configure input plans and overrides in each tab.')

    def preview(self):
        self.red_outputs.refresh(self.red_outputs.current())

    def calculate_ct_mean(self, tab, plan, calibration):
        if self.busy or not self.source:
            return
        self.red_outputs.clear_ct_red(tab)
        generation = tab['generation']
        source = self.source

        def completed(result):
            if source == self.source and self.red_outputs.set_ct_red(tab, generation, result):
                self.status.set(f'CT-derived mean RED calculated for {len(result)} structure(s).')
            else:
                self.status.set('CT-derived mean RED discarded because the input changed.')

        self.work(lambda: calculate_ct_red(source, plan, calibration), completed, 'Calculating CT-derived mean RED…')

    def save(self):
        output_format = self.output_format.get()
        try:
            edits = self.red_outputs.prepared()
            if output_format == ADD_TO_SOURCE and any(not edit['name'] for edit in edits):
                raise ValueError('Enter a new plan name on every output tab, or choose Folder or ZIP for replacements.')
        except ValueError as exc:
            show_message(self.root, 'Invalid output', str(exc))
            return
        source = self.source
        if output_format == ADD_TO_SOURCE:
            self.work(lambda: export_red_plan_copies(source, edits),
                      lambda paths: self.status.set(f'Added {len(paths)} plan(s) alongside their input plans.'),
                      'Adding plan copies…')
            return
        zipped = output_format == 'ZIP'
        path = self.filedialog.asksaveasfilename(
            title='Save complete patient ZIP' if zipped else 'Save new patient folder',
            initialfile=self.source.stem + '-RED' + ('.zip' if zipped else ''),
            defaultextension='.zip' if zipped else '',
            filetypes=[('ZIP archive', '*.zip')] if zipped else [('Patient folder', '*')])
        if path:
            self.work(lambda: export_red_patient(source, edits, path, zipped=zipped),
                      lambda _: self.status.set(f'Saved complete patient copy to {path}'), 'Saving patient…')


def main():
    return launch(REDWindow)
