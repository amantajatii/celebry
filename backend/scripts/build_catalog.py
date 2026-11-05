"""Precompute one real, normalized embedding per licensed celebrity reference."""
import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

import numpy as np

from app.contracts import Celebrity
from app.inference import encoder_from_env
from app.main import validate_image


def build_catalog(manifest_path: Path, output: Path, encoder):
    records = json.loads(manifest_path.read_text())
    people, vectors = [], []
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
        validate_image(data, 'image/jpeg')
        vectors.append(encoder.encode(data))
        people.append(person.model_dump(mode='json'))
    if len(people) < 5 or len({p['id'] for p in people}) != len(people):
        raise ValueError('At least five unique celebrities are required')
    output.parent.mkdir(parents=True, exist_ok=True)
    # Publish only a fully built archive; failures preserve the previous catalog.
    fd, temporary = tempfile.mkstemp(dir=output.parent, suffix='.npz')
    try:
        with os.fdopen(fd, 'wb') as target:
            np.savez_compressed(target, embeddings=np.stack(vectors), metadata=json.dumps(people), fingerprint=encoder.fingerprint)
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
