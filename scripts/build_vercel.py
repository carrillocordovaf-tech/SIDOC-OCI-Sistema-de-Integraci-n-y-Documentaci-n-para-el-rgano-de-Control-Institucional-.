"""Prepare CDN assets; never copy the database, uploaded files or secret config."""
import shutil
from pathlib import Path

root = Path(__file__).resolve().parent.parent
source = root / 'static'
destination = root / 'public' / 'static'
if destination.exists():
    shutil.rmtree(destination)
destination.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(source, destination)
print('Static application assets copied to public/static for Vercel CDN.')
