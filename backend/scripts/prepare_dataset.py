"""Fetch a small Hollywood research dataset, with Commons license metadata."""
import hashlib
import html
import json
import re
import sys
import time
from urllib.error import HTTPError
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SOURCES_PATH = Path(__file__).resolve().parents[1] / 'data' / 'sources.json'


def fetch(url, limit):
    for attempt in range(4):
        try:
            with urlopen(Request(url, headers={'User-Agent': 'CelebryResearch/0.5 (local prototype; Wikimedia Commons attribution)'}), timeout=30) as response:
                data = response.read(limit + 1)
            if len(data) > limit:
                raise ValueError('Download exceeds size limit')
            return data
        except HTTPError as error:
            if error.code not in {429, 503} or attempt == 3:
                raise
            try:
                delay = float(error.headers.get('Retry-After', 5 * (attempt + 1)))
            except ValueError:
                delay = 10
            time.sleep(max(1, min(delay, 30)))


def prepare(destination):
    destination.mkdir(parents=True, exist_ok=True)
    people = []
    previous = {}
    manifest = destination / 'celebrities.json'
    if manifest.exists():
        previous = {item['id']: item for item in json.loads(manifest.read_text())}
    sources = json.loads(SOURCES_PATH.read_text())
    query = urlencode({'action': 'query', 'format': 'json', 'prop': 'imageinfo',
                       'titles': '|'.join('File:' + source['file'] for source in sources),
                       'iiprop': 'url|extmetadata|mime', 'iiurlwidth': 1000})
    pages = json.loads(fetch('https://commons.wikimedia.org/w/api.php?' + query, 8_000_000))['query']['pages']
    by_title = {page['title'].replace('_', ' '): page for page in pages.values()}
    for source in sources:
        identifier, name, filename = source['id'], source['name'], source['file']
        page = by_title['File:' + filename.replace('_', ' ')]
        if 'imageinfo' not in page:
            raise ValueError(f'No Commons image found for {name}: {filename}')
        info = page['imageinfo'][0]
        metadata = info['extmetadata']
        license_name = metadata['LicenseShortName']['value']
        if license_name not in {'CC BY-SA 4.0', 'CC BY-SA 3.0', 'CC BY-SA 2.0', 'CC BY 2.0', 'CC BY 3.0', 'CC BY 4.0', 'Public domain', 'CC0'}:
            raise ValueError(f'Review license for {name}: {license_name}')
        author = html.unescape(re.sub('<[^>]+>', '', metadata['Artist']['value'])).strip()
        url = info.get('thumburl', info['url'])
        extension = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}.get(info.get('thumbmime', info.get('mime')))
        if extension is None:
            raise ValueError(f'Unsupported reference image type: {name}')
        image = identifier + extension
        cached = previous.get(identifier, {})
        local = destination / image
        data = local.read_bytes() if local.exists() and cached.get('imageUrl') == url else b''
        if not data or hashlib.sha256(data).hexdigest() != cached.get('sha256'):
            time.sleep(1)
            data = fetch(url, 10 * 1024 * 1024)
        temporary = local.with_suffix('.download')
        temporary.write_bytes(data)
        temporary.replace(local)
        people.append({'id': identifier, 'name': name, 'imageUrl': url, 'sourceUrl': info['descriptionurl'],
                       'license': license_name, 'licenseUrl': metadata.get('LicenseUrl', {}).get('value') or None, 'attribution': author + '; Wikimedia Commons; resized reference image',
                       'image': image, 'sha256': hashlib.sha256(data).hexdigest()})
        print(f'Prepared {name} ({license_name})')
    manifest = destination / 'celebrities.json'
    temporary = manifest.with_suffix('.tmp')
    temporary.write_text(json.dumps(people, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(manifest)
    return manifest


if __name__ == '__main__':
    prepare(Path(sys.argv[1] if len(sys.argv) > 1 else 'data/hollywood'))
