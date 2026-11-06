"""Local models only. InsightFace performs five-landmark ArcFace alignment.

Sources: https://github.com/deepinsight/insightface/tree/master/python-package
https://github.com/deepinsight/insightface/blob/master/python-package/insightface/model_zoo/arcface_onnx.py
"""
import hashlib
import json
import os
from io import BytesIO
from pathlib import Path
from threading import Lock

import numpy as np
from PIL import Image, ImageOps

from .contracts import APIError, Celebrity, Match, MatchResponse

DIMENSIONS = 512
PIPELINE = 'celebry-arcface-v1:exif-rgb-bgr:max1600:det640:threshold0.5'


def unit_vector(vector):
    vector = np.asarray(vector, dtype=np.float32)
    if vector.shape != (DIMENSIONS,) or not np.isfinite(vector).all():
        raise ValueError('Expected a finite 512-dimensional embedding')
    norm = np.linalg.norm(vector)
    if norm <= 1e-12 or not np.isfinite(norm):
        raise ValueError('Invalid embedding norm')
    return vector / norm


class FaceEncoder:
    def __init__(self, detection_path: Path, recognition_path: Path):
        # Explicit files prevent model-zoo's automatic network downloads.
        digest = hashlib.sha256(PIPELINE.encode())
        for path in (detection_path, recognition_path):
            with path.open('rb') as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    digest.update(chunk)
        self.fingerprint = digest.hexdigest()
        from insightface.model_zoo import get_model
        import onnxruntime as ort
        ort.disable_telemetry_events()
        options = ort.SessionOptions()
        options.intra_op_num_threads = int(os.getenv('CELEBRY_INFERENCE_THREADS', '2'))
        if options.intra_op_num_threads < 1:
            raise ValueError('Inference threads must be positive')
        options.inter_op_num_threads = 1
        self.detector = get_model(str(detection_path), providers=['CPUExecutionProvider'], sess_options=options)
        self.recognizer = get_model(str(recognition_path), providers=['CPUExecutionProvider'], sess_options=options)
        if getattr(self.detector, 'taskname', None) != 'detection' or getattr(self.recognizer, 'taskname', None) != 'recognition':
            raise ValueError('Expected detection and ArcFace recognition models')
        self.detector.prepare(ctx_id=-1, input_size=(640, 640), det_thresh=0.5)
        self.recognizer.prepare(ctx_id=-1)

    def encode(self, data: bytes):
        import cv2
        from insightface.app.common import Face
        with Image.open(BytesIO(data)) as original:
            image = ImageOps.exif_transpose(original).convert('RGB')
            image.thumbnail((1600, 1600))
            bgr = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
        boxes, landmarks = self.detector.detect(bgr, max_num=0)
        if len(boxes) == 0:
            raise APIError(422, 'NO_FACE', 'No face found. Use a clear, front-facing photo.')
        if len(boxes) != 1:
            raise APIError(422, 'MULTIPLE_FACES', 'Choose a photo with exactly one face.')
        if landmarks is None or landmarks[0].shape != (5, 2) or not np.isfinite(landmarks[0]).all():
            raise APIError(422, 'FACE_ALIGNMENT_FAILED', 'Could not align this face. Try a clearer photo.')
        face = Face(bbox=boxes[0, :4], kps=landmarks[0], det_score=boxes[0, 4])
        try:
            return unit_vector(self.recognizer.get(bgr, face))
        except ValueError:
            raise APIError(422, 'FACE_ENCODING_FAILED', 'Could not encode this face. Try another photo.') from None


def encoder_from_env():
    return FaceEncoder(Path(os.environ['CELEBRY_DETECTION_MODEL']).resolve(),
                       Path(os.environ['CELEBRY_RECOGNITION_MODEL']).resolve())


class Matcher:
    def __init__(self, encoder, catalog_path: Path):
        self.encoder = encoder
        self.lock = Lock()
        with np.load(catalog_path, allow_pickle=False) as catalog:
            if str(catalog['fingerprint'].item()) != encoder.fingerprint:
                raise ValueError('Model or preprocessing mismatch; rebuild celebrity embeddings')
            self.celebrities = [Celebrity.model_validate(item) for item in json.loads(str(catalog['metadata'].item()))]
            matrix = np.asarray(catalog['embeddings'], dtype=np.float32)
            self.photos = {}
            for index, person in enumerate(self.celebrities):
                photo = catalog[f'photo_{index}']
                if photo.dtype != np.uint8 or photo.ndim != 1 or not 0 < len(photo) <= 1024 * 1024:
                    raise ValueError('Invalid public display photo; rebuild the catalog')
                self.photos[person.id] = photo.tobytes()
        if len(self.celebrities) < 5 or len({c.id for c in self.celebrities}) != len(self.celebrities):
            raise ValueError('At least five unique celebrities are required')
        if matrix.shape != (len(self.celebrities), DIMENSIONS):
            raise ValueError('Catalog dimensions do not match its metadata')
        self.embeddings = np.stack([unit_vector(row) for row in matrix])

    def match(self, data: bytes):
        if not self.lock.acquire(blocking=False):
            raise APIError(503, 'MATCHING_BUSY', 'Analysis is busy. Please try again shortly.')
        try:
            query = unit_vector(self.encoder.encode(data))
            scores = np.clip(self.embeddings @ query, -1, 1)
            order = np.argsort(-scores, kind='stable')[:5]
            return MatchResponse(catalogSize=len(self.celebrities), matches=[Match(rank=rank, celebrity=self.celebrities[int(i)],
                                               cosineSimilarity=float(scores[i]))
                                          for rank, i in enumerate(order, 1)])
        finally:
            self.lock.release()


def load_matcher():
    keys = ('CELEBRY_DETECTION_MODEL', 'CELEBRY_RECOGNITION_MODEL', 'CELEBRY_CATALOG')
    if not all(os.getenv(key) for key in keys):
        return None
    return Matcher(encoder_from_env(), Path(os.environ['CELEBRY_CATALOG']))
