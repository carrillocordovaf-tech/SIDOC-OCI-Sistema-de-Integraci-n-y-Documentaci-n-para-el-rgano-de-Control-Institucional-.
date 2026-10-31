"""Check that every asset from the design-context manifest exists locally."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
if not (root / 'figma-assets.json').is_file():
    raise SystemExit('Regenera figma-assets.json desde el contexto de diseño de Figma; contiene URLs temporales y no se incluye en Git.')
entries = json.loads((root / 'figma-assets.json').read_text())
total = present = 0
for group, assets in entries.items():
    ready = 0
    for asset in assets.values():
        path = root / 'static' / 'figma' / asset['path']
        ready += int(path.is_file() and path.stat().st_size > 0)
    total += len(assets)
    present += ready
    print(f'{group}: {ready}/{len(assets)} recursos locales')
print(f'Total: {present}/{total}. ' + ('Listo para verificar geometría.' if present == total else 'Fidelidad visual pendiente.'))
raise SystemExit(0 if present == total else 1)
