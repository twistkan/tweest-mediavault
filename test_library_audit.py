"""Folder-year recovery, rescan notices and verified duplicate handling."""
from pathlib import Path
import json
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
from PIL import Image
from PySide6.QtWidgets import QApplication,QMessageBox
from vault_core import Catalog,Indexer,file_key
from library_audit import audit_library,prepare_imports
from desktop_app import VaultWindow,THEME

ROOT=Path(__file__).resolve().parent
APP=QApplication.instance() or QApplication([]); APP.setStyle('Fusion'); APP.setStyleSheet(THEME)

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'qa-output'); self.root=Path(self.temp.name)
        self.photos=self.root/'Phone Pix 2026'; self.photo=self.photos/'01 January 2026'/'photo.jpg'
        self.photo.parent.mkdir(parents=True); Image.new('RGB',(80,60),'red').save(self.photo)
        self.cat=Catalog(self.root/'cache'); self.cat.add_source(self.photos)

    def tearDown(self):self.temp.cleanup()

    def test_missing_changed_and_disconnected_are_distinct(self):
        report=audit_library(self.cat); self.assertEqual(report['missing'],1)
        Indexer(self.cat).scan(); self.assertEqual(audit_library(self.cat)['missing'],0)
        Image.new('RGB',(120,80),'blue').save(self.photo)
        self.assertEqual(audit_library(self.cat)['changed'],1)
        self.photos.rename(self.root/'disconnected')
        report=audit_library(self.cat); self.assertEqual(report['missing'],0); self.assertTrue(report['issues'])
        self.assertEqual(self.cat.count(),1)

    def test_old_catalog_uses_folder_year_without_face_rescan(self):
        Indexer(self.cat).scan(); key=file_key(self.photo)
        self.cat.set_tags(key,['Ivan']); self.cat.set_favourite(key,True)
        with self.cat.connect() as db:
            db.execute("UPDATE media SET date='2024-02-08',ai_done=1,embedding=? WHERE key=?",(b'keep',key))
            db.execute('ALTER TABLE media DROP COLUMN folder_year')
        upgraded=Catalog(self.root/'cache')
        self.assertEqual(len(upgraded.items(year='2026',month='01')),1)
        self.assertFalse(upgraded.items(year='2024',month='01'))
        self.assertEqual(upgraded.row(key)['embedding'],b'keep'); self.assertEqual(upgraded.row(key)['date'],'2024-02-08')
        self.assertTrue(upgraded.row(key)['favourite'])

    def test_unchanged_paths_are_skipped_but_new_files_are_scanned(self):
        Indexer(self.cat).scan()
        result=prepare_imports(self.cat,[self.photos,self.photos])
        self.assertFalse(result['accepted']); self.assertEqual(len(result['skipped']),2)
        Image.new('RGB',(80,60),'blue').save(self.photo.with_name('new.jpg'))
        self.assertEqual(prepare_imports(self.cat,[self.photos])['accepted'],[str(self.photos)])
        logs=[json.loads(line) for line in (self.cat.home/'library-log.jsonl').read_text().splitlines()]
        self.assertTrue(any(r['event']=='duplicate_folder_skipped' for r in logs))

    def test_copied_folder_requires_verified_identical_content(self):
        Indexer(self.cat).scan(); copied=self.root/'Copied folder'; shutil.copytree(self.photos,copied)
        result=prepare_imports(self.cat,[copied]); self.assertFalse(result['accepted'])
        self.assertEqual(result['skipped'][0]['matches'],str(self.photos))
        other=copied/'01 January 2026'/'photo.jpg'; data=bytearray(other.read_bytes()); data[-1]^=1; other.write_bytes(data)
        self.assertEqual(prepare_imports(self.cat,[copied])['accepted'],[str(copied)])

    def test_copies_in_one_addition_are_only_indexed_once(self):
        copied=self.root/'Copied folder'; shutil.copytree(self.photos,copied)
        result=prepare_imports(self.cat,[self.photos,copied])
        self.assertEqual(result['accepted'],[str(self.photos)]); self.assertEqual(len(result['skipped']),1)

    def test_popup_offers_targeted_rescan_and_banner_survives_decline(self):
        window=VaultWindow(self.root/'cache'); window.show(); APP.processEvents()
        report=audit_library(self.cat)
        try:
            with patch('desktop_app.QMessageBox.question',return_value=QMessageBox.StandardButton.No) as notice:
                window.on_audit_result((report,True,None)); notice.assert_called_once()
            self.assertFalse(window.audit_banner.isHidden())
            with patch.object(window,'start_scan') as scan:
                with patch('desktop_app.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):window.on_audit_result((report,True,None))
                scan.assert_called_once_with(report['paths'])
            window.grab().save(str(ROOT/'qa-output'/'rescan-notice.png'))
        finally:window.close()

    def test_rescan_request_waits_for_safe_ai_checkpoint(self):
        window=VaultWindow(self.root/'cache'); window.audit_report=audit_library(self.cat)
        try:
            window.working=True; window.job_kind='ai'; window.indexer=Indexer(window.catalog)
            window.indexer.pause.set(); window.rescan_missing()
            self.assertEqual(window.rescan_pending,window.audit_report['paths'])
            self.assertTrue(window.indexer.stop.is_set()); self.assertFalse(window.indexer.pause.is_set())
            with patch.object(window,'start_scan') as scan:
                window.on_result(None); scan.assert_called_once()
        finally:window.close()

if __name__=='__main__':unittest.main()
