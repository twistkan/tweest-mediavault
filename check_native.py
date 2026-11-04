"""Exercise the native prototype only against generated project-local fixtures."""
from pathlib import Path
import json
import os
import time
import numpy as np
from PIL import Image,ImageDraw
import cv2
from PySide6.QtCore import QTimer,Qt
from PySide6.QtGui import QColor,QPalette
from PySide6.QtWidgets import QApplication,QMessageBox
from desktop_app import VaultWindow,THEME,ROOT,DarkChrome,MediaDialog
from vault_core import Catalog,Indexer,file_key
from vault_ai import LocalAI
from setup_app import create_shortcut,install

OUT=ROOT/'qa-output'; OUT.mkdir(exist_ok=True)
fixtures=OUT/'generated-media'; fixtures.mkdir(exist_ok=True)
for name,sky,ground in [('Ivan - generated sunset.jpg','#d89c73','#534362'),('Generated mountains.jpg','#9dc5cf','#49756f'),('Generated family.jpg','#c5b0b4','#515c76')]:
    image=Image.new('RGB',(800,600),sky); draw=ImageDraw.Draw(image)
    draw.ellipse((520,60,640,180),fill='#ffe6a4'); draw.polygon([(0,420),(200,260),(540,460),(800,320),(800,600),(0,600)],fill=ground)
    image.save(fixtures/name)
video=fixtures/'Generated clip.avi'
writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),10,(320,240))
for i in range(20):
    frame=np.zeros((240,320,3),dtype=np.uint8); frame[:]=[70+i*2,105,150]; cv2.circle(frame,(30+i*10,120),25,(100,220,240),-1); writer.write(frame)
writer.release()
catalog=Catalog(OUT/'native-data'); catalog.add_source(fixtures); Indexer(catalog).scan()
assert catalog.count()==4
clip=catalog.row(file_key(video)); assert clip['duration']>1 and Path(clip['thumb']).is_file()

started=time.perf_counter(); ai=LocalAI(ROOT/'models'); load=time.perf_counter()-started
image=Image.open(fixtures/'Generated mountains.jpg')
started=time.perf_counter(); vision=ai.image_embedding(image); text=ai.text_embedding('mountains in the sunshine'); elapsed=time.perf_counter()-started
assert vision.shape==text.shape==(512,)
assert np.isfinite(vision).all() and np.isfinite(text).all()
assert isinstance(ai.faces(image),list)
reference=OUT/'opencv-reference-face.jpg'
reference_faces=ai.faces(Image.open(reference)) if reference.exists() else []
if reference.exists(): assert len(reference_faces)>=1
ai.analyze(catalog,lambda:True,lambda *args:None)
with catalog.connect() as db: assert db.execute('SELECT COUNT(*) FROM media WHERE embedding IS NOT NULL').fetchone()[0]==3
assert ai.search(catalog,'mountains',catalog.items())

app=QApplication([]); app.setStyle('Fusion'); app.setStyleSheet(THEME)
palette=QPalette(); palette.setColor(QPalette.ColorRole.Window,QColor('#151625')); palette.setColor(QPalette.ColorRole.Base,QColor('#20212f')); palette.setColor(QPalette.ColorRole.WindowText,QColor('#ede9f3')); palette.setColor(QPalette.ColorRole.Text,QColor('#ede9f3')); app.setPalette(palette)
chrome=DarkChrome(app); app.installEventFilter(chrome)
window=VaultWindow(OUT/'native-data'); window.show()
errors=[]; results={}
def exercise():
    try:
        index=next(i for i,row in enumerate(window.model.rows) if row['kind']=='photo')
        window.select(window.model.index(index,0)); window.tag_edit.setText('Ivan, test family'); window.save_tags()
        assert window.catalog.items(text='Ivan')
        window.resize(1250,930); app.processEvents()
        window.grab().save(str(OUT/'native-library.png'))
        window.change_view('Folders'); assert window.folders.count()==1
        window.grab().save(str(OUT/'native-folders.png'))
        window.change_view('People'); assert window.people.count()>=1
        window.change_view('Library')
        dialog=MediaDialog(clip,window); dialog.show(); dialog.toggle()
        playback_deadline=time.monotonic()+15
        def finish():
            try:
                from PySide6.QtMultimedia import QMediaPlayer
                assert dialog.player.error()==QMediaPlayer.Error.NoError,dialog.player.errorString()
                if dialog.player.duration()==0 and time.monotonic()<playback_deadline:
                    QTimer.singleShot(250,finish); return
                assert dialog.player.duration()>0
                dialog.close(); window.close()
                reopened=VaultWindow(OUT/'native-data'); assert reopened.catalog.count()==4; reopened.close()
                # Exercise actual Windows shortcut creation, but only inside QA output.
                create_shortcut(Path(os.__file__).resolve().parent.parent/'python.exe',OUT/'test-shortcut.lnk')
                assert (OUT/'test-shortcut.lnk').stat().st_size>100
                results.update({'model_load_seconds':round(load,3),'image_and_text_seconds':round(elapsed,3),'reference_faces_detected':len(reference_faces),'catalog_items':4,'video_duration_seconds':clip['duration'],'startup':'passed','tags_and_restart':'passed','native_video_decode':'passed','project_local_shortcut':'passed'})
                (OUT/'native-checks.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
                print(json.dumps(results),flush=True)
            except Exception as exc: errors.append(exc)
            app.quit()
        QTimer.singleShot(1800,finish)
    except Exception as exc:
        errors.append(exc); app.quit()
QTimer.singleShot(700,exercise)
app.exec()
if errors: raise errors[0]
