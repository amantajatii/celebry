import hashlib
import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from email.message import Message

import numpy as np
import pytest
from PIL import Image

from app.contracts import APIError
from scripts.build_catalog import build_catalog
from scripts import prepare_dataset as downloader


def manifest(tmp_path, fmt='PNG'):
    photo=BytesIO()
    Image.new('RGB',(32,32),'coral').save(photo,format=fmt)
    data=photo.getvalue()
    (tmp_path/'reference.png').write_bytes(data)
    people=[{'id':str(i),'name':f'Fixture {i}','imageUrl':'https://upload.wikimedia.org/example.png',
             'sourceUrl':'https://commons.wikimedia.org/example','license':'Test fixture','attribution':'Test fixture',
             'image':'reference.png','sha256':hashlib.sha256(data).hexdigest()} for i in range(5)]
    path=tmp_path/'manifest.json'
    path.write_text(json.dumps(people))
    return path


def test_build_supports_png_and_preserves_previous_catalog_on_failure(tmp_path):
    path=manifest(tmp_path)
    target=tmp_path/'catalog.npz'
    encoder=SimpleNamespace(fingerprint='fixture',encode=lambda _:np.eye(1,512,dtype=np.float32)[0])
    build_catalog(path,target,encoder)
    previous=target.read_bytes()
    def fail(_): raise APIError(422,'MULTIPLE_FACES','fixture')
    encoder.encode=fail
    with pytest.raises(ValueError,match='Reference 0 failed: MULTIPLE_FACES'):
        build_catalog(path,target,encoder)
    assert target.read_bytes()==previous


def test_catalog_rejects_changed_reference_bytes(tmp_path):
    path=manifest(tmp_path)
    (tmp_path/'reference.png').write_bytes(b'tampered')
    with pytest.raises(ValueError,match='checksum mismatch'):
        build_catalog(path,tmp_path/'catalog.npz',SimpleNamespace())


def test_downloader_respects_retry_after(monkeypatch):
    calls=[]
    delays=[]
    headers=Message()
    headers['Retry-After']='2'
    def open_url(*args,**kwargs):
        calls.append(1)
        if len(calls)==1:
            raise HTTPError('https://example.test',429,'rate limited',headers,None)
        return BytesIO(b'reference')
    monkeypatch.setattr(downloader,'urlopen',open_url)
    monkeypatch.setattr(downloader.time,'sleep',delays.append)
    assert downloader.fetch('https://example.test',100)==b'reference'
    assert delays==[2]


def test_downloader_bounds_response_size(monkeypatch):
    monkeypatch.setattr(downloader,'urlopen',lambda *a,**k:BytesIO(b'x'*11))
    with pytest.raises(ValueError,match='size limit'):
        downloader.fetch('https://example.test',10)
