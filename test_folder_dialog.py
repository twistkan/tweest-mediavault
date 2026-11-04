"""Native Ctrl/Shift folder selection and pasted path navigation."""
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt,QTimer,QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QTreeView,QDialog
from folder_dialog import FolderSelectionDialog
from desktop_app import VaultWindow,THEME

ROOT=Path(__file__).resolve().parent
APP=QApplication.instance() or QApplication([]); APP.setStyle('Fusion'); APP.setStyleSheet(THEME)

def wait_for(check):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        APP.processEvents()
        if check():return
        QTest.qWait(30)
    raise AssertionError('Folder picker did not become ready')

class FolderDialogTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'qa-output'); self.root=Path(self.temp.name)
        self.folders=[]
        for name in ['01 First','02 Second','03 Third','04 Fourth','05 Fifth']:
            path=self.root/name; path.mkdir(); self.folders.append(path)
        (self.root/'not a folder.jpg').write_bytes(b'file')
        self.dialog=None
    def tearDown(self):
        if self.dialog:self.dialog.reject(); self.dialog.deleteLater()
        APP.sendPostedEvents(None,QEvent.Type.DeferredDelete); APP.processEvents(); self.temp.cleanup()
    def make_dialog(self):
        self.dialog=FolderSelectionDialog(None,self.root); self.dialog.show(); APP.processEvents()
        view=self.dialog.findChild(QTreeView,'treeView')
        wait_for(lambda:view.model().rowCount(view.rootIndex())==5)
        return self.dialog,view
    def click_row(self,view,row,modifier=Qt.KeyboardModifier.NoModifier):
        index=view.model().index(row,0,view.rootIndex()); view.scrollTo(index); APP.processEvents()
        QTest.mouseClick(view.viewport(),Qt.MouseButton.LeftButton,modifier,view.visualRect(index).center())
    def test_ctrl_and_shift_click_select_multiple_folders(self):
        dialog,view=self.make_dialog()
        self.click_row(view,0); self.click_row(view,2,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(set(dialog.selected_folder_paths()),{str(self.folders[0]),str(self.folders[2])})
        self.click_row(view,1); self.click_row(view,4,Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(set(dialog.selected_folder_paths()),{str(p) for p in self.folders[1:]})
        dialog.grab().save(str(ROOT/'qa-output'/'multi-folder-picker.png'))
        dialog.accept(); self.assertEqual(set(dialog.selected_directories),{str(p) for p in self.folders[1:]})
    def test_paste_path_enter_navigates_without_accepting(self):
        dialog,view=self.make_dialog(); target=self.folders[0]
        child=target/'Child folder'; child.mkdir()
        self.click_row(view,0); self.click_row(view,2,Qt.KeyboardModifier.ControlModifier)
        APP.clipboard().setText('"'+str(target)+'"'); dialog.path_bar.setFocus()
        dialog.path_bar.selectAll(); QTest.keyClick(dialog.path_bar,Qt.Key.Key_V,Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(dialog.path_bar,Qt.Key.Key_Return); APP.processEvents()
        self.assertTrue(dialog.isVisible()); self.assertEqual(Path(dialog.directory().absolutePath()),target)
        self.assertEqual(dialog.selected_directories,[])
        dialog.accept(); self.assertEqual(dialog.selected_directories,[str(target)])
    def test_file_link_and_invalid_paths(self):
        dialog,view=self.make_dialog(); target=self.folders[1]
        dialog.path_bar.setText(target.as_uri()); dialog.go_button.click()
        self.assertEqual(Path(dialog.directory().absolutePath()),target)
        dialog.path_bar.setText('https://example.com/photos'); dialog.go_button.click()
        self.assertEqual(Path(dialog.directory().absolutePath()),target); self.assertIn('Web links',dialog.hint.text())
        dialog.path_bar.setText(str(self.root/'missing')); dialog.go_button.click()
        self.assertIn('not found',dialog.hint.text()); self.assertTrue(dialog.isVisible())
    def test_main_window_imports_selection_once_and_cancel_imports_nothing(self):
        window=VaultWindow(self.root/'cache')
        def choose():
            picker=APP.activeModalWidget()
            if not isinstance(picker,FolderSelectionDialog):return
            picker.setDirectory(str(self.root)); view=picker.findChild(QTreeView,'treeView'); APP.processEvents()
            # Select actual folders by filesystem-model indexes, independent of the cache directory's sorted row.
            view.clearSelection()
            from PySide6.QtCore import QItemSelectionModel
            for path in self.folders[:2]:
                index=view.model().index(str(path)); view.selectionModel().select(index,QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows)
            picker.accept()
        try:
            with patch.object(window,'add_paths') as add:
                QTimer.singleShot(200,choose); window.add_folder()
                self.assertEqual(add.call_count,1); self.assertEqual(set(add.call_args.args[0]),{str(p) for p in self.folders[:2]})
            with patch.object(window,'add_paths') as add:
                QTimer.singleShot(200,lambda:APP.activeModalWidget().reject()); window.add_folder(); add.assert_not_called()
        finally:window.close()

if __name__=='__main__':unittest.main()
