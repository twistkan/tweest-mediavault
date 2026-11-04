"""Editor geometry, lighting, safe exports and native workflows on generated photos."""
from pathlib import Path
from dataclasses import replace
import hashlib
import tempfile
import time
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from PySide6.QtCore import Qt,QPoint,QRectF,QTimer,QEvent,QStandardPaths
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox,QFileDialog,QLineEdit
from edit_core import EditState,EditHistory,load_photo,render,export_copy
from photo_editor import PhotoEditor
from desktop_app import THEME,VaultWindow,MediaDialog
from vault_core import Catalog,Indexer,file_key
from save_dialog import SaveLocationDialog

ROOT=Path(__file__).resolve().parent
APP=QApplication.instance() or QApplication([]); APP.setStyle('Fusion'); APP.setStyleSheet(THEME)

def wait_for(check):
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        APP.processEvents()
        if check():return
        QTest.qWait(30)
    raise AssertionError('Editor operation did not finish')

class EditorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'qa-output'); self.root=Path(self.temp.name)
        self.path=self.root/'sample photo.png'
        pixels=np.zeros((600,900,4),dtype=np.uint8); pixels[:,:,:3]=np.arange(900,dtype=np.uint32)[None,:,None]*255//899; pixels[:,:,3]=255
        Image.fromarray(pixels).save(self.path); self.image=load_photo(self.path)
        self.before=hashlib.sha256(self.path.read_bytes()).hexdigest(); self.stamp=self.path.stat().st_mtime_ns
        self.editor=None
    def tearDown(self):
        if self.editor:
            with patch('photo_editor.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes):self.editor.close()
            self.editor.deleteLater(); APP.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            APP.processEvents()
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),self.before); self.assertEqual(self.path.stat().st_mtime_ns,self.stamp)
        self.image.close(); self.temp.cleanup()
    def test_rotation_flips_crop_and_straighten(self):
        self.assertEqual(render(self.image,EditState(turns=1)).size,(600,900))
        flipped=render(self.image,EditState(flip_x=True)); self.assertEqual(flipped.getpixel((0,0)),self.image.getpixel((899,0)))
        rotated=render(self.image,EditState(turns=4)); self.assertEqual(rotated.tobytes(),self.image.tobytes())
        self.assertEqual(render(self.image,EditState(crop=(.25,.25,.75,.75))).size,(450,300))
        straight=render(self.image,EditState(straighten=10))
        self.assertLess(straight.width,self.image.width); self.assertGreaterEqual(straight.getchannel('A').getextrema()[0],250)
    def test_tones_adjust_distinct_regions_and_neutral_is_exact(self):
        self.assertEqual(render(self.image,EditState()).tobytes(),self.image.tobytes())
        bright=np.asarray(render(self.image,EditState(exposure=1)))[:,:,:3].mean()
        self.assertGreater(bright,np.asarray(self.image)[:,:,:3].mean())
        base=np.asarray(self.image)[:,:,:3].astype(float)
        shadows=np.asarray(render(self.image,EditState(shadows=70)))[:,:,:3].astype(float)-base
        highlights=np.asarray(render(self.image,EditState(highlights=-70)))[:,:,:3].astype(float)-base
        self.assertGreater(shadows[:,:200].mean(),shadows[:,700:].mean())
        self.assertLess(highlights[:,700:].mean(),highlights[:,:200].mean())
        for key in ['brightness','contrast']:
            self.assertNotEqual(render(self.image,replace(EditState(),**{key:50})).tobytes(),self.image.tobytes())
    def test_export_rejects_original_existing_and_aliases(self):
        with self.assertRaises(ValueError):export_copy(self.path,self.image,EditState(),self.path)
        target=self.root/'edited.jpg'; export_copy(self.path,self.image,EditState(brightness=40),target)
        with self.assertRaises(FileExistsError):export_copy(self.path,self.image,EditState(),target)
        with self.assertRaises(ValueError):export_copy(self.path,self.image,EditState(),self.root/'bad.gif')
        self.assertGreater(Image.open(target).getpixel((450,300))[0],self.image.getpixel((450,300))[0])
    def test_png_transparency_and_metadata_are_safe(self):
        image=self.image.copy(); image.putalpha(120); exif=Image.Exif(); exif[270]='private metadata'; image.info['exif']=exif.tobytes()
        output=self.root/'transparent.png'; export_copy(self.path,image,EditState(),output)
        with Image.open(output) as saved:
            self.assertEqual(saved.getchannel('A').getextrema(),(120,120)); self.assertFalse(saved.getexif())
        jpg=self.root/'flattened.jpg'; export_copy(self.path,image,EditState(),jpg)
        with Image.open(jpg) as saved:self.assertEqual(saved.mode,'RGB')
    def test_exif_orientation_is_applied_once(self):
        oriented=self.root/'oriented.jpg'; exif=Image.Exif(); exif[274]=6
        Image.new('RGB',(90,50),'red').save(oriented,exif=exif)
        image=load_photo(oriented); self.assertEqual(image.size,(50,90))
        out=self.root/'orientation-export.jpg'; export_copy(oriented,image,EditState(),out)
        with Image.open(out) as saved:self.assertEqual(saved.size,(50,90)); self.assertNotIn(274,saved.getexif())
    def test_history_branches_and_reset_is_undoable(self):
        history=EditHistory(); state=replace(history.current,exposure=1); history.push(state)
        history.push(replace(state,flip_x=True)); self.assertEqual(history.undo(),state)
        history.push(EditState()); self.assertEqual(history.undo(),state)
        self.assertEqual(history.redo(),EditState())
    def make_editor(self):
        self.editor=PhotoEditor(self.path,self.root/'cache'); self.editor.show()
        wait_for(lambda:not self.editor.canvas.image_item.pixmap().isNull()); return self.editor
    def test_native_crop_controls_compare_undo_and_save(self):
        editor=self.make_editor(); editor.aspect.setCurrentIndex(2); editor.begin_crop()
        wait_for(lambda:editor.apply_crop_button.isEnabled() and not editor.crop_initialise)
        box=editor.canvas.selection; self.assertAlmostEqual(box.width()/box.height(),1,places=4)
        editor.apply_crop(); self.assertNotEqual(editor.state.crop,(0.,0.,1.,1.))
        editor.sliders['brightness'].setValue(35); state=editor.state
        editor.undo(); self.assertEqual(editor.state.brightness,0); editor.redo(); self.assertEqual(editor.state,state)
        editor.compare(True); self.assertTrue(editor.comparing); editor.compare(False)
        target=self.root/'native-edit.jpg'; editor.export_to(target)
        wait_for(lambda:target.exists() and not editor.export_worker.is_alive() and editor.save_button.isEnabled())
        with Image.open(target) as saved:self.assertEqual(saved.width,saved.height)
        self.assertEqual(editor.saved_state,state)
        editor.grab().save(str(ROOT/'qa-output'/'photo-editor.png'))
    def test_share_exports_edited_file_and_unsaved_escape_warns(self):
        editor=self.make_editor(); editor.sliders['contrast'].setValue(30)
        with patch('photo_editor.QFileDialog.getSaveFileName',return_value=(str(self.root/'chosen-share.jpg'),'JPEG (*.jpg *.jpeg)')):editor.share_copy()
        wait_for(lambda:editor.export_worker is not None and not editor.export_worker.is_alive() and editor.save_button.isEnabled())
        mime=APP.clipboard().mimeData(); target=Path(mime.urls()[0].toLocalFile()); self.assertNotEqual(target,self.path)
        self.assertTrue(target.is_file()); self.assertIn('Nothing was sent',editor.status.text())
        editor.sliders['exposure'].setValue(5)
        with patch('photo_editor.QMessageBox.question',return_value=QMessageBox.StandardButton.No) as notice:
            editor.reject(); notice.assert_called_once(); self.assertTrue(editor.isVisible())
    def test_slider_gesture_is_one_undo_step(self):
        editor=self.make_editor(); slider=editor.sliders['brightness']; before=editor.history.index
        slider.setSliderDown(True)
        for value in range(1,20):slider.setValue(value)
        slider.setSliderDown(False)
        self.assertEqual(editor.history.index,before+1); editor.undo(); self.assertEqual(editor.state.brightness,0)
    def test_drag_crop_trims_the_selected_rectangle(self):
        editor=self.make_editor(); editor.begin_crop()
        wait_for(lambda:editor.apply_crop_button.isEnabled() and not editor.crop_initialise)
        canvas=editor.canvas; start=canvas.mapFromScene(100,100); end=canvas.mapFromScene(700,500)
        QTest.mousePress(canvas.viewport(),Qt.MouseButton.LeftButton,pos=start)
        QTest.mouseMove(canvas.viewport(),end); QTest.mouseRelease(canvas.viewport(),Qt.MouseButton.LeftButton,pos=end)
        editor.apply_crop()
        output=render(self.image,editor.state)
        self.assertAlmostEqual(output.width,600,delta=2); self.assertAlmostEqual(output.height,400,delta=2)
    def test_preview_entry_points_keep_catalog_labels(self):
        catalog=Catalog(self.root/'cache'); catalog.add_source(self.root); Indexer(catalog).scan()
        key=file_key(self.path); catalog.set_tags(key,['Ivan']); catalog.set_favourite(key,True)
        window=VaultWindow(self.root/'cache'); window.select(window.model.index(0,0)); dialog=MediaDialog(catalog.row(key),window)
        try:
            self.assertTrue(window.edit_button.isEnabled()); self.assertTrue(dialog.edit_button.isEnabled())
            with patch('desktop_app.open_photo_editor') as open_editor:
                dialog.edit_button.click(); window.edit_button.click(); self.assertEqual(open_editor.call_count,2)
            self.assertTrue(catalog.row(key)['favourite']); self.assertIn('Ivan',catalog.row(key)['tags'])
        finally:dialog.close(); window.close()

    def test_actual_save_button_and_file_dialog(self):
        editor=self.make_editor(); editor.sliders['brightness'].setValue(25)
        target=self.root/'clicked-save.jpg'; seen=[]
        def choose():
            dialog=APP.activeModalWidget()
            if isinstance(dialog,QFileDialog):
                dialog.findChild(QLineEdit,'fileNameEdit').setText(str(target)); seen.append(dialog.selectedFiles()); dialog.accept()
        QTimer.singleShot(200,choose)
        editor.save_button.click()
        self.assertTrue(seen,'Save button did not open a file dialog')
        try:wait_for(lambda:target.exists() and editor.export_worker is not None and not editor.export_worker.is_alive())
        except AssertionError:raise AssertionError(f'Save result: {editor.status.text()}; selected: {seen}; files: {list(self.root.glob("*"))}')

    def test_save_button_with_pending_crop(self):
        editor=self.make_editor(); editor.aspect.setCurrentIndex(2); editor.begin_crop()
        wait_for(lambda:editor.apply_crop_button.isEnabled() and not editor.crop_initialise)
        target=self.root/'clicked-crop.jpg'
        with patch('photo_editor.QFileDialog.getSaveFileName',return_value=(str(target),'JPEG (*.jpg *.jpeg)')):
            editor.save_button.click()
        self.assertIsNotNone(editor.export_worker,'Save silently refused the visible pending crop')
        wait_for(lambda:target.exists() and not editor.export_worker.is_alive())
        with Image.open(target) as saved:self.assertEqual(saved.width,saved.height)
        self.assertFalse(editor.canvas.cropping)

    def test_saturation_grayscale_and_vibrance_prefers_muted_colours(self):
        colours=Image.new('RGBA',(2,1)); colours.putdata([(160,120,120,255),(220,20,20,255)])
        grayscale=render(colours,EditState(saturation=-100,vibrance=80))
        for pixel in np.asarray(grayscale).reshape(-1,4):self.assertEqual(pixel[0],pixel[1]); self.assertEqual(pixel[1],pixel[2])
        neutral=render(colours,EditState()); boosted=render(colours,EditState(vibrance=80))
        old=np.asarray(neutral)[0,:,:3].astype(float); new=np.asarray(boosted)[0,:,:3].astype(float)
        relative_gain=(np.ptp(new,axis=1)-np.ptp(old,axis=1))/np.ptp(old,axis=1)
        self.assertGreater(relative_gain[0],relative_gain[1])
        muted=render(colours,EditState(saturation=-50)); self.assertLess(np.ptp(np.asarray(muted)[0,0,:3]),np.ptp(old[0]))

    def test_click_toggle_before_after_preserves_recipe_and_exports_after(self):
        editor=self.make_editor(); editor.sliders['saturation'].setValue(-100); state=editor.state
        QTest.mouseClick(editor.compare_button,Qt.MouseButton.LeftButton)
        self.assertTrue(editor.comparing); self.assertTrue(editor.compare_button.isChecked()); self.assertFalse(editor.settings.isEnabled())
        QTest.mouseClick(editor.compare_button,Qt.MouseButton.LeftButton)
        self.assertFalse(editor.comparing); self.assertEqual(editor.state,state)
        editor.compare_button.click(); target=self.root/'after.png'; editor.export_to(target)
        wait_for(lambda:target.exists() and not editor.export_worker.is_alive() and editor.save_button.isEnabled())
        self.assertFalse(editor.comparing); self.assertFalse(editor.result_panel.isHidden())

    def test_share_button_applies_pending_crop_and_reports_output(self):
        editor=self.make_editor(); editor.aspect.setCurrentIndex(2); editor.begin_crop()
        wait_for(lambda:editor.apply_crop_button.isEnabled() and not editor.crop_initialise)
        editor.compare_button.click()
        with patch('photo_editor.QFileDialog.getSaveFileName',return_value=(str(self.root/'cropped-share.jpg'),'JPEG (*.jpg *.jpeg)')):editor.share_button.click()
        wait_for(lambda:editor.export_worker is not None and not editor.export_worker.is_alive() and editor.save_button.isEnabled())
        path=Path(APP.clipboard().mimeData().urls()[0].toLocalFile())
        with Image.open(path) as image:self.assertEqual(image.width,image.height)
        self.assertFalse(editor.result_panel.isHidden()); self.assertTrue(editor.progress.isHidden())
        with patch('photo_editor.show_in_explorer') as reveal:
            editor.show_export(); reveal.assert_called_once_with(path)

    def test_save_error_recovers_buttons_and_shows_message(self):
        editor=self.make_editor()
        with patch('photo_editor.QMessageBox.information') as notice:
            editor.export_to(self.path)
            wait_for(lambda:editor.export_worker is not None and not editor.export_worker.is_alive() and editor.save_button.isEnabled())
            notice.assert_called_once()
        self.assertTrue(editor.progress.isHidden()); self.assertIn('Could not export',editor.status.text())

    def test_chosen_export_directory_is_remembered_for_save_and_share(self):
        editor=self.make_editor(); folder=self.root/'My chosen exports'; folder.mkdir()
        target=folder/'my-photo.png'
        with patch('photo_editor.QFileDialog.getSaveFileName',return_value=(str(target),'PNG (*.png)')):editor.save_button.click()
        wait_for(lambda:target.exists() and not editor.export_worker.is_alive() and editor.save_button.isEnabled())
        self.assertEqual(editor.export_folder(),folder)
        editor.close(); editor.deleteLater(); APP.sendPostedEvents(None,QEvent.Type.DeferredDelete); self.editor=None
        editor=self.make_editor(); self.assertEqual(editor.export_folder(),folder)
        with patch('photo_editor.QFileDialog.getSaveFileName',return_value=('','')) as picker:
            editor.share_button.click(); self.assertEqual(Path(picker.call_args.args[2]).parent,folder)
        self.assertIsNone(editor.export_worker); self.assertFalse((editor.cache/'shared-edits').exists())

    def test_share_uses_chosen_file_instead_of_appdata(self):
        editor=self.make_editor(); folder=self.root/'Share destination'; folder.mkdir(); target=folder/'for-sharing.png'
        with patch('photo_editor.QFileDialog.getSaveFileName',return_value=(str(target),'PNG (*.png)')):editor.share_button.click()
        wait_for(lambda:target.exists() and not editor.export_worker.is_alive() and editor.save_button.isEnabled())
        self.assertEqual(Path(APP.clipboard().mimeData().urls()[0].toLocalFile()),target)
        self.assertFalse((editor.cache/'shared-edits').exists())

    def test_editor_and_preview_minimize_and_restore(self):
        editor=self.make_editor()
        self.assertTrue(editor.windowFlags() & Qt.WindowType.WindowMinimizeButtonHint)
        import ctypes
        from ctypes import wintypes
        system_menu=ctypes.windll.user32.GetSystemMenu; system_menu.argtypes=[wintypes.HWND,wintypes.BOOL]; system_menu.restype=wintypes.HMENU
        menu_state=ctypes.windll.user32.GetMenuState; menu_state.argtypes=[wintypes.HMENU,wintypes.UINT,wintypes.UINT]; menu_state.restype=wintypes.UINT
        for command,name in [(0xF020,'Minimize'),(0xF030,'Maximize'),(0xF060,'Close')]:
            state=menu_state(system_menu(int(editor.winId()),False),command,0)
            self.assertNotEqual(state,0xFFFFFFFF); self.assertEqual(state & 3,0,f'Windows {name} command must be enabled')
        editor.showMinimized(); APP.processEvents(); self.assertTrue(editor.isMinimized())
        editor.showNormal(); APP.processEvents(); self.assertFalse(editor.isMinimized())
        catalog=Catalog(self.root/'catalog'); catalog.add_source(self.root); Indexer(catalog).scan()
        window=VaultWindow(self.root/'catalog'); dialog=MediaDialog(catalog.row(file_key(self.path)),window)
        try:
            self.assertTrue(dialog.windowFlags() & Qt.WindowType.WindowMinimizeButtonHint)
            dialog.show(); dialog.showMinimized(); APP.processEvents(); self.assertTrue(dialog.isMinimized())
            dialog.showNormal(); APP.processEvents(); self.assertFalse(dialog.isMinimized())
            for command,name in [(0xF020,'Minimize'),(0xF030,'Maximize'),(0xF060,'Close')]:
                state=menu_state(system_menu(int(dialog.winId()),False),command,0)
                self.assertNotEqual(state,0xFFFFFFFF); self.assertEqual(state & 3,0,f'Preview {name} must be enabled')
        finally:dialog.close(); window.close()

    def test_windows_close_command_respects_unsaved_edits(self):
        import ctypes
        from ctypes import wintypes
        post=ctypes.windll.user32.PostMessageW
        post.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]; post.restype=wintypes.BOOL
        editor=self.make_editor(); editor.sliders['brightness'].setValue(20)
        with patch('photo_editor.QMessageBox.question',return_value=QMessageBox.StandardButton.No) as notice:
            self.assertTrue(post(int(editor.winId()),0x0112,0xF060,0))
            wait_for(lambda:notice.called); self.assertTrue(editor.isVisible()); self.assertFalse(editor.closing)
        with patch('photo_editor.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes) as notice:
            self.assertTrue(post(int(editor.winId()),0x0112,0xF060,0))
            wait_for(lambda:editor.closing and not editor.isVisible()); notice.assert_called_once()
        editor.deleteLater(); APP.sendPostedEvents(None,QEvent.Type.DeferredDelete); self.editor=None

    def test_save_location_dropdown_changes_folder_and_keeps_filename(self):
        editor=self.make_editor(); destinations={}
        for place,name in [(QStandardPaths.StandardLocation.DownloadLocation,'Downloads'),(QStandardPaths.StandardLocation.DocumentsLocation,'Documents'),
                (QStandardPaths.StandardLocation.DesktopLocation,'Desktop'),(QStandardPaths.StandardLocation.PicturesLocation,'Pictures'),
                (QStandardPaths.StandardLocation.MoviesLocation,'Videos'),(QStandardPaths.StandardLocation.HomeLocation,'Home')]:
            folder=self.root/name; folder.mkdir(); destinations[place]=str(folder)
        selected=[]
        def choose():
            dialog=APP.activeModalWidget()
            if not isinstance(dialog,SaveLocationDialog):return
            combo=dialog.location_combo
            labels=[combo.itemText(i) for i in range(combo.count())]
            selected.append(labels); combo.setCurrentIndex(combo.findText('Documents'))
            self.assertEqual(Path(dialog.directory().absolutePath()),self.root/'Documents')
            self.assertEqual(dialog.findChild(QLineEdit,'fileNameEdit').text(),'sample photo-edited.jpg')
            dialog.grab().save(str(ROOT/'qa-output'/'save-location-dropdown.png')); dialog.accept()
        with patch('save_dialog.QStandardPaths.writableLocation',side_effect=lambda location:destinations[location]):
            QTimer.singleShot(200,choose); editor.save_button.click()
        target=self.root/'Documents'/'sample photo-edited.jpg'
        self.assertTrue(selected); self.assertIn('Downloads',selected[0]); self.assertIn('Pictures',selected[0])
        wait_for(lambda:target.exists() and not editor.export_worker.is_alive() and editor.save_button.isEnabled())
        self.assertEqual(editor.export_folder(),self.root/'Documents')

if __name__=='__main__':unittest.main()
