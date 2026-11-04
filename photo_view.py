"""Native photo canvas with fit, pixel zoom and drag-to-pan."""
from PySide6.QtCore import Qt,Signal
from PySide6.QtGui import QPainter,QPixmap
from PySide6.QtWidgets import QGraphicsView,QGraphicsScene,QFrame

class PhotoView(QGraphicsView):
    zoomChanged=Signal(str)
    navigateRequested=Signal(int)

    def __init__(self,parent=None):
        super().__init__(parent)
        scene=QGraphicsScene(self); self.setScene(scene); self.image_item=scene.addPixmap(QPixmap())
        self.fitted=True; self.wheel_delta=0
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setBackgroundBrush(Qt.GlobalColor.black)
        self.setRenderHints(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setAccessibleName('Photo preview; double-click to zoom, drag to pan')

    def set_photo(self,pixmap):
        self.wheel_delta=0
        self.image_item.setPixmap(pixmap); self.scene().setSceneRect(self.image_item.boundingRect())
        self.fit_photo()

    def fit_photo(self):
        self.fitted=True; self.resetTransform()
        if not self.image_item.pixmap().isNull():self.fitInView(self.image_item,Qt.AspectRatioMode.KeepAspectRatio)
        self.report_zoom()

    def report_zoom(self):
        self.zoomChanged.emit(('Fit · ' if self.fitted else '')+f'{round(self.transform().m11()*100)}%')

    def zoom_to(self,value):
        if self.image_item.pixmap().isNull():return
        self.wheel_delta=0
        value=max(.01,min(8.0,value)); current=self.transform().m11()
        self.fitted=False; self.scale(value/current,value/current); self.report_zoom()

    def zoom_in(self):self.zoom_to(self.transform().m11()*1.25)
    def zoom_out(self):self.zoom_to(self.transform().m11()/1.25)
    def actual_size(self):self.zoom_to(1.0)

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            if self.fitted:self.zoom_to(max(1.0,self.transform().m11()*2))
            else:self.fit_photo()
            event.accept()
        else:super().mouseDoubleClickEvent(event)

    def wheelEvent(self,event):
        delta=event.angleDelta().y()
        pixels=event.pixelDelta().y()
        if self.fitted:
            self.wheel_delta+=delta if delta else pixels*2
            if abs(self.wheel_delta)>=120:
                direction=-1 if self.wheel_delta>0 else 1
                self.wheel_delta=0; self.navigateRequested.emit(direction)
        else:
            # At manual zoom the wheel always pans vertically, never changes media.
            bar=self.verticalScrollBar()
            distance=pixels if pixels else round(delta/120*bar.singleStep()*3)
            bar.setValue(bar.value()-distance)
        event.accept()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.fitted:self.fit_photo()
