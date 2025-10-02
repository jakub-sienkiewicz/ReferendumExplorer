from typing import Optional, Tuple
import re
import unicodedata
import difflib

import geopandas as gpd
import pandas as pd
import matplotlib.pyplot as plt
from pyaxis import pyaxis
import data_setup

pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', 120)

CANTONS_SHP = "Data/swissBOUNDARIES3D/swissBOUNDARIES3D_1_5_TLM_KANTONSGEBIET.shp"
VOTE_FILE = "Data/volksabstimmungen.px"

COUNT_CATEGORIES = {'STIMMBERECHTIGTE','ABGEGEBENE STIMMEN','GÜLTIGE STIMMZETTEL','JA','NEIN'}

GERMAN_DIACRITIC_MAP = {
    #'UEBER': 'ÜBER',
    #'UEBERFREMDUNG': 'ÜBERFREMDUNG',
    #'UEBERBEVÖLKERUNG': 'ÜBERBEVÖLKERUNG'.upper(),
    'AE': 'Ä',
    'OE': 'Ö',
    'UE': 'Ü',
}

def strip_accents(s: str) -> str:
    """Return string without diacritical marks."""
    return ''.join(
        ch for ch in unicodedata.normalize('NFD', s)
        if unicodedata.category(ch) != 'Mn'
    )


def clean_area_name(s: str) -> str:
    """Normalize raw hierarchical area names by trimming control characters and excess whitespace."""
    if s is None:
        return s
    st = str(s).strip()
    st = re.sub(r'^(\-\s*|>+\s*)', '', st)
    st = re.sub(r'^\.*', '', st)
    return re.sub(r'\s+', ' ', st).strip()


def clean_number_series(series: pd.Series) -> pd.Series:
    """Convert string series with mixed thousand separators / commas to numeric."""
    return pd.to_numeric(
        series.astype(str)
              .str.replace(r"[\u202f\u00A0' ]", "", regex=True)
              .str.replace(",", "."),
        errors='coerce'
    )


def load_base_data() -> Tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """Load shapefile (cantons) and referendum raw data (PX file) with minimal normalization."""
    kantone = gpd.read_file(CANTONS_SHP).to_crs(4326)
    encodings = ['cp1252', 'ISO-8859-1', 'ISO-8859-2']
    vt = None
    for enc in encodings:
        try:
            candidate = pyaxis.parse(VOTE_FILE, encoding=enc, lang='de')
            dfc = candidate['DATA']
            if 'Datum und Vorlage' in dfc.columns:
                titles_sample = dfc['Datum und Vorlage'].dropna().astype(str).head(250)
                if titles_sample.str.contains('[Ťť]').any():
                    continue
            vt = candidate
            break
        except Exception:
            continue
    if vt is None:
        vt = pyaxis.parse(VOTE_FILE, encoding='ISO-8859-2', lang='de')
    raw = vt['DATA'].copy()
    RAW_AREA_COL = 'Kanton (-) / Bezirk (>>) / Gemeinde (......)'
    if RAW_AREA_COL not in raw.columns:
        raise KeyError('Missing hierarchical area column in vote data.')
    raw = raw.rename(columns={
        RAW_AREA_COL: 'AREA_RAW',
        'Datum und Vorlage': 'TITLE',
        'Ergebnis': 'CATEGORY',
        'DATA': 'VALUE'
    })
    raw['AREA_CLEAN'] = raw['AREA_RAW'].apply(clean_area_name)
    raw['AREA_JOIN'] = raw['AREA_CLEAN'].str.upper()
    kantone['NAME_JOIN'] = kantone['NAME'].str.upper()
    if 'TITLE' in raw.columns:
        raw['TITLE'] = raw['TITLE'].apply(clean_title_text)
    return kantone, raw


def clean_title_text(title: str) -> str:
    """Normalize referendum title formatting.

    - Replace stray high-ASCII quotes with standard « » if needed.
    - Optionally map ASCII digraphs (UE -> Ü) in all-caps segments.
    - Remove trailing accidental 't' caused by encoding artifact (rare).
    """
    if title is None:
        return title
    t = str(title)
    t = t.replace('"', '"')
    t = re.sub(r'(Ueberfremdung|Ueberfremdungsinitiative|Ueberbevölkerung der Schweiz)t\b', r'\1', t)
    def restore_token(tok: str) -> str:
        if not tok.isupper() or len(tok) < 2:
            return tok
        out = tok
        for k in sorted(GERMAN_DIACRITIC_MAP.keys(), key=len, reverse=True):
            if k in out:
                out = out.replace(k, GERMAN_DIACRITIC_MAP[k])
        return out
    tokens = re.split(r'(\s+)', t)
    tokens = [restore_token(tok) if i % 2 == 0 else tok for i, tok in enumerate(tokens)]
    t = ''.join(tokens)
    return t


