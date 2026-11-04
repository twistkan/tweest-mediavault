"""Month browsing and cached-catalog upgrades with generated media only."""
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from PySide6.QtWidgets import QApplication
from vault_core import Catalog,Indexer,file_key,folder_month
from desktop_app import VaultWindow,THEME

ROOT=Path(__file__).resolve().parent
APP=QApplication.instance() or QApplication([])
APP.setStyle('Fusion'); APP.setStyleSheet(THEME)

class MonthFilterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'qa-output'); self.root=Path(self.temp.name)
        self.photos=self.root/'photos'; self.paths=[]
        for year,month in [('2005','January'),('2005','03 March'),('2005','12'),('2006','March')]:
            path=self.photos/year/month/'Ivan.jpg'; path.parent.mkdir(parents=True)
            Image.new('RGB',(80,60),'blue').save(path); self.paths.append(path)
        self.cat=Catalog(self.root/'cache'); self.cat.add_source(self.photos); Indexer(self.cat).scan()

    def tearDown(self):self.temp.cleanup()

    def test_folder_names_and_date_fallback(self):
        for name,month in [('Jan','01'),('02 February','02'),('12 December 2005','12'),('2005-09','09')]:
            self.assertEqual(folder_month(self.photos/'2005'/name/'photo.jpg'),month)
        self.assertEqual(folder_month(self.photos/'2005'/'03'/'photo.jpg'),'03')
        self.assertEqual(folder_month(self.photos/'holiday'/'03'/'photo.jpg'),'')
        self.assertEqual(folder_month(self.photos/'2005'/'January.jpg'),'')
        self.assertEqual(len(self.cat.items(year='2005',month='03')),1)
        self.assertEqual(self.cat.row(file_key(self.paths[1]))['date'],'2005-03-01')
        self.assertEqual(len(self.cat.items(year='2005',month='12')),1)
        self.assertEqual(len(self.cat.items(month='03')),2)
        self.assertEqual(len(self.cat.items(year='2005',month='02')),0)
        with self.cat.connect() as db:
            db.execute("UPDATE media SET folder_month='',date='2005-07-04' WHERE key=?",(file_key(self.paths[0]),))
        self.assertEqual(len(self.cat.items(year='2005',month='07')),1)

    def test_month_combines_with_other_filters(self):
        key=file_key(self.paths[1]); self.cat.set_favourite(key,True); self.cat.set_tags(key,['Birthday'])
        self.assertEqual(len(self.cat.items(year='2005',month='03',text='Birthday',favourite_only=True)),1)
        self.assertFalse(self.cat.people_search('Birthday',year='2005',month='12'))
        with self.cat.connect() as db:db.execute("UPDATE media SET kind='video' WHERE key=?",(key,))
        self.assertEqual(len(self.cat.items(year='2005',month='03',kind='video')),1)
        self.assertFalse(self.cat.items(year='2005',month='03',kind='photo'))

    def test_legacy_upgrade_preserves_cached_analysis(self):
        key=file_key(self.paths[1]); self.cat.set_tags(key,['Keep']); self.cat.set_favourite(key,True)
        thumbnail=Path(self.cat.row(key)['thumb']); stamp=thumbnail.stat().st_mtime_ns
        with self.cat.connect() as db:
            db.execute('UPDATE media SET embedding=?,ai_done=1 WHERE key=?',(b'keep embedding',key))
            person=db.execute('INSERT INTO people(name,feature) VALUES(?,?)',('Ivan',b'keep person')).lastrowid
            db.execute('INSERT INTO faces(media_key,person,feature,confirmed) VALUES(?,?,?,1)',(key,person,b'keep face'))
            db.execute('ALTER TABLE media DROP COLUMN folder_month')
        upgraded=Catalog(self.root/'cache')
        row=upgraded.items(year='2005',month='03',text='Ivan',favourite_only=True)[0]
        self.assertEqual(row['ai_done'],1); self.assertIn('Keep',row['tags'])
        self.assertEqual(upgraded.row(key)['embedding'],b'keep embedding')
        self.assertEqual(upgraded.faces(key)[0]['feature'],b'keep face')
        Indexer(upgraded).scan()
        self.assertEqual(thumbnail.stat().st_mtime_ns,stamp)
        self.assertEqual(upgraded.row(key)['ai_done'],1)

    def test_native_selection_and_restart(self):
        window=VaultWindow(self.root/'cache')
        window.year.setCurrentIndex(window.year.findData('2005'))
        window.month.setCurrentIndex(window.month.findData('03'))
        self.assertEqual(window.model.rowCount(),1)
        self.assertEqual(window.month.count(),13)
        window.resize(1250,900); window.show(); APP.processEvents()
        window.grab().save(str(ROOT/'qa-output'/'month-filter.png')); window.close()
        reopened=VaultWindow(self.root/'cache')
        try:
            self.assertEqual(reopened.month.currentData(),'03'); self.assertEqual(reopened.year.currentData(),'2005')
            self.assertEqual(reopened.model.rowCount(),1)
            reopened.month.setCurrentIndex(0); self.assertEqual(reopened.model.rowCount(),3)
        finally:reopened.close()

if __name__=='__main__':unittest.main()
