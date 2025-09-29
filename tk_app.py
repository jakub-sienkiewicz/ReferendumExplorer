import tkinter as tk
from tkinter import ttk
from typing import Dict, List, Optional
import threading

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import geopandas as gpd
import pandas as pd

import main


class ReferendumExplorerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Swiss Referendum Explorer")
        self.root.geometry("1100x750")

        self.kantone_gdf: Optional[gpd.GeoDataFrame] = None
        self.raw_votes: Optional[pd.DataFrame] = None
        self.titles: List[str] = []
        self.cache: Dict[str, gpd.GeoDataFrame] = {}
        self._cbar = None

        self._build_layout()
        self._load_data_async()

    def _build_layout(self):
        left = tk.Frame(self.root, width=320)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        search_frame = tk.Frame(left)
        search_frame.pack(fill=tk.X, padx=6, pady=4)
        tk.Label(search_frame, text="Search:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        search_entry = tk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        search_entry.bind('<KeyRelease>', lambda e: self._filter_titles())

        list_frame = tk.Frame(left)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        self.listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE, activestyle='none')
        ysb = ttk.Scrollbar(list_frame, orient='vertical', command=self.listbox.yview)
        xsb = ttk.Scrollbar(list_frame, orient='horizontal', command=self.listbox.xview)
        self.listbox.config(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        self.listbox.grid(row=0, column=0, sticky='nsew')
        ysb.grid(row=0, column=1, sticky='ns')
        xsb.grid(row=1, column=0, columnspan=2, sticky='ew')
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        self.listbox.bind('<<ListboxSelect>>', self._on_select_title)

        btn_frame = tk.Frame(left)
        btn_frame.pack(fill=tk.X, padx=6, pady=4)
        tk.Button(btn_frame, text="Export GeoJSON", command=self._export_current).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="Refresh", command=self._refresh_current).pack(side=tk.LEFT, padx=4)

        self.status_var = tk.StringVar(value="Loading…")
        tk.Label(left, textvariable=self.status_var, anchor='w').pack(fill=tk.X, padx=6, pady=4)

        right = tk.Frame(self.root)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.fig = plt.Figure(figsize=(7,7), constrained_layout=False)

        self.ax = self.fig.add_axes([0.02, 0.02, 0.78, 0.96])
        self.cax = self.fig.add_axes([0.82, 0.15, 0.03, 0.7])
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.ax.set_axis_off()
        self.cax.set_axis_off()
        self.canvas.draw()

    def _load_data_async(self):
        thread = threading.Thread(target=self._load_data, daemon=True)
        thread.start()

    def _load_data(self):
        try:
            self.status_var.set("Loading base data…")
            kantone, raw = main.load_base_data()
            titles = sorted([t for t in raw['TITLE'].dropna().unique()])
            self.kantone_gdf = kantone
            self.raw_votes = raw
            self.titles = titles
            self._populate_titles(titles)
            self.status_var.set(f"Loaded {len(titles)} referendums. Select one.")
        except Exception as e:
            self.status_var.set(f"Error loading data: {e}")

    def _populate_titles(self, titles: List[str]):
        self.listbox.delete(0, tk.END)
        for t in titles:
            self.listbox.insert(tk.END, t)
        if titles:
            self.listbox.selection_set(0)
            self._on_select_title()

    def _filter_titles(self):
        query = self.search_var.get().strip().lower()
        if not query:
            self._populate_titles(self.titles)
            return
        filtered = [t for t in self.titles if query in t.lower()]
        self._populate_titles(filtered)
        self.status_var.set(f"Filtered: {len(filtered)} matches")

    def _on_select_title(self, event=None):
        if self.raw_votes is None or self.kantone_gdf is None:
            return
        if self.raw_votes.empty or len(self.kantone_gdf) == 0:
            return
        if not self.listbox.curselection():
            return
        idx = self.listbox.curselection()[0]
        title = self.listbox.get(idx)
        self.status_var.set(f"Processing: {title[:60]}…")
        self.root.after(10, lambda t=title: self._build_map_for_title(t))

    def _build_map_for_title(self, title: str):
        try:
            if title in self.cache:
                merged = self.cache[title]
            else:
                pivot, merged = main.build_canton_votes(self.raw_votes, self.kantone_gdf, title_filter=title)
                self.cache[title] = merged
            self._draw_map(merged, title)
            self.status_var.set(f"Rendered: {title[:60]} (YES range {merged['YES_PCT'].min():.1f}-{merged['YES_PCT'].max():.1f}%)")
        except Exception as e:
            self.status_var.set(f"Error: {e}")

    def _draw_map(self, merged: gpd.GeoDataFrame, title: str):
        self.ax.clear()
        self.cax.clear()
        self.ax.set_axis_off()
        if 'YES_PCT' not in merged.columns or merged['YES_PCT'].isna().all():
            self.ax.set_title("No YES_PCT data available")
            self.canvas.draw()
            return

        cmap = 'RdYlGn'
        data = merged.copy()
        vmin, vmax = 0, 100
        data.plot(column='YES_PCT', cmap=cmap, linewidth=0.4, edgecolor='black', ax=self.ax, vmin=vmin, vmax=vmax)
        import matplotlib as mpl
        norm = mpl.colors.Normalize(vmin=vmin, vmax=vmax)
        cmap_obj = mpl.colormaps.get(cmap)
        sm = mpl.cm.ScalarMappable(cmap=cmap_obj, norm=norm)
        sm.set_array([])
        cb = self.fig.colorbar(sm, cax=self.cax, format='%.0f%%')
        cb.ax.tick_params(labelsize=8)
        cb.set_label('Yes %', fontsize=9)
        self.ax.set_title(title, fontsize=10)
        self.canvas.draw()

    def _export_current(self):
        if not self.listbox.curselection():
            return
        title = self.listbox.get(self.listbox.curselection()[0])
        if title not in self.cache:
            self.status_var.set("Nothing to export yet (select first)")
            return
        out_name = 'kantone_votes.geojson'
        try:
            main.export_geojson(self.cache[title], path=out_name)
            self.status_var.set(f"Exported {out_name}")
        except Exception as e:
            self.status_var.set(f"Export failed: {e}")

    def _refresh_current(self):
        if not self.listbox.curselection():
            return
        title = self.listbox.get(self.listbox.curselection()[0])
        if title in self.cache:
            del self.cache[title]
        self._build_map_for_title(title)


def run_app():
    root = tk.Tk()
    app = ReferendumExplorerApp(root)
    root.mainloop()


if __name__ == '__main__':
    run_app()