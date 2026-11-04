"""Real native click/drag seeking against a generated local video."""
from pathlib import Path
import tempfile
import time
import unittest
import cv2
import numpy as np
from PySide6.QtCore import Qt,QPoint,QUrl
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QMediaPlayer
from desktop_app import VaultWindow,MediaDialog,THEME
from vault_core import Catalog,Indexer,file_key

APP=QApplication.instance() or QApplication([])
APP.setStyle('Fusion'); APP.setStyleSheet(THEME)
ROOT=Path(__file__).resolve().parent

def until(check,timeout=10):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        APP.processEvents()
        if check():return
        QTest.qWait(30)
    raise AssertionError('Timed out waiting for native playback state')

class VideoSeekTests(unittest.TestCase):
    def test_click_drag_and_keyboard_with_real_player(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'qa-output') as temp:
            home=Path(temp); media=home/'media'; media.mkdir(); video=media/'seek test.avi'
            writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),10,(320,240))
            for frame in range(120):writer.write(np.full((240,320,3),frame*2,dtype=np.uint8))
            writer.release()
            catalog=Catalog(home/'cache'); catalog.add_source(media); Indexer(catalog).scan()
            owner=VaultWindow(home/'cache'); dialog=MediaDialog(catalog.row(file_key(video)),owner)
            try:
                dialog.show(); dialog.player.play()
                until(lambda:dialog.player.duration()>10000 and dialog.player.isSeekable() and dialog.player.position()>0)
                slider=dialog.slider
                until(lambda:slider.isEnabled())
                volume=dialog.volume_slider
                QTest.mouseClick(volume,Qt.MouseButton.LeftButton,pos=QPoint(round(volume.width()*.4),volume.height()//2))
                self.assertAlmostEqual(dialog.audio.volume(),.4,delta=.08)
                level=dialog.audio.volume()
                QTest.mouseClick(dialog.mute_button,Qt.MouseButton.LeftButton)
                self.assertTrue(dialog.audio.isMuted()); self.assertTrue(dialog.mute_button.isChecked())
                self.assertEqual(dialog.volume_label.text(),'0%')
                QTest.mouseClick(dialog.mute_button,Qt.MouseButton.LeftButton)
                self.assertFalse(dialog.audio.isMuted()); self.assertAlmostEqual(dialog.audio.volume(),level)
                dialog.set_volume(0); self.assertTrue(dialog.mute_button.isChecked())
                QTest.mouseClick(dialog.mute_button,Qt.MouseButton.LeftButton)
                self.assertGreater(dialog.audio.volume(),0); self.assertFalse(dialog.audio.isMuted())
                dialog.audio.setMuted(True); dialog.set_volume(65)
                self.assertFalse(dialog.audio.isMuted()); self.assertEqual(dialog.volume_label.text(),'65%')
                dialog.player.pause()
                until(lambda:dialog.player.playbackState()==QMediaPlayer.PlaybackState.PausedState)
                def point(fraction):return QPoint(round(8+(slider.width()-16)*fraction),slider.height()//2)
                QTest.mouseClick(slider,Qt.MouseButton.LeftButton,pos=point(.75))
                until(lambda:abs(dialog.player.position()-9000)<650)
                self.assertEqual(dialog.player.playbackState(),QMediaPlayer.PlaybackState.PausedState)
                dialog.player.play()
                QTest.mousePress(slider,Qt.MouseButton.LeftButton,pos=point(.75))
                QTest.mouseMove(slider,point(.25))
                held=slider.value(); self.assertTrue(slider.isSliderDown())
                dialog.update_playhead(11000)
                self.assertEqual(slider.value(),held)
                QTest.mouseRelease(slider,Qt.MouseButton.LeftButton,pos=point(.25))
                until(lambda:abs(dialog.player.position()-3000)<650)
                self.assertEqual(dialog.player.playbackState(),QMediaPlayer.PlaybackState.PlayingState)
                dialog.player.pause(); before=slider.value()
                QTest.keyClick(slider,Qt.Key.Key_Right)
                until(lambda:abs(dialog.player.position()-(before+1000))<300)
                dialog.grab().save(str(ROOT/'qa-output'/'video-seek.png'))
            finally:
                dialog.player.stop(); dialog.player.setSource(QUrl())
                dialog.close(); owner.close(); APP.processEvents(); QTest.qWait(250)

if __name__=='__main__':unittest.main()
