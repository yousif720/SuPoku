"""Build an allowlisted GitHub Pages artifact, excluding server/data files."""
import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).parent
OUT = ROOT / '_site'
FILES = ['index.html', 'about.html', 'how-to-play.html', 'privacy.html',
         'contact.html', 'terms.html', 'style.css', 'social.css', 'app.js',
         'theme.js', 'social.js', 'api-client.js', 'api-config.js', 'robots.txt']


def build():
    if OUT.exists():
        raise SystemExit('The _site directory already exists. Use a clean build checkout.')
    api = os.environ.get('SUPOKU_API_BASE', '').rstrip('/')
    parsed = urlsplit(api)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise SystemExit('Set SUPOKU_API_BASE to the HTTPS Render origin, without a path.')
    OUT.mkdir()
    for name in FILES:
        shutil.copy2(ROOT / name, OUT / name)
    shutil.copytree(ROOT / 'assets', OUT / 'assets')
    (OUT / 'data').mkdir()
    shutil.copy2(ROOT / 'data/pokedex.json', OUT / 'data/pokedex.json')
    (OUT / 'api-config.js').write_text('window.SUPOKU_API_BASE = ' + json.dumps(api) + ';\n', encoding='utf-8')
    (OUT / '.nojekyll').touch()
    if (ROOT / 'sitemap.xml').exists():
        shutil.copy2(ROOT / 'sitemap.xml', OUT / 'sitemap.xml')
    print('Built frontend in _site; account databases and backend source excluded.')


if __name__ == '__main__':
    build()
