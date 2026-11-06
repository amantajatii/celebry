"""Fetch curated Hollywood references with per-photo Commons licensing metadata."""
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


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temporary.replace(path)


def prepare(destination):
    destination.mkdir(parents=True, exist_ok=True)
    sources = json.loads(SOURCES_PATH.read_text())
    manifest = destination / 'celebrities.json'
    cache_path = destination / '.reference-cache.json'
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    if manifest.exists():
        for person in json.loads(manifest.read_text()):
            for reference in [person, *person.get('references', [])]:
                cache.setdefault(reference['image'], reference)
    titles = ['File:' + filename for source in sources for filename in [source['file'], *source.get('additionalFiles', [])]]
    by_title = {}
    for start in range(0, len(titles), 40):
        query = urlencode({'action': 'query', 'format': 'json', 'prop': 'imageinfo', 'titles': '|'.join(titles[start:start + 40]),
                           'iiprop': 'url|extmetadata|mime', 'iiurlwidth': 330})
        pages = json.loads(fetch('https://commons.wikimedia.org/w/api.php?' + query, 8_000_000))['query']['pages']
        by_title.update({page['title'].replace('_', ' '): page for page in pages.values()})
    people = []
    for source in sources:
        references = []
        for index, filename in enumerate([source['file'], *source.get('additionalFiles', [])]):
            page = by_title.get('File:' + filename.replace('_', ' '), {})
            if 'imageinfo' not in page:
                raise ValueError(f'No Commons image found: {filename}')
            info = page['imageinfo'][0]
            metadata = info['extmetadata']
            license_name = metadata['LicenseShortName']['value']
            if license_name not in {'CC BY-SA 4.0', 'CC BY-SA 3.0', 'CC BY-SA 2.0', 'CC BY-SA 2.5', 'CC BY 2.0', 'CC BY 3.0', 'CC BY 4.0', 'Public domain', 'CC0'}:
                raise ValueError(f'Review license for {filename}: {license_name}')
            author = html.unescape(re.sub('<[^>]+>', '', metadata['Artist']['value'])).strip()
            url = info.get('thumburl', info['url'])
            extension = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}.get(info.get('thumbmime', info.get('mime')))
            if extension is None:
                raise ValueError(f'Unsupported reference image type: {filename}')
            image = source['id'] + (f'-reference-{index + 1}' if index else '') + extension
            cached = cache.get(image, {})
            local = destination / image
            data = local.read_bytes() if local.exists() and cached.get('sourceUrl') == info['descriptionurl'] else b''
            if data and hashlib.sha256(data).hexdigest() == cached.get('sha256'):
                url = cached['imageUrl']
            else:
                print(f'Downloading {filename}: {url}', flush=True)
                time.sleep(2)
                data = fetch(url, 10 * 1024 * 1024)
            temporary = local.with_suffix('.download')
            temporary.write_bytes(data)
            temporary.replace(local)
            reference = {'imageUrl': url, 'sourceUrl': info['descriptionurl'], 'license': license_name,
                         'licenseUrl': metadata.get('LicenseUrl', {}).get('value') or None,
                         'attribution': author + '; Wikimedia Commons; resized reference image',
                         'image': image, 'sha256': hashlib.sha256(data).hexdigest()}
            references.append(reference)
            cache[image] = reference
            write_json(cache_path, cache)
            print(f'Prepared {source["name"]} reference {index + 1} ({license_name})', flush=True)
        people.append({'id': source['id'], 'name': source['name'], 'collection': source['collection'],
                       **references[0], 'references': references[1:]})
    write_json(manifest, people)
    return manifest


if __name__ == '__main__':
    prepare(Path(sys.argv[1] if len(sys.argv) > 1 else 'data/hollywood'))
