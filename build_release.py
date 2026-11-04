"""Build only inside this project. Does not install or create a desktop shortcut."""
from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parent
SETUP_NAME='TweestMediaVaultSetup-0.2.9'

def run(args):
    environment=os.environ.copy()
    windows=Path(os.environ.get('SystemRoot','C:/Windows'))
    work=(ROOT/'build').resolve()
    assert work.is_relative_to(ROOT.resolve())
    environment['PYINSTALLER_CONFIG_DIR']=str(work/'.pyinstaller-cache')
    # The host's broader PATH contains another application's versioned ICU DLL.
    # Qt uses Windows' unversioned ICU API; never collect the unrelated DLL.
    environment['PATH']=os.pathsep.join([str(Path(sys.executable).parent),str(Path(sys.base_prefix)),str(windows/'System32'),str(windows)])
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean',*args],cwd=ROOT,env=environment,check=True)

if __name__=='__main__':
    run(['--windowed','--onedir','--name','TweestMediaVault','--icon','Branding/Twisted-logo idea 04.jpg','--add-data','Branding;Branding','--add-data','assets;assets',
         '--exclude-module','PySide6.QtWebEngineCore','--exclude-module','PySide6.QtWebEngineWidgets',
         '--exclude-module','huggingface_hub','--collect-all','tokenizers','desktop_app.py'])
    app=ROOT/'dist'/'TweestMediaVault'
    shutil.copytree(ROOT/'models',app/'models',dirs_exist_ok=True)
    shutil.copy(ROOT/'README.md',app/'README.md')
    if (app/'_internal'/'icuuc.dll').exists():
        raise RuntimeError('Unexpected bundled ICU DLL: inspect its source before packaging.')
    environment=os.environ.copy(); environment['TWEEST_DATA']=str(ROOT/'qa-output'/'release-self-check')
    subprocess.run([str(app/'TweestMediaVault.exe'),'--verify-install'],env=environment,check=True)
    payload=ROOT/'build'/'payload.zip'
    with zipfile.ZipFile(payload,'w',zipfile.ZIP_DEFLATED,compresslevel=5) as archive:
        for path in app.rglob('*'):
            if path.is_file() and 'data' not in path.relative_to(app).parts:
                archive.write(path,path.relative_to(app))
    run(['--windowed','--onefile','--name',SETUP_NAME,'--icon','Branding/Twisted-logo idea 04.jpg','--add-data','Branding;Branding',
         '--add-data',str(payload)+';.', 'setup_app.py'])
    setup=ROOT/'dist'/(SETUP_NAME+'.exe')
    environment=os.environ.copy(); environment['TWEEST_SETUP_TARGET']=str(ROOT/'qa-output'/'release-installation')
    subprocess.run([str(setup),'--verify-setup'],env=environment,check=True)
    # Keep verification evidence in build records; distribution needs only the EXE.
    (ROOT/'build'/'release-checksum.txt').write_text(hashlib.sha256(setup.read_bytes()).hexdigest()+'  '+setup.name+'\n')
    print('Setup built:',setup)
