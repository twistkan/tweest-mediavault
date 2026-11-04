import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication,QMessageBox
from vault_core import Catalog,Indexer,file_key
from desktop_app import VaultWindow,MediaDialog
from reconnect_media import candidates,reconnect

ROOT=Path(__file__).resolve().parent
APP=QApplication.instance() or QApplication([])

class ReconnectTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'qa-output'); self.root=Path(self.temp.name)
        self.photos=self.root/'photos'; old=self.photos/'old'; new=self.photos/'new'
        old.mkdir(parents=True); new.mkdir()
        self.old=old/'same.jpg'; self.new=new/'same.jpg'
        Image.new('RGB',(120,80),'blue').save(self.old); shutil.copyfile(self.old,self.new)
        self.before=hashlib.sha256(self.new.read_bytes()).hexdigest()
        self.cat=Catalog(self.root/'cache'); self.cat.add_source(self.photos); Indexer(self.cat).scan()
        self.oldkey=file_key(self.old); self.newkey=file_key(self.new)
        self.cat.set_tags(self.oldkey,['Ivan','old tag']); self.cat.set_tags(self.newkey,['new tag','Ivan'])
        self.cat.set_favourite(self.oldkey,True)
        feature=np.array([1,0,0],dtype=np.float32).tobytes()
        with self.cat.connect() as db:
            for key in [self.oldkey,self.newkey]:
                face=db.execute('INSERT INTO faces(media_key,x,y,w,h,feature) VALUES(?,?,?,?,?,?)',(key,0,0,10,10,feature)).lastrowid
                if key==self.oldkey:self.oldface=face
            db.execute('UPDATE media SET embedding=?,ai_done=1 WHERE key=?',(feature,self.oldkey))
        self.cat.name_face(self.oldface,'Ivan')
        old.rename(self.root/'detached'); self.detached=self.root/'detached/same.jpg'

    def tearDown(self):
        self.assertEqual(hashlib.sha256(self.new.read_bytes()).hexdigest(),self.before)
        self.assertEqual(hashlib.sha256(self.detached.read_bytes()).hexdigest(),self.before)
        self.temp.cleanup()

    def test_reconnect_preserves_labels_faces_embeddings_and_backup(self):
        self.assertEqual([row['key'] for row in candidates(self.cat,self.oldkey)],[self.newkey])
        backup=reconnect(self.cat,self.oldkey,self.newkey)
        self.assertTrue(backup.is_file()); self.assertIsNone(self.cat.row(self.oldkey)); self.assertEqual(self.cat.count(),1)
        row=self.cat.row(self.newkey)
        self.assertEqual(set(json.loads(row['tags'])),{'Ivan','old tag','new tag'})
        self.assertTrue(row['favourite']); self.assertEqual(row['ai_done'],1)
        self.assertEqual(len(self.cat.faces(self.newkey)),1); self.assertEqual(self.cat.faces(self.newkey)[0]['name'],'Ivan')
        self.assertEqual(self.cat.person_matches('Ivan'),[self.newkey])
        backup_db=sqlite3.connect(backup)
        try:self.assertEqual(backup_db.execute('SELECT COUNT(*) FROM media').fetchone()[0],2)
        finally:backup_db.close()
        with self.cat.connect() as db:self.assertIsNotNone(db.execute('SELECT embedding FROM media WHERE key=?',(self.newkey,)).fetchone()[0])
        self.assertTrue(Path(self.cat.row(self.newkey)['thumb']).is_file())

    def test_validation_and_different_confirmed_people_do_not_lose_labels(self):
        self.cat.name_face(self.cat.faces(self.newkey)[0]['id'],'Other label')
        reconnect(self.cat,self.oldkey,self.newkey)
        self.assertEqual({face['name'] for face in self.cat.faces(self.newkey)},{'Ivan','Other label'})

    def test_connected_original_or_changed_copy_is_not_reconnected(self):
        shutil.copyfile(self.detached,self.old.parent.parent/'same.jpg')
        self.old.parent.mkdir(); shutil.copyfile(self.detached,self.old)
        with self.assertRaises(ValueError):reconnect(self.cat,self.oldkey,self.newkey)
        self.old.unlink()
        self.new.write_bytes(b'different size')
        try:
            with self.assertRaises(ValueError):reconnect(self.cat,self.oldkey,self.newkey)
            self.assertEqual(self.cat.count(),2)
        finally:shutil.copyfile(self.detached,self.new)

    def test_native_cached_preview_and_confirmed_reconnect(self):
        window=VaultWindow(self.root/'cache'); window.current=self.cat.row(self.oldkey); window.update_preview()
        with patch('desktop_app.MediaDialog') as dialog,patch('desktop_app.QMessageBox.information') as notice:
            window.open_preview(); dialog.assert_called_once(); notice.assert_not_called()
        dialog=MediaDialog(self.cat.row(self.oldkey),window)
        try:
            self.assertFalse(dialog.photo_view.image_item.pixmap().isNull())
            self.assertTrue(dialog.actions.reconnect.isEnabled())
            with patch('desktop_app.QInputDialog.getItem',return_value=(str(self.new),True)),patch('desktop_app.QMessageBox.question',return_value=QMessageBox.StandardButton.No):
                dialog.actions.reconnect.click(); self.assertIsNotNone(self.cat.row(self.oldkey))
            with patch('desktop_app.QInputDialog.getItem',return_value=(str(self.new),True)),patch('desktop_app.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):
                dialog.actions.reconnect.click()
            self.assertEqual(dialog.row['key'],self.newkey); self.assertFalse(dialog.actions.reconnect.isEnabled())
            self.assertEqual(dialog.keys,[self.newkey]); self.assertEqual(window.current['key'],self.newkey)
            self.assertEqual(self.cat.count(),1)
        finally:dialog.close(); window.close(); APP.processEvents()

if __name__=='__main__':unittest.main()
