"""Tweest MediaVault: native Qt Widgets desktop prototype, no web view."""
from __future__ import annotations
import ctypes
import json
import os
import sqlite3
from pathlib import Path
import sys
import threading
import time
from collections import OrderedDict

from PySide6.QtCore import Qt, QSize, QTimer, Signal, QObject, QAbstractListModel, QModelIndex, QRect, QEvent,QStandardPaths
from PySide6.QtGui import QColor, QPalette, QPixmap, QIcon, QPainter, QFont, QImageReader
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QLineEdit, QComboBox, QHBoxLayout, QVBoxLayout, QListView, QAbstractItemView,
    QStyledItemDelegate, QStackedWidget, QListWidget, QListWidgetItem, QFileDialog,
    QMessageBox, QCheckBox, QInputDialog, QDialog, QSlider, QScrollArea,QGridLayout,QMenu,QSizePolicy,QStyle,QStyleOptionSlider)
from vault_core import Catalog, Indexer, MONTH_NAMES
from library_audit import audit_library,prepare_imports,log_event
from storage_paths import data_folder,migrate_legacy_data
from PySide6.QtSvg import QSvgRenderer
from media_actions import show_in_explorer,open_in_default_app,save_copy,file_share_mime,media_copy_mime

ASSETS = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
ROOT = Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
HOME = data_folder(ROOT,installed=getattr(sys,'frozen',False))
MODELS = ROOT/'models'
LOGO = ASSETS/'Branding'/'Twisted-logo idea 04.jpg'

THEME = '''
QWidget{background:#151625;color:#e7e5ed;font-family:"Segoe UI";font-size:13px;}
QMainWindow{background:#121321;} QLabel{background:transparent;}
QFrame#title{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #262832,stop:1 #1b1d29);border-bottom:1px solid #41404b;}
QFrame#sidebar{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #262731,stop:1 #1b1b2e);border-right:1px solid #363540;}
QFrame#preview{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #34343c,stop:1 #20212d);border:1px solid #47434e;border-radius:12px;}
QLabel#heading{font-size:26px;font-weight:600;} QLabel#brand{font-size:17px;font-weight:600;}
QLabel#previewTitle{font-size:20px;font-weight:600;}
QLabel#eyebrow{font-size:10px;color:#f5c45b;letter-spacing:2px;}
QLabel#muted{color:#b3adbf;font-size:12px;} QLabel#status{color:#d3c9ad;font-size:11px;}
QPushButton{background:#282833;border:1px solid #48444f;border-radius:6px;padding:8px 13px;}
QPushButton:hover{background:#373540;border-color:#8e784d;} QPushButton:pressed{background:#4a4030;}
QPushButton:disabled{color:#777481;border-color:#34323d;}
QPushButton#primary{background:#51442c;border-color:#8d713d;color:#ffe3a4;}
QPushButton#nav{text-align:left;background:transparent;border:0;padding:13px 15px;color:#c6c0d2;}
QPushButton#nav:checked{background:#393640;border-left:3px solid #f5c45b;color:#fff0cd;}
QLineEdit,QComboBox{background:#232431;border:1px solid #4a4553;border-radius:7px;padding:9px;color:#eeebf3;selection-background-color:#6b5730;}
QLineEdit:focus{border-color:#d0a852;} QComboBox QAbstractItemView{background:#262633;selection-background-color:#4b412f;}
QListView,QListWidget{background:transparent;border:0;outline:0;} QListWidget::item{padding:10px;border-bottom:1px solid #34313f;}
QListWidget::item:selected{background:#443a2a;} QScrollArea{border:0;background:transparent;}
QScrollBar:vertical{background:#1a1b29;width:10px;} QScrollBar::handle:vertical{background:#4c485c;border-radius:4px;min-height:30px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;} QDialog,QMessageBox,QInputDialog{background:#20212f;}
QToolTip{background:#30303a;color:#f2edf5;border:1px solid #6f5b39;}
'''

def label(text='', name=''):
    item = QLabel(text)
    if name: item.setObjectName(name)
    return item

def button(text, callback, primary=False):
    item = QPushButton(text)
    if primary: item.setObjectName('primary')
    item.clicked.connect(callback)
    return item

def open_photo_editor(row,owner,parent):
    if not row or row['kind']!='photo':return
    try:
        from photo_editor import PhotoEditor
        editor=PhotoEditor(row['path'],owner.catalog.home,parent)
    except Exception as exc:
        QMessageBox.information(parent,'Cannot edit this photo',str(exc)); return
    try:editor.exec()
    finally:editor.deleteLater()

def duration(seconds):
    value = int(seconds or 0)
    return f'{value//60}:{value%60:02d}'

def menu_icon(name,selected=False):
    content=(ASSETS/'assets'/'icons'/(name.lower()+'.svg')).read_bytes()
    if selected: content=content.replace(b'#c8c2d6',b'#f5c45b')
    pixmap=QPixmap(48,48); pixmap.fill(Qt.GlobalColor.transparent)
    renderer=QSvgRenderer(content); painter=QPainter(pixmap); renderer.render(painter); painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)

class Bus(QObject):
    message = Signal(str, str)
    result = Signal(object)

class DarkChrome(QObject):
    def eventFilter(self,watched,event):
        if sys.platform=='win32' and event.type()==QEvent.Type.Show and isinstance(watched,QWidget) and watched.isWindow():
            try: ctypes.windll.dwmapi.DwmSetWindowAttribute(int(watched.winId()),20,ctypes.byref(ctypes.c_int(1)),4)
            except Exception: pass
        return False

class LibraryModel(QAbstractListModel):
    def __init__(self):
        super().__init__(); self.rows = []; self.pixmaps = OrderedDict()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid(): return None
        row = self.rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole: return row['name']
        if role == Qt.ItemDataRole.ToolTipRole: return row['path']+ ('\n'+row['error'] if row['error'] else '')
        if role == Qt.ItemDataRole.UserRole: return row

    def replace(self, rows):
        if len(rows)>len(self.rows) and rows[:len(self.rows)]==self.rows:
            start=len(self.rows); self.beginInsertRows(QModelIndex(),start,len(rows)-1)
            self.rows.extend(rows[start:]); self.endInsertRows(); return
        self.beginResetModel(); self.rows = rows; self.endResetModel()

    def thumbnail(self, path):
        if not path: return QPixmap()
        if path not in self.pixmaps:
            self.pixmaps[path] = QPixmap(path)
            if len(self.pixmaps)>180: self.pixmaps.popitem(last=False)
        else: self.pixmaps.move_to_end(path)
        return self.pixmaps[path]

class TileDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        row = index.data(Qt.ItemDataRole.UserRole)
        rect = option.rect.adjusted(7, 7, -7, -7)
        edge = min(rect.width(), rect.height()-48)
        art = QRect(rect.x(), rect.y(), edge, edge)
        painter.save(); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(art,QColor('#292b39'))
        pixmap = index.model().thumbnail(row['thumb'])
        if not pixmap.isNull(): painter.drawPixmap(art,pixmap)
        else:
            painter.setPen(QColor('#c6bdca')); painter.drawText(art,Qt.AlignmentFlag.AlignCenter,'VIDEO' if row['kind']=='video' else 'PREVIEW\nUNAVAILABLE')
        if row['kind']=='video':
            badge = QRect(art.right()-48,art.top()+5,43,20)
            painter.fillRect(badge,QColor(17,18,30,210)); painter.setPen(QColor('#ffffff'))
            painter.drawText(badge,Qt.AlignmentFlag.AlignCenter,duration(row['duration']))
        if row.get('favourite'):
            painter.fillRect(QRect(art.left()+4,art.top()+4,23,23),QColor(20,20,30,210))
            painter.setPen(QColor('#f5c45b')); painter.drawText(QRect(art.left()+4,art.top()+4,23,23),Qt.AlignmentFlag.AlignCenter,'★')
        if option.state & option.state.State_Selected:
            painter.setPen(QColor('#f5c45b')); painter.drawRoundedRect(art.adjusted(-2,-2,2,2),4,4)
        painter.setPen(QColor('#ded8e7'))
        title = painter.fontMetrics().elidedText(row['name'],Qt.TextElideMode.ElideMiddle,edge)
        painter.drawText(QRect(rect.x(),art.bottom()+8,edge,22),Qt.AlignmentFlag.AlignLeft,title)
        painter.setPen(QColor('#aaa1b8'))
        subtitle='Possible face match' if row.get('_possible') else (row['date'] or '')
        painter.drawText(QRect(rect.x(),art.bottom()+29,edge,16),Qt.AlignmentFlag.AlignLeft,subtitle)
        painter.restore()

    def sizeHint(self, option, index): return QSize(160,208)

