import sys
import os
from pathlib import Path

# Add project root directory to Python path
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.main import app

# Vercel ASGI application handler
