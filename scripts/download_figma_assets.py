"""Download the exact Figma assets listed in the design-context manifest.

The URLs expire. Regenerate figma-assets.json using get_design_context when needed.
No runtime page loads remote Figma URLs.
"""
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent.parent
if not (root / 'figma-assets.json').is_file():
    raise SystemExit('Regenera figma-assets.json desde el contexto de diseño de Figma; contiene URLs temporales y no se incluye en Git.')
assets = json.loads((root / 'figma-assets.json').read_text())
folder = root / 'static' / 'figma'
folder.mkdir(parents=True, exist_ok=True)
failed = []
for group, entries in assets.items():
    for name, entry in entries.items():
        destination = folder / entry['path']
        if destination.is_file() and destination.stat().st_size:
            continue
        temporary = destination.with_suffix(destination.suffix + '.part')
        result = subprocess.run(['curl', '-f', '-L', '--connect-timeout', '15', '--max-time', '60',
                                 '-o', str(temporary), entry['url']], capture_output=True)
        if result.returncode:
            temporary.unlink(missing_ok=True)
            failed.append(f'{group}/{name}')
            # Stop at the first failure to avoid repeated blocked requests.
            print('Descarga bloqueada o URL vencida:', failed[-1])
            raise SystemExit(1)
        temporary.replace(destination)
print('Todos los recursos originales están disponibles localmente.')