class PreviewActions(QWidget):
    def __init__(self,row,owner,parent=None):
        super().__init__(parent); self.row=row; self.owner=owner
        grid=QGridLayout(self); grid.setContentsMargins(0,0,0,0); grid.setSpacing(7)
        self.explorer=button('Show in Explorer',self.reveal); self.explorer.setIcon(menu_icon('explorer'))
        self.external=button('Open in default app',self.open_external); self.external.setIcon(menu_icon('open'))
        self.external.setToolTip('Open the original in Windows Photos or your chosen default application')
        self.export=button('Save a copy…',self.export_copy); self.export.setIcon(menu_icon('save'))
        self.share=button('Share…',self.share_menu); self.share.setIcon(menu_icon('share'))
        self.copy=button('Copy',self.copy_media); self.copy.setIcon(menu_icon('copy'))
        self.copy.setToolTip('Copy this photo or video, then paste into WhatsApp or another app')
        self.star=button('Favourite',self.toggle_star); self.star.setCheckable(True)
        self.person=button('Name a person…',self.name_person); self.person.setIcon(menu_icon('people'))
        self.reconnect=button('Reconnect original…',self.reconnect_original); self.reconnect.setIcon(menu_icon('folders'))
        self.reconnect.setToolTip('Reconnect a moved original to an available indexed copy, preserving labels')
        for index,control in enumerate([self.external,self.explorer,self.export,self.copy,self.share,self.star,self.person,self.reconnect]):
            grid.addWidget(control,index//4,index%4)
        self.set_row(row)

    def set_row(self,row):
        self.row=row
        for item in [self.external,self.explorer,self.export,self.copy,self.share,self.star,self.person]: item.setEnabled(bool(row))
        favourite=bool(row and row.get('favourite'))
        self.star.setChecked(favourite); self.star.setText('Favourited' if favourite else 'Favourite')
        self.star.setIcon(menu_icon('favourites',favourite))
        self.star.setToolTip('Remove from favourites' if favourite else 'Add to favourites')
        self.person.setEnabled(bool(row and row['kind']=='photo'))
        self.reconnect.setEnabled(bool(row and not Path(row['path']).is_file()))

    def reconnect_original(self):
        if not self.row or self.owner.busy():return
        from reconnect_media import candidates,reconnect
        old_key=self.row['key']; available=candidates(self.owner.catalog,old_key)
        if not available:
            QMessageBox.information(self,'No available indexed copy','Reconnect the source drive, or add/rescan the folder containing the moved file. Then try Reconnect original again.\n\nSaved path: '+self.row['path']); return
        path,ok=QInputDialog.getItem(self,'Choose the available copy','Matching filename, type and size — choose the same photo/video:',[row['path'] for row in available],0,False)
        if not ok:return
        target=next(row for row in available if row['path']==path)
        if QMessageBox.question(self,'Reconnect this original?',
            'Only confirm if this is the same photo/video. Filename and size alone cannot prove it.\n\nMissing: '+self.row['path']+'\n\nAvailable: '+path+
            '\n\nCombine these cached entries and keep their tags, favourites and face labels? A catalog backup will be saved first. Original files are unchanged.')!=QMessageBox.StandardButton.Yes:return
        try:
            backup=reconnect(self.owner.catalog,old_key,target['key'])
        except (OSError,ValueError,sqlite3.Error) as exc:
            QMessageBox.information(self,'Could not reconnect',str(exc)); return
        row=self.owner.catalog.row(target['key'])
        self.owner.current=row; self.owner.refresh(); self.owner.update_preview()
        if isinstance(self.parent(),MediaDialog):
            dialog=self.parent(); dialog.keys=list(dict.fromkeys(target['key'] if key==old_key else key for key in dialog.keys))
            dialog.position=dialog.keys.index(target['key']); dialog.show_media(row)
        self.owner.status.setText('Original reconnected; labels kept. Catalog backup: '+str(backup))

    def toggle_star(self):
        if not self.row:return
        self.owner.toggle_favourite(self.row['key'])
        self.set_row(self.owner.catalog.row(self.row['key']))

    def reveal(self):
        try: show_in_explorer(self.row['path'])
        except OSError as exc: QMessageBox.information(self,'Original unavailable',str(exc))

    def open_external(self):
        try: open_in_default_app(self.row['path'])
        except OSError as exc: QMessageBox.information(self,'Cannot open original',str(exc))

    def export_copy(self):
        initial=Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation) or str(Path.home()))/self.row['name']
        destination,_=QFileDialog.getSaveFileName(self,'Save an unchanged copy',str(initial),'All files (*)',options=QFileDialog.Option.DontUseNativeDialog|QFileDialog.Option.DontConfirmOverwrite)
        if not destination:return
        try:
            save_copy(self.row['path'],destination)
            self.owner.status.setText('Copy saved. The original photo and its filename are unchanged.')
        except FileExistsError:QMessageBox.information(self,'Save a copy','A file with this name already exists. Choose a new name to keep the existing file unchanged.')
        except (OSError,ValueError) as exc:QMessageBox.information(self,'Save a copy',str(exc))

    def share_menu(self):
        menu=QMenu(self)
        menu.addAction('Copy file for sharing',self.copy_for_sharing)
        menu.addAction('Copy original file path',lambda:QApplication.clipboard().setText(self.row['path']))
        menu.exec(self.share.mapToGlobal(self.share.rect().bottomLeft()))

    def copy_for_sharing(self):
        try:
            QApplication.clipboard().setMimeData(file_share_mime(self.row['path']))
            QMessageBox.information(self,'File ready to share','The original file is copied to the clipboard. Paste it into the app or message you choose. Nothing has been sent automatically.')
        except OSError as exc:QMessageBox.information(self,'Original unavailable',str(exc))

    def copy_media(self):
        if not self.row:return
        try:
            mime=media_copy_mime(self.row['path'],self.row['kind'])
            has_image=mime.hasImage()
            QApplication.clipboard().setMimeData(mime)
            message='Photo copied. Paste into WhatsApp or another app.' if has_image else 'File copied. Paste into an app that accepts files.'
            self.owner.status.setText(message)
            self.copy.setToolTip(message)
        except OSError as exc:QMessageBox.information(self,'Original unavailable',str(exc))

    def name_person(self):
        if self.row:self.owner.name_person(self.row['key'])

class SeekSlider(QSlider):
    seekRequested=Signal(int)

    def __init__(self,parent=None):
        super().__init__(Qt.Orientation.Horizontal,parent)
        self.setRange(0,0); self.setEnabled(False)

    def pointer_value(self,event):
        option=QStyleOptionSlider(); self.initStyleOption(option)
        handle=self.style().subControlRect(QStyle.ComplexControl.CC_Slider,option,QStyle.SubControl.SC_SliderHandle,self)
        groove=self.style().subControlRect(QStyle.ComplexControl.CC_Slider,option,QStyle.SubControl.SC_SliderGroove,self)
        span=max(1,groove.width()-handle.width())
        position=round(event.position().x()-groove.x()-handle.width()/2)
        return QStyle.sliderValueFromPosition(self.minimum(),self.maximum(),max(0,min(span,position)),span,option.upsideDown)

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.setFocus(); self.setSliderDown(True); self.setValue(self.pointer_value(event)); event.accept()
        else:super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.isSliderDown():self.setValue(self.pointer_value(event)); event.accept()
        else:super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.isSliderDown():
            self.setValue(self.pointer_value(event)); self.setSliderDown(False)
            self.seekRequested.emit(self.value()); event.accept()
        else:super().mouseReleaseEvent(event)

    def keyPressEvent(self,event):
        before=self.value(); super().keyPressEvent(event)
        if self.value()!=before:self.seekRequested.emit(self.value())

