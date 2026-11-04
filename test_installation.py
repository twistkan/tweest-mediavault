"""Protected-path behavior is simulated; tests never write to Program Files or show UAC."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from PIL import Image
from PySide6.QtWidgets import QApplication
from setup_app import Installer,install
from install_paths import installation_folder,is_protected_folder,request_elevation
from storage_paths import data_folder,migrate_legacy_data
from vault_core import Catalog,Indexer
from desktop_app import VaultWindow

ROOT=Path(__file__).resolve().parent
APP=QApplication.instance() or QApplication([])

class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'qa-output'); self.root=Path(self.temp.name)
        self.payload=self.root/'payload.zip'
        with zipfile.ZipFile(self.payload,'w') as archive:
            archive.writestr('TweestMediaVault.exe',b'test payload')
            archive.writestr('README.md','test documentation')
    def tearDown(self):
        assert self.root.resolve().is_relative_to((ROOT/'qa-output').resolve())
        self.temp.cleanup()

    def test_parent_always_uses_dedicated_folder(self):
        parent=self.root/'Program Files (x86)'; parent.mkdir()
        target=install(self.payload,parent)
        self.assertEqual(target,parent/'TweestMediaVault'/'TweestMediaVault.exe')
        self.assertFalse((parent/'README.md').exists())
        self.assertTrue((target.parent/'README.md').is_file())
        self.assertEqual(installation_folder(target.parent),target.parent)

    def test_protected_root_requests_elevation_before_writes(self):
        target=self.root/'Program Files (x86)'
        options=argparse.Namespace(target=str(target),shortcut_path=str(self.root/'desktop.lnk'),no_shortcut=False,elevated_auto_install=False)
        window=Installer(options)
        with patch('setup_app.is_protected_folder',return_value=True),patch('setup_app.is_administrator',return_value=False),patch('setup_app.request_elevation') as elevation,patch('setup_app.install') as extraction:
            window.start()
            elevation.assert_called_once_with(target/'TweestMediaVault',self.root/'desktop.lnk')
            extraction.assert_not_called()
        self.assertFalse(target.exists()); window.close()

    def test_cancelled_elevation_keeps_setup_available(self):
        window=Installer()
        window.path.setText(str(self.root/'Program Files'))
        with patch('setup_app.is_protected_folder',return_value=True),patch('setup_app.is_administrator',return_value=False),patch('setup_app.desktop_path',return_value=self.root),patch('setup_app.request_elevation',side_effect=PermissionError('Administrator approval was cancelled.')):
            window.start()
        self.assertIn('cancelled',window.status.text()); self.assertTrue(window.action.isEnabled()); window.close()

    def test_elevation_quotes_spaces_and_uses_runas(self):
        with patch('install_paths.ctypes.windll.shell32.ShellExecuteW',return_value=42) as shell:
            request_elevation(self.root/'Program Files'/'TweestMediaVault',self.root/'Desktop Folder'/'MediaVault.lnk')
            args=shell.call_args.args
            self.assertEqual(args[1],'runas'); self.assertIn('--elevated-auto-install',args[3]); self.assertIn('"',args[3])
        with patch('install_paths.ctypes.windll.shell32.ShellExecuteW',return_value=5):
            with self.assertRaises(PermissionError): request_elevation(self.root,None)

    def test_permission_failure_writes_nothing(self):
        target=self.root/'Denied'
        with patch('setup_app.check_writable',side_effect=PermissionError('Denied')):
            with self.assertRaises(PermissionError):install(self.payload,target)
        self.assertFalse(target.exists())

    def test_unsafe_archive_rejected_before_extraction(self):
        with zipfile.ZipFile(self.payload,'a') as archive:archive.writestr('../escape.txt','unsafe')
        with self.assertRaises(ValueError):install(self.payload,self.root/'Parent')
        self.assertFalse((self.root/'Parent').exists())

    def test_cache_profile_path_and_migration_preserve_original(self):
        old_app=self.root/'Old app'; old=Catalog(old_app/'data')
        photos=self.root/'photos'; photos.mkdir(); Image.new('RGB',(50,50),'green').save(photos/'Ivan.jpg')
        old.add_source(photos); Indexer(old).scan(); row=old.items()[0]; old.set_tags(row['key'],['Ivan'])
        with patch.dict(os.environ,{'LOCALAPPDATA':str(self.root/'User profile')}):
            os.environ.pop('TWEEST_DATA',None)
            new=data_folder(old_app,installed=True)
        self.assertFalse(new.is_relative_to(old_app)); self.assertTrue(migrate_legacy_data(old_app,new))
        moved=Catalog(new).items(text='Ivan')[0]
        self.assertEqual(Path(moved['thumb']).parent,new/'thumbnails'); self.assertTrue(Path(moved['thumb']).exists())
        self.assertTrue((old_app/'data'/'library.sqlite3').exists())
        self.assertEqual(old.count(),1); self.assertEqual(len(old.items(text='Ivan')),1)
        self.assertFalse(migrate_legacy_data(old_app,new))

    def test_native_menu_icons_all_present(self):
        window=VaultWindow(self.root/'native-cache')
        for name,control in window.nav.items():
            self.assertFalse(control.icon().isNull(),name)
        window.change_view('People'); self.assertTrue(window.nav['People'].isChecked()); window.close()

if __name__=='__main__':
    (ROOT/'qa-output').mkdir(exist_ok=True)
    unittest.main()
