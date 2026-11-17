"""Shared Tk window, background work, and support dialogs for plan applications."""
from pathlib import Path
import queue
import threading
import traceback


def show_message(parent, title, message, *, actions=()):
    """Show selectable, scrollable details with an explicit full-report copy action."""
    import tkinter as tk
    from tkinter import ttk

    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    width = min(850, max(320, parent.winfo_screenwidth() - 80))
    height = min(500, max(240, parent.winfo_screenheight() - 100))
    dialog.geometry(f'{width}x{height}')
    dialog.columnconfigure(0, weight=1)
    dialog.rowconfigure(0, weight=1)
    body = ttk.Frame(dialog, padding=12)
    body.grid(row=0, column=0, sticky='nsew')
    body.columnconfigure(0, weight=1)
    body.rowconfigure(0, weight=1)
    text = tk.Text(body, wrap='word', padx=8, pady=8, exportselection=False)
    text.grid(row=0, column=0, sticky='nsew')
    scroll = ttk.Scrollbar(body, orient='vertical', command=text.yview)
    scroll.grid(row=0, column=1, sticky='ns')
    text.configure(yscrollcommand=scroll.set)
    text.insert('1.0', message)
    text.configure(state='disabled')

    def select_all(event=None):
        text.tag_add('sel', '1.0', 'end-1c')
        return 'break'

    def copy_all():
        dialog.clipboard_clear()
        dialog.clipboard_append(message)

    for sequence in ('<Control-a>', '<Command-a>'):
        text.bind(sequence, select_all)
    action_bar = ttk.Frame(dialog, padding=(12, 0, 12, 12))
    action_bar.grid(row=1, column=0, sticky='ew')
    ttk.Button(action_bar, text='Copy all', command=copy_all).pack(side='left')
    for label, command in actions:
        ttk.Button(action_bar, text=label, command=command).pack(side='left', padx=(8, 0))
    ttk.Button(action_bar, text='Close', command=dialog.destroy).pack(side='right')
    dialog.bind('<Escape>', lambda event: dialog.destroy())
    text.focus_set()
    return dialog


def grid_scrollable_table(table):
    """Place a table and both scrollbars in its containing frame."""
    from tkinter import ttk

    host = table.master
    table.grid(row=0, column=0, sticky='nsew')
    vertical = ttk.Scrollbar(host, orient='vertical', command=table.yview)
    horizontal = ttk.Scrollbar(host, orient='horizontal', command=table.xview)
    vertical.grid(row=0, column=1, sticky='ns')
    horizontal.grid(row=1, column=0, sticky='ew')
    table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)


def launch(window):
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as exc:
        raise SystemExit('These applications require Python with Tk support. '
                         'See applications/README.md for Windows and macOS setup.') from exc

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise SystemExit(f'Unable to open the desktop GUI: {exc}') from exc
    window(root, tk, ttk, filedialog, messagebox)
    root.mainloop()
    return 0


