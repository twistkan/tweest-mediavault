"""Local folder checks and conservative duplicate detection. Never edits originals."""
from pathlib import Path
from datetime import datetime
import hashlib
import json
import os
from vault_core import PHOTO_EXT,VIDEO_EXT

def log_event(catalog,event,**details):
    with (catalog.home/'library-log.jsonl').open('a',encoding='utf-8') as stream:
        stream.write(json.dumps({'time':datetime.now().astimezone().isoformat(),'event':event,**details},ensure_ascii=False)+'\n')

def inventory(root,cache,stop=lambda:False):
    root=Path(root).resolve(); files={}; issues=[]
    if not root.is_dir():return files,[f'Folder unavailable: {root}']
    for directory,folders,names in os.walk(root,followlinks=False,onerror=lambda exc:issues.append(str(exc))):
        if stop():return files,issues+['Check cancelled']
        folders[:]=[n for n in folders if not (Path(directory)/n).is_symlink() and not (Path(directory)/n).is_junction() and (Path(directory)/n).resolve()!=cache]
        for name in names:
            if stop():return files,issues+['Check cancelled']
            path=Path(directory)/name
            if path.suffix.lower() not in PHOTO_EXT|VIDEO_EXT or path.is_symlink():continue
            try:
                stat=path.stat(); files[str(path.relative_to(root))]=(path,stat.st_size,stat.st_mtime_ns)
            except OSError as exc:issues.append(str(exc))
    return files,issues

def audit_library(catalog,stop=lambda:False):
    with catalog.connect() as db:
        cached={os.path.normcase(r['path']):(r['size'],r['mtime']) for r in db.execute('SELECT path,size,mtime FROM media')}
    missing=changed=0; roots=set(); issues=[]
    for source in catalog.sources():
        root=Path(source['path']).resolve(); files,errors=inventory(root,catalog.home,stop); issues.extend(errors)
        for relative,(path,size,mtime) in files.items():
            old=cached.get(os.path.normcase(str(path)))
            if old is None or old!=(size,mtime):
                missing+=old is None; changed+=old is not None
                parts=Path(relative).parts
                roots.add(str(root/parts[0]) if len(parts)>1 else str(root))
    result={'missing':missing,'changed':changed,'paths':sorted(roots),'issues':issues}
    if not stop():log_event(catalog,'folder_check',**result)
    return result

def file_hash(path,stop):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024):
            if stop():raise InterruptedError('Folder check cancelled')
            digest.update(block)
    return digest.digest()

def prepare_imports(catalog,paths,stop=lambda:False):
    """Skip unchanged paths and exact copies; changed/new media still gets scanned."""
    with catalog.connect() as db:
        cached={os.path.normcase(r['path']):(r['size'],r['mtime']) for r in db.execute('SELECT path,size,mtime FROM media')}
        known=[r[0] for r in db.execute('SELECT path FROM folder_checks')]
    candidates=list(dict.fromkeys(known+[s['path'] for s in catalog.sources()]))
    accepted=[]; skipped=[]; errors=[]; seen=set()
    for value in paths:
        target=Path(value).resolve(); canonical=os.path.normcase(str(target))
        if canonical in seen:
            skipped.append({'path':str(target),'reason':'repeated selection'}); continue
        seen.add(canonical)
        if target.is_relative_to(catalog.home):errors.append(f'Cache folder cannot be imported: {target}'); continue
        files,issues=inventory(target,catalog.home,stop)
        if stop():break
        if not target.is_dir():errors.extend(issues); continue
        if files and not issues and all(cached.get(os.path.normcase(str(p)))==(size,mtime) for p,size,mtime in files.values()):
            skipped.append({'path':str(target),'reason':'already indexed; no new or changed media'}); continue
        duplicate=None
        if files and not issues:
            shape={relative:entry[1] for relative,entry in files.items()}
            for candidate in candidates:
                other=Path(candidate).resolve()
                if target.is_relative_to(other) or other.is_relative_to(target):continue
                old,old_issues=inventory(other,catalog.home,stop)
                # Only skip copies of a fully indexed folder, never an incomplete scan.
                if old_issues or {r:e[1] for r,e in old.items()}!=shape:continue
                if str(other) not in accepted and not all(cached.get(os.path.normcase(str(p)))==(size,mtime) for p,size,mtime in old.values()):continue
                try:
                    if all(file_hash(files[r][0],stop)==file_hash(old[r][0],stop) for r in files):duplicate=str(other); break
                except OSError as exc:issues.append(str(exc))
        if duplicate:skipped.append({'path':str(target),'reason':'byte-identical media folder','matches':duplicate})
        else:accepted.append(str(target)); candidates.append(str(target))
        errors.extend(issues)
    for item in skipped:log_event(catalog,'duplicate_folder_skipped',**item)
    for item in accepted:log_event(catalog,'folder_queued',path=item)
    for error in errors:log_event(catalog,'folder_check_error',detail=error)
    return {'accepted':accepted,'skipped':skipped,'errors':errors}
