"""Project-local native installer. Source media and existing catalog data are excluded."""
import ctypes
import os
from pathlib import Path
import sys
import threading
import uuid
import zipfile
import argparse
from install_paths import installation_folder,default_installation_folder,is_administrator,is_protected_folder,check_writable,request_elevation
from PySide6.QtCore import QObject,Signal,Qt,QTimer
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QLineEdit,QFileDialog,QCheckBox,QProgressBar,QMessageBox
from PySide6.QtGui import QPixmap,QIcon

ASSETS=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))

def create_shortcut(executable,output):
    """Use the Windows Shell COM interface directly, without Windows Script Host."""
    from ctypes import wintypes
    class GUID(ctypes.Structure):
        _fields_=[('data',ctypes.c_ubyte*16)]
        @classmethod
        def from_text(cls,text): return cls((ctypes.c_ubyte*16).from_buffer_copy(uuid.UUID(text).bytes_le))
    ole=ctypes.OleDLL('ole32')
    ole.CoInitialize(None)
    shell=ctypes.c_void_p(); persist=ctypes.c_void_p()
    def call(obj,index,types,*args):
        table=ctypes.cast(obj,ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        fn=ctypes.WINFUNCTYPE(ctypes.c_long,ctypes.c_void_p,*types)(table[index])
        value=fn(obj,*args)
        if value<0: raise OSError(f'Windows Shell error: {value:#x}')
    try:
        clsid=GUID.from_text('00021401-0000-0000-c000-000000000046')
        iid=GUID.from_text('000214f9-0000-0000-c000-000000000046')
        result=ole.CoCreateInstance(ctypes.byref(clsid),None,1,ctypes.byref(iid),ctypes.byref(shell))
        if result<0: raise OSError(f'Cannot create Windows shortcut: {result:#x}')
        call(shell,20,[wintypes.LPCWSTR],str(executable))
        call(shell,9,[wintypes.LPCWSTR],str(executable.parent))
        call(shell,7,[wintypes.LPCWSTR],'Tweest MediaVault · Powered by Tweest')
        piid=GUID.from_text('0000010b-0000-0000-c000-000000000046')
        call(shell,0,[ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p)],ctypes.byref(piid),ctypes.byref(persist))
        call(persist,6,[wintypes.LPCWSTR,wintypes.BOOL],str(output),True)
    finally:
        for pointer in [persist,shell]:
            if pointer:
                table=ctypes.cast(pointer,ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
                ctypes.WINFUNCTYPE(ctypes.c_ulong,ctypes.c_void_p)(table[2])(pointer)
        ole.CoUninitialize()

def desktop_path():
    # Respect OneDrive/Desktop redirection instead of assuming USERPROFILE/Desktop.
    class GUID(ctypes.Structure): _fields_=[('data',ctypes.c_ubyte*16)]
    guid=GUID((ctypes.c_ubyte*16).from_buffer_copy(uuid.UUID('b4bfcc3a-db2c-424c-b029-7fe99a87c641').bytes_le))
    result=ctypes.c_wchar_p()
    ctypes.OleDLL('shell32').SHGetKnownFolderPath(ctypes.byref(guid),0,None,ctypes.byref(result))
    try: return Path(result.value)
    finally: ctypes.OleDLL('ole32').CoTaskMemFree(ctypes.cast(result,ctypes.c_void_p))

def install(payload,destination,progress=lambda value:None):
    destination=installation_folder(destination)
    with zipfile.ZipFile(payload) as archive:
        entries=archive.infolist()
        # Validate every entry before creating the app directory or extracting files.
        for entry in entries:
            target=(destination/entry.filename).resolve()
            if not target.is_relative_to(destination): raise ValueError('Invalid installer archive path')
            if target.is_relative_to(destination/'data'): raise ValueError('Installer must not contain personal library data')
        check_writable(destination)
        destination.mkdir(parents=True,exist_ok=True)
        for index,entry in enumerate(entries):
            target=(destination/entry.filename).resolve()
            if not target.is_relative_to(destination): raise ValueError('Invalid installer archive path')
            if target.is_relative_to(destination/'data'): raise ValueError('Installer must not contain personal library data')
            if entry.is_dir(): target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(entry) as source,target.open('wb') as out:
                    import shutil
                    shutil.copyfileobj(source,out)
            progress(int((index+1)*100/len(entries)))
    return destination/'TweestMediaVault.exe'

class Bus(QObject):
    progress=Signal(int); finished=Signal(str,str)

class Installer(QWidget):
    def __init__(self,options=None):
        super().__init__(); self.setWindowTitle('Tweest MediaVault Setup'); self.setFixedWidth(560)
        self.options=options or argparse.Namespace(target=None,shortcut_path=None,no_shortcut=False,elevated_auto_install=False)
        self.shortcut_target=Path(self.options.shortcut_path) if self.options.shortcut_path else None
        self.setStyleSheet('QWidget{background:#1d1e2d;color:#ede9f3;font:13px "Segoe UI";} QLabel{background:transparent;} QLineEdit{background:#292b38;padding:10px;border:1px solid #53505d;border-radius:6px;} QPushButton{background:#4d4028;color:#ffe3ab;padding:11px;border:1px solid #9b7940;border-radius:6px;} QProgressBar{background:#30313e;border:0;text-align:center;} QProgressBar::chunk{background:#a7823e;}')
        layout=QVBoxLayout(self); layout.setContentsMargins(28,26,28,26); layout.setSpacing(15)
        row=QHBoxLayout(); logo=QLabel(); logo.setPixmap(QPixmap(str(ASSETS/'Branding'/'Twisted-logo idea 04.jpg')).scaled(82,82,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)); row.addWidget(logo)
        title=QLabel('Tweest MediaVault\nPowered by Tweest'); title.setStyleSheet('font-size:22px;'); row.addWidget(title,1); layout.addLayout(row)
        text=QLabel('Install the native desktop app and local search models.\nYour original photos and videos are never changed.'); text.setWordWrap(True); layout.addWidget(text)
        location=installation_folder(self.options.target) if self.options.target else default_installation_folder()
        self.path=QLineEdit(str(location)); layout.addWidget(self.path); self.browse_button=QPushButton('Choose installation folder'); self.browse_button.clicked.connect(self.browse); layout.addWidget(self.browse_button)
        help_text=QLabel('Files go in a dedicated TweestMediaVault folder. Program Files requires Windows administrator approval.'); help_text.setWordWrap(True); layout.addWidget(help_text)
        self.shortcut=QCheckBox('Create a desktop shortcut'); self.shortcut.setChecked(not self.options.no_shortcut); layout.addWidget(self.shortcut)
        self.bar=QProgressBar(); self.bar.setRange(0,100); layout.addWidget(self.bar)
        self.status=QLabel('Ready. No account or separate Python installation needed.'); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.action=QPushButton('Install Tweest MediaVault'); self.action.clicked.connect(self.start); layout.addWidget(self.action)
        self.bus=Bus(); self.bus.progress.connect(self.bar.setValue); self.bus.finished.connect(self.finished); self.thread=None; self.installed=None

    def browse(self):
        location=QFileDialog.getExistingDirectory(self,'Installation folder',self.path.text())
        if location:self.path.setText(str(installation_folder(location)))

    def start(self):
        if self.installed:
            if not is_administrator(): os.startfile(str(self.installed))
            self.close(); return
        try:
            destination=installation_folder(self.path.text()); self.path.setText(str(destination))
            shortcut=self.shortcut_target or (desktop_path()/'Tweest MediaVault.lnk' if self.shortcut.isChecked() else None)
            needs_admin=is_protected_folder(destination) and not is_administrator()
            if not needs_admin:
                try: check_writable(destination)
                except PermissionError:
                    if is_administrator(): raise
                    needs_admin=True
            if needs_admin:
                self.status.setText('Approve the Windows administrator prompt to install in this folder.')
                request_elevation(destination,shortcut)
                self.close(); return
        except (OSError,ValueError) as exc:
            self.status.setText(str(exc)); return
        self.action.setEnabled(False); self.path.setEnabled(False); self.browse_button.setEnabled(False); self.shortcut.setEnabled(False); self.status.setText('Installing app and offline models…')
        def work():
            try:
                exe=install(ASSETS/'payload.zip',destination,self.bus.progress.emit)
                warning=''
                if shortcut:
                    try:create_shortcut(exe,shortcut)
                    except Exception as exc:warning='Installed, but the desktop shortcut could not be created: '+str(exc)
                self.bus.finished.emit(str(exe),warning)
            except Exception as exc:self.bus.finished.emit('',str(exc))
        self.thread=threading.Thread(target=work,daemon=True); self.thread.start()

    def finished(self,exe,message):
        self.action.setEnabled(True)
        if exe:
            self.installed=Path(exe)
            if is_administrator():
                self.status.setText(message or 'Installed. Close setup and open Tweest MediaVault from its desktop shortcut.'); self.action.setText('Finish setup')
            else:
                self.status.setText(message or 'Installed. Add a sample folder when you are ready.'); self.action.setText('Open Tweest MediaVault')
        else:
            self.status.setText('Installation failed: '+message); self.path.setEnabled(True); self.browse_button.setEnabled(True); self.shortcut.setEnabled(True)

    def closeEvent(self,event):
        if self.thread and self.thread.is_alive(): event.ignore(); return
        super().closeEvent(event)

if __name__=='__main__':
    if '--verify-setup' in sys.argv:
        import subprocess
        destination=Path(os.environ['TWEEST_SETUP_TARGET']).resolve()
        exe=install(ASSETS/'payload.zip',destination)
        create_shortcut(exe,destination/'TweestMediaVault-test.lnk')
        environment=os.environ.copy(); environment['TWEEST_DATA']=str(destination/'qa-data')
        subprocess.run([str(exe),'--verify-install'],env=environment,check=True)
        sys.exit(0)
    parser=argparse.ArgumentParser(); parser.add_argument('--target'); parser.add_argument('--shortcut-path'); parser.add_argument('--no-shortcut',action='store_true'); parser.add_argument('--elevated-auto-install',action='store_true'); options=parser.parse_args()
    app=QApplication(sys.argv); app.setStyle('Fusion'); window=Installer(options); window.show()
    def dark_titlebar():
        try: ctypes.windll.dwmapi.DwmSetWindowAttribute(int(window.winId()),20,ctypes.byref(ctypes.c_int(1)),4)
        except Exception: pass
    QTimer.singleShot(50,dark_titlebar)
    if options.elevated_auto_install: QTimer.singleShot(150,window.start)
    sys.exit(app.exec())
