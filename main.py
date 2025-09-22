import numpy as np
import pandas as pd

from tkinter import ttk

from pyaxis import pyaxis

px_file = "Data/volksabstimmungen.px"

df = pyaxis.parse(px_file, encoding="ISO-8859-2", lang="de")

titles = df["DATA"].iloc[:, 1]

print(titles.head(10))