class VideoPoster(QLabel):
    def __init__(self):
        super().__init__(); self.original=QPixmap()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter); self.setStyleSheet('background:black;')
        self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Ignored)
    def set_poster(self,pixmap):
        self.original=pixmap; self.update_poster()
    def update_poster(self):
        if self.original.isNull():self.clear(); self.setText('Video thumbnail unavailable\nPress Play to preview this clip.')
        else:self.setPixmap(self.original.scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
    def resizeEvent(self,event):
        super().resizeEvent(event); self.update_poster()

class MediaDialog(QDialog):
    def __init__(self,row,parent,rows=None):
        super().__init__(parent); self.owner=parent; self.player=None
        self.setWindowFlags((self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)|Qt.WindowType.WindowMinimizeButtonHint|Qt.WindowType.WindowMaximizeButtonHint|Qt.WindowType.WindowSystemMenuHint|Qt.WindowType.WindowCloseButtonHint)
        area=self.screen().availableGeometry(); self.resize(min(1280,area.width()-40),min(900,area.height()-70))
        self.setMinimumSize(min(860,area.width()-40),min(600,area.height()-70))
        self.keys=list(dict.fromkeys(r['key'] for r in (rows if rows is not None else parent.model.rows)))
        if row['key'] not in self.keys:self.keys.insert(0,row['key'])
        self.position=self.keys.index(row['key'])
        layout=QVBoxLayout(self); layout.setContentsMargins(16,14,16,16); layout.setSpacing(12)
        navigation=QHBoxLayout()
        self.previous_button=button('Previous',lambda:self.navigate(-1)); self.previous_button.setIcon(menu_icon('previous'))
        self.next_button=button('Next',lambda:self.navigate(1)); self.next_button.setIcon(menu_icon('next'))
        navigation.addWidget(self.previous_button); navigation.addWidget(self.next_button)
        self.counter=label('','muted'); navigation.addWidget(self.counter)
        self.edit_button=button('Edit a copy…',self.edit_photo); self.edit_button.setIcon(menu_icon('edit')); navigation.addWidget(self.edit_button); navigation.addStretch()
        self.zoom_controls=QWidget(); zoomrow=QHBoxLayout(self.zoom_controls); zoomrow.setContentsMargins(0,0,0,0)
        from photo_view import PhotoView
        self.photo_view=PhotoView(); self.zoom_label=label(); self.zoom_label.setMinimumWidth(85)
        self.photo_view.zoomChanged.connect(self.zoom_label.setText)
        self.photo_view.navigateRequested.connect(self.navigate)
        self.zoom_out_button=button('',self.photo_view.zoom_out); self.zoom_out_button.setIcon(menu_icon('zoom-out')); self.zoom_out_button.setToolTip('Zoom out')
        self.zoom_in_button=button('',self.photo_view.zoom_in); self.zoom_in_button.setIcon(menu_icon('zoom-in')); self.zoom_in_button.setToolTip('Zoom in; drag the photo to pan')
        self.fit_button=button('Fit',self.photo_view.fit_photo); self.actual_button=button('100%',self.photo_view.actual_size)
        for control in [self.zoom_out_button,self.zoom_label,self.zoom_in_button,self.actual_button,self.fit_button]:zoomrow.addWidget(control)
        navigation.addWidget(self.zoom_controls); layout.addLayout(navigation)
        self.surface=QStackedWidget(); self.surface.addWidget(self.photo_view); layout.addWidget(self.surface,1)
        self.media_note=label('','muted'); layout.addWidget(self.media_note); self.media_note.hide()
        self.path_label=label('','muted'); self.path_label.setWordWrap(True); layout.addWidget(self.path_label)
        self.actions=PreviewActions(None,parent,self); layout.addWidget(self.actions)
        self.show_media(row)
        QApplication.instance().installEventFilter(self)

    def eventFilter(self,watched,event):
        if (event.type()==QEvent.Type.Wheel and self.isVisible() and self.row['kind']=='video'
                and isinstance(watched,QWidget) and hasattr(self,'video_surface')
                and (watched is self.video_surface or self.video_surface.isAncestorOf(watched))
                and QApplication.activeModalWidget() in [None,self]):
            self.video_wheel_delta+=event.angleDelta().y() or event.pixelDelta().y()*2
            if abs(self.video_wheel_delta)>=120:
                direction=-1 if self.video_wheel_delta>0 else 1
                self.video_wheel_delta=0; self.navigate(direction)
            event.accept(); return True
        if (event.type()==QEvent.Type.KeyPress and self.isVisible() and isinstance(watched,QWidget)
                and (watched is self or self.isAncestorOf(watched))
                and QApplication.activeModalWidget() in [None,self]
                and event.modifiers()==Qt.KeyboardModifier.NoModifier):
            key=event.key()
            if self.row['kind']=='photo':
                if self.photo_view.fitted and key in [Qt.Key.Key_Left,Qt.Key.Key_Right]:
                    self.navigate(-1 if key==Qt.Key.Key_Left else 1); return True
                if not self.photo_view.fitted and key in [Qt.Key.Key_Left,Qt.Key.Key_Right,Qt.Key.Key_Up,Qt.Key.Key_Down]:
                    horizontal=key in [Qt.Key.Key_Left,Qt.Key.Key_Right]
                    bar=self.photo_view.horizontalScrollBar() if horizontal else self.photo_view.verticalScrollBar()
                    direction=-1 if key in [Qt.Key.Key_Left,Qt.Key.Key_Up] else 1
                    bar.setValue(bar.value()+direction*bar.singleStep()*3); return True
            elif key in [Qt.Key.Key_Left,Qt.Key.Key_Right] and not isinstance(watched,QSlider):
                self.navigate(-1 if key==Qt.Key.Key_Left else 1); return True
        return super().eventFilter(watched,event)

    def ensure_video(self):
        if self.player:return
        from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
        from PySide6.QtMultimediaWidgets import QVideoWidget
        self.video_page=QWidget(); layout=QVBoxLayout(self.video_page); layout.setContentsMargins(0,0,0,0)
        video=QVideoWidget(); self.video_display=video; self.video_poster=VideoPoster()
        self.video_surface=QStackedWidget(); self.video_surface.addWidget(self.video_poster); self.video_surface.addWidget(video)
        layout.addWidget(self.video_surface,1)
        self.player=QMediaPlayer(self); self.audio=QAudioOutput(self); self.last_volume=100
        self.player.setAudioOutput(self.audio); self.player.setVideoOutput(video)
        self.player.playbackStateChanged.connect(self.video_state_changed)
        controls=QHBoxLayout(); self.play_button=button('Play / Pause',self.toggle); controls.addWidget(self.play_button)
        self.slider=SeekSlider(); controls.addWidget(self.slider,1)
        self.player.durationChanged.connect(lambda n:self.slider.setRange(0,n))
        self.player.positionChanged.connect(self.update_playhead)
        self.player.seekableChanged.connect(self.slider.setEnabled); self.slider.seekRequested.connect(self.player.setPosition)
        self.slider.setSingleStep(1000); self.slider.setPageStep(5000)
        self.mute_button=button('',self.toggle_mute); self.mute_button.setCheckable(True); self.mute_button.setFixedWidth(42); controls.addWidget(self.mute_button)
        self.volume_slider=SeekSlider(); self.volume_slider.setRange(0,100); self.volume_slider.setEnabled(True)
        self.volume_slider.setFixedWidth(110); self.volume_slider.setSingleStep(5); self.volume_slider.setPageStep(10)
        self.volume_slider.setAccessibleName('Video volume'); self.volume_slider.seekRequested.connect(self.set_volume); controls.addWidget(self.volume_slider)
        self.volume_label=label(); self.volume_label.setFixedWidth(36); controls.addWidget(self.volume_label)
        self.audio.volumeChanged.connect(self.update_volume); self.audio.mutedChanged.connect(self.update_volume); self.update_volume()
        layout.addLayout(controls); self.error=label('Local playback'); layout.addWidget(self.error)
        self.player.errorOccurred.connect(lambda *_:self.error.setText(self.player.errorString()))
        self.surface.addWidget(self.video_page)

    def show_media(self,row):
        from PySide6.QtCore import QUrl
        self.video_wheel_delta=0
        if self.player:self.player.stop(); self.player.setSource(QUrl())
        self.row=row; self.setWindowTitle(row['name']); self.path_label.setText(row['path']); self.actions.set_row(row)
        self.edit_button.setEnabled(row['kind']=='photo')
        self.counter.setText(f'{self.position+1:,} / {len(self.keys):,}')
        self.previous_button.setEnabled(self.position>0); self.next_button.setEnabled(self.position<len(self.keys)-1)
        self.media_note.hide(); self.zoom_controls.setVisible(row['kind']=='photo')
        if row['kind']=='video':
            self.photo_view.set_photo(QPixmap()); self.ensure_video(); self.surface.setCurrentWidget(self.video_page)
            self.video_poster.set_poster(QPixmap(row.get('thumb') or '')); self.video_surface.setCurrentWidget(self.video_poster)
            exists=Path(row['path']).is_file(); self.play_button.setEnabled(exists)
            self.slider.setRange(0,0); self.slider.setEnabled(False)
            self.error.setText('Local playback' if exists else 'Original unavailable. Reconnect its source drive, or use Previous / Next.')
            if exists:self.player.setSource(QUrl.fromLocalFile(row['path']))
        else:
            self.surface.setCurrentWidget(self.photo_view)
            reader=QImageReader(row['path']); reader.setAutoTransform(True)
            size=reader.size()
            if max(size.width(),size.height())>8192:
                size.scale(QSize(8192,8192),Qt.AspectRatioMode.KeepAspectRatio); reader.setScaledSize(size)
            pixmap=QPixmap.fromImage(reader.read())
            if pixmap.isNull():
                pixmap=QPixmap(row.get('thumb') or '')
                self.media_note.setText('Original unavailable or unsupported; showing its cached thumbnail when available. You can keep navigating.'); self.media_note.show()
            self.photo_view.set_photo(pixmap); QTimer.singleShot(0,self.photo_view.fit_photo)

    def navigate(self,step):
        position=self.position+step
        while 0<=position<len(self.keys):
            row=self.owner.catalog.row(self.keys[position])
            if row:
                self.position=position; self.show_media(row)
                self.owner.current=row; self.owner.update_preview()
                return
            position+=step

    def edit_photo(self):open_photo_editor(self.row,self.owner,self)

    def video_state_changed(self,state):
        from PySide6.QtMultimedia import QMediaPlayer
        if state==QMediaPlayer.PlaybackState.PlayingState:self.video_surface.setCurrentWidget(self.video_display)
        elif state==QMediaPlayer.PlaybackState.StoppedState:self.video_surface.setCurrentWidget(self.video_poster)

    def toggle(self):
        from PySide6.QtMultimedia import QMediaPlayer
        self.player.pause() if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState else self.player.play()

    def update_playhead(self,position):
        # Playback notifications must not pull the handle away while scrubbing.
        if not self.slider.isSliderDown():self.slider.setValue(position)

    def set_volume(self,value):
        self.audio.setVolume(value/100)
        if value>0:self.audio.setMuted(False)

    def toggle_mute(self):
        if self.audio.volume()==0:
            self.audio.setVolume(self.last_volume/100); self.audio.setMuted(False)
        else:self.audio.setMuted(not self.audio.isMuted())

    def update_volume(self,*_):
        value=round(self.audio.volume()*100)
        if value>0:self.last_volume=value
        muted=self.audio.isMuted() or value==0
        if not self.volume_slider.isSliderDown():self.volume_slider.setValue(value)
        self.volume_label.setText('0%' if muted else f'{value}%')
        self.volume_slider.setToolTip(f'Volume: {value}%')
        self.mute_button.setChecked(muted); self.mute_button.setIcon(menu_icon('muted' if muted else 'volume'))
        self.mute_button.setToolTip('Unmute' if muted else 'Mute')
        self.mute_button.setAccessibleName('Unmute video' if muted else 'Mute video')

    def closeEvent(self,event):
        QApplication.instance().removeEventFilter(self)
        if self.player:
            from PySide6.QtCore import QUrl
            self.player.stop(); self.player.setSource(QUrl())
        super().closeEvent(event)

class VaultWindow(QMainWindow):
    def __init__(self,home=HOME):
        super().__init__()
        self.started=time.perf_counter(); self.catalog=Catalog(home); self.current=None
        self.job=None; self.indexer=None; self.ai=None; self.limit=500; self.view='Library'
        self.result_callback=None; self.pending_refresh=False; self.search_generation=0; self.pending_search=False; self.working=False; self.job_kind=''; self.closing=False
        self.setWindowTitle('Tweest MediaVault · Powered by Tweest')
        self.setWindowIcon(QIcon(str(LOGO))); self.resize(1250,900); self.setMinimumSize(900,650)
        self.setAcceptDrops(True)
        self.bus=Bus(); self.bus.message.connect(self.on_message); self.bus.result.connect(self.on_result)
        self.people_bus=Bus(); self.people_bus.result.connect(self.on_people_result); self.people_worker=None; self.priority_person_key=None
        self.audit_bus=Bus(); self.audit_bus.result.connect(self.on_audit_result); self.audit_worker=None
        self.audit_report=None; self.audit_stop=threading.Event(); self.rescan_pending=None
        root=QWidget(); self.setCentralWidget(root); outer=QVBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        title=QFrame(); title.setObjectName('title'); top=QHBoxLayout(title); top.setContentsMargins(22,12,22,12)
        logo=label(); logo.setPixmap(QPixmap(str(LOGO)).scaled(64,64,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)); top.addWidget(logo)
        identity=QVBoxLayout(); identity.addWidget(label('Tweest MediaVault','brand')); identity.addWidget(label('POWERED BY TWEEST','eyebrow')); top.addLayout(identity); top.addStretch()
        top.addWidget(label('LOCAL • ORIGINALS UNCHANGED','muted')); outer.addWidget(title)
        body=QHBoxLayout(); body.setSpacing(0); outer.addLayout(body,1)
        sidebar=QFrame(); sidebar.setObjectName('sidebar'); sidebar.setFixedWidth(205); side=QVBoxLayout(sidebar); side.setContentsMargins(14,25,14,18); side.setSpacing(7)
        side.addWidget(label('YOUR COLLECTION','muted')); self.nav={}
        for name in ['Library','Photos','Videos','Favourites','People','Folders']:
            item=button(name,lambda checked=False,n=name:self.change_view(n)); item.setObjectName('nav'); item.setCheckable(True); item.setIcon(menu_icon(name)); item.setIconSize(QSize(21,21)); self.nav[name]=item; side.addWidget(item)
        side.addSpacing(24); side.addWidget(label('FOLDER SOURCES','muted'))
        self.source_list=QListWidget(); self.source_list.setMaximumHeight(200); self.source_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); self.source_list.setTextElideMode(Qt.TextElideMode.ElideMiddle); self.source_list.itemClicked.connect(self.source_selected); side.addWidget(self.source_list)
        side.addWidget(button('+ Add folders',self.add_folder)); side.addStretch()
        self.offline=label('Private by design\nAll processing stays here.','muted'); self.offline.setWordWrap(True); side.addWidget(self.offline)
        body.addWidget(sidebar)
        content=QWidget(); main=QVBoxLayout(content); main.setContentsMargins(24,22,24,15); main.setSpacing(12); body.addWidget(content,1)
        searchrow=QHBoxLayout(); self.search=QLineEdit(); self.search.setPlaceholderText('Describe a memory, enter a name, or search filenames…'); self.search.setMinimumHeight(44); searchrow.addWidget(self.search,1)
        self.mode=QComboBox(); self.mode.addItems(['Names, tags & filenames','Similar people','Visual scenes']); self.mode.setMinimumWidth(185); searchrow.addWidget(self.mode); main.addLayout(searchrow)
        self.search_timer=QTimer(); self.search_timer.setSingleShot(True); self.search_timer.setInterval(350); self.search_timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda *_:self.search_timer.start()); self.mode.currentIndexChanged.connect(self.refresh)
        heading=QHBoxLayout(); self.heading=label('Your memories, together.','heading'); heading.addWidget(self.heading); heading.addStretch()
        heading.addWidget(button('Rescan',self.start_scan)); self.pause_button=button('Pause',self.pause_job); self.pause_button.setEnabled(False); heading.addWidget(self.pause_button); main.addLayout(heading)
        filters=QHBoxLayout(); self.kind=QComboBox(); self.kind.addItems(['Everything','Photos','Videos']); filters.addWidget(self.kind)
        self.source_filter=QComboBox(); filters.addWidget(self.source_filter,1)
        self.year=QComboBox(); self.year.addItem('All years',''); filters.addWidget(self.year)
        self.month=QComboBox(); self.month.addItem('All months','')
        for number,name in enumerate(MONTH_NAMES,1):self.month.addItem(name,f'{number:02}')
        self.month.setAccessibleName('Filter by month'); self.month.setToolTip('Month folder, or media date when no month folder is recognised')
        filters.addWidget(self.month)
        self.ai_button=button('Index visual && faces',self.start_ai); filters.addWidget(self.ai_button)
        for combo in [self.kind,self.source_filter,self.year,self.month]: combo.currentIndexChanged.connect(self.refresh)
        main.addLayout(filters)
        self.audit_banner=QWidget(); auditrow=QHBoxLayout(self.audit_banner); auditrow.setContentsMargins(0,0,0,0)
        self.audit_text=label('','muted'); self.audit_text.setWordWrap(True); auditrow.addWidget(self.audit_text,1)
        self.audit_rescan=button('Rescan missing media',self.rescan_missing); auditrow.addWidget(self.audit_rescan)
        main.addWidget(self.audit_banner); self.audit_banner.hide()
        self.preview=QFrame(); self.preview.setObjectName('preview'); previewrow=QHBoxLayout(self.preview); previewrow.setContentsMargins(12,12,16,12)
        self.poster=label(); self.poster.setFixedSize(210,170); self.poster.setAlignment(Qt.AlignmentFlag.AlignCenter); previewrow.addWidget(self.poster)
        details=QVBoxLayout(); details.addWidget(label('IN FOCUS','eyebrow')); self.preview_title=label('Your collection starts here','previewTitle'); self.preview_title.setWordWrap(True); details.addWidget(self.preview_title)
        self.metadata=label('Add a folder to build your local library.','muted'); self.metadata.setWordWrap(True); details.addWidget(self.metadata)
        self.tag_edit=QLineEdit(); self.tag_edit.setPlaceholderText('Tags, e.g. Ivan, family, birthday'); self.tag_edit.setEnabled(False); details.addWidget(self.tag_edit)
        actions=QHBoxLayout(); self.save_tag=button('Save tags',self.save_tags,True); self.open_button=button('Open preview',self.open_preview)
        self.edit_button=button('Edit a copy…',lambda:open_photo_editor(self.current,self,self)); self.edit_button.setIcon(menu_icon('edit'))
        actions.addWidget(self.save_tag); actions.addWidget(self.open_button); actions.addWidget(self.edit_button); actions.addStretch(); details.addLayout(actions)
        self.face_row=QHBoxLayout(); details.addLayout(self.face_row); previewrow.addLayout(details,1); main.addWidget(self.preview)
        self.actions=PreviewActions(None,self); details.addWidget(self.actions)
        hint=label('Tags describe a photo. Name a person to find matching faces — offline.','muted'); hint.setWordWrap(True); details.addWidget(hint)
        self.pages=QStackedWidget(); main.addWidget(self.pages,1)
        library=QWidget(); lib=QVBoxLayout(library); lib.setContentsMargins(0,0,0,0)
        countrow=QHBoxLayout(); self.count_label=label('','muted'); countrow.addWidget(self.count_label,1)
        self.clear_filters=button('Show all media',self.reset_filters); countrow.addWidget(self.clear_filters); lib.addLayout(countrow)
        self.grid=QListView(); self.model=LibraryModel(); self.grid.setModel(self.model); self.grid.setItemDelegate(TileDelegate(self.grid)); self.grid.setViewMode(QListView.ViewMode.IconMode); self.grid.setResizeMode(QListView.ResizeMode.Adjust); self.grid.setMovement(QListView.Movement.Static); self.grid.setSpacing(5); self.grid.setGridSize(QSize(167,213)); self.grid.setUniformItemSizes(True); self.grid.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection); self.grid.clicked.connect(self.select); self.grid.doubleClicked.connect(lambda *_:self.open_preview()); lib.addWidget(self.grid,1)
        self.more=button('Load next 500',self.load_more); lib.addWidget(self.more); self.pages.addWidget(library)
        folderpage=QWidget(); fp=QVBoxLayout(folderpage); fp.addWidget(label('Manage your source folders','heading')); fp.addWidget(label('Removing a source affects this library only. Your photos and videos stay where they are.','muted'))
        self.folders=QListWidget(); fp.addWidget(self.folders,1); fa=QHBoxLayout(); fa.addWidget(button('Add folder',self.add_folder,True)); fa.addWidget(button('Remove selected folder',self.remove_source)); fa.addWidget(button('Clear library…',lambda:self.remove_source(all_sources=True))); fp.addLayout(fa); self.pages.addWidget(folderpage)
        checks=QHBoxLayout(); checks.addWidget(button('Check for missing media',lambda:self.check_folders(True))); checks.addWidget(button('Open library log',self.open_library_log)); fp.addLayout(checks)
        peoplepage=QWidget(); pp=QVBoxLayout(peoplepage); pp.addWidget(label('People you remember','heading')); pp.addWidget(label('Name a detected face in the photo preview. Search similar faces, then review possible matches.','muted'))
        self.people=QListWidget(); self.people.itemClicked.connect(self.person_selected); pp.addWidget(self.people,1); self.pages.addWidget(peoplepage)
        self.status=label('Ready · add a folder to begin.','status'); main.addWidget(self.status)
        self.timer=QTimer(self); self.timer.setInterval(1200); self.timer.timeout.connect(self.progress_refresh); self.timer.start()
        self.load_sources(); self.change_view('Library'); self.refresh()
        self.save_tag.setEnabled(False); self.open_button.setEnabled(False); self.edit_button.setEnabled(False)
        self.restore_view()
        # No automatic first-time scans. Existing cached catalog opens before any drive access.
        QTimer.singleShot(100,self.dark_titlebar)
        if Path(home).resolve()==HOME.resolve():QTimer.singleShot(1000,lambda:self.check_folders(True))

    def dark_titlebar(self):
        if sys.platform=='win32':
            try: ctypes.windll.dwmapi.DwmSetWindowAttribute(int(self.winId()),20,ctypes.byref(ctypes.c_int(1)),4)
            except Exception: pass

    def load_sources(self):
        previous=self.source_filter.currentData(); self.source_filter.blockSignals(True); self.source_filter.clear(); self.source_filter.addItem('All folders',None)
        self.source_list.clear(); self.folders.clear()
        for source in self.catalog.sources():
            self.source_filter.addItem(source['path'],source['id'])
            for widget in [self.source_list,self.folders]:
                text=Path(source['path']).name if widget is self.source_list else source['path']
                item=QListWidgetItem(text); item.setData(Qt.ItemDataRole.UserRole,source['id']); item.setToolTip(source['path']); widget.addItem(item)
        index=self.source_filter.findData(previous); self.source_filter.setCurrentIndex(max(0,index)); self.source_filter.blockSignals(False)
        current=self.year.currentData(); self.year.blockSignals(True); self.year.clear(); self.year.addItem('All years','')
        with self.catalog.connect() as db:
            for row in db.execute("SELECT DISTINCT COALESCE(NULLIF(folder_year,''),substr(date,1,4)) year FROM media WHERE date IS NOT NULL ORDER BY year DESC"):
                self.year.addItem(row[0],row[0])
        self.year.setCurrentIndex(max(0,self.year.findData(current))); self.year.blockSignals(False)

    def change_view(self,name):
        self.view=name
        for n,item in self.nav.items(): item.setChecked(n==name); item.setIcon(menu_icon(n,n==name))
        self.heading.setText('Your memories, together.' if name=='Library' else name)
        self.pages.setCurrentIndex(1 if name=='Folders' else 2 if name=='People' else 0)
        self.preview.setVisible(name not in ['Folders','People'])
        if name=='People': self.load_people()
        if name in ['Photos','Videos','Library','Favourites']:
            self.kind.blockSignals(True); self.kind.setCurrentIndex({'Library':0,'Favourites':0,'Photos':1,'Videos':2}[name]); self.kind.blockSignals(False)
        self.refresh()

    def source_selected(self,item):
        self.change_view('Library'); self.source_filter.setCurrentIndex(self.source_filter.findData(item.data(Qt.ItemDataRole.UserRole)))

    def person_selected(self,item):
        name=item.data(Qt.ItemDataRole.UserRole)
        if not name: return
        self.change_view('Library'); self.mode.setCurrentIndex(1); self.search.setText(name); self.refresh()

    def load_people(self):
        self.people.clear()
        with self.catalog.connect() as db:
            for row in db.execute('SELECT p.name,COUNT(f.id) n FROM people p LEFT JOIN faces f ON f.person=p.id WHERE p.name IS NOT NULL GROUP BY p.name ORDER BY p.name'):
                item=QListWidgetItem(f"{row['name']}  ·  {row['n']} confirmed faces  ·  click to find possible matches")
                item.setData(Qt.ItemDataRole.UserRole,row['name']); self.people.addItem(item)
        if self.people.count()==0: self.people.addItem('No named people yet. Index faces, open a photo and choose a face to name.')

    def add_folder(self):
        if self.busy(): return
        from folder_dialog import FolderSelectionDialog
        initial=next((source['path'] for source in self.catalog.sources() if Path(source['path']).is_dir()),str(Path.home()))
        picker=FolderSelectionDialog(self,initial)
        try:
            if picker.exec()==QDialog.DialogCode.Accepted:self.add_paths(picker.selected_directories)
        finally:picker.deleteLater()

    def add_paths(self,paths):
        if self.busy(): return
        self.status.setText('Checking folders for new media and verified duplicates…')
        self.run_job(lambda:prepare_imports(self.catalog,paths,self.audit_stop.is_set),self.finish_imports,kind='import')

    def finish_imports(self,result):
        selected=[]
        for path in result['accepted']:
            try:
                target=Path(path).resolve()
                # A child already belongs to its parent source; scan just that child.
                if not any(target.is_relative_to(Path(s['path']).resolve()) for s in self.catalog.sources()):self.catalog.add_source(target)
                selected.append(str(target))
            except ValueError as exc:
                log_event(self.catalog,'folder_rejected',path=str(path),detail=str(exc)); QMessageBox.information(self,'Folder source',str(exc))
        if selected:
            self.load_sources(); self.reset_filters(); self.start_scan(selected)
        elif result['skipped']:
            self.status.setText(f"{len(result['skipped'])} duplicate/unchanged folders skipped. Details: Folders → Open library log.")
        if result['errors']:QMessageBox.information(self,'Folder check','\n'.join(result['errors'][:5]))

    def open_library_log(self):
        log_event(self.catalog,'log_opened')
        try:open_in_default_app(self.catalog.home/'library-log.jsonl')
        except OSError:
            import subprocess
            subprocess.Popen([str(Path(os.environ.get('SystemRoot','C:/Windows'))/'notepad.exe'),str(self.catalog.home/'library-log.jsonl')])

    def check_folders(self,popup=False):
        if self.closing or (self.audit_worker and self.audit_worker.is_alive()):return
        self.status.setText('Checking folder filenames for missing or changed media…')
        def check():
            try:
                report=audit_library(self.catalog,self.audit_stop.is_set)
                if not self.audit_stop.is_set():self.audit_bus.result.emit((report,popup,None))
            except Exception as exc:
                if not self.audit_stop.is_set():self.audit_bus.result.emit((None,popup,str(exc)))
        self.audit_worker=threading.Thread(target=check,daemon=True); self.audit_worker.start()

    def on_audit_result(self,result):
        if self.closing:return
        report,popup,error=result
        if error:self.status.setText(f'Folder check failed: {error}'); return
        self.audit_report=report; count=report['missing']+report['changed']
        self.audit_banner.setVisible(bool(count or report['issues'])); self.audit_rescan.setVisible(bool(count))
        message=f"{report['missing']:,} media files are not indexed; {report['changed']:,} have changed. Rescan to make them available in year/month browsing."
        if report['issues']:message+=f" {len(report['issues'])} folder access issues; unavailable drives keep their cache."
        self.audit_text.setText(message)
        if not self.working:self.status.setText(message if count or report['issues'] else 'Folder check complete: supported media is up to date.')
        if count and popup and self.isVisible():
            answer=QMessageBox.question(self,'Media needs rescanning',message+'\n\nRescan these folders now? Existing labels and unchanged face analysis will be kept.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.Yes)
            if answer==QMessageBox.StandardButton.Yes:self.rescan_missing()

    def rescan_missing(self):
        if not self.audit_report or not self.audit_report['paths']:return
        paths=self.audit_report['paths']
        if self.working:
            self.rescan_pending=paths
            if self.job_kind=='ai' and self.indexer:self.indexer.stop.set(); self.indexer.pause.clear()
            self.status.setText('Rescan queued; current work will stop at a safe checkpoint or finish first.')
        else:self.reset_filters(); self.start_scan(paths)

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()

    def dropEvent(self,event):
        self.add_paths([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile() and Path(u.toLocalFile()).is_dir()])

    def busy(self):
        if self.working:
            QMessageBox.information(self,'Work in progress','Pause/resume is available. Wait for the current scan or search to finish before changing the library.'); return True
        return False

    def run_job(self,work,callback=None,kind='other'):
        if self.working:return False
        self.result_callback=callback; self.working=True; self.job_kind=kind
        def task():
            try:
                result=work()
                self.bus.result.emit(result)
            except Exception as exc:
                self.bus.message.emit('error',str(exc)); self.bus.result.emit(None)
        self.job=threading.Thread(target=task,daemon=True); self.job.start(); return True

    def start_scan(self,paths=None):
        if self.busy(): return
        if not self.catalog.sources():
            self.status.setText('Add a source folder first. Suggested source: G:\\TK RESTORE\\PHOTOS'); return
        self.indexer=Indexer(self.catalog,self.bus.message.emit); self.pause_button.setEnabled(True)
        self.status.setText('Checking source folders… Originals are read-only.')
        self.run_job(lambda:self.indexer.scan(paths if isinstance(paths,list) else None),kind='scan')

    def pause_job(self):
        if not self.indexer: return
        paused=self.indexer.pause.is_set()
        self.indexer.pause.clear() if paused else self.indexer.pause.set()
        self.pause_button.setText('Pause' if paused else 'Resume')
        self.status.setText('Resumed.' if paused else 'Paused. Completed work is saved; closing is safe.')

    def start_ai(self):
        if self.busy(): return
        if not all((MODELS/name).exists() for name in ['vision.onnx','text.onnx','yunet.onnx','sface.onnx','tokenizer.json','clip-config.json']):
            QMessageBox.information(self,'Local AI models','Local model files are not installed. Filename and tag search still works. See README.md for the one-time model setup.'); return
        if not self.catalog.count():
            self.status.setText('Add and scan a sample folder before indexing visual content and faces.'); return
        self.indexer=Indexer(self.catalog,self.bus.message.emit); self.pause_button.setEnabled(True)
        self.status.setText('Loading local AI. Browsing stays available…')
        def analyze():
            from vault_ai import LocalAI
            if self.ai is None: self.ai=LocalAI(MODELS)
            self.ai.analyze(self.catalog,self.indexer.checkpoint,self.bus.message.emit,priority=self.take_priority_person)
        self.run_job(analyze,kind='ai')

    def on_message(self,kind,message):
        if self.closing:return
        if kind=='person-ready':self.choose_person_face(message); return
        self.status.setText(message)
        if kind in ['progress','done']: self.pending_refresh=True

    def on_result(self,result):
        kind=self.job_kind; self.working=False; self.job_kind=''
        if self.closing:return
        self.model.pixmaps.clear()
        callback=self.result_callback; self.result_callback=None
        self.pause_button.setEnabled(False); self.pause_button.setText('Pause')
        self.load_sources(); self.pending_refresh=kind!='search'
        if self.current and self.catalog.row(self.current['key']): self.update_preview()
        if callback and result is not None:callback(result)
        if self.rescan_pending and not self.working:
            paths=self.rescan_pending; self.rescan_pending=None; self.reset_filters(); self.start_scan(paths); return
        if self.pending_search:
            self.pending_search=False; QTimer.singleShot(100,self.refresh)
        if kind=='scan' and self.models_ready() and self.catalog.ai_pending():
            QTimer.singleShot(180,self.auto_ai)
        if kind=='scan':self.check_folders(False)
        if kind in ['scan','ai'] and self.priority_person_key:
            key=self.take_priority_person(); QTimer.singleShot(100,lambda:self.name_person(key))

    def take_priority_person(self):
        key=self.priority_person_key; self.priority_person_key=None; return key

    def models_ready(self):
        return all((MODELS/name).exists() for name in ['vision.onnx','text.onnx','yunet.onnx','sface.onnx','tokenizer.json','clip-config.json'])

    def auto_ai(self):
        if self.closing:return
        if self.working:
            QTimer.singleShot(800,self.auto_ai); return
        if self.catalog.ai_pending(): self.start_ai()

    def progress_refresh(self):
        if self.pending_refresh:
            self.pending_refresh=False
            if self.mode.currentIndex() in [0,1]: self.refresh()

    def load_more(self): self.limit+=500; self.refresh()

    def reset_filters(self):
        for control in [self.search,self.mode,self.kind,self.source_filter,self.year,self.month]:control.blockSignals(True)
        self.search.clear(); self.mode.setCurrentIndex(0)
        for control in [self.kind,self.source_filter,self.year,self.month]:control.setCurrentIndex(0)
        for control in [self.search,self.mode,self.kind,self.source_filter,self.year,self.month]:control.blockSignals(False)
        self.limit=500; self.change_view('Library')

    def refresh(self,*_):
        if not hasattr(self,'model') or self.closing:return
        self.pending_refresh=False
        generation=self.search_generation=self.search_generation+1
        text=self.search.text().strip(); kind=['','photo','video'][self.kind.currentIndex()]
        mode=self.mode.currentIndex()
        named_person=self.catalog.has_named_person(text)
        args={'kind':kind,'source':self.source_filter.currentData(),'year':self.year.currentData() or '', 'month':self.month.currentData() or '', 'limit':self.limit,'favourite_only':self.view=='Favourites'}
        if (mode==0 and not named_person) or not text:
            matching=self.catalog.items(text=text,count_only=True,**args)
            self.show_rows(self.catalog.items(text=text,**args),matching=matching); return
        if mode==1 or (mode==0 and named_person):
            self.start_people_search(generation,text,args); return
        # Search runs off the UI thread. Source/date filters apply before similarity ranking.
        if self.working:
            self.pending_search=True
            self.status.setText('Visual/person search will be available after the current indexing job finishes.'); return
        def search():
            candidates=self.catalog.items(**{**args,'limit':1000000})
            lookup={row['key']:row for row in candidates}
            if self.ai is None:
                from vault_ai import LocalAI
                self.ai=LocalAI(MODELS)
            keys=self.ai.search(self.catalog,text,candidates)
            return generation,[lookup[k] for k in keys if k in lookup][:self.limit]
        self.status.setText('Searching locally…')
        self.run_job(search,lambda result:self.accept_search(result),kind='search')

    def start_people_search(self,generation,text,args):
        if self.people_worker and self.people_worker.is_alive():return
        def work():
            try:self.people_bus.result.emit((generation,self.catalog.people_search(text,**args),None))
            except Exception as exc:self.people_bus.result.emit((generation,[],str(exc)))
        self.status.setText('Finding named and possible matching faces locally…')
        self.people_worker=threading.Thread(target=work,daemon=True); self.people_worker.start()

    def on_people_result(self,result):
        if self.closing:return
        generation,rows,error=result
        if generation!=self.search_generation:
            QTimer.singleShot(50,self.refresh); return
        if error:self.status.setText(error)
        else:self.accept_search((generation,rows))

    def accept_search(self,result):
        generation,rows=result
        if generation==self.search_generation:
            self.show_rows(rows); self.status.setText('Possible face/scene matches need review. Filename/tag matches are exact text matches.')

    def show_rows(self,rows,matching=None):
        self.model.replace(rows)
        shown=f'{len(rows):,} of {matching:,} matching' if matching is not None else f'{len(rows):,} results shown'
        self.count_label.setText(f'{shown} · {self.catalog.count():,} cached · originals unchanged')
        has_more=len(rows)<matching if matching is not None else len(rows)>=self.limit
        self.more.setVisible(has_more)
        self.more.setText(f'Load next 500 · {matching-len(rows):,} more available' if has_more and matching is not None else 'Load next 500')

    def select(self,index):
        if not index.isValid(): return
        self.current=index.data(Qt.ItemDataRole.UserRole)
        self.update_preview()

    def update_preview(self):
        possible=self.current.get('_possible',False)
        row=self.catalog.row(self.current['key'])
        if not row: return
        row['_possible']=possible
        self.current=row; self.preview_title.setText(row['name'])
        self.actions.set_row(row)
        self.edit_button.setEnabled(row['kind']=='photo')
        self.metadata.setText(f"{row['kind'].title()} · {row['date']} · {row['width']} × {row['height']}"+(' · '+duration(row['duration']) if row['kind']=='video' else '')+(f"\n{row['error']}" if row['error'] else ''))
        if possible:self.metadata.setText('Possible face match · please review\n'+self.metadata.text())
        pixmap=QPixmap(row['thumb']) if row['thumb'] else QPixmap()
        self.poster.setPixmap(pixmap.scaled(210,170,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        self.tag_edit.setEnabled(True); self.save_tag.setEnabled(True); self.open_button.setEnabled(True); self.tag_edit.setText(', '.join(json.loads(row['tags'])))
        while self.face_row.count():
            item=self.face_row.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        faces=self.catalog.faces(row['key'])
        face_image=None
        if faces and Path(row['path']).exists():
            reader=QImageReader(row['path']); reader.setAutoTransform(True); face_image=reader.read()
        for face in faces[:10]:
            face_button=button(face['name'] or 'Name face',lambda checked=False,f=face:self.edit_face(f))
            face_button.setToolTip('Name this face; this does not rename or edit the original.')
            if face_image is not None:
                image=face_image.copy(face['x'],face['y'],face['w'],face['h'])
                face_button.setIcon(QIcon(QPixmap.fromImage(image))); face_button.setIconSize(QSize(34,34))
            self.face_row.addWidget(face_button)
        self.face_row.addStretch()

    def save_tags(self):
        if self.current:
            self.catalog.set_tags(self.current['key'],self.tag_edit.text().split(',')); self.status.setText('Tags saved. For matching untagged faces, choose Name a person. Everything stays offline.'); self.refresh()

    def toggle_favourite(self,key):
        row=self.catalog.row(key)
        if not row:return
        self.catalog.set_favourite(key,not row['favourite'])
        if self.current and self.current['key']==key:
            self.current['favourite']=not row['favourite']; self.actions.set_row(self.current)
        self.refresh()
        self.status.setText('Favourite saved locally.' if not row['favourite'] else 'Removed from favourites.')

    def name_person(self,key):
        row=self.catalog.row(key)
        if not row or row['kind']!='photo':return
        if row['ai_done']:
            self.choose_person_face(key); return
        if self.working and self.job_kind in ['scan','ai']:
            self.priority_person_key=key; self.status.setText('This photo is queued next for offline face detection. Keep browsing while it is prepared.'); return
        if self.busy():return
        if not self.models_ready():
            QMessageBox.information(QApplication.activeModalWidget() or self,'Offline models unavailable','The local face models are missing. Please reinstall the current setup; no internet account is needed.'); return
        self.status.setText('Finding faces in this photo locally…')
        def prepare():
            if self.ai is None:
                from vault_ai import LocalAI
                self.ai=LocalAI(MODELS)
            self.ai.analyze_photo(self.catalog,key)
            return key
        self.run_job(prepare,self.choose_person_face,kind='name')

    def choose_person_face(self,key):
        if self.closing:return
        row=self.catalog.row(key)
        if not row:return
        faces=self.catalog.faces(key); parent=QApplication.activeModalWidget() or self
        if not faces:
            QMessageBox.information(parent,'No clear face found','Try another photo with a clearer face. General photo tags still work.'); return
        if len(faces)==1: face=faces[0]
        else:
            chooser=QDialog(parent); chooser.setWindowTitle('Which person are you naming?'); layout=QVBoxLayout(chooser)
            layout.addWidget(label(row['name'],'muted')); controls=QGridLayout(); layout.addLayout(controls); selected=[]
            reader=QImageReader(row['path']); reader.setAutoTransform(True); image=reader.read()
            for index,value in enumerate(faces):
                option=button('Face '+str(index+1),lambda checked=False,f=value:(selected.append(f),chooser.accept()))
                option.setIcon(QIcon(QPixmap.fromImage(image.copy(value['x'],value['y'],value['w'],value['h'])))); option.setIconSize(QSize(72,72)); controls.addWidget(option,index//4,index%4)
            layout.addWidget(button('Cancel',chooser.reject))
            if chooser.exec()!=QDialog.DialogCode.Accepted or not selected:return
            face=selected[0]
        tags=json.loads(row['tags']); proposed=face['name'] or (tags[0] if len(tags)==1 else '')
        name,ok=QInputDialog.getText(QApplication.activeModalWidget() or self,'Name this person','Name for offline face matching:',text=proposed)
        if not ok or not name.strip():return
        self.catalog.name_face(face['id'],name.strip())
        if self.current and self.current['key']==key:self.update_preview()
        self.load_people(); self.refresh()
        self.status.setText(f'{name.strip()} remembered. Type this name to find confirmed photos and possible untagged matches.')
        if self.models_ready() and self.catalog.ai_pending():QTimer.singleShot(180,self.auto_ai)

    def edit_face(self,face):
        name,ok=QInputDialog.getText(self,'Name this person','Name (leave empty to remove this face’s confirmed label):',text=face['name'] or '')
        if ok:
            if name.strip(): self.catalog.name_face(face['id'],name)
            else: self.catalog.unname_face(face['id'])
            self.update_preview(); self.load_people(); self.status.setText('Person label saved. Use Similar people to find possible matches.')

    def open_preview(self):
        if not self.current: return
        MediaDialog(self.current,self,rows=self.preview_sequence()).exec()

    def preview_sequence(self):
        text=self.search.text().strip()
        named=self.catalog.has_named_person(text)
        if self.mode.currentIndex()!=0 or named:return list(self.model.rows)
        # Browsing/text filters can navigate beyond the first 500 loaded tiles.
        return self.catalog.items(text=text,kind=['','photo','video'][self.kind.currentIndex()],
            source=self.source_filter.currentData(),year=self.year.currentData() or '',month=self.month.currentData() or '',
            favourite_only=self.view=='Favourites',limit=max(self.limit,self.catalog.count()))

    def remove_source(self,all_sources=False):
        if self.busy(): return
        item=self.folders.currentItem()
        if not all_sources and not item: return
        box=QMessageBox(self); box.setWindowTitle('Clear library' if all_sources else 'Remove folder')
        box.setText('Remove all registered folders and their thumbnail/search cache?' if all_sources else 'Remove this folder and its thumbnail/search cache?')
        box.setInformativeText('Your original photos, videos and filenames will not be changed. Re-adding folders rebuilds their cache.')
        keep=QCheckBox('Keep my tags, favourites and named-face references for later'); keep.setChecked(True); box.setCheckBox(keep)
        box.setStandardButtons(QMessageBox.StandardButton.Ok|QMessageBox.StandardButton.Cancel); box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if box.exec()!=QMessageBox.StandardButton.Ok: return
        self.catalog.forget(None if all_sources else item.data(Qt.ItemDataRole.UserRole),keep.isChecked())
        self.model.pixmaps.clear(); self.current=None; self.poster.clear(); self.preview_title.setText('Choose a memory'); self.metadata.setText('Add a folder to rebuild its cache.'); self.tag_edit.clear(); self.tag_edit.setEnabled(False); self.save_tag.setEnabled(False); self.open_button.setEnabled(False)
        self.actions.set_row(None)
        self.edit_button.setEnabled(False)
        while self.face_row.count():
            control=self.face_row.takeAt(0)
            if control.widget(): control.widget().deleteLater()
        self.load_sources(); self.refresh(); self.status.setText('Library cache cleared. Originals untouched.')

    def closeEvent(self,event):
        self.closing=True; self.timer.stop(); self.search_timer.stop()
        state={'view':self.view,'text':self.search.text(),'mode':self.mode.currentIndex(),'source':self.source_filter.currentData(),'year':self.year.currentData(),'month':self.month.currentData(),'kind':self.kind.currentIndex()}
        (self.catalog.home/'view.json').write_text(json.dumps(state),encoding='utf-8')
        self.audit_stop.set()
        if self.indexer:
            self.indexer.stop.set(); self.indexer.pause.clear()
        if self.job and self.job.is_alive(): self.job.join(timeout=2)
        if self.people_worker and self.people_worker.is_alive():self.people_worker.join(timeout=2)
        if self.audit_worker and self.audit_worker.is_alive():self.audit_worker.join(timeout=2)
        super().closeEvent(event)

    def restore_view(self):
        try:
            state=json.loads((self.catalog.home/'view.json').read_text(encoding='utf-8'))
        except (OSError,ValueError): return
        # Restore cached browsing immediately; expensive AI only loads on explicit search.
        self.change_view(state.get('view','Library'))
        self.source_filter.setCurrentIndex(max(0,self.source_filter.findData(state.get('source'))))
        self.year.setCurrentIndex(max(0,self.year.findData(state.get('year',''))))
        self.month.setCurrentIndex(max(0,self.month.findData(state.get('month',''))))
        self.kind.setCurrentIndex(state.get('kind',0)); self.search.setText(state.get('text',''))
        self.mode.setCurrentIndex(0); self.refresh()

def main():
    if getattr(sys,'frozen',False) and not os.environ.get('TWEEST_DATA'):
        migrate_legacy_data(ROOT,HOME)
    if '--verify-install' in sys.argv:
        from vault_ai import LocalAI
        from PIL import Image
        started=time.perf_counter(); ai=LocalAI(MODELS)
        vector=ai.image_embedding(Image.new('RGB',(256,256),'blue'))
        text=ai.text_embedding('blue sky'); faces=ai.faces(Image.new('RGB',(256,256),'blue'))
        assert vector.shape==text.shape==(512,) and faces==[]
        HOME.mkdir(parents=True,exist_ok=True)
        # Verify the frozen editor's Pillow/Qt conversion and full export path too.
        from photo_editor import PhotoEditor
        fixture=HOME/'editor-verification-original.png'; Image.new('RGB',(240,180),'blue').save(fixture)
        before=fixture.read_bytes(); target=HOME/'editor-verification-copy.png'; target.unlink(missing_ok=True)
        global _verification_app
        _verification_app=QApplication.instance() or QApplication([])
        qa_app=_verification_app; qa_app.setStyle('Fusion'); qa_app.setStyleSheet(THEME)
        editor=PhotoEditor(fixture,HOME); editor.sliders['brightness'].setValue(40); editor.start_preview(); editor.export_to(target)
        deadline=time.monotonic()+15
        while (editor.canvas.image_item.pixmap().isNull() or editor.export_worker.is_alive() or not editor.save_button.isEnabled()) and time.monotonic()<deadline:
            qa_app.processEvents(); time.sleep(.01)
        assert target.exists() and not editor.canvas.image_item.pixmap().isNull()
        with Image.open(target) as edited:assert edited.size==(240,180) and edited.getpixel((0,0))[0]>0
        assert fixture.read_bytes()==before
        editor.grab().save(str(HOME/'editor-window.png')); editor.close(); editor.deleteLater()
        qa_app.sendPostedEvents(None,QEvent.Type.DeferredDelete); qa_app.processEvents()
        import tempfile
        import numpy as np
        with tempfile.TemporaryDirectory(dir=HOME,prefix='partial-name-check-') as temporary:
            root=Path(temporary); photos=root/'photos'; photos.mkdir()
            for name in ['named','similar']:Image.new('RGB',(40,30),'blue').save(photos/(name+'.jpg'))
            catalog=Catalog(root/'cache'); catalog.add_source(photos); Indexer(catalog).scan()
            ids=[]
            with catalog.connect() as db:
                for row in catalog.items():
                    ids.append(db.execute('INSERT INTO faces(media_key,x,y,w,h,feature) VALUES(?,?,?,?,?,?)',
                        (row['key'],0,0,10,10,np.array([1.,0.,0.],dtype=np.float32).tobytes())).lastrowid)
            catalog.name_face(ids[0],'Daphine Aine')
            for query in ['Daphine','Aine','Daphine Aine']:
                assert catalog.has_named_person(query) and len(catalog.people_search(query))==2
            from reconnect_media import reconnect
            rows=catalog.items(); old,new=rows
            catalog.set_tags(old['key'],['retained tag']); catalog.set_favourite(old['key'],True)
            Path(old['path']).rename(root/'moved-original.jpg')
            backup=reconnect(catalog,old['key'],new['key'])
            assert backup.is_file() and catalog.count()==1
            assert catalog.row(new['key'])['favourite'] and 'retained tag' in catalog.row(new['key'])['tags']
            assert len(catalog.people_search('Aine'))==1
        (HOME/'installed-check.json').write_text(json.dumps({'native_imports':True,'offline_image_text_inference':True,'face_models':True,'photo_editor_export':True,'partial_person_search':True,'reconnect_original':True,'seconds':round(time.perf_counter()-started,3)}),encoding='utf-8')
        return 0
    app=QApplication(sys.argv); app.setApplicationName('Tweest MediaVault'); app.setStyle('Fusion')
    palette=QPalette()
    for role,color in [(QPalette.ColorRole.Window,'#151625'),(QPalette.ColorRole.Base,'#20212f'),(QPalette.ColorRole.Text,'#e7e5ed'),(QPalette.ColorRole.WindowText,'#e7e5ed'),(QPalette.ColorRole.Button,'#282833'),(QPalette.ColorRole.ButtonText,'#e7e5ed'),(QPalette.ColorRole.Highlight,'#6b5730')]: palette.setColor(role,QColor(color))
    app.setPalette(palette); app.setStyleSheet(THEME)
    chrome=DarkChrome(app); app.installEventFilter(chrome)
    window=VaultWindow(); window.show()
    if '--smoke' in sys.argv:
        out=ROOT/'qa-output'; out.mkdir(exist_ok=True)
        def snapshot():
            window.grab().save(str(out/'native-window.png')); print(f'Native window ready in {time.perf_counter()-window.started:.3f}s',flush=True); app.quit()
        QTimer.singleShot(1500,snapshot)
    return app.exec()

if __name__=='__main__':
    try: sys.exit(main())
    except Exception:
        import traceback
        HOME.mkdir(parents=True,exist_ok=True)
        (HOME/'startup-error.log').write_text(traceback.format_exc(),encoding='utf-8')
        raise
