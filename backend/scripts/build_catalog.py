"""Precompute a normalized mean reference profile per licensed celebrity."""
import argparse
import hashlib
import json
import os
import tempfile
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from app.contracts import APIError, Celebrity, PhotoCredit
from app.inference import encoder_from_env, unit_vector
from app.main import FORMATS, validate_image


def build_catalog(manifest_path: Path, output: Path, encoder):
    records = json.loads(manifest_path.read_text())
    people, vectors, photos = [], [], {}
    for entry in records:
        record = dict(entry)
        extra = record.pop('references', [])
        relative, expected_hash = record.pop('image'), record.pop('sha256')
        person = Celebrity.model_validate(record)
        primary = {key: record[key] for key in PhotoCredit.model_fields if key in record}
        references = [dict(primary, image=relative, sha256=expected_hash), *extra]
        reference_vectors, credits, checksums = [], [], set()
        primary_data = b''
        for reference in references:
            item = dict(reference)
            relative, checksum = item.pop('image'), item.pop('sha256')
            credit = PhotoCredit.model_validate(item)
            image = (manifest_path.parent / relative).resolve()
            if not image.is_relative_to(manifest_path.parent.resolve()):
                raise ValueError('Reference images must be inside the manifest directory')
            data = image.read_bytes()
            if hashlib.sha256(data).hexdigest() != checksum:
                raise ValueError(f'Reference checksum mismatch: {person.id}')
            if checksum in checksums:
                raise ValueError(f'Duplicate reference image: {person.id}')
            checksums.add(checksum)
            with Image.open(BytesIO(data)) as reference_image:
                mime = FORMATS.get(reference_image.format)
            validate_image(data, mime)
            try:
                reference_vectors.append(unit_vector(encoder.encode(data)))
            except APIError as error:
                raise ValueError(f'Reference {person.id}/{relative} failed: {error.code}') from None
            credits.append(credit)
            if not primary_data:
                primary_data = data
        vectors.append(unit_vector(np.mean(reference_vectors, axis=0)))
        with Image.open(BytesIO(primary_data)) as reference_image:
            display = ImageOps.exif_transpose(reference_image).convert('RGB')
            display.thumbnail((500, 700))
            buffer = BytesIO()
            display.save(buffer, format='JPEG', quality=85, optimize=True)
        photos[f'photo_{len(people)}'] = np.frombuffer(buffer.getvalue(), dtype=np.uint8)
        person = person.model_copy(update={'referenceCount': len(credits), 'references': credits})
        people.append(person.model_dump(mode='json'))
    if len(people) < 5 or len({p['id'] for p in people}) != len(people):
        raise ValueError('At least five unique celebrities are required')
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=output.parent, suffix='.npz')
    try:
        with os.fdopen(fd, 'wb') as target:
            np.savez_compressed(target, embeddings=np.stack(vectors), metadata=json.dumps(people),
                                fingerprint=encoder.fingerprint, aggregation='l2_normalized_mean', **photos)
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f'Built {len(people)} celebrity profiles from {sum(p["referenceCount"] for p in people)} references in {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    build_catalog(args.manifest, args.output, encoder_from_env())
