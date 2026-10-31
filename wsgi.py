"""Vercel's Flask entrypoint. Cloud credentials are supplied as private env vars."""
from app import create_app

app = create_app()
