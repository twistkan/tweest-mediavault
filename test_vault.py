import hashlib
from pathlib import Path
import tempfile
import threading
import time
import unittest
from PIL import Image
import numpy as np
from vault_core import Catalog, Indexer, file_key

class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent/'qa-output')
        self.root=Path(self.temp.name); self.photos=self.root/'photos'/'2004'; self.photos.mkdir(parents=True)
        self.photo=self.photos/'Ivan and family.jpg'; Image.new('RGB',(120,90),'red').save(self.photo)
        self.before=hashlib.sha256(self.photo.read_bytes()).hexdigest(),self.photo.stat().st_mtime_ns
        self.cat=Catalog(self.root/'cache'); self.source=self.cat.add_source(self.photos)
        self.events=[]; self.scan=Indexer(self.cat,lambda *args:self.events.append(args)); self.scan.scan()

    def tearDown(self):
        assert self.root.resolve().is_relative_to((Path(__file__).parent/'qa-output').resolve())
        self.temp.cleanup()

    def test_persistent_incremental_readonly(self):
        row=self.cat.items()[0]; thumb=Path(row['thumb']); before=thumb.stat().st_mtime_ns
        self.scan.scan()
        self.assertEqual(thumb.stat().st_mtime_ns,before)
        self.assertEqual(self.before,(hashlib.sha256(self.photo.read_bytes()).hexdigest(),self.photo.stat().st_mtime_ns))
        self.assertEqual(Catalog(self.root/'cache').count(),1)
        self.assertEqual(row['date'],'2004-01-01')

    def test_filename_and_saved_tags(self):
        self.assertEqual(len(self.cat.items(text='Ivan')),1)
        self.cat.set_tags(file_key(self.photo),['Uncle','Birthday'])
        self.assertEqual(len(Catalog(self.root/'cache').items(text='Birthday')),1)
        self.assertEqual(self.photo.name,'Ivan and family.jpg')
        self.assertEqual(len(self.cat.items(text='%')),0)

    def test_disconnected_source_and_resume(self):
        moved=self.photos.with_name('temporarily-disconnected'); self.photos.rename(moved)
        self.scan.scan(); self.assertEqual(self.cat.count(),1)
        moved.rename(self.photos); self.scan.scan(); self.assertEqual(self.cat.count(),1)
        self.scan.pause.set(); worker=threading.Thread(target=self.scan.scan); worker.start(); time.sleep(.1)
        self.assertTrue(worker.is_alive()); self.scan.pause.clear(); worker.join(2); self.assertFalse(worker.is_alive())

    def test_clear_cache_keep_labels_and_readd(self):
        key=file_key(self.photo); self.cat.set_tags(key,['Ivan'])
        self.cat.forget(keep_labels=True); self.assertEqual(self.cat.count(),0)
        self.assertTrue(self.photo.is_file()); self.assertFalse((self.cat.thumbs/(key+'.jpg')).exists())
        self.cat.add_source(self.photos); self.scan.scan(); self.assertEqual(len(self.cat.items(text='Ivan')),1)
        self.assertEqual(self.before[0],hashlib.sha256(self.photo.read_bytes()).hexdigest())

    def test_named_faces_and_possible_matches(self):
        key=file_key(self.photo); feature=np.array([1.,0.,0.],dtype=np.float32).tobytes()
        with self.cat.connect() as db:
            face_id=db.execute('INSERT INTO faces(media_key,x,y,w,h,feature) VALUES(?,?,?,?,?,?)',(key,0,0,10,10,feature)).lastrowid
        self.cat.name_face(face_id,'Ivan'); self.assertEqual(self.cat.person_matches('Ivan'),[key])
        self.assertEqual(self.cat.faces(key)[0]['name'],'Ivan')
        self.cat.forget(keep_labels=False)
        with self.cat.connect() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM people').fetchone()[0],0)

    def test_changed_media_and_invalid_file(self):
        self.cat.set_tags(file_key(self.photo),['Keep this'])
        Image.new('RGB',(300,200),'blue').save(self.photo)
        (self.photos/'broken.jpg').write_bytes(b'not an image')
        self.scan.scan(); self.assertEqual(self.cat.count(),2)
        self.assertEqual(self.cat.row(file_key(self.photo))['width'],300)
        self.assertEqual(len(self.cat.items(text='Keep this')),1)
        self.assertTrue(self.cat.row(file_key(self.photos/'broken.jpg'))['error'])

if __name__=='__main__':
    (Path(__file__).parent/'qa-output').mkdir(exist_ok=True)
    unittest.main()
