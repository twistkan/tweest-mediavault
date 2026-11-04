"""Dark native-widget save picker with explicit common-folder destinations."""
from pathlib import Path
from PySide6.QtCore import QStandardPaths,QUrl,Qt
from PySide6.QtWidgets import QFileDialog,QComboBox,QLabel,QWidget,QHBoxLayout,QGridLayout,QLineEdit,QDialog

class SaveLocationDialog(QFileDialog):
    def __init__(self,parent,caption,initial,filters,selected_filter,options):
        super().__init__(parent,caption,str(Path(initial).parent),filters)
        self.setOptions(options|QFileDialog.Option.DontUseNativeDialog)
        self.setAcceptMode(QFileDialog.AcceptMode.AcceptSave); self.setFileMode(QFileDialog.FileMode.AnyFile)
        self.selectNameFilter(selected_filter); self.selectFile(Path(initial).name)
        self.resize(900,620)
        self.location_combo=QComboBox(self); self.location_combo.setObjectName('saveLocationCombo')
        self.location_combo.setAccessibleName('Quick save location')
        destinations=[('Last location',str(Path(initial).parent))]
        for label,location in [('Downloads',QStandardPaths.StandardLocation.DownloadLocation),
                ('Documents',QStandardPaths.StandardLocation.DocumentsLocation),('Desktop',QStandardPaths.StandardLocation.DesktopLocation),
                ('Pictures',QStandardPaths.StandardLocation.PicturesLocation),('Videos',QStandardPaths.StandardLocation.MoviesLocation),
                ('Home',QStandardPaths.StandardLocation.HomeLocation)]:
            value=QStandardPaths.writableLocation(location)
            if value:destinations.append((label,value))
        sidebar=list(self.sidebarUrls())
        for label,value in destinations:
            self.location_combo.addItem(label,value)
            self.location_combo.setItemData(self.location_combo.count()-1,value,Qt.ItemDataRole.ToolTipRole)
            self.location_combo.model().item(self.location_combo.count()-1).setEnabled(Path(value).is_dir())
            if Path(value).is_dir():
                url=QUrl.fromLocalFile(value)
                if url not in sidebar:sidebar.append(url)
        self.setSidebarUrls(sidebar)
        quick=QWidget(self); row=QHBoxLayout(quick); row.setContentsMargins(0,0,0,8)
        row.addWidget(QLabel('Save location:')); row.addWidget(self.location_combo,1)
        grid=self.layout()
        if isinstance(grid,QGridLayout):
            stretches=[grid.rowStretch(i) for i in range(grid.rowCount())]; columns=grid.columnCount(); items=[]
            while grid.count():
                position=grid.getItemPosition(0); items.append((grid.takeAt(0),position))
            for item,(r,c,rs,cs) in items:grid.addItem(item,r+1,c,rs,cs)
            for r,stretch in enumerate(stretches):grid.setRowStretch(r+1,stretch)
            grid.setRowStretch(0,0); grid.addWidget(quick,0,0,1,columns)
        self.location_combo.currentIndexChanged.connect(self.change_location)

    def change_location(self,index):
        target=self.location_combo.itemData(index)
        if not target:return
        edit=self.findChild(QLineEdit,'fileNameEdit'); filename=Path(edit.text()).name if edit else ''
        self.setDirectory(target)
        if edit and filename:edit.setText(filename)

    @staticmethod
    def getSaveFileName(parent=None,caption='',dir='',filter='',selectedFilter='',options=QFileDialog.Option(0)):
        dialog=SaveLocationDialog(parent,caption,dir,filter,selectedFilter,options)
        try:
            if dialog.exec()==QDialog.DialogCode.Accepted:
                files=dialog.selectedFiles()
                return (files[0] if files else '',dialog.selectedNameFilter())
            return '',dialog.selectedNameFilter()
        finally:dialog.deleteLater()