def normalize_canton_names(raw: pd.DataFrame, kantone: gpd.GeoDataFrame) -> pd.DataFrame:
    """Map variant canton spellings to canonical shapefile names (best-effort)."""
    canton_set = set(kantone['NAME_JOIN'])
    canonical_map = {strip_accents(c.upper()): c for c in canton_set}
    extra_aliases = {
        'GENF': 'GENÈVE', 'GENEVE': 'GENÈVE', 'GENEVA': 'GENÈVE', 'GENEVE ': 'GENÈVE',
        'WALLIS': 'VALAIS',
        'GRAUBUNDEN': 'GRAUBÜNDEN', 'GRISONS': 'GRAUBÜNDEN', 'GRIGIONI': 'GRAUBÜNDEN', 'GRAUBUENDEN': 'GRAUBÜNDEN',
        'FREIBURG': 'FRIBOURG', 'FRIBURG': 'FRIBOURG'
    }

    def norm(s: str) -> str:
        su = s.upper()
        key = strip_accents(su)

        if '/' in su:
            parts = [p.strip() for p in su.split('/') if p.strip()]
            for part in parts:
                part_key = strip_accents(part)
                if part in canton_set:
                    return part
                if part in extra_aliases and extra_aliases[part] in canton_set:
                    return extra_aliases[part]
                if part_key in canonical_map:
                    return canonical_map[part_key]
                if part_key in extra_aliases and extra_aliases[part_key] in canton_set:
                    return extra_aliases[part_key]

        if key in canonical_map:
            return canonical_map[key]
        if su in canton_set:
            return su
        if su in extra_aliases and extra_aliases[su] in canton_set:
            return extra_aliases[su]
        if key in extra_aliases and extra_aliases[key] in canton_set:
            return extra_aliases[key]
        cand = difflib.get_close_matches(key, list(canonical_map.keys()), n=1, cutoff=0.83)
        return canonical_map[cand[0]] if cand else su

    raw['AREA_JOIN_NORM'] = raw['AREA_JOIN'].apply(norm)
    return raw


def collapse_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse multiple rows per (canton, category) to a single numeric value.

    For count-like categories we take the max (should be identical in clean data),
    otherwise we keep the first non-null distinct value.
    """
    df = df.copy()
    df['VALUE_NUM'] = clean_number_series(df['VALUE'])

    def collapse(series: pd.Series) -> float:
        name = series.name.upper()
        cleaned = series.dropna()
        if cleaned.empty:
            return None
        if cleaned.astype(str).nunique() == 1:
            return cleaned.iloc[0]
        if name in COUNT_CATEGORIES:
            return pd.to_numeric(cleaned, errors='coerce').max()
        return cleaned.iloc[0]

    return (
        df.groupby(['AREA_JOIN_NORM', 'CATEGORY'])['VALUE_NUM']
          .agg(collapse)
          .reset_index()
    )


def build_canton_votes(
    raw: pd.DataFrame,
    kantone: gpd.GeoDataFrame,
    title_filter: Optional[str] = None,
    title_index: int = 0,
    recover_missing: bool = True,
) -> Tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Produce canton-level referendum aggregation for a selected title."""
    all_titles = sorted(t for t in raw['TITLE'].dropna().unique())
    if not all_titles:
        raise ValueError('No referendum titles found.')
    if title_filter:
        candidates = [t for t in all_titles if title_filter.lower() in t.lower()]
        if not candidates:
            raise ValueError(f'No titles match filter: {title_filter}')
        selected = candidates[0]
    else:
        selected = all_titles[title_index]

    sel = normalize_canton_names(raw[raw['TITLE'] == selected].copy(), kantone)
    canton_set = set(kantone['NAME_JOIN'])
    sel_canton = sel[sel['AREA_JOIN_NORM'].isin(canton_set)].copy()
    if sel_canton.empty:
        raise ValueError('No canton-level rows after normalization.')

    collapsed = collapse_duplicates(sel_canton[['AREA_JOIN_NORM', 'CATEGORY', 'VALUE']])

    missing = canton_set - set(collapsed['AREA_JOIN_NORM'])
    if missing and recover_missing:
        for miss in missing:
            key = strip_accents(miss)[:4]
            sub = sel[
                sel['CATEGORY'].isin(['Ja', 'Nein']) &
                sel['AREA_JOIN'].apply(lambda x: key in strip_accents(str(x)))
            ]
            if not sub.empty:
                agg = sub.groupby('CATEGORY')['VALUE'].apply(lambda x: clean_number_series(x).sum())
                for cat in ['Ja', 'Nein']:
                    collapsed = pd.concat([
                        collapsed,
                        pd.DataFrame({'AREA_JOIN_NORM': [miss], 'CATEGORY': [cat], 'VALUE_NUM': [agg.get(cat)]})
                    ], ignore_index=True)

    if 'VALUE_NUM' not in collapsed.columns:
        collapsed['VALUE_NUM'] = collapsed['VALUE']

    pivot = (
        collapsed.pivot_table(
            index='AREA_JOIN_NORM', columns='CATEGORY', values='VALUE_NUM', aggfunc='first'
        ).reset_index().rename(columns={'AREA_JOIN_NORM': 'AREA_JOIN'})
    )
    pivot.columns.name = None

    cols = [c for c in pivot.columns if c != 'AREA_JOIN']

    def find_col(candidates, pattern):
        for col in candidates:
            if re.fullmatch(pattern, col, flags=re.IGNORECASE):
                return col
        return None

    yes_col = find_col(cols, r'(?i)ja')
    no_col = find_col(cols, r'(?i)nein')
    if yes_col and no_col:
        pivot['YES'] = clean_number_series(pivot[yes_col])
        pivot['NO'] = clean_number_series(pivot[no_col])
        pivot['TOTAL'] = pivot['YES'].fillna(0) + pivot['NO'].fillna(0)
        pivot['YES_PCT'] = (pivot['YES'] / pivot['TOTAL'].where(pivot['TOTAL'] != 0)) * 100

    merged = kantone.merge(pivot, left_on='NAME_JOIN', right_on='AREA_JOIN', how='left')
    return pivot, merged


