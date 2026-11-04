"""Multiple-directory picker with a pasteable path bar."""
from pathlib import Path
import os
from PySide6.QtCore import Qt,QDir,QUrl,QAbstractProxyModel
from PySide6.QtWidgets import (QFileDialog,QDialog,QLineEdit,QPushButton,QLabel,QWidget,
    QHBoxLayout,QGridLayout,QListView,QTreeView,QAbstractItemView)

class FolderPathEdit(QLineEdit):
    def keyPressEvent(self,event):
        if event.key() in [Qt.Key.Key_Return,Qt.Key.Key_Enter]:
            self.returnPressed.emit(); event.accept(); return
        super().keyPressEvent(event)

class FolderSelectionDialog(QFileDialog):
    def __init__(self,parent=None,initial=None):
        super().__init__(parent,'Add photo/video folders',str(initial or Path.home()))
        self.setOption(QFileDialog.Option.DontUseNativeDialog,True)
        self.setFileMode(QFileDialog.FileMode.Directory); self.setOption(QFileDialog.Option.ShowDirsOnly,True)
        self.setFilter(QDir.Filter.AllDirs|QDir.Filter.NoDotAndDotDot|QDir.Filter.Drives)
        self.setViewMode(QFileDialog.ViewMode.Detail)
        self.setLabelText(QFileDialog.DialogLabel.Accept,'Add selected folders')
        self.resize(1000,680); self.selected_directories=[]
        self.path_bar=FolderPathEdit(self.directory().absolutePath()); self.path_bar.setObjectName('folderPathEdit')
        self.path_bar.setPlaceholderText('Paste a folder path or file:// link, then Enter or Go')
        self.path_bar.setAccessibleName('Folder path')
        self.go_button=QPushButton('Go'); self.go_button.setAutoDefault(False)
        self.go_button.clicked.connect(self.go_to_path); self.path_bar.returnPressed.connect(self.go_to_path)
        top=QWidget(); top_row=QHBoxLayout(top); top_row.setContentsMargins(0,0,0,8)
        top_row.addWidget(QLabel('Folder path:')); top_row.addWidget(self.path_bar,1); top_row.addWidget(self.go_button)
        grid=self.layout()
        if isinstance(grid,QGridLayout):
            stretches=[grid.rowStretch(i) for i in range(grid.rowCount())]; columns=grid.columnCount(); items=[]
            while grid.count():
                position=grid.getItemPosition(0); items.append((grid.takeAt(0),position))
            for item,(r,c,rs,cs) in items:grid.addItem(item,r+1,c,rs,cs)
            for r,stretch in enumerate(stretches):grid.setRowStretch(r+1,stretch)
            grid.setRowStretch(0,0); grid.addWidget(top,0,0,1,columns)
            self.hint=QLabel('Ctrl+click selects separate folders; Shift+click selects a range. With no selection, Add uses the current folder.')
            self.hint.setWordWrap(True); grid.addWidget(self.hint,grid.rowCount(),0,1,columns)
        self.directoryEntered.connect(self.directory_changed)
        self.enable_multiple_selection()

    def enable_multiple_selection(self):
        for view in [self.findChild(QListView,'listView'),self.findChild(QTreeView,'treeView')]:
            if view:
                view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
                view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

    def showEvent(self,event):
        super().showEvent(event); self.enable_multiple_selection()

    def directory_changed(self,path):
        self.path_bar.setText(path); self.enable_multiple_selection()

    def go_to_path(self):
        text=self.path_bar.text().strip()
        if len(text)>=2 and text[0]==text[-1] and text[0] in ['"',"'"]:text=text[1:-1]
        if text.lower().startswith('file:'):
            url=QUrl(text)
            if not url.isLocalFile():self.hint.setText('Paste a Windows folder path or a local file:// folder link.'); return
            text=url.toLocalFile()
        elif '://' in text:
            self.hint.setText('Web links are not folders. Paste the Windows folder path or a file:// link.'); return
        target=Path(os.path.expandvars(os.path.expanduser(text)))
        if not text or not target.is_dir():
            self.hint.setText('That folder was not found or is unavailable. Check the path and reconnect its drive.'); return
        self.setDirectory(str(target.resolve()))
        for view in [self.findChild(QListView,'listView'),self.findChild(QTreeView,'treeView')]:
            if view:view.clearSelection()
        filename=self.findChild(QLineEdit,'fileNameEdit')
        if filename:filename.clear()
        self.path_bar.setText(str(target.resolve())); self.hint.setText('Select folders with Ctrl/Shift, or Add the current folder with nothing selected.')
        self.enable_multiple_selection()

    def selected_folder_paths(self):
        views=[self.findChild(QTreeView,'treeView'),self.findChild(QListView,'listView')]
        view=next((v for v in views if v and v.isVisible()),None)
        paths=[]
        if view:
            for index in view.selectionModel().selectedRows(0):
                model=index.model()
                while isinstance(model,QAbstractProxyModel):index=model.mapToSource(index); model=model.sourceModel()
                if hasattr(model,'filePath'):
                    path=Path(model.filePath(index))
                    if path.is_dir():paths.append(str(path.resolve()))
        return list(dict.fromkeys(paths))

    def accept(self):
        self.selected_directories=self.selected_folder_paths() or [self.directory().absolutePath()]
        self.selected_directories=[str(Path(path).resolve()) for path in self.selected_directories if Path(path).is_dir()]
        if not self.selected_directories:self.hint.setText('Choose an available folder first.'); return
        QDialog.accept(self)
