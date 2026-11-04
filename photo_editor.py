"""Native offline Edit a copy workspace."""
from dataclasses import replace
from pathlib import Path
import sys
import threading
import json
from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt,QTimer,Signal,QObject,QRectF,QStandardPaths
from PySide6.QtGui import QPixmap,QPen,QColor,QIcon
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QWidget,QLabel,QPushButton,QSlider,
    QComboBox,QScrollArea,QFileDialog,QMessageBox,QApplication,QGridLayout,QGroupBox,QSpinBox,QProgressBar,QFrame)
from edit_core import EditState,EditHistory,load_photo,render,geometry,export_copy
from media_actions import file_share_mime,show_in_explorer
from photo_view import PhotoView
from save_dialog import SaveLocationDialog as QFileDialog

ASSETS=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))

class EditorBus(QObject):
    preview=Signal(object)
    exported=Signal(object)

class CropCanvas(PhotoView):
    selectionChanged=Signal(object)
    def __init__(self):
        super().__init__(); self.cropping=False; self.selection=QRectF(); self.anchor=None; self.aspect=None
    def start_crop(self,normalised,aspect):
        self.cropping=True; self.aspect=aspect; self.setDragMode(self.DragMode.NoDrag)
        area=self.image_item.boundingRect(); x0,y0,x1,y1=normalised
        self.selection=QRectF(x0*area.width(),y0*area.height(),(x1-x0)*area.width(),(y1-y0)*area.height())
        if aspect and not self.selection.isEmpty():
            width=min(self.selection.width(),self.selection.height()*aspect); height=width/aspect
            center=self.selection.center(); self.selection=QRectF(center.x()-width/2,center.y()-height/2,width,height)
        self.viewport().update()
    def stop_crop(self):
        self.cropping=False; self.anchor=None; self.setDragMode(self.DragMode.ScrollHandDrag); self.viewport().update()
    def normalised_crop(self):
        area=self.image_item.boundingRect(); selected=self.selection.intersected(area)
        if selected.width()<2 or selected.height()<2:return None
        return (selected.left()/area.width(),selected.top()/area.height(),selected.right()/area.width(),selected.bottom()/area.height())
    def mousePressEvent(self,event):
        if self.cropping and not getattr(self,'hide_guides',False) and event.button()==Qt.MouseButton.LeftButton:
            area=self.image_item.boundingRect(); point=self.mapToScene(event.position().toPoint())
            self.anchor=(max(0,min(area.width(),point.x())),max(0,min(area.height(),point.y())))
            event.accept()
        else:super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.cropping and not getattr(self,'hide_guides',False) and self.anchor is not None:
            area=self.image_item.boundingRect(); point=self.mapToScene(event.position().toPoint()); x,y=self.anchor
            dx=max(0,min(area.width(),point.x()))-x; dy=max(0,min(area.height(),point.y()))-y
            width,height=abs(dx),abs(dy)
            if self.aspect:
                width=max(width,height*self.aspect); height=width/self.aspect
                factor=min(1,(area.width()-x if dx>=0 else x)/max(width,.001),(area.height()-y if dy>=0 else y)/max(height,.001))
                width*=factor; height*=factor
            self.selection=QRectF(x if dx>=0 else x-width,y if dy>=0 else y-height,width,height)
            self.selectionChanged.emit(self.normalised_crop()); self.viewport().update(); event.accept()
        else:super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        if self.cropping and not getattr(self,'hide_guides',False) and event.button()==Qt.MouseButton.LeftButton:
            self.mouseMoveEvent(event); self.anchor=None; event.accept()
        else:super().mouseReleaseEvent(event)
    def mouseDoubleClickEvent(self,event):
        if self.cropping:event.accept()
        else:super().mouseDoubleClickEvent(event)
    def drawForeground(self,painter,rect):
        super().drawForeground(painter,rect)
        if getattr(self,'hide_guides',False):return
        area=self.selection if self.cropping and not self.selection.isEmpty() else self.image_item.boundingRect()
        painter.setPen(QPen(QColor('#f5c45b' if self.cropping else '#55ffffff'),0))
        if self.cropping:painter.drawRect(area)
        for fraction in [1/3,2/3]:
            painter.drawLine(area.left()+area.width()*fraction,area.top(),area.left()+area.width()*fraction,area.bottom())
            painter.drawLine(area.left(),area.top()+area.height()*fraction,area.right(),area.top()+area.height()*fraction)

