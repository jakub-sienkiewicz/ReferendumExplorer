import numpy as np
import pandas as pd
import tkinter as tk
from tkinter import ttk
from pyaxis import pyaxis

px_file = "Data/volksabstimmungen.px"
df = pyaxis.parse(px_file, encoding="ISO-8859-2", lang="de")

titles = df["DATA"].iloc[:, 1].unique()

root = tk.Tk()
root.title("Swiss Referendum Explorer")
root.geometry("800x1000")

map_frame = tk.Frame(root, height=400, width=800, bg="lightgray")
map_frame.pack_propagate(False)
map_frame.pack(side=tk.TOP, fill=tk.X)
map_label = tk.Label(map_frame, text="[Swiss Map Placeholder]", bg="lightgray", font=("Arial", 16))
map_label.pack(expand=True)

list_frame = tk.Frame(root)
list_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE, activestyle='dotbox')
scrollbar_x = ttk.Scrollbar(list_frame, orient="horizontal", command=listbox.xview)
scrollbar_y = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
listbox.config(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

listbox.grid(row=0, column=0, sticky="nsew")
scrollbar_x.grid(row=1, column=0, sticky="ew")
scrollbar_y.grid(row=0, column=1, sticky="ns")

list_frame.rowconfigure(0, weight=1)
list_frame.columnconfigure(0, weight=1)

for title in titles:
	listbox.insert(tk.END, title)

root.mainloop()