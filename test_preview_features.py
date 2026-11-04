"""Preview actions, persistent favourites and actual offline tagged-person search."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch
from PIL import Image
from PySide6.QtWidgets import QApplication
from vault_core import Catalog,Indexer,file_key
from media_actions import save_copy,show_in_explorer,open_in_default_app,file_share_mime,media_copy_mime
from desktop_app import VaultWindow,MediaDialog,THEME

ROOT=Path(__file__).resolve().parent
APP=QApplication.instance() or QApplication([])
APP.setStyle('Fusion'); APP.setStyleSheet(THEME)

class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'qa-output'); self.root=Path(self.temp.name)
        self.photos=self.root/'photos'; self.photos.mkdir()
        self.photo=self.photos/'Example photo with spaces.jpg'; Image.new('RGB',(120,80),'blue').save(self.photo)
        self.before=hashlib.sha256(self.photo.read_bytes()).hexdigest()
        self.catalog=Catalog(self.root/'cache'); self.catalog.add_source(self.photos); Indexer(self.catalog).scan()
        self.key=file_key(self.photo)

    def tearDown(self):
        assert self.root.resolve().is_relative_to((ROOT/'qa-output').resolve())
        self.temp.cleanup()

    def test_save_copy_preserves_bytes_and_rejects_overwrites(self):
        destination=self.root/'exported photo.jpg'; save_copy(self.photo,destination)
        self.assertEqual(hashlib.sha256(destination.read_bytes()).hexdigest(),self.before)
        with self.assertRaises(ValueError):save_copy(self.photo,self.photo)
        with self.assertRaises(FileExistsError):save_copy(self.photo,destination)
        self.assertEqual(hashlib.sha256(self.photo.read_bytes()).hexdigest(),self.before)

    def test_explorer_and_share_remain_local(self):
        with patch('media_actions.subprocess.Popen') as launch:
            show_in_explorer(self.photo)
            args=launch.call_args.args[0]
            self.assertEqual(args[1],'/select,'); self.assertEqual(args[2],str(self.photo.resolve()))
        mime=file_share_mime(self.photo)
        self.assertTrue(mime.hasUrls()); self.assertEqual(mime.urls()[0].toLocalFile(),str(self.photo.resolve()).replace('\\','/'))

    def test_default_app_uses_original_and_handles_unavailable_files(self):
        with patch('media_actions.os.startfile') as launch:
            open_in_default_app(self.photo)
            launch.assert_called_once_with(str(self.photo.resolve()))
        with patch('media_actions.os.startfile') as launch:
            with self.assertRaises(FileNotFoundError):open_in_default_app(self.root/'missing.jpg')
            launch.assert_not_called()
        window=VaultWindow(self.root/'cache'); window.select(window.model.index(0,0))
        dialog=MediaDialog(self.catalog.row(self.key),window)
        with patch('desktop_app.open_in_default_app') as launch:
            window.actions.external.click(); dialog.actions.external.click()
            self.assertEqual(launch.call_count,2)
        with patch('desktop_app.open_in_default_app',side_effect=OSError('No default application')),patch('desktop_app.QMessageBox.information') as notice:
            dialog.actions.external.click(); notice.assert_called_once()
        dialog.close(); window.close()

    def test_copy_buttons_put_photo_pixels_and_original_file_on_clipboard(self):
        window=VaultWindow(self.root/'cache'); window.select(window.model.index(0,0))
        dialog=MediaDialog(self.catalog.row(self.key),window)
        try:
            for actions in [window.actions,dialog.actions]:
                self.assertTrue(actions.copy.isEnabled()); self.assertFalse(actions.copy.icon().isNull())
                APP.clipboard().clear(); actions.copy.click(); APP.processEvents()
                mime=APP.clipboard().mimeData()
                self.assertTrue(mime.hasImage()); self.assertTrue(mime.hasUrls())
                self.assertEqual(APP.clipboard().image().size().width(),120)
                self.assertEqual(mime.urls()[0].toLocalFile(),str(self.photo.resolve()).replace('\\','/'))
                self.assertIn('copied',window.status.text())
            window.resize(1250,990); window.show(); APP.processEvents()
            window.grab().save(str(ROOT/'qa-output'/'copy-button-preview.png'))
            self.photo.unlink()
            with patch('desktop_app.QMessageBox.information') as notice:
                dialog.actions.copy.click(); notice.assert_called_once()
            self.assertTrue(APP.clipboard().mimeData().hasImage(),'Missing original must not replace clipboard')
            window.actions.set_row(None); self.assertFalse(window.actions.copy.isEnabled())
        finally:
            APP.clipboard().clear(); dialog.close(); window.close()

    def test_copy_orientation_video_and_unsupported_photo(self):
        oriented=self.photos/'oriented.jpg'
        exif=Image.Exif(); exif[274]=6
        Image.new('RGB',(40,20),'green').save(oriented,exif=exif)
        from PySide6.QtGui import QImage
        mime=media_copy_mime(oriented,'photo'); image=QImage(mime.imageData())
        self.assertEqual((image.width(),image.height()),(20,40))
        video=self.photos/'clip.mp4'; video.write_bytes(b'file clipboard fixture')
        before=video.read_bytes()
        mime=media_copy_mime(video,'video'); self.assertTrue(mime.hasUrls()); self.assertFalse(mime.hasImage())
        mime=media_copy_mime(video,'photo'); self.assertTrue(mime.hasUrls()); self.assertFalse(mime.hasImage())
        self.assertEqual(video.read_bytes(),before)
        self.assertEqual(hashlib.sha256(self.photo.read_bytes()).hexdigest(),self.before)

    def test_favourites_survive_restart_rescan_and_disconnection(self):
        self.catalog.set_favourite(self.key,True)
        self.assertTrue(Catalog(self.root/'cache').row(self.key)['favourite'])
        Indexer(self.catalog).scan(); self.assertEqual(len(self.catalog.items(favourite_only=True)),1)
        moved=self.photos.with_name('disconnected'); self.photos.rename(moved)
        Indexer(self.catalog).scan(); self.assertEqual(len(self.catalog.items(favourite_only=True)),1)
        with self.assertRaises(FileNotFoundError):file_share_mime(self.photo)
        self.catalog.set_favourite(self.key,False); self.assertFalse(self.catalog.items(favourite_only=True))
        moved.rename(self.photos)

    def test_folder_clear_retains_or_forgets_favourites_by_choice(self):
        self.catalog.set_favourite(self.key,True); self.catalog.forget(keep_labels=True)
        self.catalog.add_source(self.photos); Indexer(self.catalog).scan()
        self.assertEqual(len(self.catalog.items(favourite_only=True)),1)
        self.catalog.forget(keep_labels=False); self.catalog.add_source(self.photos); Indexer(self.catalog).scan()
        self.assertEqual(len(self.catalog.items(favourite_only=True)),0)

    def test_embedded_and_full_preview_share_favourite_state(self):
        window=VaultWindow(self.root/'cache'); window.select(window.model.index(0,0))
        dialog=MediaDialog(self.catalog.row(self.key),window)
        dialog.actions.toggle_star()
        self.assertTrue(window.actions.star.isChecked()); self.assertTrue(dialog.actions.star.isChecked())
        window.change_view('Favourites'); self.assertEqual(window.model.rowCount(),1)
        dialog.actions.toggle_star(); self.assertEqual(window.model.rowCount(),0)
        self.assertFalse(window.nav['Favourites'].icon().isNull())
        self.assertTrue(dialog.actions.explorer.isEnabled()); self.assertTrue(dialog.actions.person.isEnabled())
        dialog.close(); window.close()

    def test_old_catalog_gains_favourites_without_losing_tags(self):
        self.catalog.set_tags(self.key,['Keep me'])
        with self.catalog.connect() as db:db.execute('DROP TABLE favourites')
        upgraded=Catalog(self.root/'cache')
        self.assertEqual(len(upgraded.items(text='Keep me')),1); upgraded.set_favourite(self.key,True)
        self.assertEqual(len(upgraded.items(favourite_only=True)),1)

    def test_group_photo_requires_a_chosen_face(self):
        import numpy as np
        feature=np.ones(128,dtype=np.float32); feature/=np.linalg.norm(feature)
        with self.catalog.connect() as db:
            for x in [0,45]:db.execute('INSERT INTO faces(media_key,x,y,w,h,feature) VALUES(?,?,?,?,?,?)',(self.key,x,0,30,30,feature.tobytes()))
            db.execute('UPDATE media SET ai_done=1 WHERE key=?',(self.key,))
        window=VaultWindow(self.root/'cache')
        with patch('desktop_app.QDialog.exec',return_value=0),patch('desktop_app.QInputDialog.getText') as naming:
            window.name_person(self.key); naming.assert_not_called()
        self.assertTrue(all(face['name'] is None for face in self.catalog.faces(self.key))); window.close()

class OfflinePersonSearchTests(unittest.TestCase):
    def test_naming_one_tagged_photo_finds_an_untagged_photo_offline(self):
        fixture=ROOT/'qa-output'/'opencv-reference-face.jpg'
        self.assertTrue(fixture.exists(),'Public OpenCV face fixture must be present locally.')
        with tempfile.TemporaryDirectory(dir=ROOT/'qa-output') as directory:
            root=Path(directory); self.assertTrue(root.resolve().is_relative_to((ROOT/'qa-output').resolve()))
            photos=root/'photos'; photos.mkdir()
            first=photos/'Reference.jpg'; second=photos/'Unlabelled.jpg'; third=photos/'Other scene.jpg'
            shutil.copyfile(fixture,first); shutil.copyfile(fixture,second); Image.new('RGB',(200,200),'green').save(third)
            catalog=Catalog(root/'cache'); catalog.add_source(photos); Indexer(catalog).scan()
            key1,key2=file_key(first),file_key(second); catalog.set_tags(key1,['Ivan'])
            window=VaultWindow(root/'cache'); window.show(); window.search_timer.stop()
            calls=[]
            original_run=window.run_job
            def run(*args,**kwargs):calls.append(kwargs.get('kind')); return original_run(*args,**kwargs)
            window.run_job=run
            def wait_for(predicate,timeout=30):
                end=time.monotonic()+timeout
                while time.monotonic()<end:
                    APP.processEvents()
                    if predicate():return
                    time.sleep(.02)
                self.fail('Timed out waiting for local inference/UI completion')
            # Both the selected-photo preparation and remaining-library analysis must be offline.
            with patch('socket.create_connection',side_effect=AssertionError('No network allowed')),patch('urllib.request.urlopen',side_effect=AssertionError('No downloads allowed')),patch('desktop_app.QInputDialog.getText',return_value=('Ivan',True)),patch('desktop_app.QMessageBox.information') as notice:
                window.name_person(key1)
                wait_for(lambda:not window.working and catalog.ai_pending()==0)
                notice.assert_not_called()
                self.assertEqual(catalog.faces(key1)[0]['name'],'Ivan')
                self.assertEqual(json.loads(catalog.row(key2)['tags']),[])
                self.assertIsNone(catalog.faces(key2)[0]['name'])
                window.search.setText('Ivan'); window.search_timer.stop(); window.refresh()
                wait_for(lambda:len(window.model.rows)==2 and not window.people_worker.is_alive())
                found={row['key']:row for row in window.model.rows}
                self.assertEqual(set(found),{key1,key2}); self.assertTrue(found[key2]['_possible'])
                generation=window.search_generation; end=time.monotonic()+1.5
                while time.monotonic()<end:APP.processEvents(); time.sleep(.02)
                self.assertEqual(window.search_generation,generation,'Search must not rerun itself forever')
                # Person lookup must remain usable while the main AI job is busy/paused.
                window.working=True; window.job_kind='ai'; window.model.replace([]); window.refresh()
                wait_for(lambda:len(window.model.rows)==2 and not window.people_worker.is_alive())
                self.assertTrue(window.working); window.working=False; window.job_kind=''
                catalog.set_favourite(key2,True); window.change_view('Favourites'); window.search_timer.stop()
                wait_for(lambda:len(window.model.rows)==1 and not window.people_worker.is_alive())
                self.assertEqual([r['key'] for r in window.model.rows],[key2])
                window.resize(1250,990); APP.processEvents(); window.grab().save(str(ROOT/'qa-output'/'preview-features.png'))
            window.close(); APP.processEvents()

if __name__=='__main__':
    (ROOT/'qa-output').mkdir(exist_ok=True)
    unittest.main()
