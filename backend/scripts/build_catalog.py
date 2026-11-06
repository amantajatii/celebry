"""Precompute one real, normalized embedding per licensed celebrity reference."""
import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from io import BytesIO

from app.contracts import APIError

from app.contracts import Celebrity
from app.inference import encoder_from_env
from app.main import validate_image, FORMATS


def build_catalog(manifest_path: Path, output: Path, encoder):
    records = json.loads(manifest_path.read_text())
    people, vectors, photos = [], [], {}
    for entry in records:
        record = dict(entry)
        relative = record.pop('image')
        expected_hash = record.pop('sha256')
        person = Celebrity.model_validate(record)
        image = (manifest_path.parent / relative).resolve()
        if not image.is_relative_to(manifest_path.parent.resolve()):
            raise ValueError('Reference images must be inside the manifest directory')
        data = image.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected_hash:
            raise ValueError(f'Reference checksum mismatch: {person.id}')
        with Image.open(BytesIO(data)) as reference:
            mime = FORMATS.get(reference.format)
        validate_image(data, mime)
        try:
            vectors.append(encoder.encode(data))
        except APIError as error:
            raise ValueError(f'Reference {person.id} failed: {error.code}') from None
        with Image.open(BytesIO(data)) as reference:
            display = ImageOps.exif_transpose(reference).convert('RGB')
            display.thumbnail((500, 700))
            buffer = BytesIO()
            display.save(buffer, format='JPEG', quality=85, optimize=True)
        photos[f'photo_{len(people)}'] = np.frombuffer(buffer.getvalue(), dtype=np.uint8)
        people.append(person.model_dump(mode='json'))
    if len(people) < 5 or len({p['id'] for p in people}) != len(people):
        raise ValueError('At least five unique celebrities are required')
    output.parent.mkdir(parents=True, exist_ok=True)
    # Publish only a fully built archive; failures preserve the previous catalog.
    fd, temporary = tempfile.mkstemp(dir=output.parent, suffix='.npz')
    try:
        with os.fdopen(fd, 'wb') as target:
            np.savez_compressed(target, embeddings=np.stack(vectors), metadata=json.dumps(people), fingerprint=encoder.fingerprint, **photos)
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f'Built {len(people)} celebrity embeddings in {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    build_catalog(args.manifest, args.output, encoder_from_env())
