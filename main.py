from typing import Optional, Tuple
import geopandas as gpd
import pandas as pd
import re, unicodedata, difflib
from pyaxis import pyaxis
import matplotlib.pyplot as plt

pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', 120)

SB3_DIR = "Data/swissBOUNDARIES3D"
CANTONS_SHP = f"{SB3_DIR}/swissBOUNDARIES3D_1_5_TLM_KANTONSGEBIET.shp"
VOTE_FILE = "Data/volksabstimmungen.px"

COUNT_CATEGORIES = {'STIMMBERECHTIGTE','ABGEGEBENE STIMMEN','GÜLTIGE STIMMZETTEL','JA','NEIN'}
PERCENT_CATEGORIES = {'BETEILIGUNG IN %','JA IN %'}


def strip_accents(s: str) -> str:
    return ''.join(ch for ch in unicodedata.normalize('NFD', s) if unicodedata.category(ch) != 'Mn')


def clean_area_name(s: str) -> str:
    if s is None:
        return s
    st = str(s).strip()
    st = re.sub(r'^(\-\s*|>+\s*)', '', st)
    st = re.sub(r'^\.*', '', st)
    st = re.sub(r'\s+', ' ', st).strip()
    return st


def clean_number_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str)
              .str.replace(r"[\u202f\u00A0' ]", "", regex=True)
              .str.replace(",", "."), errors='coerce'
    )


def load_base_data() -> Tuple[gpd.GeoDataFrame, pd.DataFrame]:
    kantone = gpd.read_file(CANTONS_SHP).to_crs(4326)
    vt = pyaxis.parse(VOTE_FILE, encoding='ISO-8859-2', lang='de')
    raw = vt['DATA'].copy()
    RAW_AREA_COL = 'Kanton (-) / Bezirk (>>) / Gemeinde (......)'
    assert RAW_AREA_COL in raw.columns, 'Missing hierarchical area column'
    raw = raw.rename(columns={
        RAW_AREA_COL: 'AREA_RAW',
        'Datum und Vorlage': 'TITLE',
        'Ergebnis': 'CATEGORY',
        'DATA': 'VALUE'
    })
    raw['AREA_CLEAN'] = raw['AREA_RAW'].apply(clean_area_name)
    raw['AREA_JOIN'] = raw['AREA_CLEAN'].str.upper()
    kantone['NAME_JOIN'] = kantone['NAME'].str.upper()
    return kantone, raw


def normalize_canton_names(raw: pd.DataFrame, kantone: gpd.GeoDataFrame) -> pd.DataFrame:
    canton_set = set(kantone['NAME_JOIN'])
    canonical_map = {strip_accents(c.upper()): c for c in canton_set}
    extra_aliases = {
        'GENF': 'GENÈVE', 'GENEVE': 'GENÈVE', 'GENEVA': 'GENÈVE', 'GENEVE ': 'GENÈVE',
        'WALLIS': 'VALAIS',
        'GRAUBUNDEN': 'GRAUBÜNDEN', 'GRISONS': 'GRAUBÜNDEN', 'GRIGIONI': 'GRAUBÜNDEN', 'GRAUBUENDEN': 'GRAUBÜNDEN',
        'FREIBURG': 'FRIBOURG', 'FRIBURG': 'FRIBOURG'  # German / common variants -> French canonical form
    }

    def norm(s: str) -> str:
        su = s.upper()
        key = strip_accents(su)
        if key in canonical_map: return canonical_map[key]
        if su in canton_set: return su
        if su in extra_aliases and extra_aliases[su] in canton_set: return extra_aliases[su]
        if key in extra_aliases and extra_aliases[key] in canton_set: return extra_aliases[key]
        cand = difflib.get_close_matches(key, list(canonical_map.keys()), n=1, cutoff=0.83)
        if cand: return canonical_map[cand[0]]
        return su

    raw['AREA_JOIN_NORM'] = raw['AREA_JOIN'].apply(norm)
    return raw


