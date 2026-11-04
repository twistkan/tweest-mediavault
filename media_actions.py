"""Local preview actions; no upload or network-sharing service."""
import os
from pathlib import Path
import shutil
import subprocess

def original_file(value):
    path=Path(value)
    if not path.is_file():
        raise FileNotFoundError('The original is unavailable. Reconnect its source drive to open, copy or share it.')
    return path

def show_in_explorer(value):
    path=original_file(value)
    explorer=Path(os.environ.get('SystemRoot','C:/Windows'))/'explorer.exe'
    subprocess.Popen([str(explorer),'/select,',str(path.resolve())])

def open_in_default_app(value):
    """Ask Windows to open the original with its registered default application."""
    path=original_file(value)
    os.startfile(str(path.resolve()))

def save_copy(source,destination):
    source=original_file(source)
    destination=Path(destination)
    if destination.resolve()==source.resolve() or (destination.exists() and os.path.samefile(source,destination)):
        raise ValueError('Choose a different file. The original cannot be overwritten.')
    # Exclusive creation avoids replacing any existing file, including another original.
    with source.open('rb') as incoming,destination.open('xb') as outgoing:
        shutil.copyfileobj(incoming,outgoing)
    return destination

def file_share_mime(value):
    from PySide6.QtCore import QMimeData,QUrl
    path=original_file(value)
    mime=QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(path.resolve()))])
    return mime

def media_copy_mime(value,kind):
    """Offer both an original file and orientation-correct pixels for paste targets."""
    mime=file_share_mime(value)
    if kind=='photo':
        from PySide6.QtGui import QImageReader
        reader=QImageReader(str(original_file(value))); reader.setAutoTransform(True)
        image=reader.read()
        # Unsupported decoders still leave a valid original-file clipboard payload.
        if not image.isNull():mime.setImageData(image)
    return mime
