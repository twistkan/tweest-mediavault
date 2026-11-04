"""Local catalog. Original media is only ever opened for reading."""
from __future__ import annotations
import hashlib
import json
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

PHOTO_EXT = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff', '.heic', '.heif'}
VIDEO_EXT = {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.3gp', '.mts', '.m2ts', '.wmv'}

MONTH_NAMES=('January','February','March','April','May','June','July','August','September','October','November','December')

def folder_month(path):
    """Read archive month folders without touching the original media."""
    parts=Path(path).parts[:-1]
    for index in range(len(parts)-1,-1,-1):
        part=parts[index].lower()
        for number,name in enumerate(MONTH_NAMES,1):
            if re.search(r'(?<![a-z])'+name[:3].lower()+r'(?:'+name[3:].lower()+r')?(?![a-z])',part):return f'{number:02}'
        match=re.fullmatch(r'(?:19|20)\d{2}[-_ .](0?[1-9]|1[0-2])',part)
        if match:return f'{int(match[1]):02}'
        if re.fullmatch(r'0?[1-9]|1[0-2]',part) and index>0 and re.fullmatch(r'(?:19|20)\d{2}',parts[index-1]):return f'{int(part):02}'
    return ''

def file_key(path):
    return hashlib.sha256(os.path.normcase(os.path.abspath(path)).encode('utf-8')).hexdigest()

def folder_year(path):
    for part in reversed(Path(path).parts[:-1]):
        found=re.findall(r'(?<!\d)((?:19|20)\d{2})(?!\d)',part)
        if found:return found[-1]
    return ''

class Catalog:
    def __init__(self, home):
        self.home = Path(home).resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.thumbs = self.home / 'thumbnails'
        self.thumbs.mkdir(exist_ok=True)
        self.database = self.home / 'library.sqlite3'
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS sources(id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL);
            CREATE TABLE IF NOT EXISTS media(
                key TEXT PRIMARY KEY, source INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                path TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL, size INTEGER NOT NULL,
                mtime INTEGER NOT NULL, date TEXT, duration REAL DEFAULT 0,
                width INTEGER DEFAULT 0, height INTEGER DEFAULT 0, thumb TEXT, error TEXT,
                embedding BLOB, ai_done INTEGER DEFAULT 0);
            CREATE INDEX IF NOT EXISTS media_date ON media(date);
            CREATE INDEX IF NOT EXISTS media_source ON media(source);
            CREATE TABLE IF NOT EXISTS annotations(key TEXT PRIMARY KEY, tags TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS favourites(key TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS people(id INTEGER PRIMARY KEY, name TEXT, feature BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS faces(id INTEGER PRIMARY KEY,
                media_key TEXT REFERENCES media(key) ON DELETE CASCADE,
                person INTEGER REFERENCES people(id), x INTEGER,y INTEGER,w INTEGER,h INTEGER,
                feature BLOB NOT NULL, confirmed INTEGER DEFAULT 0);
            CREATE INDEX IF NOT EXISTS faces_media ON faces(media_key);
            CREATE INDEX IF NOT EXISTS faces_person ON faces(person);
            CREATE TABLE IF NOT EXISTS folder_checks(path TEXT PRIMARY KEY,completed TEXT NOT NULL);
            ''')
            if 'folder_month' not in {r[1] for r in db.execute('PRAGMA table_info(media)')}:
                db.execute("ALTER TABLE media ADD COLUMN folder_month TEXT NOT NULL DEFAULT ''")
                # Upgrade cached paths only; keep all face embeddings and thumbnails.
                rows=db.execute('SELECT key,path FROM media').fetchall()
                db.executemany('UPDATE media SET folder_month=? WHERE key=?',[(folder_month(r['path']),r['key']) for r in rows])
            if 'folder_year' not in {r[1] for r in db.execute('PRAGMA table_info(media)')}:
                db.execute("ALTER TABLE media ADD COLUMN folder_year TEXT NOT NULL DEFAULT ''")
                rows=db.execute('SELECT key,path FROM media').fetchall()
                db.executemany('UPDATE media SET folder_year=? WHERE key=?',[(folder_year(r['path']),r['key']) for r in rows])

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA journal_mode=WAL')
        try:
            with db:
                yield db
        finally:
            db.close()

    def sources(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM sources ORDER BY path')]

    def add_source(self, path):
        path = str(Path(path).resolve())
        if Path(path).is_relative_to(self.home):
            raise ValueError("The app's cache cannot be added as a source folder.")
        if not Path(path).is_dir():
            raise ValueError('Choose a folder that is currently connected.')
        # Overlapping roots would give ambiguous ownership of cached items.
        for source in self.sources():
            a, b = os.path.normcase(source['path']), os.path.normcase(path)
            if a == b:
                return source['id']
            try:
                if os.path.commonpath([a, b]) in (a, b):
                    raise ValueError('This folder overlaps an existing source. Choose its parent or remove the overlapping source first.')
            except ValueError as error:
                if 'overlaps' in str(error):
                    raise
        with self.connect() as db:
            return db.execute('INSERT INTO sources(path) VALUES(?)', (path,)).lastrowid

    def row(self, key):
        with self.connect() as db:
            r = db.execute('SELECT media.*,COALESCE(annotations.tags,\'[]\') tags,EXISTS(SELECT 1 FROM favourites f WHERE f.key=media.key) favourite FROM media LEFT JOIN annotations USING(key) WHERE key=?', (key,)).fetchone()
            return dict(r) if r else None

    def items(self, text='', kind='', source=None, year='', limit=500, offset=0, favourite_only=False, month='', count_only=False):
        terms, args = [], []
        if kind:
            terms.append('m.kind=?'); args.append(kind)
        if source:
            terms.append('m.source=?'); args.append(source)
        if year:
            terms.append("COALESCE(NULLIF(m.folder_year,''),substr(m.date,1,4))=?"); args.append(str(year))
        if month:
            terms.append("COALESCE(NULLIF(m.folder_month,''),substr(m.date,6,2))=?"); args.append(str(month).zfill(2))
        if favourite_only:
            terms.append('EXISTS(SELECT 1 FROM favourites f WHERE f.key=m.key)')
        if text.strip():
            # Literal substring matching. User underscores and percent signs are not SQL wildcards.
            q = '%'+text.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
            terms.append("(m.name LIKE ? ESCAPE '\\' OR a.tags LIKE ? ESCAPE '\\' OR EXISTS(SELECT 1 FROM faces f JOIN people p ON p.id=f.person WHERE f.media_key=m.key AND p.name LIKE ? ESCAPE '\\'))")
            args += [q, q, q]
        where = ' WHERE '+' AND '.join(terms) if terms else ''
        with self.connect() as db:
            if count_only:return db.execute('SELECT COUNT(*) FROM media m LEFT JOIN annotations a ON a.key=m.key'+where,args).fetchone()[0]
            columns='m.key,m.source,m.path,m.name,m.kind,m.size,m.mtime,m.date,m.duration,m.width,m.height,m.thumb,m.error,m.ai_done'
            return [dict(r) for r in db.execute('SELECT '+columns+',COALESCE(a.tags,\'[]\') tags,EXISTS(SELECT 1 FROM favourites f WHERE f.key=m.key) favourite FROM media m LEFT JOIN annotations a ON a.key=m.key'+where+' ORDER BY m.date DESC,m.path LIMIT ? OFFSET ?', args+[limit, offset])]

    def set_favourite(self,key,value):
        with self.connect() as db:
            if value: db.execute('INSERT OR IGNORE INTO favourites SELECT key FROM media WHERE key=?',(key,))
            else: db.execute('DELETE FROM favourites WHERE key=?',(key,))

    def ai_pending(self):
        with self.connect() as db:
            return db.execute("SELECT COUNT(*) FROM media WHERE kind='photo' AND error IS NULL AND ai_done=0").fetchone()[0]

    def people_search(self,text,**filters):
        """Literal name/tag text hits first, then tentative faces, within all filters."""
        limit=filters.pop('limit',500)
        candidates=self.items(limit=1000000,**filters)
        lookup={r['key']:r for r in candidates}
        exact=self.items(text=text,limit=1000000,**filters)
        confirmed={r['key'] for r in exact}
        keys=list(dict.fromkeys([r['key'] for r in exact]+self.person_matches(text)))
        rows=[]
        for key in keys:
            if key in lookup:
                row=lookup[key]; row['_possible']=key not in confirmed; rows.append(row)
        return rows[:limit]

    def count(self):
        with self.connect() as db:
            return db.execute('SELECT COUNT(*) FROM media').fetchone()[0]

    def set_tags(self, key, tags):
        values = list(dict.fromkeys(t.strip() for t in tags if t.strip()))
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO annotations VALUES(?,?)', (key, json.dumps(values, ensure_ascii=False)))

    def forget(self, source_id=None, keep_labels=True):
        """Unregister sources and remove owned cache only, never original media."""
        with self.connect() as db:
            where, args = (' WHERE source=?', (source_id,)) if source_id else ('', ())
            keys = [r[0] for r in db.execute('SELECT key FROM media'+where, args)]
            if not keep_labels:
                db.executemany('DELETE FROM annotations WHERE key=?', [(k,) for k in keys])
                db.executemany('DELETE FROM favourites WHERE key=?',[(k,) for k in keys])
                if source_id is None:
                    db.execute('DELETE FROM annotations')
                    db.execute('DELETE FROM favourites')
            if source_id:
                db.execute('DELETE FROM sources WHERE id=?', (source_id,))
            else:
                db.execute('DELETE FROM sources')
            if not keep_labels:
                db.execute('DELETE FROM people WHERE id NOT IN (SELECT person FROM faces WHERE person IS NOT NULL)')
        for key in keys:
            # Never trust a database-supplied file path for deletion.
            if len(key)==64 and all(c in '0123456789abcdef' for c in key):
                (self.thumbs / (key+'.jpg')).unlink(missing_ok=True)
        return len(keys)

    def faces(self, key):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT f.*,p.name FROM faces f LEFT JOIN people p ON p.id=f.person WHERE media_key=? ORDER BY f.x', (key,))]

    def name_face(self, face_id, name):
        name = name.strip()
        if not name:
            raise ValueError('Enter a name.')
        with self.connect() as db:
            face = db.execute('SELECT * FROM faces WHERE id=?', (face_id,)).fetchone()
            person = db.execute('SELECT id FROM people WHERE name=? COLLATE NOCASE', (name,)).fetchone()
            if person:
                person_id = person[0]
            else:
                # Only the chosen face is confirmed. Other matches remain suggestions.
                person_id = db.execute('INSERT INTO people(name,feature) VALUES(?,?)', (name, face['feature'])).lastrowid
            db.execute('UPDATE faces SET person=?,confirmed=1 WHERE id=?', (person_id, face_id))

    def unname_face(self, face_id):
        with self.connect() as db:
            db.execute('UPDATE faces SET person=NULL,confirmed=0 WHERE id=?', (face_id,))

    def has_named_person(self, text):
        if not text.strip():return False
        q='%'+text.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        with self.connect() as db:
            return bool(db.execute("SELECT 1 FROM people WHERE name LIKE ? ESCAPE '\\' LIMIT 1",(q,)).fetchone())

    def person_matches(self, name, minimum=.50):
        import numpy as np
        if not name.strip():return []
        q='%'+name.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        with self.connect() as db:
            templates = [np.frombuffer(r[0], dtype=np.float32) for r in db.execute("SELECT feature FROM people WHERE name LIKE ? ESCAPE '\\'", (q,))]
            templates += [np.frombuffer(r[0], dtype=np.float32) for r in db.execute("SELECT f.feature FROM faces f JOIN people p ON p.id=f.person WHERE p.name LIKE ? ESCAPE '\\' AND f.confirmed=1", (q,))]
            if not templates:
                return []
            results = {}
            for face in db.execute('SELECT media_key,feature FROM faces'):
                f = np.frombuffer(face['feature'], dtype=np.float32)
                score = max(float(f @ t) for t in templates)
                if score >= minimum:
                    results[face['media_key']] = max(results.get(face['media_key'], 0), score)
            return sorted(results, key=results.get, reverse=True)

def make_thumbnail(path, output, kind):
    from PIL import Image, ImageOps
    duration = 0
    if kind == 'video':
        import cv2
        capture = cv2.VideoCapture(str(path))
        try:
            count, fps = capture.get(cv2.CAP_PROP_FRAME_COUNT), capture.get(cv2.CAP_PROP_FPS)
            duration = count/fps if fps else 0
            if count > 2:
                capture.set(cv2.CAP_PROP_POS_FRAMES, min(int(count*.1), 90))
            ok, frame = capture.read()
            if not ok:
                raise ValueError('This video could not be decoded.')
            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            date = ''
        finally:
            capture.release()
    else:
        with Image.open(path) as original:
            exif = original.getexif()
            date = str(exif.get_ifd(0x8769).get(36867) or exif.get(36867) or exif.get(306) or '')[:10].replace(':', '-')
            image = ImageOps.exif_transpose(original).convert('RGB')
    width, height = image.size
    ImageOps.fit(image, (320, 320), method=Image.Resampling.LANCZOS).save(output, 'JPEG', quality=82)
    return width, height, duration, date

class Indexer:
    def __init__(self, catalog, notify=lambda *args: None):
        self.catalog, self.notify = catalog, notify
        self.pause = threading.Event()
        self.stop = threading.Event()

    def checkpoint(self):
        while self.pause.is_set() and not self.stop.wait(.15):
            pass
        return not self.stop.is_set()

    def scan(self,paths=None):
        processed = changed = errors = 0
        sources=self.catalog.sources()
        if paths is not None:
            selected=[]
            for value in paths:
                target=Path(value).resolve()
                owner=next((source for source in sources if target.is_relative_to(Path(source['path']).resolve())),None)
                if owner is None:raise ValueError('The selected folder must belong to an existing library source.')
                if any(target.is_relative_to(Path(s['path'])) for s in selected):continue
                selected=[s for s in selected if not Path(s['path']).is_relative_to(target)]
                selected.append({**owner,'path':str(target)})
            sources=selected
        for source in sources:
            root = Path(source['path'])
            self.notify('status',f'Checking {root}…')
            if not root.is_dir():
                self.notify('status', f"Drive unavailable: {root}. Cached items kept.")
                continue
            # No missing-file pruning: an interrupted/disconnected drive must never erase records.
            walk_errors = []
            for directory, folders, files in os.walk(root, followlinks=False, onerror=walk_errors.append):
                folders[:] = [f for f in folders if not (Path(directory)/f).is_symlink() and not (Path(directory)/f).is_junction() and (Path(directory)/f).resolve()!=self.catalog.home]
                for filename in files:
                    if not self.checkpoint():
                        return
                    path = Path(directory)/filename
                    ext = path.suffix.lower()
                    if ext not in PHOTO_EXT | VIDEO_EXT or path.is_symlink():
                        continue
                    key = file_key(path)
                    try:
                        info = path.stat()
                        old = self.catalog.row(key)
                        if old and old['mtime'] == info.st_mtime_ns and old['size'] == info.st_size and not old['error'] and (self.catalog.thumbs/(key+'.jpg')).exists():
                            processed += 1
                            if processed%100==0:self.notify('progress',f'{processed:,} checked · {changed:,} updated · {errors:,} unsupported')
                            continue
                        kind = 'video' if ext in VIDEO_EXT else 'photo'
                        output = self.catalog.thumbs/(key+'.jpg')
                        try:
                            width, height, duration, date = make_thumbnail(path, output, kind)
                            error = None
                        except Exception as exc:
                            width = height = duration = 0; date = ''; error = str(exc)[:250]; errors += 1
                        # Folder dates are useful for old restored archives with unreliable mtimes.
                        if not date:
                            date = next((part[:4]+'-'+(folder_month(path) or '01')+'-01' for part in reversed(path.parts[:-1]) if len(part) == 4 and part.isdigit() and 1900 <= int(part) <= 2100), '')
                        date = date or datetime.fromtimestamp(info.st_mtime).date().isoformat()
                        with self.catalog.connect() as db:
                            db.execute('DELETE FROM faces WHERE media_key=?', (key,))
                            db.execute('''INSERT INTO media(key,source,path,name,kind,size,mtime,date,duration,width,height,thumb,error,folder_month,folder_year) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                            ON CONFLICT(key) DO UPDATE SET source=excluded.source,size=excluded.size,mtime=excluded.mtime,date=excluded.date,duration=excluded.duration,width=excluded.width,height=excluded.height,thumb=excluded.thumb,error=excluded.error,folder_month=excluded.folder_month,folder_year=excluded.folder_year,embedding=NULL,ai_done=0''',
                            (key, source['id'], str(path), path.name, kind, info.st_size, info.st_mtime_ns, date, duration, width, height, str(output) if not error else '', error,folder_month(path),folder_year(path)))
                        changed += 1; processed += 1
                        self.notify('progress', f'{processed:,} checked · {changed:,} updated · {errors:,} unsupported')
                    except OSError as exc:
                        self.notify('status', f'Unavailable file: {filename}: {exc}')
            if walk_errors:
                self.notify('status', f'{len(walk_errors)} folders could not be read; cached items were kept.')
            else:
                with self.catalog.connect() as db:db.execute('INSERT OR REPLACE INTO folder_checks VALUES(?,?)',(str(root.resolve()),datetime.now().isoformat()))
        self.notify('done', f'Scan finished · {processed:,} checked · {changed:,} updated · {errors:,} unsupported')

