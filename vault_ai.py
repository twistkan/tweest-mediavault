"""Offline CLIP scene search and opt-in named-face similarity. CPU compatible."""
from pathlib import Path
import json
import numpy as np

def unit(value):
    value = np.asarray(value, dtype=np.float32).reshape(-1)
    return value / max(float(np.linalg.norm(value)), 1e-10)

class LocalAI:
    def __init__(self, models):
        import cv2
        import onnxruntime as ort
        from tokenizers import Tokenizer
        ort.disable_telemetry_events()
        models = Path(models)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self.vision = ort.InferenceSession(str(models/'vision.onnx'), options, providers=['CPUExecutionProvider'])
        self.text = ort.InferenceSession(str(models/'text.onnx'), options, providers=['CPUExecutionProvider'])
        self.tokenizer = Tokenizer.from_file(str(models/'tokenizer.json'))
        self.tokenizer.enable_truncation(max_length=77)
        self.config = json.loads((models/'clip-config.json').read_text())
        self.detector = cv2.FaceDetectorYN.create(str(models/'yunet.onnx'), '', (640, 640), .85, .3, 5000)
        self.recognizer = cv2.FaceRecognizerSF.create(str(models/'sface.onnx'), '')

    def image_embedding(self, image):
        from PIL import ImageOps, Image
        image = ImageOps.fit(image.convert('RGB'), (224, 224), method=Image.Resampling.BICUBIC)
        values = np.asarray(image, dtype=np.float32)/255
        values = (values-np.array(self.config['image_mean'], dtype=np.float32))/np.array(self.config['image_std'], dtype=np.float32)
        pixels = values.transpose(2, 0, 1)[None, ...].astype(np.float32)
        result = self.vision.run(['image_embeds'], {'pixel_values':pixels})[0]
        return unit(result)

    def text_embedding(self, query):
        encoded = self.tokenizer.encode(query)
        values = {'input_ids': np.array([encoded.ids], dtype=np.int64), 'attention_mask':np.ones((1,len(encoded.ids)), dtype=np.int64)}
        inputs = {node.name:values[node.name] for node in self.text.get_inputs()}
        return unit(self.text.run(['text_embeds'], inputs)[0])

    def faces(self, image):
        import cv2
        values = cv2.cvtColor(np.array(image.convert('RGB')), cv2.COLOR_RGB2BGR)
        height, width = values.shape[:2]
        scale = min(1, 1280/max(height, width))
        values = cv2.resize(values, (int(width*scale), int(height*scale)))
        self.detector.setInputSize((values.shape[1], values.shape[0]))
        _, faces = self.detector.detect(values)
        result = []
        for face in [] if faces is None else faces:
            aligned = self.recognizer.alignCrop(values, face)
            embedding = unit(self.recognizer.feature(aligned))
            result.append((*(int(float(v)/scale) for v in face[:4]), embedding))
        return result

    def analyze_photo(self,catalog,key):
        from PIL import Image, ImageOps
        row=catalog.row(key)
        if not row or row['kind']!='photo': raise ValueError('Choose a photo to name a person.')
        if row['ai_done']: return catalog.faces(key)
        with Image.open(row['path']) as original:
            image=ImageOps.exif_transpose(original).convert('RGB')
        embedding=self.image_embedding(image)
        faces=self.faces(image)
        with catalog.connect() as db:
            # Do not overwrite a newer scan or records removed while analysis was running.
            current=db.execute('SELECT mtime,size FROM media WHERE key=?',(key,)).fetchone()
            if not current or current['mtime']!=row['mtime'] or current['size']!=row['size']:
                return []
            db.execute('DELETE FROM faces WHERE media_key=?',(key,))
            for x,y,w,h,feature in faces:
                db.execute('INSERT INTO faces(media_key,x,y,w,h,feature) VALUES(?,?,?,?,?,?)',(key,x,y,w,h,feature.tobytes()))
            db.execute('UPDATE media SET embedding=?,ai_done=1 WHERE key=?',(embedding.tobytes(),key))
        return catalog.faces(key)

    def analyze(self, catalog, checkpoint, notify,priority=None):
        with catalog.connect() as db:
            keys = [r[0] for r in db.execute("SELECT key FROM media WHERE kind='photo' AND error IS NULL AND ai_done=0")]
        for index, key in enumerate(keys):
            if not checkpoint():
                return
            priority_key=priority() if priority else None
            if priority_key:
                try:
                    self.analyze_photo(catalog,priority_key)
                    notify('person-ready',priority_key)
                except Exception as exc:notify('status',f'Could not prepare the selected face: {exc}')
            row = catalog.row(key)
            if not row:
                continue
            try:
                self.analyze_photo(catalog,key)
                notify('progress', f'Visual & face index · {index+1:,}/{len(keys):,}')
            except Exception as exc:
                notify('status', f"Could not analyze {row['name']}: {exc}")
        notify('done','Visual and face index ready. Face matches are suggestions for review.')

    def search(self, catalog, query, candidates):
        vector = self.text_embedding(query)
        keys = {r['key'] for r in candidates}
        with catalog.connect() as db:
            scores = [(r['key'],float(np.frombuffer(r['embedding'], dtype=np.float32) @ vector)) for r in db.execute('SELECT key,embedding FROM media WHERE embedding IS NOT NULL') if r['key'] in keys]
        return [k for k, score in sorted(scores, key=lambda r:r[1], reverse=True)[:100] if score > .15]
