"""Explicit one-time model installation; the desktop app never downloads models."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent / 'models'
CLIP_BASE = 'https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/d15189d/'
FILES = {
    'vision.onnx': CLIP_BASE+'onnx/vision_model_quantized.onnx',
    'text.onnx': CLIP_BASE+'onnx/text_model_quantized.onnx',
    'tokenizer.json': CLIP_BASE+'tokenizer.json',
    'clip-config.json': CLIP_BASE+'preprocessor_config.json',
    'clip-license.txt': 'https://raw.githubusercontent.com/openai/CLIP/main/LICENSE',
    'yunet.onnx': 'https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx',
    'sface.onnx': 'https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx',
    'sface-license.txt': 'https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/face_recognition_sface/LICENSE',
    'yunet-license.txt': 'https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/face_detection_yunet/LICENSE',
}

def download(entry):
    name, url = entry
    target = ROOT/name
    if target.exists():
        return name, {'url': url, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
    temp = ROOT/(name+'.part')
    request = urllib.request.Request(url, headers={'User-Agent':'TweestMediaVault-model-setup/0.1'})
    with urllib.request.urlopen(request, timeout=90) as response, temp.open('wb') as out:
        total = 0
        while chunk := response.read(1024*1024):
            out.write(chunk); total += len(chunk)
        if name.endswith('.onnx') and total < 100000:
            raise ValueError(f'{name}: response was not a model file')
    temp.replace(target)
    print(f'{name}: {total:,} bytes', flush=True)
    return name, {'url':url, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}

if __name__ == '__main__':
    ROOT.mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        manifest = dict(pool.map(download, FILES.items()))
    (ROOT/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Models installed locally. No personal media was accessed.')