class PlanSourceWindow:
    """Window layout and source handling shared by the RED and DVH workflows."""

    def __init__(self, root, tk, ttk, filedialog, messagebox):
        self.root = root
        self.tk, self.ttk, self.filedialog, self.messagebox = tk, ttk, filedialog, messagebox
        root.title(self.title)
        root.geometry('1250x760')
        root.minsize(850, 450)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)
        self.source = None
        self.plans = []
        self.busy = False
        self.log_events = []
        self.batch_outcomes = []
        self.messages = queue.Queue()
        self.controls = []
        self.directory = tk.StringVar()
        self.status = tk.StringVar(value='Choose a patient-set directory or ZIP archive to begin.')

        controls = ttk.Frame(root, padding=12)
        controls.grid(row=0, column=0, sticky='ew')
        controls.columnconfigure(1, weight=1)
        ttk.Label(controls, text='Patient set').grid(row=0, column=0, sticky='w')
        ttk.Entry(controls, textvariable=self.directory, state='readonly').grid(row=0, column=1, sticky='ew', padx=8)
        self.button(controls, 'Choose directory…', self.choose_directory).grid(row=0, column=2)
        self.button(controls, 'Choose ZIP…', self.choose_zip).grid(row=0, column=3, padx=(8, 0))
        self.build_source_options(controls)

        log_actions = ttk.Frame(controls)
        log_actions.grid(row=2, column=0, columnspan=4, sticky='w', pady=(4, 0))
        self.log_buttons = [
            self.button(log_actions, 'Export full logs…', lambda: self.export_logs(False)),
            self.button(log_actions, 'Export anonymised full logs…', lambda: self.export_logs(True)),
        ]
        for widget in self.log_buttons:
            widget.pack(side='left', padx=(0, 8))
        ttk.Label(log_actions, text='Full logs include identifiers; anonymised logs omit free text.').pack(side='left')

        actions = ttk.Frame(root, padding=(12, 0, 12, 8))
        actions.grid(row=1, column=0, sticky='ew')
        self.build_actions(actions)

        host = ttk.Frame(root, padding=(12, 0, 12, 8))
        host.grid(row=2, column=0, sticky='nsew')
        host.columnconfigure(0, weight=1)
        host.rowconfigure(0, weight=1)
        self.build_content(host)
        self.update_actions()
        root.after(100, self.poll)

    def button(self, parent, label, command):
        widget = self.ttk.Button(parent, text=label, command=command)
        self.controls.append((widget, 'normal'))
        return widget

    def update_actions(self):
        for widget in self.log_buttons:
            widget.configure(state='normal' if self.source and not self.busy else 'disabled')

    def discard_result(self):
        """Drop any cached calculation result after a completion callback fails."""

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
                self.log_events.append({'error': str(error),
                                        'traceback': ''.join(traceback.format_exception(error))})
                self.status.set(f'Failed: {error}')
                self.show_error('HyperIO error', str(error))
            else:
                try:
                    success(value)
                except Exception as exc:
                    self.log_events.append({'error': str(exc), 'traceback': traceback.format_exc()})
                    self.discard_result()
                    self.status.set(f'Failed: {exc}')
                    self.show_error('HyperIO error', str(exc))
            self.update_actions()
        self.root.after(100, self.poll)

    def choose_directory(self):
        path = self.filedialog.askdirectory(title='Choose a patient set or a directory containing patient sets')
        if path:
            self.open_source(path)

    def choose_zip(self):
        path = self.filedialog.askopenfilename(
            title='Choose a Monaco patient-set ZIP archive',
            filetypes=[('ZIP archives', '*.zip'), ('All files', '*.*')])
        if path:
            self.open_source(path)

    def open_source(self, path):
        if not path:
            return
        self.source = Path(path)
        self.log_events = []
        self.batch_outcomes = []
        self.directory.set(path)
        self.plans = []
        self.reset_source_view()
        self.work(lambda: self.discover(path), self.found_plans, 'Scanning patient sets…')

    def show_error(self, title, message):
        actions = []
        if self.source:
            actions = [('Export full logs…', lambda: self.export_logs(False)),
                       ('Export anonymised full logs…', lambda: self.export_logs(True))]
        show_message(self.root, title, message, actions=actions)

    def export_logs(self, anonymised):
        if self.busy or not self.source:
            return
        path = self.filedialog.asksaveasfilename(
            title='Export anonymised full logs' if anonymised else 'Export full logs (contains identifiers)',
            initialfile='hyperio-anonymised-logs.json' if anonymised else 'hyperio-full-logs.json',
            defaultextension='.json', filetypes=[('JSON support report', '*.json')])
        if not path:
            return
        from ..diagnostics import export_diagnostic_report
        source, events, outcomes = self.source, list(self.log_events), list(self.batch_outcomes)
        self.work(lambda: export_diagnostic_report(source, path, anonymised=anonymised,
                                                   events=events, outcomes=outcomes),
                  lambda _: self.status.set(f'Saved diagnostic logs to {path}'),
                  'Collecting diagnostic metadata…')
