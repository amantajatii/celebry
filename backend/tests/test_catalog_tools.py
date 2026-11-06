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
    with pytest.raises(ValueError,match='Reference 0/reference.png failed: MULTIPLE_FACES'):
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


def test_multiple_references_use_normalized_mean_and_keep_credits(tmp_path):
    path=manifest(tmp_path)
    photo=BytesIO()
    Image.new('RGB',(32,32),'blue').save(photo,format='PNG')
    second=photo.getvalue()
    (tmp_path/'second.png').write_bytes(second)
    records=json.loads(path.read_text())
    for person in records:
        person['collection']='actors'
        person['references']=[{key:value for key,value in person.items() if key not in {'id','name','collection'}}]
        person['references'][0].update(image='second.png',sha256=hashlib.sha256(second).hexdigest())
    path.write_text(json.dumps(records))
    first=np.zeros(512,dtype=np.float32); first[0]=1
    other=first.copy(); other[:2]=[.8,.6]
    encoder=SimpleNamespace(fingerprint='fixture',encode=lambda data:other if data==second else first)
    output=tmp_path/'catalog.npz'
    build_catalog(path,output,encoder)
    with np.load(output,allow_pickle=False) as catalog:
        expected=(first+other)/np.linalg.norm(first+other)
        np.testing.assert_allclose(catalog['embeddings'][0],expected,atol=1e-6)
        person=json.loads(str(catalog['metadata'].item()))[0]
        assert person['referenceCount']==2
        assert len(person['references'])==2
        assert person['collection']=='actors'
        assert str(catalog['aggregation'].item())=='l2_normalized_mean'


def test_duplicate_reference_bytes_are_rejected(tmp_path):
    path=manifest(tmp_path)
    records=json.loads(path.read_text())
    for person in records:
        person['references']=[{key:value for key,value in person.items() if key not in {'id','name'}}]
    path.write_text(json.dumps(records))
    encoder=SimpleNamespace(fingerprint='fixture',encode=lambda _:np.eye(1,512,dtype=np.float32)[0])
    with pytest.raises(ValueError,match='Duplicate reference'):
        build_catalog(path,tmp_path/'catalog.npz',encoder)


@pytest.mark.parametrize('same_source,valid_hash', [(True, True), (False, True), (True, False)])
def test_downloader_reuses_only_verified_bytes_from_same_source(tmp_path, monkeypatch, same_source, valid_hash):
    sources=tmp_path/'sources.json'
    sources.write_text(json.dumps([{'id':'subject','name':'Fixture','collection':'actors','file':'Portrait.jpg'}]))
    destination=tmp_path/'photos'; destination.mkdir()
    data=b'cached fixture'
    (destination/'subject.jpg').write_bytes(data)
    source='https://commons.wikimedia.org/wiki/File:Portrait.jpg'
    (destination/'.reference-cache.json').write_text(json.dumps({'subject.jpg':{
        'sourceUrl':source if same_source else 'https://commons.wikimedia.org/wiki/File:Other.jpg',
        'imageUrl':'https://upload.wikimedia.org/previous.jpg','sha256':hashlib.sha256(data if valid_hash else b'changed').hexdigest()}}))
    info={'url':'https://upload.wikimedia.org/original.jpg','thumburl':'https://upload.wikimedia.org/500px-Portrait.jpg',
          'mime':'image/jpeg','descriptionurl':source,
          'extmetadata':{'LicenseShortName':{'value':'CC BY 2.0'},'Artist':{'value':'Fixture photographer'}}}
    calls=[]
    def fetch(url, limit):
        calls.append(url)
        if '/w/api.php?' in url:
            assert 'iiurlwidth=330' in url
            return json.dumps({'query':{'pages':{'1':{'title':'File:Portrait.jpg','imageinfo':[info]}}}}).encode()
        return b'new fixture'
    monkeypatch.setattr(downloader,'SOURCES_PATH',sources)
    monkeypatch.setattr(downloader,'fetch',fetch)
    monkeypatch.setattr(downloader.time,'sleep',lambda _:None)
    result=json.loads(downloader.prepare(destination).read_text())[0]
    reused=same_source and valid_hash
    assert len(calls)==(1 if reused else 2)
    assert result['imageUrl']==('https://upload.wikimedia.org/previous.jpg' if reused else info['thumburl'])
    expected=data if reused else b'new fixture'
    assert result['sha256']==hashlib.sha256(expected).hexdigest()