def export_geojson(merged: gpd.GeoDataFrame, path: str = 'kantone_votes.geojson') -> None:
    """Export a minimal GeoJSON with vote metrics."""
    cols = ['NAME', 'YES', 'NO', 'TOTAL', 'YES_PCT', 'geometry']
    available = [c for c in cols if c in merged.columns]
    merged[available].to_file(path, driver='GeoJSON')
    print(f'Exported GeoJSON: {path}')


def plot_choropleth(merged: gpd.GeoDataFrame, column: str = 'YES_PCT') -> None:
    """Render a simple choropleth (matplotlib)."""
    if column not in merged.columns:
        print(f'Column {column} not found; skipping plot.')
        return
    fig, ax = plt.subplots(figsize=(6, 6))
    merged.plot(
        column=column, cmap='RdYlGn', linewidth=0.5,
        edgecolor='black', ax=ax, legend=True
    )
    ax.set_title(f'Referendum – {column}')
    ax.axis('off')
    plt.tight_layout()
    plt.show()


def main(
    title_filter: Optional[str] = None,
    title_index: int = 0,
    export: bool = True,
    draw: bool = True,
    auto_download: bool = True,
):
    """High-level orchestration: load data, aggregate and optionally export / plot."""
    if auto_download and data_setup.list_missing():
        try:
            data_setup.download_all()
        except Exception as e:
            print(f"Warning: automatic data download failed: {e}")
    if data_setup.list_missing():
        raise FileNotFoundError(
            f"Required data files missing: {data_setup.list_missing()} (run data_setup.download_all())"
        )
    kantone, raw = load_base_data()
    pivot, merged = build_canton_votes(
        raw, kantone,
        title_filter=title_filter,
        title_index=title_index,
    )
    if export:
        export_geojson(merged)
    if draw:
        plot_choropleth(merged)
    return pivot, merged


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Swiss Referendum aggregation')
    parser.add_argument('--filter', help='Substring to match referendum title')
    parser.add_argument('--index', type=int, default=0, help='Index of title if no filter')
    parser.add_argument('--no-export', action='store_true', help='Disable GeoJSON export')
    parser.add_argument('--no-draw', action='store_true', help='Disable plotting')
    parser.add_argument('--no-auto-download', action='store_true', help='Do not auto download missing data')
    args = parser.parse_args()
    main(
        title_filter=args.filter,
        title_index=args.index,
        export=not args.no_export,
        draw=not args.no_draw,
        auto_download=not args.no_auto_download,
    )