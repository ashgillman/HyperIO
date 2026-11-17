"""Tk application for RED overrides in a copy of a Monaco patient set."""
from ..application_io import export_red_patient, load_red_plans
from ..red_outputs import REDOutputs
from .common import PlanSourceWindow, launch, show_message


class REDWindow(PlanSourceWindow):
    title = 'HyperIO — RED overrides'

    def build_source_options(self, controls):
        ttk = self.ttk
        self.output_format = self.tk.StringVar(value='Folder')
        ttk.Label(controls, text='Save as').grid(row=1, column=0, sticky='w', pady=8)
        output_box = ttk.Combobox(controls, textvariable=self.output_format,
                                 values=['Folder', 'ZIP'], state='readonly', width=12)
        output_box.grid(row=1, column=1, sticky='w', padx=8)
        self.controls.append((output_box, 'readonly'))

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
        self.red_outputs = REDOutputs(host, self.update_actions)
        note = ('Double-click New RED or Resulting mode to edit a structure. Presets use exact names and force the plan-level RED. '
                'Save writes a complete patient copy with every output tab applied. Blank output names replace the input plan in that copy. '
                'Studyset defaults and saved dose are unchanged; dose must be recalculated after RED edits. '
                'Native density editing remains experimental and requires Monaco load/save/recalculation review.')
        self.ttk.Label(self.root, text=note, wraplength=1100, padding=12).grid(row=3, column=0, sticky='ew')

    def update_actions(self):
        super().update_actions()
        self.save_button.configure(state='normal' if self.plans and not self.busy else 'disabled')

    def reset_source_view(self):
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

    def save(self):
        try:
            edits = self.red_outputs.prepared()
        except ValueError as exc:
            show_message(self.root, 'Invalid output', str(exc))
            return
        zipped = self.output_format.get() == 'ZIP'
        path = self.filedialog.asksaveasfilename(
            title='Save complete patient ZIP' if zipped else 'Save new patient folder',
            initialfile=self.source.stem + '-RED' + ('.zip' if zipped else ''),
            defaultextension='.zip' if zipped else '',
            filetypes=[('ZIP archive', '*.zip')] if zipped else [('Patient folder', '*')])
        if path:
            source = self.source
            self.work(lambda: export_red_patient(source, edits, path, zipped=zipped),
                      lambda _: self.status.set(f'Saved complete patient copy to {path}'), 'Saving patient…')


def main():
    return launch(REDWindow)
