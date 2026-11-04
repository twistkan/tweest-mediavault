"""User-confirmed reconciliation of a missing cached entry with an indexed copy."""
import json
from pathlib import Path
import sqlite3
import tempfile


def candidates(catalog,key):
    old=catalog.row(key)
    if not old or Path(old['path']).is_file():return []
    with catalog.connect() as db:
        rows=db.execute('SELECT key,path FROM media WHERE key!=? AND name=? COLLATE NOCASE AND size=? AND kind=? ORDER BY path',
            (key,old['name'],old['size'],old['kind'])).fetchall()
    return [dict(row) for row in rows if Path(row['path']).is_file()]


def reconnect(catalog,old_key,new_key):
    """Only call after the user confirms the candidate depicts the same media."""
    if old_key==new_key:raise ValueError('Choose another indexed file.')
    def validate(db):
        old=db.execute('SELECT * FROM media WHERE key=?',(old_key,)).fetchone()
        new=db.execute('SELECT * FROM media WHERE key=?',(new_key,)).fetchone()
        if not old or not new:raise ValueError('The library changed. Choose the photo again.')
        if Path(old['path']).is_file():raise ValueError('The original is available again; no reconnection is needed.')
        if not Path(new['path']).is_file():raise FileNotFoundError('The chosen copy is no longer available.')
        if old['kind']!=new['kind'] or old['size']!=new['size'] or Path(new['path']).stat().st_size!=old['size']:
            raise ValueError('The chosen file differs in type or size. It was not reconnected.')
        return old,new
    with catalog.connect() as db:validate(db)
    backups=catalog.home/'recovery-backups'; backups.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=backups,prefix='before-reconnect-',suffix='.sqlite3',delete=False) as file:
        backup=Path(file.name)
    source=sqlite3.connect(catalog.database.as_uri()+'?mode=ro',uri=True)
    target=sqlite3.connect(backup)
    try:source.backup(target)
    finally:target.close(); source.close()
    with catalog.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        old,new=validate(db)
        tags=[]
        for key in [new_key,old_key]:
            row=db.execute('SELECT tags FROM annotations WHERE key=?',(key,)).fetchone()
            if row:tags.extend(json.loads(row[0]))
        db.execute('INSERT OR REPLACE INTO annotations VALUES(?,?)',(new_key,json.dumps(list(dict.fromkeys(tags)),ensure_ascii=False)))
        db.execute('INSERT OR IGNORE INTO favourites SELECT ? FROM favourites WHERE key=?',(new_key,old_key))
        for face in db.execute('SELECT * FROM faces WHERE media_key=?',(old_key,)).fetchall():
            same=db.execute('SELECT * FROM faces WHERE media_key=? AND x=? AND y=? AND w=? AND h=? AND feature=?',
                (new_key,face['x'],face['y'],face['w'],face['h'],face['feature'])).fetchall()
            compatible=next((row for row in same if row['person'] is None or face['person'] is None or row['person']==face['person']),None)
            if compatible:
                db.execute('UPDATE faces SET person=COALESCE(person,?),confirmed=MAX(confirmed,?) WHERE id=?',
                    (face['person'],face['confirmed'],compatible['id']))
                db.execute('DELETE FROM faces WHERE id=?',(face['id'],))
            else:db.execute('UPDATE faces SET media_key=? WHERE id=?',(new_key,face['id']))
        db.execute('UPDATE media SET embedding=COALESCE(embedding,?),ai_done=MAX(ai_done,?) WHERE key=?',
            (old['embedding'],old['ai_done'],new_key))
        db.execute('DELETE FROM annotations WHERE key=?',(old_key,))
        db.execute('DELETE FROM favourites WHERE key=?',(old_key,))
        db.execute('DELETE FROM media WHERE key=?',(old_key,))
    return backup
