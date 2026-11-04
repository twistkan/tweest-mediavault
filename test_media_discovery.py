"""Missing-media discovery and browsing regression tests with generated data."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QSignalSpy
from PySide6.QtTest import QTest
import time
from vault_core import Catalog,Indexer,file_key
from desktop_app import VaultWindow,LibraryModel,THEME

ROOT=Path(__file__).resolve().parent
APP=QApplication.instance() or QApplication([]); APP.setStyle('Fusion'); APP.setStyleSheet(THEME)

class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'qa-output'); self.root=Path(self.temp.name)
        self.photos=self.root/'photos'; self.old=self.photos/'Phone Pix 2024'/'old.jpg'
        self.target=self.photos/'Phone Pix 2026'; self.new=self.target/'01 January 2026'/'new.jpg'
        for path in [self.old,self.new]:
            path.parent.mkdir(parents=True,exist_ok=True); Image.new('RGB',(80,60),'red').save(path)
        self.cat=Catalog(self.root/'cache'); self.cat.add_source(self.photos)

    def tearDown(self):self.temp.cleanup()

    def test_targeted_scan_reaches_child_without_parent_rescan(self):
        import vault_core
        original=vault_core.make_thumbnail
        visited=[]
        def thumbnail(path,*args):visited.append(path); return original(path,*args)
        with patch('vault_core.make_thumbnail',side_effect=thumbnail):Indexer(self.cat).scan([self.target])
        self.assertEqual(visited,[self.new]); self.assertEqual(self.cat.count(),1)
        self.assertEqual(self.cat.row(file_key(self.new))['source'],self.cat.sources()[0]['id'])
        key=file_key(self.new); self.cat.set_tags(key,['Keep']); self.cat.set_favourite(key,True)
        with self.cat.connect() as db:db.execute('UPDATE media SET ai_done=1,embedding=? WHERE key=?',(b'cached',key))
        stamp=Path(self.cat.row(key)['thumb']).stat().st_mtime_ns
        Indexer(self.cat).scan([self.target,self.target/'01 January 2026'])
        self.assertEqual(self.cat.count(),1); self.assertEqual(self.cat.row(key)['embedding'],b'cached')
        self.assertEqual(Path(self.cat.row(key)['thumb']).stat().st_mtime_ns,stamp)
        with self.assertRaises(ValueError):Indexer(self.cat).scan([self.root])

    def test_readding_child_starts_targeted_scan_and_clears_filters(self):
        Indexer(self.cat).scan()
        with self.cat.connect() as db:db.execute('DELETE FROM media WHERE key=?',(file_key(self.new),))
        window=VaultWindow(self.root/'cache')
        try:
            window.change_view('Videos'); window.month.setCurrentIndex(3); window.search.setText('hidden')
            with patch.object(window,'start_scan') as scan,patch('desktop_app.QMessageBox.information') as notice:
                window.add_paths([str(self.target)])
                deadline=time.monotonic()+10
                while window.working and time.monotonic()<deadline:APP.processEvents(); QTest.qWait(20)
                scan.assert_called_once_with([str(self.target.resolve())]); notice.assert_not_called()
            self.assertEqual(len(window.catalog.sources()),1); self.assertEqual(window.view,'Library')
            self.assertEqual(window.month.currentData(),''); self.assertEqual(window.search.text(),'')
            self.assertEqual(window.model.rowCount(),1)
        finally:window.close()

    def test_pagination_reports_all_matching_and_appends_without_reset(self):
        Indexer(self.cat).scan()
        with self.cat.connect() as db:
            source=self.cat.sources()[0]['id']
            db.executemany('INSERT INTO media(key,source,path,name,kind,size,mtime,date) VALUES(?,?,?,?,?,?,?,?)',
                [(f'generated-{i}',source,str(self.target/f'{i}.jpg'),f'photo {i}','photo',1,1,'2026-01-01') for i in range(1100)])
        window=VaultWindow(self.root/'cache')
        try:
            window.reset_filters(); self.assertEqual(window.model.rowCount(),500)
            self.assertIn('500 of 1,102 matching',window.count_label.text()); self.assertFalse(window.more.isHidden())
            resets=QSignalSpy(window.model.modelReset)
            window.load_more(); self.assertEqual(window.model.rowCount(),1000); self.assertEqual(resets.count(),0)
            window.load_more(); self.assertEqual(window.model.rowCount(),1102); self.assertTrue(window.more.isHidden())
            self.assertEqual(window.catalog.items(kind='video',count_only=True),0)
            window.resize(1250,900); window.show(); APP.processEvents()
            window.grab().save(str(ROOT/'qa-output'/'media-discovery.png'))
        finally:window.close()

if __name__=='__main__':unittest.main()
