"""Vercel entrypoint. Demonstration must be explicitly enabled."""
import os

if os.environ.get('SIDOC_DEMO') == '1':
    from demo_app import create_demo_app
    app = create_demo_app()
else:
    from app import create_app
    app = create_app()
