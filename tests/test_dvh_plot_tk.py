"""Native Tk regression checks; skipped when Tk or a display is unavailable."""
import pytest


def test_switch_from_scrolled_catalogue_to_tcc_selects_and_plots_goals():
    tk = pytest.importorskip('tkinter')
    from tkinter import ttk
    from hyperio.dvh_goals import library_paths
    from hyperio.dvh_plot import DVHPlot

    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f'Tk display unavailable: {error}')
    try:
        root.withdraw()
        host = ttk.Frame(root)
        host.pack(fill='both', expand=True)
        plot = DVHPlot(host)
        plot.set_result(dict(structures=[dict(structure='PTV_70', volume_cm3=10,
            dvh_curve=dict(dose_cgy=[0, 7000, 7500], volume_percent=[100, 98, 0]))]))
        plot.rx.set('70')
        paths = {p.stem: p for p in library_paths()}
        plot.load_goals(paths['eviq'])
        plot.goal_filter.set('prostate')
        root.update_idletasks()
        plot.goal_list_canvases[0].yview_moveto(1)
        plot.library_box.current(plot.library_paths.index(paths['TCC']))
        plot.library_box.event_generate('<<ComboboxSelected>>')
        root.update()
        assert plot.goal_protocol.get() == 0
        assert plot.goal_regimen.get() == 'Relative to prescription'
        assert plot.goal_group.get() == 0
        assert len(plot.protocol_list.winfo_children()) == 1
        assert len(plot.regimen_list.winfo_children()) == 1
        assert len(plot.target_list.winfo_children()) == 1
        assert len(plot.goal_points()) == 7
        # The sole goal remains clickable after automatic selection.
        plot.target_list.winfo_children()[0].invoke()
        plot.draw()
        labels = [i for i in plot.canvas.find_all() if plot.canvas.type(i) == 'text'
                  and ': ' in plot.canvas.itemcget(i, 'text')]
        assert len(labels) == 7
        assert [plot.canvas.itemcget(i, 'fill') for i in labels] == [
            '#ff7f0e', '#d62728', 'black', 'black', 'black', 'black', 'black']
    finally:
        root.destroy()