class PhotoEditor(QDialog):
    def __init__(self,path,cache,parent=None):
        super().__init__(parent); self.path=Path(path); self.cache=Path(cache)
        self.original=load_photo(path); self.preview_source=self.original.copy(); self.preview_source.thumbnail((1500,1500))
        self.history=EditHistory(); self.state=self.history.current; self.saved_state=self.state
        self.worker=None; self.export_worker=None; self.generation=0; self.crop_initialise=False; self.closing=False; self.comparing=False
        self.setWindowTitle('Edit a copy · '+self.path.name)
        self.setWindowFlags((self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)|Qt.WindowType.WindowMinimizeButtonHint|Qt.WindowType.WindowMaximizeButtonHint|Qt.WindowType.WindowSystemMenuHint|Qt.WindowType.WindowCloseButtonHint)
        area=self.screen().availableGeometry(); self.resize(min(1460,area.width()-40),min(940,area.height()-60))
        self.setMinimumSize(min(950,area.width()-40),min(650,area.height()-60))
        self.bus=EditorBus(); self.bus.preview.connect(self.on_preview); self.bus.exported.connect(self.on_exported)
        layout=QVBoxLayout(self); layout.setContentsMargins(18,16,18,16); layout.setSpacing(12)
        top=QHBoxLayout(); title=QLabel('EDIT A COPY'); title.setObjectName('heading'); top.addWidget(title); top.addStretch()
        self.undo_button=self.make_button('Undo',self.undo); self.redo_button=self.make_button('Redo',self.redo)
        self.reset_button=self.make_button('Reset',lambda:self.commit(EditState()))
        self.compare_button=QPushButton('After · show Before'); self.compare_button.setCheckable(True); self.compare_button.toggled.connect(self.compare)
        self.compare_button.setStyleSheet('QPushButton:checked{background:#51442c;border-color:#b89146;}')
        for control in [self.undo_button,self.redo_button,self.reset_button,self.compare_button]:top.addWidget(control)
        layout.addLayout(top); layout.addWidget(QLabel(self.path.name+' · Original stays unchanged · Edits remain temporary until exported'))
        body=QHBoxLayout(); self.canvas=CropCanvas(); body.addWidget(self.canvas,1)
        settings=QWidget(); settings.setFixedWidth(310); panel=QVBoxLayout(settings); panel.setContentsMargins(8,0,8,0)
        geometry_box=QGroupBox('Crop and geometry'); tools=QVBoxLayout(geometry_box)
        transforms=QGridLayout()
        for index,(text,callback) in enumerate([
            ('Rotate left',lambda:self.transform(turns=(self.state.turns-1)%4)),
            ('Rotate right',lambda:self.transform(turns=(self.state.turns+1)%4)),
            ('Flip horizontal',lambda:self.transform(flip_x=not self.state.flip_x)),
            ('Flip vertical',lambda:self.transform(flip_y=not self.state.flip_y))]):transforms.addWidget(self.make_button(text,callback),index//2,index%2)
        tools.addLayout(transforms)
        self.aspect=QComboBox(); self.aspect.addItems(['Free crop','Original ratio','Square · 1:1','Landscape · 4:3','Landscape · 16:9','Portrait · 3:4','Portrait · 9:16']); tools.addWidget(self.aspect)
        self.aspect.currentIndexChanged.connect(self.aspect_changed)
        crop_row=QHBoxLayout(); self.crop_button=self.make_button('Select crop',self.begin_crop)
        self.apply_crop_button=self.make_button('Apply crop',self.apply_crop); self.cancel_crop_button=self.make_button('Cancel',self.cancel_crop)
        for control in [self.crop_button,self.apply_crop_button,self.cancel_crop_button]:crop_row.addWidget(control)
        tools.addLayout(crop_row); tools.addWidget(QLabel('Drag a crop rectangle; the grid helps align horizons.'))
        self.sliders={}; self.values={}; self.add_slider(tools,'straighten','Straighten',-150,150)
        tools.addWidget(QLabel('Straightening trims empty edges. Geometry changes reset the crop.'))
        panel.addWidget(geometry_box)
        tones=QGroupBox('Light and tone'); tone_layout=QVBoxLayout(tones)
        for key,title,low,high in [('exposure','Exposure',-20,20),('brightness','Brightness',-100,100),('contrast','Contrast',-100,100),('highlights','Highlights',-100,100),('shadows','Shadows',-100,100)]:self.add_slider(tone_layout,key,title,low,high)
        panel.addWidget(tones)
        colours=QGroupBox('Color'); colour_layout=QVBoxLayout(colours)
        self.add_slider(colour_layout,'saturation','Saturation',-100,100)
        self.add_slider(colour_layout,'vibrance','Vibrance',-100,100)
        colour_layout.addWidget(QLabel('Saturation −100 makes black-and-white. Vibrance favours muted colours.'))
        panel.addWidget(colours)
        export_box=QGroupBox('Export'); export_layout=QVBoxLayout(export_box)
        self.format=QComboBox(); self.format.addItems(['JPEG','PNG']); export_layout.addWidget(self.format)
        quality_row=QHBoxLayout(); quality_row.addWidget(QLabel('JPEG quality')); self.quality=QSpinBox(); self.quality.setRange(60,100); self.quality.setValue(92); quality_row.addWidget(self.quality); export_layout.addLayout(quality_row)
        self.format.currentIndexChanged.connect(lambda index:self.quality.setEnabled(index==0))
        export_layout.addWidget(QLabel('JPEG flattens transparency onto white.\nExports omit camera/location metadata.'))
        panel.addWidget(export_box); panel.addStretch()
        for item in settings.findChildren(QLabel):item.setWordWrap(True)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(settings); scroll.setFixedWidth(334); body.addWidget(scroll)
        self.settings=scroll; layout.addLayout(body,1)
        bottom=QHBoxLayout(); bottom.addWidget(self.make_button('−',self.canvas.zoom_out)); bottom.addWidget(self.make_button('+',self.canvas.zoom_in)); bottom.addWidget(self.make_button('Fit',self.canvas.fit_photo))
        self.zoom_label=QLabel(); self.canvas.zoomChanged.connect(self.zoom_label.setText); bottom.addWidget(self.zoom_label); bottom.addStretch()
        self.save_button=self.make_button('Save edited copy…',self.save_copy); self.share_button=self.make_button('Share edited copy',self.share_copy)
        self.save_button.setObjectName('primary'); self.share_button.setObjectName('primary'); bottom.addWidget(self.save_button); bottom.addWidget(self.share_button); layout.addLayout(bottom)
        self.status=QLabel('Ready · changes affect only this temporary edit'); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.progress=QProgressBar(); self.progress.setRange(0,0); self.progress.hide(); layout.addWidget(self.progress)
        self.result_panel=QFrame(); self.result_panel.setObjectName('ExportResult')
        self.result_panel.setStyleSheet('QFrame#ExportResult{background:#203831;border:1px solid #4a8064;border-radius:6px;}')
        result_row=QHBoxLayout(self.result_panel); self.result_label=QLabel(); self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); result_row.addWidget(self.result_label,1)
        result_row.addWidget(self.make_button('Show saved copy',self.show_export)); layout.addWidget(self.result_panel); self.result_panel.hide()
        self.debounce=QTimer(self); self.debounce.setSingleShot(True); self.debounce.setInterval(75); self.debounce.timeout.connect(self.start_preview)
        self.sync_controls(); self.schedule_preview()

    def make_button(self,text,callback):
        button=QPushButton(text); button.clicked.connect(callback); return button
    def add_slider(self,layout,key,title,low,high):
        row=QHBoxLayout(); row.addWidget(QLabel(title),1); value=QLabel('0'); self.values[key]=value; row.addWidget(value); layout.addLayout(row)
        slider=QSlider(Qt.Orientation.Horizontal); slider.setRange(low,high); slider.setAccessibleName(title); self.sliders[key]=slider; layout.addWidget(slider)
        slider.valueChanged.connect(lambda n,k=key:self.slider_changed(k,n)); slider.sliderReleased.connect(lambda:self.commit(self.state))
    def slider_changed(self,key,value):
        value=value/10 if key in ['exposure','straighten'] else value
        changes={key:value}
        if key=='straighten':
            if self.canvas.cropping:self.cancel_crop()
            changes['crop']=(0.,0.,1.,1.)
        new=replace(self.state,**changes)
        if self.sliders[key].isSliderDown():self.state=new; self.schedule_preview(); self.update_values()
        else:self.commit(new)
    def update_values(self):
        for key,label in self.values.items():
            value=getattr(self.state,key); label.setText(f'{value:+.1f}'+(' EV' if key=='exposure' else '°') if key in ['exposure','straighten'] else f'{value:+d}')
    def sync_controls(self):
        for key,slider in self.sliders.items():
            slider.blockSignals(True); slider.setValue(round(getattr(self.state,key)*(10 if key in ['exposure','straighten'] else 1))); slider.blockSignals(False)
        self.update_values(); self.undo_button.setEnabled(self.history.index>0); self.redo_button.setEnabled(self.history.index<len(self.history.states)-1)
        self.apply_crop_button.setVisible(self.canvas.cropping); self.cancel_crop_button.setVisible(self.canvas.cropping)
        self.crop_button.setVisible(not self.canvas.cropping)
    def commit(self,state):
        self.history.push(state); self.state=state; self.sync_controls(); self.schedule_preview()
    def undo(self):self.cancel_crop(); self.state=self.history.undo(); self.sync_controls(); self.schedule_preview()
    def redo(self):self.cancel_crop(); self.state=self.history.redo(); self.sync_controls(); self.schedule_preview()
    def transform(self,**changes):
        self.cancel_crop(); self.commit(replace(self.state,crop=(0.,0.,1.,1.),**changes))
    def crop_aspect(self):
        index=self.aspect.currentIndex()
        if index==0:return None
        if index==1:
            size=geometry(self.preview_source,replace(self.state,straighten=0,crop=(0.,0.,1.,1.))).size
            return size[0]/size[1]
        return [1,4/3,16/9,3/4,9/16][index-2]
    def begin_crop(self):
        self.crop_initialise=True
        self.canvas.start_crop(self.state.crop,self.crop_aspect()); self.sync_controls(); self.schedule_preview()
        self.apply_crop_button.setEnabled(False)
        self.status.setText('Drag the crop rectangle, then Apply crop. Choose an aspect ratio before drawing.')
    def aspect_changed(self,*_):
        if self.canvas.cropping:self.canvas.start_crop(self.canvas.normalised_crop() or self.state.crop,self.crop_aspect())
    def apply_crop(self):
        crop=self.canvas.normalised_crop()
        if crop is None:self.status.setText('Drag a larger crop rectangle first.'); return
        self.canvas.stop_crop(); self.commit(replace(self.state,crop=crop))
    def cancel_crop(self):
        if self.canvas.cropping:self.canvas.stop_crop(); self.sync_controls(); self.schedule_preview()
    def compare(self,pressed):
        self.comparing=pressed
        if pressed:self.comparison_crop=self.canvas.normalised_crop() if self.canvas.cropping else None
        self.compare_button.blockSignals(True); self.compare_button.setChecked(pressed); self.compare_button.blockSignals(False)
        self.compare_button.setText('Before · show After' if pressed else 'After · show Before')
        self.canvas.hide_guides=pressed
        self.settings.setEnabled(not pressed)
        if pressed:
            self.generation+=1; self.debounce.stop(); self.canvas.set_photo(QPixmap.fromImage(ImageQt(self.preview_source)))
        else:self.schedule_preview()
    def schedule_preview(self):
        self.generation+=1; self.debounce.start()
    def start_preview(self):
        if self.closing or self.comparing:return
        if self.worker and self.worker.is_alive():self.debounce.start(40); return
        generation=self.generation; state=self.state; crop_mode=self.canvas.cropping
        def work():
            try:self.bus.preview.emit((generation,render(self.preview_source,state,apply_crop=not crop_mode),None))
            except Exception as exc:self.bus.preview.emit((generation,None,str(exc)))
        self.worker=threading.Thread(target=work,daemon=True); self.worker.start()
    def on_preview(self,result):
        generation,image,error=result
        if self.closing or self.comparing or generation!=self.generation:return
        if error:self.status.setText('Preview error: '+error); return
        crop=self.canvas.selection if self.canvas.cropping else None
        self.canvas.set_photo(QPixmap.fromImage(ImageQt(image)))
        if crop is not None:
            if self.crop_initialise:self.canvas.start_crop(self.state.crop,self.crop_aspect()); self.crop_initialise=False
            else:self.canvas.selection=crop; self.canvas.viewport().update()
            self.apply_crop_button.setEnabled(True)
    def save_copy(self):
        self.choose_export(False)
    def share_copy(self):
        self.choose_export(True)
    def export_folder(self):
        fallback=Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation) or str(Path.home()))
        try:
            settings=json.loads((self.cache/'editor-preferences.json').read_text(encoding='utf-8'))
            selected=Path(settings['last_export_directory'])
            if selected.is_dir():return selected
        except (OSError,ValueError,KeyError,TypeError):pass
        return fallback
    def choose_export(self,share=False):
        if not self.prepare_export():return
        suffix='.jpg' if self.format.currentIndex()==0 else '.png'
        folder=self.export_folder(); initial=folder/(self.path.stem+'-edited'+suffix); number=2
        while initial.exists():initial=folder/(self.path.stem+f'-edited-{number}'+suffix); number+=1
        target,selected=QFileDialog.getSaveFileName(self,'Save edited copy for sharing' if share else 'Save an edited copy',str(initial),'JPEG (*.jpg *.jpeg);;PNG (*.png)',
            'JPEG (*.jpg *.jpeg)' if suffix=='.jpg' else 'PNG (*.png)',options=QFileDialog.Option.DontUseNativeDialog|QFileDialog.Option.DontConfirmOverwrite)
        if not target:return
        if not Path(target).suffix:target+=('.png' if selected.startswith('PNG') else '.jpg')
        self.export_to(Path(target),share)
    def export_to(self,target,share=False):
        if self.export_worker and self.export_worker.is_alive():return
        if not self.prepare_export():return
        state=self.state; quality=self.quality.value(); self.set_export_busy(True); self.status.setText('Rendering the full-resolution edited copy…')
        def work():
            try:self.bus.exported.emit((export_copy(self.path,self.original,state,target,quality),share,state,None))
            except Exception as exc:self.bus.exported.emit((target,share,state,str(exc)))
        self.export_worker=threading.Thread(target=work,daemon=True); self.export_worker.start()
    def set_export_busy(self,busy):
        for control in [self.settings,self.undo_button,self.redo_button,self.reset_button,self.compare_button,self.save_button,self.share_button]:control.setEnabled(not busy)
        if not busy:self.sync_controls()
        self.progress.setVisible(busy); self.save_button.setText('Saving…' if busy else 'Save edited copy…')
    def on_exported(self,result):
        if self.closing:return
        target,share,state,error=result; self.set_export_busy(False)
        if error:self.status.setText('Could not export: '+error); QMessageBox.information(self,'Save edited copy',error); return
        self.saved_state=state
        try:
            self.cache.mkdir(parents=True,exist_ok=True)
            (self.cache/'editor-preferences.json').write_text(json.dumps({'last_export_directory':str(Path(target).parent.resolve())}),encoding='utf-8')
        except OSError:pass  # A saved copy remains successful if preferences cannot be remembered.
        self.last_export=target; self.result_label.setText('Edited copy saved: '+str(target)); self.result_panel.show()
        if share:
            QApplication.clipboard().setMimeData(file_share_mime(target)); self.status.setText('Edited file copied for sharing. Paste it into your chosen app. Nothing was sent automatically. Saved at '+str(target))
        else:self.status.setText('Edited copy saved: '+str(target))
    def prepare_export(self):
        if self.canvas.cropping:
            if self.crop_initialise:
                QMessageBox.information(self,'Crop is preparing','The crop preview is still preparing. Try saving again when the crop rectangle is ready.'); return False
            crop=getattr(self,'comparison_crop',None) if self.comparing else self.canvas.normalised_crop()
            if crop is None:
                QMessageBox.information(self,'Select a crop','Drag a larger crop rectangle or cancel cropping before saving.'); return False
            self.canvas.stop_crop(); self.commit(replace(self.state,crop=crop))
        if self.comparing:self.compare(False)
        return True
    def show_export(self):
        try:show_in_explorer(self.last_export)
        except OSError as exc:QMessageBox.information(self,'Saved copy unavailable',str(exc))
    def closeEvent(self,event):
        if self.export_worker and self.export_worker.is_alive():
            QMessageBox.information(self,'Export in progress','Wait for the edited copy to finish saving.'); event.ignore(); return
        if self.state!=self.saved_state:
            answer=QMessageBox.question(self,'Discard temporary edits?','Close without saving the latest edits? Your original remains unchanged.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:event.ignore(); return
        self.closing=True; self.debounce.stop()
        if self.worker and self.worker.is_alive():self.worker.join()
        self.canvas.set_photo(QPixmap())
        self.original.close(); self.preview_source.close(); super().closeEvent(event)

    def reject(self):
        if self.closing:super().reject()
        else:self.close()