def collapse_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    # Work on a copy to avoid chained assignment warnings
    df = df.copy()
    df['VALUE_NUM'] = clean_number_series(df['VALUE'])

    def collapse(series: pd.Series) -> float:
        name = series.name.upper()
        cleaned = series.dropna()
        if cleaned.empty: return None
        if cleaned.astype(str).nunique() == 1: return cleaned.iloc[0]
        if name in COUNT_CATEGORIES:
            return pd.to_numeric(cleaned, errors='coerce').max()
        return cleaned.iloc[0]

    return df.groupby(['AREA_JOIN_NORM', 'CATEGORY'])['VALUE_NUM'].agg(collapse).reset_index()


def build_canton_votes(
    raw: pd.DataFrame,
    kantone: gpd.GeoDataFrame,
    title_filter: Optional[str] = None,
    title_index: Optional[int] = 0,
    recover_missing: bool = True,
    debug: bool = True
) -> Tuple[pd.DataFrame, gpd.GeoDataFrame]:
    all_titles = sorted([t for t in raw['TITLE'].dropna().unique()])
    if not all_titles:
        raise ValueError('No referendum titles found.')
    if title_filter:
        candidates = [t for t in all_titles if title_filter.lower() in t.lower()]
        if not candidates:
            raise ValueError(f'No titles match filter: {title_filter}')
        selected = candidates[0]
    else:
        selected = all_titles[title_index or 0]
    print(f"Using referendum title: {selected}")

    sel = raw[raw['TITLE'] == selected].copy()
    sel = normalize_canton_names(sel, kantone)
    if debug:
        print('\nDEBUG: Shapefile canton names containing FRI/FREI:')
        print(sorted([n for n in kantone['NAME_JOIN'] if ('FRI' in n or 'FREI' in n)]))
        tmp = sel[sel['AREA_JOIN'].str.contains('FRI|FREI', regex=True, na=False)].copy()
        if tmp.empty:
            print('DEBUG: No raw AREA entries containing FRI/FREI found for this title.')
        else:
            print('DEBUG: Raw AREA rows containing FRI/FREI (first 12):')
            sample_cols = ['AREA_RAW','AREA_CLEAN','AREA_JOIN','AREA_JOIN_NORM','CATEGORY','VALUE']
            print(tmp[sample_cols].drop_duplicates().head(12).to_string(index=False))
    canton_set = set(kantone['NAME_JOIN'])
    sel_canton = sel[sel['AREA_JOIN_NORM'].isin(canton_set)].copy()
    if debug:
        missing_norm = sorted(set(sel['AREA_JOIN_NORM']) - canton_set)
        if missing_norm:
            print('DEBUG: Normalized names not in canton_set (first 20):', missing_norm[:20])
    if sel_canton.empty:
        raise ValueError('No canton-level rows after normalization.')

    collapsed = collapse_duplicates(sel_canton[['AREA_JOIN_NORM', 'CATEGORY', 'VALUE']])
    if debug:
        if 'FRIBOURG' in canton_set or 'FREIBURG' in canton_set:
            target_name = 'FRIBOURG' if 'FRIBOURG' in canton_set else 'FREIBURG'
            dbg_rows = collapsed[collapsed['AREA_JOIN_NORM'] == target_name]
            print(f'DEBUG: Collapsed rows for {target_name}:')
            print(dbg_rows.to_string(index=False) if not dbg_rows.empty else '  <none>')
    missing = canton_set - set(collapsed['AREA_JOIN_NORM'])
    if missing:
        print('Missing canton rows (before recovery):', missing)
        if recover_missing:
            print('Attempting aggregate recovery for missing cantons:', missing)
            for miss in missing:
                key = strip_accents(miss)[:4]
                sub = sel[sel['CATEGORY'].isin(['Ja', 'Nein']) & sel['AREA_JOIN'].apply(lambda x: key in strip_accents(str(x)))]
                if not sub.empty:
                    agg = sub.groupby('CATEGORY')['VALUE'].apply(lambda x: clean_number_series(x).sum())
                    for cat in ['Ja', 'Nein']:
                        collapsed = pd.concat([
                            collapsed,
                            pd.DataFrame({'AREA_JOIN_NORM': [miss], 'CATEGORY': [cat], 'VALUE_NUM': [agg.get(cat)]})
                        ], ignore_index=True)
        else:
            print('Recovery disabled; proceeding with available cantons only.')

    if 'VALUE_NUM' not in collapsed.columns:
        collapsed['VALUE_NUM'] = collapsed['VALUE']

    pivot = collapsed.pivot_table(index='AREA_JOIN_NORM', columns='CATEGORY', values='VALUE_NUM', aggfunc='first').reset_index().rename(columns={'AREA_JOIN_NORM': 'AREA_JOIN'})
    if debug:
        if 'FRIBOURG' in pivot['AREA_JOIN'].values or 'FREIBURG' in pivot['AREA_JOIN'].values:
            nm = 'FRIBOURG' if 'FRIBOURG' in pivot['AREA_JOIN'].values else 'FREIBURG'
            print(f'DEBUG: Pivot row for {nm}:')
            print(pivot[pivot['AREA_JOIN'] == nm].to_string(index=False))
    pivot.columns.name = None

    cols = [c for c in pivot.columns if c != 'AREA_JOIN']

    def find_col(candidates, patterns):
        out = []
        for col in candidates:
            cl = col.lower()
            if any(re.search(p, cl) for p in patterns):
                out.append(col)
        return out

    yes_col = (find_col(cols, [r'^ja$']) or [None])[0]
    no_col = (find_col(cols, [r'^nein$']) or [None])[0]
    if yes_col and no_col:
        pivot['YES'] = clean_number_series(pivot[yes_col])
        pivot['NO'] = clean_number_series(pivot[no_col])
        pivot['TOTAL'] = pivot['YES'].fillna(0) + pivot['NO'].fillna(0)
        pivot['YES_PCT'] = (pivot['YES'] / pivot['TOTAL'].where(pivot['TOTAL'] != 0)) * 100

    merged = kantone.merge(pivot, left_on='NAME_JOIN', right_on='AREA_JOIN', how='left')
    if debug:
        nm = 'FRIBOURG' if 'FRIBOURG' in kantone['NAME_JOIN'].values else ('FREIBURG' if 'FREIBURG' in kantone['NAME_JOIN'].values else None)
        if nm:
            print(f'DEBUG: Merged row for {nm}:')
            print(merged[merged['NAME_JOIN'] == nm].to_string(index=False))
    return pivot, merged


