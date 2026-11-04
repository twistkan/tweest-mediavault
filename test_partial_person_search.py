"""Partial saved names must include the same offline face matches as full names."""
import hashlib
from pathlib import Path
import tempfile
import time
import unittest
import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication
from vault_core import Catalog,Indexer,file_key
from desktop_app import VaultWindow

ROOT=Path(__file__).resolve().parent
APP=QApplication.instance() or QApplication([])

class PartialPersonTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'qa-output'); self.root=Path(self.temp.name)
        self.photos=self.root/'photos'/'2025'; self.photos.mkdir(parents=True)
        for name in ['named','similar','second','second-similar','unrelated','tags']:
            Image.new('RGB',(60,40),'blue').save(self.photos/(name+'.jpg'))
        self.hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.photos.iterdir()}
        self.cat=Catalog(self.root/'cache'); self.cat.add_source(self.photos); Indexer(self.cat).scan()
        self.keys={p.stem:file_key(p) for p in self.photos.iterdir()}
        with self.cat.connect() as db:
            for name,vector in [('named',[1,0,0]),('similar',[1,0,0]),('second',[0,1,0]),('second-similar',[0,1,0]),('unrelated',[0,0,1])]:
                feature=np.array(vector,dtype=np.float32).tobytes()
                face=db.execute('INSERT INTO faces(media_key,x,y,w,h,feature) VALUES(?,?,?,?,?,?)',(self.keys[name],0,0,10,10,feature)).lastrowid
                if name=='named':self.first_face=face
                if name=='second':self.second_face=face
            db.execute('UPDATE media SET ai_done=1')
        self.cat.name_face(self.first_face,'Daphine Aine'); self.cat.name_face(self.second_face,'Peter Aine')
        self.cat.set_tags(self.keys['tags'],['Daphine Aine'])

    def tearDown(self):
        self.assertTrue(all(hashlib.sha256(p.read_bytes()).hexdigest()==value for p,value in self.hashes.items()))
        self.temp.cleanup()

    def test_first_last_full_and_case_names_find_cached_matches(self):
        expected={self.keys[name] for name in ['named','similar','tags']}
        for query in ['Daphine Aine','Daphine',' dApHiNe ']:
            rows=self.cat.people_search(query)
            self.assertEqual({row['key'] for row in rows},expected)
            self.assertTrue(next(row for row in rows if row['key']==self.keys['similar'])['_possible'])
            self.assertFalse(next(row for row in rows if row['key']==self.keys['named'])['_possible'])
        rows=Catalog(self.root/'cache').people_search('Aine')
        self.assertEqual({row['key'] for row in rows},{self.keys[name] for name in ['named','similar','tags','second','second-similar']})
        self.assertEqual(self.cat.faces(self.keys['similar'])[0]['name'],None)

    def test_literal_wildcards_empty_names_and_filters(self):
        for query in ['',' ','%','_','\\','Unknown']:
            self.assertFalse(self.cat.has_named_person(query)); self.assertEqual(self.cat.person_matches(query),[])
        self.assertTrue(self.cat.has_named_person('Aine'))
        self.assertFalse(self.cat.people_search('Daphine',year='2024'))
        self.assertEqual(len(self.cat.people_search('Daphine',year='2025')),3)
        self.cat.set_favourite(self.keys['similar'],True)
        self.assertEqual([row['key'] for row in self.cat.people_search('Daphine',favourite_only=True)],[self.keys['similar']])
        self.cat.name_face(self.second_face,'Test_% Name')
        self.assertTrue(self.cat.has_named_person('_%'))
        self.assertEqual(set(self.cat.person_matches('_%')),{self.keys['second'],self.keys['second-similar']})

    def test_native_search_and_preview_keep_partial_face_results(self):
        window=VaultWindow(self.root/'cache')
        try:
            for mode,query in [(0,'Daphine'),(0,'Aine'),(1,'Daphine')]:
                window.mode.setCurrentIndex(mode); window.search.setText(query)
                window.search_timer.stop(); window.refresh()
                end=time.monotonic()+10
                while time.monotonic()<end:
                    APP.processEvents()
                    worker=window.people_worker
                    if worker and not worker.is_alive() and len(window.model.rows)==(5 if query=='Aine' else 3):break
                    time.sleep(.02)
                else:self.fail('Partial person search did not complete in the native UI')
                self.assertIn(self.keys['similar'],{row['key'] for row in window.model.rows})
                self.assertEqual(window.preview_sequence(),window.model.rows)
        finally:
            window.close(); APP.processEvents()

if __name__=='__main__':unittest.main()
