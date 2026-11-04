"""Writable installed-app storage, with non-destructive legacy migration."""
import os
from pathlib import Path
import shutil

def data_folder(root, installed=False):
    override = os.environ.get('TWEEST_DATA')
    if override: return Path(override)
    if not installed: return Path(root)/'data'
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'AppData'/'Local')))/'TweestMediaVault'/'data'

def migrate_legacy_data(root, target):
    """Copy an old beside-executable catalog only when no new catalog exists."""
    old = (Path(root)/'data').resolve()
    target = Path(target).resolve()
    if old == target or (target/'library.sqlite3').exists() or not (old/'library.sqlite3').exists():
        return False
    import sqlite3
    target.mkdir(parents=True,exist_ok=True)
    # SQLite backup includes any committed WAL data without modifying the source.
    source = sqlite3.connect((old/'library.sqlite3').as_uri()+'?mode=ro',uri=True)
    staging=target/'library.migrating.sqlite3'
    destination = sqlite3.connect(staging)
    try: source.backup(destination)
    finally: destination.close(); source.close()
    if (old/'thumbnails').exists(): shutil.copytree(old/'thumbnails',target/'thumbnails',dirs_exist_ok=True)
    for name in ['view.json']:
        if (old/name).exists(): shutil.copy2(old/name,target/name)
    # Thumbnails use absolute paths in the old database; point at the migrated cache.
    db=sqlite3.connect(staging)
    try:
        with db:
            rows = db.execute('SELECT key FROM media WHERE thumb IS NOT NULL AND thumb != \'\'').fetchall()
            db.executemany('UPDATE media SET thumb=? WHERE key=?',[(str(target/'thumbnails'/(key+'.jpg')),key) for (key,) in rows])
    finally: db.close()
    staging.replace(target/'library.sqlite3')
    return True
