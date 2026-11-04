"""Native preview navigation, image zoom and mixed-media lifecycle checks."""
from pathlib import Path
import hashlib
import tempfile
import time
import unittest
import cv2
import numpy as np
from PIL import Image,ImageDraw
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QMediaPlayer
from desktop_app import VaultWindow,MediaDialog,THEME
from vault_core import Catalog,Indexer,file_key

ROOT=Path(__file__).resolve().parent
APP=QApplication.instance() or QApplication([]); APP.setStyle('Fusion'); APP.setStyleSheet(THEME)

def until(check):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        APP.processEvents()
        if check():return
        QTest.qWait(30)
    raise AssertionError('Native preview state did not become ready')

class PreviewNavigationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'qa-output'); self.root=Path(self.temp.name)
        self.photos=self.root/'2026'/'January'; self.photos.mkdir(parents=True)
        for name,size in [('landscape.jpg',(2400,1800)),('portrait.jpg',(1200,1800))]:
            image=Image.new('RGB',size,'#7296aa'); draw=ImageDraw.Draw(image)
            draw.ellipse((size[0]*.6,100,size[0]*.8,400),fill='#ffe2a0')
            draw.polygon([(0,size[1]),(size[0]*.4,size[1]*.35),(size[0],size[1])],fill='#40585c'); image.save(self.photos/name)
        for name in ['clip.avi','second.avi']:
            writer=cv2.VideoWriter(str(self.photos/name),cv2.VideoWriter_fourcc(*'MJPG'),10,(320,240))
            for frame in range(30):
                image=np.full((240,320,3),(95,135,180),dtype=np.uint8)
                cv2.circle(image,(40+frame*6,120),25,(225,235,250),-1); writer.write(image)
            writer.release()
        self.before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.photos.iterdir()}
        self.cat=Catalog(self.root/'cache'); self.cat.add_source(self.root/'2026'); Indexer(self.cat).scan()
        self.rows=[self.cat.row(file_key(self.photos/name)) for name in ['landscape.jpg','clip.avi','second.avi','portrait.jpg']]
        self.window=VaultWindow(self.root/'cache')

    def tearDown(self):
        self.window.close(); APP.processEvents()
        for path,digest in self.before.items():self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)
        self.temp.cleanup()

    def test_double_click_buttons_pan_and_fit(self):
        dialog=MediaDialog(self.rows[0],self.window,rows=self.rows); dialog.show(); APP.processEvents(); QTest.qWait(80)
        try:
            view=dialog.photo_view; fitted=view.transform().m11()
            self.assertTrue(view.fitted); self.assertLess(fitted,1)
            QTest.mouseDClick(view.viewport(),Qt.MouseButton.LeftButton,pos=view.viewport().rect().center())
            self.assertFalse(view.fitted); self.assertGreater(view.transform().m11(),fitted)
            self.assertGreater(view.horizontalScrollBar().maximum(),0)
            self.assertEqual(view.dragMode(),view.DragMode.ScrollHandDrag)
            QTest.mouseDClick(view.viewport(),Qt.MouseButton.LeftButton,pos=view.viewport().rect().center())
            self.assertTrue(view.fitted)
            dialog.zoom_in_button.click(); self.assertGreater(view.transform().m11(),fitted)
            dialog.actual_button.click(); self.assertAlmostEqual(view.transform().m11(),1)
            dialog.resize(1100,750); APP.processEvents(); self.assertAlmostEqual(view.transform().m11(),1)
            dialog.fit_button.click(); self.assertTrue(view.fitted)
            dialog.grab().save(str(ROOT/'qa-output'/'preview-navigation.png'))
        finally:dialog.close()

    def test_navigation_updates_actions_and_stops_previous_video(self):
        dialog=MediaDialog(self.rows[0],self.window,rows=self.rows); dialog.show(); APP.processEvents()
        try:
            self.assertFalse(dialog.previous_button.isEnabled()); self.assertIn('1 / 4',dialog.counter.text())
            dialog.next_button.click(); self.assertEqual(dialog.row['key'],self.rows[1]['key'])
            self.assertTrue(dialog.zoom_controls.isHidden()); self.assertEqual(dialog.actions.row['key'],self.rows[1]['key'])
            dialog.player.play(); until(lambda:dialog.player.duration()>0 and dialog.player.position()>0)
            dialog.set_volume(35); dialog.next_button.click()
            self.assertAlmostEqual(dialog.audio.volume(),.35,delta=.01)
            self.assertEqual(dialog.player.source().toLocalFile().replace('\\','/'),self.rows[2]['path'].replace('\\','/'))
            self.assertEqual(dialog.player.playbackState(),QMediaPlayer.PlaybackState.StoppedState)
            dialog.next_button.click(); self.assertFalse(dialog.next_button.isEnabled())
            self.assertFalse(dialog.zoom_controls.isHidden()); self.assertEqual(dialog.row['key'],self.rows[3]['key'])
            self.assertTrue(dialog.player.source().isEmpty()); self.assertTrue(dialog.photo_view.fitted)
            dialog.previous_button.click(); self.assertEqual(dialog.row['key'],self.rows[2]['key'])
        finally:dialog.close()

    def test_unavailable_original_does_not_trap_navigation(self):
        dialog=MediaDialog(self.rows[0],self.window,rows=self.rows)
        try:
            renamed=self.photos/'away.jpg'; (self.photos/'portrait.jpg').rename(renamed)
            dialog.navigate(3); self.assertFalse(dialog.media_note.isHidden())
            dialog.navigate(-3); self.assertEqual(dialog.row['key'],self.rows[0]['key'])
            renamed.rename(self.photos/'portrait.jpg')
        finally:dialog.close()

    def test_browsing_sequence_crosses_500_and_respects_filters(self):
        with self.cat.connect() as db:
            source=self.cat.sources()[0]['id']
            db.executemany('INSERT INTO media(key,source,path,name,kind,size,mtime,date,folder_year,folder_month) VALUES(?,?,?,?,?,?,?,?,?,?)',
                [(f'nav-{i}',source,str(self.photos/f'{i}.jpg'),f'nav {i}','photo',1,1,'2026-01-01','2026','01') for i in range(505)])
        self.window.load_sources(); self.window.reset_filters(); self.window.year.setCurrentIndex(self.window.year.findData('2026'))
        self.window.month.setCurrentIndex(self.window.month.findData('01')); self.window.kind.setCurrentIndex(1)
        sequence=self.window.preview_sequence(); self.assertEqual(len(sequence),507)
        self.assertTrue(all(row['kind']=='photo' for row in sequence))
        dialog=MediaDialog(sequence[499],self.window,rows=sequence)
        try:
            dialog.next_button.click(); self.assertEqual(dialog.position,500)
            self.assertEqual(dialog.actions.row['key'],sequence[500]['key'])
        finally:dialog.close()

    def test_arrows_and_wheel_navigate_at_fit_but_pan_when_zoomed(self):
        dialog=MediaDialog(self.rows[0],self.window,rows=[self.rows[0],self.rows[3]])
        dialog.show(); APP.processEvents(); QTest.qWait(60)
        def wheel(delta):
            viewport=dialog.photo_view.viewport(); point=viewport.rect().center()
            event=QWheelEvent(QPointF(point),QPointF(viewport.mapToGlobal(point)),QPoint(),QPoint(0,delta),
                Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.ScrollUpdate,False)
            APP.sendEvent(viewport,event); APP.processEvents()
        try:
            # Arrows work even when an action button, rather than the canvas, has focus.
            dialog.actions.star.setFocus(); QTest.keyClick(dialog.actions.star,Qt.Key.Key_Right)
            self.assertEqual(dialog.position,1)
            QTest.keyClick(dialog.actions.star,Qt.Key.Key_Left); self.assertEqual(dialog.position,0)
            wheel(-60); self.assertEqual(dialog.position,0)
            wheel(-60); self.assertEqual(dialog.position,1)
            wheel(-120); self.assertEqual(dialog.position,1)  # end of list
            wheel(120); self.assertEqual(dialog.position,0)
            dialog.actual_button.click(); APP.processEvents()
            vertical=dialog.photo_view.verticalScrollBar(); vertical.setValue(vertical.maximum()//2)
            before=vertical.value(); wheel(-120)
            self.assertGreater(vertical.value(),before); self.assertEqual(dialog.position,0)
            before=vertical.value(); wheel(120); self.assertLess(vertical.value(),before)
            horizontal=dialog.photo_view.horizontalScrollBar(); horizontal.setValue(horizontal.maximum()//2)
            before=horizontal.value(); QTest.keyClick(dialog.zoom_in_button,Qt.Key.Key_Right)
            self.assertGreater(horizontal.value(),before); self.assertEqual(dialog.position,0)
            dialog.fit_button.click(); wheel(-120); self.assertEqual(dialog.position,1)
        finally:dialog.close()

    def test_wheel_crosses_video_posters_playback_and_photos(self):
        dialog=MediaDialog(self.rows[0],self.window,rows=self.rows); dialog.show(); APP.processEvents(); QTest.qWait(60)
        def wheel(delta,widget=None):
            if widget is None:widget=dialog.photo_view.viewport() if dialog.row['kind']=='photo' else dialog.video_surface.currentWidget()
            point=widget.rect().center()
            event=QWheelEvent(QPointF(point),QPointF(widget.mapToGlobal(point)),QPoint(),QPoint(0,delta),
                Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.ScrollUpdate,False)
            APP.sendEvent(widget,event); APP.processEvents()
        try:
            wheel(-120); self.assertEqual(dialog.position,1)
            self.assertIs(dialog.video_surface.currentWidget(),dialog.video_poster)
            self.assertFalse(dialog.video_poster.original.isNull())
            self.assertEqual(dialog.player.playbackState(),QMediaPlayer.PlaybackState.StoppedState)
            dialog.grab().save(str(ROOT/'qa-output'/'video-poster-preview.png'))
            wheel(-60); self.assertEqual(dialog.position,1)
            wheel(-60); self.assertEqual(dialog.position,2)
            self.assertFalse(dialog.video_poster.original.isNull())
            wheel(120); self.assertEqual(dialog.position,1)
            dialog.player.play(); until(lambda:dialog.player.duration()>0 and dialog.player.position()>0)
            self.assertIs(dialog.video_surface.currentWidget(),dialog.video_display)
            wheel(-120); self.assertEqual(dialog.position,2)
            self.assertEqual(dialog.player.playbackState(),QMediaPlayer.PlaybackState.StoppedState)
            wheel(-120); self.assertEqual(dialog.position,3); self.assertTrue(dialog.player.source().isEmpty())
            wheel(120); self.assertEqual(dialog.position,2)
            wheel(-120,dialog.volume_slider); self.assertEqual(dialog.position,2)
            wheel(120); wheel(120); self.assertEqual(dialog.position,0)
            wheel(120); self.assertEqual(dialog.position,0)
        finally:dialog.close()

    def test_video_poster_remains_when_original_is_disconnected(self):
        moved=self.photos/'clip-away.avi'; original=self.photos/'clip.avi'; original.rename(moved)
        dialog=MediaDialog(self.rows[1],self.window,rows=self.rows); dialog.show(); APP.processEvents()
        try:
            self.assertFalse(dialog.video_poster.original.isNull()); self.assertFalse(dialog.play_button.isEnabled())
            self.assertIs(dialog.video_surface.currentWidget(),dialog.video_poster)
            dialog.navigate(1); self.assertEqual(dialog.position,2)
        finally:dialog.close(); moved.rename(original)

if __name__=='__main__':unittest.main()
