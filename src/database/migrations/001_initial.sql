-- Initial schema for DupliPix.
-- Every image discovered during a scan is cached here so subsequent scans can
-- reuse hashes and metadata instead of re-reading the file from disk.

CREATE TABLE IF NOT EXISTS scan_sessions (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time         TEXT,
    end_time           TEXT,
    folders            TEXT NOT NULL DEFAULT '[]',
    files_scanned      INTEGER NOT NULL DEFAULT 0,
    images_found       INTEGER NOT NULL DEFAULT 0,
    duplicates_found   INTEGER NOT NULL DEFAULT 0,
    space_recoverable  INTEGER NOT NULL DEFAULT 0,
    status             TEXT NOT NULL DEFAULT 'pending',
    error              TEXT
);

CREATE TABLE IF NOT EXISTS images (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    path         TEXT NOT NULL,
    filename     TEXT NOT NULL,
    extension    TEXT NOT NULL,
    size         INTEGER NOT NULL,
    width        INTEGER NOT NULL DEFAULT 0,
    height       INTEGER NOT NULL DEFAULT 0,
    created_at   REAL NOT NULL DEFAULT 0,
    modified_at  REAL NOT NULL DEFAULT 0,
    sha256       TEXT,
    ahash        TEXT,
    dhash        TEXT,
    phash        TEXT,
    whash        TEXT,
    embedding    BLOB,
    scan_id      INTEGER REFERENCES scan_sessions(id) ON DELETE CASCADE,
    error        TEXT,
    UNIQUE(path, size, modified_at)
);

CREATE INDEX IF NOT EXISTS idx_images_scan        ON images(scan_id);
CREATE INDEX IF NOT EXISTS idx_images_sha256      ON images(sha256);
CREATE INDEX IF NOT EXISTS idx_images_phash       ON images(phash);
CREATE INDEX IF NOT EXISTS idx_images_size        ON images(size);
CREATE INDEX IF NOT EXISTS idx_images_path        ON images(path);

CREATE TABLE IF NOT EXISTS duplicate_groups (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id          INTEGER REFERENCES scan_sessions(id) ON DELETE CASCADE,
    group_type       TEXT NOT NULL DEFAULT 'similar',
    similarity_score REAL NOT NULL DEFAULT 100,
    keep_id          INTEGER,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_groups_scan ON duplicate_groups(scan_id);

CREATE TABLE IF NOT EXISTS group_items (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES duplicate_groups(id) ON DELETE CASCADE,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    UNIQUE(group_id, image_id)
);

CREATE INDEX IF NOT EXISTS idx_group_items_group ON group_items(group_id);
CREATE INDEX IF NOT EXISTS idx_group_items_image ON group_items(image_id);

-- Files that were removed by the cleanup service so the operation can be undone.
CREATE TABLE IF NOT EXISTS deleted_files (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id       INTEGER,
    original_path  TEXT NOT NULL,
    backup_path    TEXT,          -- location when moved into quarantine
    method         TEXT NOT NULL, -- quarantine | recycle_bin | permanent
    size           INTEGER NOT NULL DEFAULT 0,
    deleted_at     TEXT NOT NULL DEFAULT (datetime('now')),
    restored       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_deleted_restored ON deleted_files(restored);
