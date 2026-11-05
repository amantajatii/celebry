"""Fetch a small Hollywood research dataset, with Commons license metadata."""
import hashlib
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SOURCES = [
    ('zendaya', 'Zendaya', 'Zendaya 2019 by Glenn Francis.jpg'),
    ('timothee-chalamet', 'Timothée Chalamet', 'Timothée Chalamet-63482 (cropped).jpg'),
    ('florence-pugh', 'Florence Pugh', 'Florence Pugh - The Wonder BFI London Film Festival Premiere, October 2022 (cropped).jpg'),
    ('emma-stone', 'Emma Stone', 'Emma Stone at the 39th Mill Valley Film Festival (cropped).jpg'),
    ('ryan-gosling', 'Ryan Gosling', 'Ryan Gosling in 2018.jpg'),
]


def fetch(url, limit):
    with urlopen(Request(url, headers={'User-Agent': 'CelebryResearch/0.3 (local prototype; Wikimedia Commons attribution)'}), timeout=30) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Download exceeds size limit')
    return data


def prepare(destination):
    destination.mkdir(parents=True, exist_ok=True)
    people = []
    for identifier, name, filename in SOURCES:
        query = urlencode({'action': 'query', 'format': 'json', 'prop': 'imageinfo', 'titles': 'File:' + filename,
                           'iiprop': 'url|extmetadata', 'iiurlwidth': 1000})
        pages = json.loads(fetch('https://commons.wikimedia.org/w/api.php?' + query, 1_000_000))['query']['pages']
        info = next(iter(pages.values()))['imageinfo'][0]
        metadata = info['extmetadata']
        license_name = metadata['LicenseShortName']['value']
        if license_name not in {'CC BY-SA 4.0', 'CC BY-SA 3.0', 'CC BY-SA 2.0', 'CC BY 2.0', 'CC BY 3.0', 'CC BY 4.0', 'Public domain'}:
            raise ValueError(f'Review license for {name}: {license_name}')
        author = html.unescape(re.sub('<[^>]+>', '', metadata['Artist']['value'])).strip()
        url = info.get('thumburl', info['url'])
        data = fetch(url, 10 * 1024 * 1024)
        image = identifier + '.jpg'
        (destination / image).write_bytes(data)
        people.append({'id': identifier, 'name': name, 'imageUrl': url, 'sourceUrl': info['descriptionurl'],
                       'license': license_name, 'licenseUrl': metadata.get('LicenseUrl', {}).get('value') or None, 'attribution': author + '; Wikimedia Commons; resized reference image',
                       'image': image, 'sha256': hashlib.sha256(data).hexdigest()})
        print(f'Prepared {name} ({license_name})')
    manifest = destination / 'celebrities.json'
    manifest.write_text(json.dumps(people, indent=2, ensure_ascii=False) + '\n')
    return manifest


if __name__ == '__main__':
    prepare(Path(sys.argv[1] if len(sys.argv) > 1 else 'data/hollywood'))
