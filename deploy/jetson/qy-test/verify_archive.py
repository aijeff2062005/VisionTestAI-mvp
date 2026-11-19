"""Validate gzip/tar integrity and the four ARM64 images in a Docker save archive."""
from pathlib import Path
import gzip
import json
import sys
import tarfile

path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('out/qy-arm64-images.tar.gz')
metadata = {}
with gzip.open(path, 'rb') as stream:
    with tarfile.open(fileobj=stream, mode='r|') as archive:
        for member in archive:
            candidate = member.name.endswith('.json') or member.name.startswith('blobs/sha256/')
            if member.isfile() and candidate and member.size < 2 * 1024 * 1024:
                content = archive.extractfile(member).read()
                try:
                    metadata[member.name] = json.loads(content)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
    # Consume the trailer too, so gzip verifies the complete stream CRC.
    while stream.read(8 * 1024 * 1024):
        pass
manifest = metadata['manifest.json']
assert len(manifest) == 4, len(manifest)
images = []
for entry in manifest:
    config = metadata[entry['Config']]
    assert config['architecture'] == 'arm64', (entry['RepoTags'], config['architecture'])
    images.append({'tags': entry['RepoTags'], 'architecture': config['architecture']})
result = {'gzip_tar_integrity': 'PASS', 'images': images, 'archive_bytes': path.stat().st_size}
print(json.dumps(result, indent=2))