def export_geojson(merged: gpd.GeoDataFrame, path: str = 'kantone_votes.geojson') -> None:
    cols = ['NAME', 'YES', 'NO', 'TOTAL', 'YES_PCT', 'geometry']
    available = [c for c in cols if c in merged.columns]
    merged[available].to_file(path, driver='GeoJSON')
    print(f'GeoJSON exported -> {path}')


def plot_choropleth(merged: gpd.GeoDataFrame, column: str = 'YES_PCT') -> None:
    if column not in merged.columns:
        print(f'Column {column} not in merged data.')
        return
    fig, ax = plt.subplots(figsize=(6, 6))
    merged.plot(column=column, cmap='RdYlGn', linewidth=0.5, edgecolor='black', ax=ax, legend=True)
    ax.set_title(f'Swiss Referendum – {column}')
    ax.axis('off')
    plt.tight_layout()
    plt.show()


def main(title_filter: Optional[str] = None, title_index: Optional[int] = 0, export: bool = True, draw: bool = True, debug: bool = False):
    print('Loading base data…')
    kantone, raw = load_base_data()
    print('Building canton votes…')
    pivot, merged = build_canton_votes(raw, kantone, title_filter=title_filter, title_index=title_index, debug=debug)
    print('Canton rows:', len(pivot))
    print(pivot[['AREA_JOIN', 'YES', 'NO', 'TOTAL', 'YES_PCT']].head())
    if export:
        export_geojson(merged)
    if draw:
        plot_choropleth(merged)
    return pivot, merged


if __name__ == '__main__':
    main()