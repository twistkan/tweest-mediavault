"""Installation paths and Windows elevation, independent of the UI."""
import ctypes
import os
from pathlib import Path
import subprocess
import sys

APP_FOLDER = 'TweestMediaVault'

def installation_folder(value):
    if not str(value).strip():
        raise ValueError('Choose an installation folder.')
    selected = Path(value).expanduser().resolve()
    return selected if selected.name.casefold() == APP_FOLDER.casefold() else selected / APP_FOLDER

def default_installation_folder():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'AppData'/'Local'))) / 'Programs' / APP_FOLDER

def is_administrator():
    return bool(sys.platform == 'win32' and ctypes.windll.shell32.IsUserAnAdmin())

def is_protected_folder(destination):
    destination = Path(destination).resolve()
    roots = [os.environ.get(key) for key in ['ProgramFiles','ProgramFiles(x86)','ProgramW6432','SystemRoot']]
    return any(destination.is_relative_to(Path(root).resolve()) for root in roots if root)

def check_writable(destination):
    """Preflight the nearest existing parent before extracting anything."""
    import tempfile
    parent = Path(destination)
    while not parent.exists(): parent = parent.parent
    with tempfile.TemporaryFile(prefix='.tweest-write-check-', dir=parent):
        pass

def request_elevation(destination, shortcut):
    arguments = ['--elevated-auto-install','--target',str(destination)]
    if shortcut: arguments += ['--shortcut-path',str(shortcut)]
    else: arguments += ['--no-shortcut']
    executable = sys.executable
    if not getattr(sys,'frozen',False): arguments.insert(0,str(Path(__file__).resolve().parent/'setup_app.py'))
    execute=ctypes.windll.shell32.ShellExecuteW
    execute.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_int]
    execute.restype=ctypes.c_void_p
    result = execute(None,'runas',executable,subprocess.list2cmdline(arguments),str(Path(executable).parent),1)
    if not result or result <= 32:
        raise PermissionError('Administrator approval was cancelled or could not be obtained. Choose your user installation folder or approve the Windows prompt.')
