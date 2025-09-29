# Referendum Explorer

Interactive exploration of Swiss federal referendum results at the canton level.

The tool loads a PC-Axis dataset (`volksabstimmungen.px`) containing referendum outcomes, normalizes multilingual canton names, aggregates vote counts, and renders an interactive Tkinter + Matplotlib choropleth map colored by percentage of YES votes per canton.

![Screenshot of the application interface](Screenshot.png)

## Repository Structure

```
Data/                     # Input data (PC-Axis and Swiss boundary shapefiles)
Scripts/download_data.sh  # (Optional) Data fetch helper
main.py                   # ETL + CLI / plotting utilities
tk_app.py                 # Interactive GUI application
Screenshot.png            # Example UI screenshot
README.md                 # This file
```

## Requirements

Python 3.10+ (tested newer). Core dependencies:

- pandas
- geopandas
- pyaxis
- matplotlib

```bash
python -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install pandas geopandas pyaxis matplotlib pyogrio
```

## Data Preparation

Place the following in `Data/` or simply run `Scripts/download_data.sh`:

1. `volksabstimmungen.px` – PC-Axis file of Swiss referendum results (German language version used here).
2. Swiss cantonal boundaries shapefile folder `swissBOUNDARIES3D` containing at least:
	 - `swissBOUNDARIES3D_1_5_TLM_KANTONSGEBIET.shp` (and its associated component files: .dbf, .shx, .prj, etc.)

## Running the GUI

```bash
python tk_app.py
```

Actions:
- Select a referendum title from the left list (type to filter).
- The map colors cantons by YES percentage (green = higher YES).
- Export current view to GeoJSON via the button.

## Command-Line Usage (Non-GUI)

Generate a static plot and GeoJSON for the first referendum:

```bash
python main.py
```

## Missing Canton Recovery (Heuristic)

Some referendums may only list district or sub-aggregates for certain cantons. If enabled (`recover_missing=True`), the loader:
- Searches sub-rows containing a prefix of the canton name (first 4 letters, accent stripped) for Ja/Nein rows.
- Sums them to synthesize canton-level Ja / Nein totals.
Disable this by passing `recover_missing=False` to `build_canton_votes` if you prefer strict raw completeness.

## Exported GeoJSON Schema

Properties (when available):
- NAME
- YES
- NO
- TOTAL
- YES_PCT
- geometry (MultiPolygon/Polygon)