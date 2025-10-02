"""Data setup utilities: ensure required referendum + boundary data is present.

If required data files / shapefiles are missing, provide helpers to download
and extract them (either via CLI prompt or Tk popup).
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Callable, Optional
import threading
import urllib.request
import zipfile
import io
import sys

# Source URLs (mirroring Scripts/download_data.sh)
BOUNDARIES_ZIP_URL = (
    "https://data.geo.admin.ch/ch.swisstopo.swissboundaries3d/"
    "swissboundaries3d_2025-04/swissboundaries3d_2025-04_2056_5728.shp.zip"
)
VOTES_PX_URL = (
    "https://dam-api.bfs.admin.ch/hub/api/dam/assets/34787122/master"
)

# Target paths (relative to project root)
DATA_DIR = Path("Data")
BOUNDARIES_ZIP_PATH = DATA_DIR / "boundaries.shp.zip"
BOUNDARIES_DIR = DATA_DIR / "swissBOUNDARIES3D"
VOTES_PX_PATH = DATA_DIR / "volksabstimmungen.px"

# Canonical shapefile we rely on elsewhere in the code
CANTON_SHP_REQUIRED = BOUNDARIES_DIR / "swissBOUNDARIES3D_1_5_TLM_KANTONSGEBIET.shp"

REQUIRED_PATHS: List[Path] = [VOTES_PX_PATH, CANTON_SHP_REQUIRED]


def list_missing(required: Iterable[Path] = REQUIRED_PATHS) -> List[Path]:
    return [p for p in required if not p.exists()]


def _download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as r:  # nosec B310 (trusted fixed URL)
        data = r.read()
    target.write_bytes(data)


def _download_and_extract_boundaries(progress: Callable[[str], None]):
    progress("Downloading boundaries zip …")
    with urllib.request.urlopen(BOUNDARIES_ZIP_URL) as r:  # nosec B310
        payload = r.read()
    progress("Extracting boundaries …")
    BOUNDARIES_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        # Extract only files we don't already have (idempotence)
        for name in zf.namelist():
            out_path = BOUNDARIES_DIR / Path(name).name
            if out_path.exists():
                continue
            with zf.open(name) as src, open(out_path, 'wb') as dst:
                dst.write(src.read())
    progress("Boundaries ready.")


def _download_votes(progress: Callable[[str], None]):
    progress("Downloading vote data …")
    _download(VOTES_PX_URL, VOTES_PX_PATH)
    progress("Vote data ready.")


def download_all(progress: Optional[Callable[[str], None]] = None) -> None:
    """Download all missing assets. Safe to call repeatedly."""
    def log(msg: str):
        if progress:
            progress(msg)
        else:
            print(msg)
    missing_now = list_missing()
    if not missing_now:
        log("All required data already present.")
        return
    if VOTES_PX_PATH in missing_now:
        _download_votes(log)
    if CANTON_SHP_REQUIRED in missing_now:
        _download_and_extract_boundaries(log)
    still = list_missing()
    if still:
        raise RuntimeError(f"Some files are still missing after download: {still}")
    log("All data downloaded.")


def ensure_data(interactive: bool = False) -> bool:
    """Ensure data exists; optionally prompt in CLI if missing.

    Returns True if data present (after potential download) else False.
    """
    missing = list_missing()
    if not missing:
        return True
    if not interactive:
        return False
    # Simple CLI prompt
    print("Missing required data files:")
    for p in missing:
        print(" -", p)
    resp = input("Download them now? [y/N] ").strip().lower()
    if resp == 'y':
        try:
            download_all()
            return True
        except Exception as e:  # pragma: no cover
            print("Download failed:", e, file=sys.stderr)
            return False
    return False


# -------------------- Tk integration helpers --------------------

def ensure_data_tk(
    root,  # tk.Tk
    on_status: Optional[Callable[[str], None]] = None,
    on_ready: Optional[Callable[[], None]] = None,
):
    """Check for data; if missing, ask user via popup and (optionally) download.

    on_status: callback for progress messages (UI label)
    on_ready: called (in main thread) once data confirmed present.
    """
    import tkinter as tk
    from tkinter import messagebox

    def set_status(msg: str):
        if on_status:
            on_status(msg)

    missing = list_missing()
    if not missing:
        if on_ready:
            root.after(0, on_ready)
        return

    pretty = "\n".join(str(m) for m in missing)
    if not messagebox.askyesno(
        "Download data",
        f"The following required data files are missing:\n\n{pretty}\n\nDownload now?"
    ):
        set_status("Data missing – download declined.")
        return

    def worker():
        try:
            download_all(set_status)
        except Exception as e:  # pragma: no cover
            set_status(f"Download failed: {e}")
        else:
            set_status("Data ready.")
        finally:
            if on_ready:
                root.after(0, on_ready)

    threading.Thread(target=worker, daemon=True).start()

__all__ = [
    'ensure_data', 'download_all', 'ensure_data_tk', 'list_missing',
    'VOTES_PX_PATH', 'CANTON_SHP_REQUIRED'
]
