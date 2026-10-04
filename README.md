# Smart Duplicate Photo Finder — یاب هوشمند عکس‌های تکراری

A desktop application (Windows-first, PySide6) that finds **exact** and
**similar** photos on a computer and helps reclaim the wasted space safely —
nothing is ever deleted without confirmation, and the default removal method is
a quarantine folder with full undo.

Everything runs locally. No network access, no telemetry.

## Features

- **Multi-stage pipeline** — filesystem walk → image detection → metadata +
  SHA-256 → exact duplicates → perceptual hashing (pHash / aHash / dHash /
  wHash) → similarity (histogram, SSIM, ORB feature matching) → grouping.
- **Smart "keep this" recommendation** — ranks group members by resolution,
  compression quality, creation date, file-name and path hints, so the original
  is kept and the derived copies are the ones flagged for removal.
- **Pause / resume / cancel** any scan at any stage; live progress, ETA and
  per-stage percentages.
- **Safe cleanup** — quarantine (undoable), Windows Recycle Bin, or permanent
  deletion with an extra warning. Protected system locations are refused
  outright.
- **Scan history** — every session is stored in SQLite with its groups, so
  results can be re-opened later without re-scanning.
- **Image comparison** — side-by-side viewer with per-method similarity scores.
- **Persian (RTL) and English** UI with a dark and light theme.
- **Optional AI similarity** — local embeddings or CLIP when `torch` /
  `open_clip_torch` are installed; the app works without them.

## Requirements

- Python 3.11+
- `pip install -r requirements.txt`

Core dependencies: **PySide6**, **numpy**, **pillow**.
Optional: **psutil** (system stats), **torch** + **open_clip_torch** (AI engines).

## Running

```bash
pip install -r requirements.txt
python main.py
```

Configuration, logs, thumbnails, quarantine and the SQLite database live under
`%APPDATA%\SmartDuplicatePhotoFinder\` (see `src/core/constants.py`).

## Architecture

```
main.py                     entry point: logging, config, database, window
src/
  core/                     constants, config, logging, system info, exceptions
  scanner/                  filesystem walk, drive enumeration, image detection
  hashing/                  SHA-256, perceptual hashes, hash cache
  similarity/               histogram / SSIM / feature matching, image loading
  ai/                       optional embedding + CLIP engines
  models/                   ImageRecord, DuplicateGroup, ScanSession, results
  database/                 SQLite wrapper, migrations, repositories
  services/                 scan pipeline, grouping, cleanup (undo), history
  workers/                  QThread wrappers around the services
  i18n/                     fa.json / en.json + Translator
  ui/                       main window, pages, widgets, styles, thumbnails
tests/                      unittest suite
```

The UI never blocks: heavy work runs in `QThread` workers
(`src/workers/`) that emit Qt signals the pages subscribe to.

## Tests

```bash
python -m unittest discover -t . -s tests
```

The suite covers configuration round-trips, hashing, grouping logic, the full
scan pipeline on a synthetic photo set, quarantine + undo, i18n, and an
offscreen smoke test of the Qt layer (`QT_QPA_PLATFORM=offscreen`).

## Safety notes

- Scans are read-only.
- `CleanupService` refuses protected paths (`Windows`, `Program Files`,
  `AppData\Local`, executables, …) via `is_protected_path`.
- The configured default method is `QUARANTINE`; every quarantined file can be
  restored from **Settings → Cleanup** or the results page's undo button, and
  expires automatically after the configured retention window.

## License

Proprietary — © Afshin Software.
