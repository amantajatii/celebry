import json
import os
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.contracts import APIError
from app.inference import FaceEncoder, Matcher, encoder_from_env, unit_vector
from app.main import create_app


def catalog(path, fingerprint='test-model', matrix=None):
    people = [{'id': str(i), 'name': f'Test subject {i}', 'imageUrl': 'https://example.org/image.jpg',
               'sourceUrl': 'https://example.org/source', 'license': 'Test fixture', 'attribution': 'Test fixture'}
              for i in range(6)]
    if matrix is None:
        matrix = np.zeros((6, 512), dtype=np.float32)
        matrix[:, :2] = [[1, 0], [0.8, 0.6], [0.6, 0.8], [0, 1], [-0.6, 0.8], [-1, 0]]
    np.savez(path, embeddings=matrix, metadata=json.dumps(people), fingerprint=fingerprint,
             **{f'photo_{i}':np.frombuffer(b'fixture',dtype=np.uint8) for i in range(len(people))})
    return path


@pytest.fixture
def matcher(tmp_path):
    # Only tests use fixed vectors. Production always calls the real FaceEncoder.
    encoder = SimpleNamespace(fingerprint='test-model', encode=lambda _: np.eye(1, 512)[0])
    return Matcher(encoder, catalog(tmp_path / 'catalog.npz'))


def test_cosine_ranking(matcher):
    result = matcher.match(b'unused fixture')
    assert [m.celebrity.id for m in result.matches] == ['0', '1', '2', '3', '4']
    assert [m.cosineSimilarity for m in result.matches] == pytest.approx([1, .8, .6, 0, -.6])
    assert [m.rank for m in result.matches] == [1, 2, 3, 4, 5]
    assert 'embedding' not in result.model_dump_json().lower()


@pytest.mark.parametrize('vector', [np.zeros(512), np.full(512, np.nan), np.ones(3), np.full(512, np.inf)])
def test_reject_invalid_embedding(vector):
    with pytest.raises(ValueError):
        unit_vector(vector)


def test_catalog_model_mismatch(tmp_path):
    with pytest.raises(ValueError, match='mismatch'):
        Matcher(SimpleNamespace(fingerprint='another-model'), catalog(tmp_path / 'bad.npz'))


def test_catalog_invalid_rows(tmp_path):
    with pytest.raises(ValueError):
        Matcher(SimpleNamespace(fingerprint='test-model'), catalog(tmp_path / 'bad.npz', matrix=np.zeros((6, 512))))


def test_model_lock_released_on_failure(matcher):
    def fail(_):
        raise APIError(422, 'NO_FACE', 'No face')
    matcher.encoder.encode = fail
    with pytest.raises(APIError):
        matcher.match(b'fixture')
    assert matcher.lock.acquire(blocking=False)
    try:
        with pytest.raises(APIError) as error:
            matcher.match(b'fixture')
        assert error.value.code == 'MATCHING_BUSY'
    finally:
        matcher.lock.release()


@pytest.mark.parametrize('count,code', [(0, 'NO_FACE'), (2, 'MULTIPLE_FACES')])
def test_face_count_checked_before_embedding(count, code):
    pytest.importorskip('cv2')
    pytest.importorskip('insightface')
    encoder = FaceEncoder.__new__(FaceEncoder)
    encoder.detector = SimpleNamespace(detect=lambda image, max_num: (np.zeros((count, 5)), None))
    data = BytesIO()
    Image.new('RGB', (64, 64)).save(data, format='PNG')
    with pytest.raises(APIError) as error:
        encoder.encode(data.getvalue())
    assert error.value.code == code


def test_ready_api_uses_matcher(matcher):
    with TestClient(create_app(matcher=matcher)) as client:
        assert client.get('/api/health').json()['matchingReady'] is True
        assert client.get('/api/celebrities').json()['total'] == 6
        image = client.get('/media/celebrities/0.jpg')
        assert image.status_code == 200
        assert image.headers['content-type'] == 'image/jpeg'
        assert image.headers['cache-control'] == 'public, max-age=86400'
        assert client.get('/media/celebrities/missing.jpg').status_code == 404
        photo = BytesIO()
        Image.new('RGB', (64, 64)).save(photo, format='PNG')
        response = client.post('/api/match', files={'photo': ('fixture.png', photo.getvalue(), 'image/png')}, data={'consent': 'true'})
        assert response.status_code == 200
        assert len(response.json()['matches']) == 5
        assert response.json()['metric'] == 'cosine_similarity'
        assert 'embedding' not in response.text.lower()


@pytest.mark.skipif(not os.getenv('CELEBRY_REAL_INFERENCE_TEST'), reason='Requires local models and prepared Hollywood catalog')
def test_real_inference_api():
    with TestClient(create_app()) as client:
        assert client.get('/api/health').json()['matchingReady'] is True
        data = Path('data/hollywood/zendaya.jpg').read_bytes()
        response = client.post('/api/match', files={'photo': ('reference.jpg', data, 'image/jpeg')}, data={'consent': 'true'})
        assert response.status_code == 200, response.text
        result = response.json()
        assert len(result['matches']) == 5
        assert result['matches'][0]['celebrity']['id'] == 'zendaya'
        assert result['matches'][0]['cosineSimilarity'] > .99
        blank = BytesIO()
        Image.new('RGB', (500, 500), 'white').save(blank, format='PNG')
        response = client.post('/api/match', files={'photo': ('blank.png', blank.getvalue(), 'image/png')}, data={'consent': 'true'})
        assert response.json()['error']['code'] == 'NO_FACE'
        with Image.open(BytesIO(data)) as face:
            face = face.convert('RGB')
            collage = Image.new('RGB', (face.width * 2, face.height))
            collage.paste(face, (0, 0))
            collage.paste(face, (face.width, 0))
            photo = BytesIO()
            collage.save(photo, format='JPEG')
        response = client.post('/api/match', files={'photo': ('two.jpg', photo.getvalue(), 'image/jpeg')}, data={'consent': 'true'})
        assert response.json()['error']['code'] == 'MULTIPLE_FACES'


@pytest.mark.skipif(not os.getenv('CELEBRY_REAL_INFERENCE_TEST'), reason='Requires local model/catalog and public reference files')
def test_every_real_catalog_reference_self_matches():
    from app.inference import load_matcher
    matcher = load_matcher()
    records = json.loads(Path('data/hollywood/celebrities.json').read_text())
    assert len(matcher.celebrities) == len(records)
    for reference in records:
        result = matcher.match((Path('data/hollywood') / reference['image']).read_bytes())
        assert result.catalogSize == len(records)
        assert result.matches[0].celebrity.id == reference['id']
        assert result.matches[0].cosineSimilarity > .99
        with Image.open(BytesIO(matcher.photos[reference['id']])) as display:
            assert display.format == 'JPEG'
            assert display.width <= 500 and display.height <= 700
            display.load()
