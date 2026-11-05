from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from starlette.datastructures import UploadFile

from app.main import MAX_FILE_BYTES, create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def picture(fmt='PNG'):
    buffer = BytesIO()
    Image.new('RGB', (64, 64), 'coral').save(buffer, format=fmt)
    return buffer.getvalue()


def upload(client, data=None, mime='image/png', consent='true'):
    return client.post('/api/match', files={'photo': ('selfie', picture() if data is None else data, mime)}, data={'consent': consent})


def test_health_and_empty_dataset(client):
    assert client.get('/api/health').json()['matchingReady'] is False
    assert client.get('/api/health').headers['cache-control'] == 'no-store'
    assert client.get('/api/celebrities').json() == {'celebrities': [], 'total': 0}


@pytest.mark.parametrize('fmt,mime', [('PNG', 'image/png'), ('JPEG', 'image/jpeg'), ('WEBP', 'image/webp')])
def test_real_images_return_honest_unavailable(client, fmt, mime):
    response = upload(client, picture(fmt), mime)
    assert response.status_code == 503
    assert response.json()['error']['code'] == 'MATCHING_NOT_READY'
    assert 'embedding' not in response.text


@pytest.mark.parametrize('data,mime,status,code', [
    (b'', 'image/png', 422, 'EMPTY_IMAGE'),
    (b'not an image', 'image/png', 422, 'INVALID_IMAGE'),
    (b'<svg/>', 'image/svg+xml', 415, 'UNSUPPORTED_IMAGE'),
    (picture(), 'image/jpeg', 415, 'IMAGE_TYPE_MISMATCH'),
    (b'x' * (MAX_FILE_BYTES + 1), 'image/png', 413, 'IMAGE_TOO_LARGE'),
])
def test_invalid_images(client, data, mime, status, code):
    response = upload(client, data, mime)
    assert response.status_code == status
    assert response.json()['error']['code'] == code


def test_consent_and_required_fields(client):
    assert upload(client, consent='false').json()['error']['code'] == 'CONSENT_REQUIRED'
    response = client.post('/api/match', files={'photo': ('x.png', picture(), 'image/png')})
    assert response.status_code == 422
    assert client.post('/api/match', json={}).status_code == 415


def test_pixel_limit(client):
    buffer = BytesIO()
    Image.new('1', (5000, 4001)).save(buffer, format='PNG')
    response = upload(client, buffer.getvalue())
    assert response.status_code == 413
    assert response.json()['error']['code'] == 'IMAGE_DIMENSIONS_TOO_LARGE'


def test_body_limit_without_content_length(client):
    response = client.post('/api/match', content=iter([b'x' * (1024 * 1024)] * 11), headers={'Content-Type': 'multipart/form-data; boundary=test'})
    assert response.status_code == 413


def test_rate_limit(monkeypatch):
    monkeypatch.setenv('CELEBRY_RATE_LIMIT', '2')
    client = TestClient(create_app())
    upload(client)
    upload(client)
    response = upload(client)
    assert response.status_code == 429
    assert response.headers['Retry-After'] == '60'
    assert client.get('/api/health').status_code == 200


def test_temp_file_is_closed(client, monkeypatch):
    closed = []
    original = UploadFile.close

    async def record_close(self):
        await original(self)
        closed.append(self.file.closed)

    monkeypatch.setattr(UploadFile, 'close', record_close)
    upload(client, b'broken')
    upload(client)
    assert closed == [True, True]


def test_malformed_multipart_and_extra_files(client):
    response = client.post('/api/match', content=b'broken', headers={'Content-Type': 'multipart/form-data'})
    assert response.status_code == 400
    response = client.post('/api/match', files=[('photo', ('a', picture(), 'image/png')), ('extra', ('b', picture(), 'image/png'))], data={'consent': 'true'})
    assert response.status_code == 400


def test_cors_and_error_contract(client):
    response = client.options('/api/match', headers={'Origin': 'http://localhost:3000', 'Access-Control-Request-Method': 'POST'})
    assert response.headers['Access-Control-Allow-Origin'] == 'http://localhost:3000'
    response = client.get('/not-found')
    assert response.status_code == 404
    assert set(response.json()['error']) == {'code', 'message'}
