"""Explicit ownership-contract entrypoint; public submission remains disabled."""
import os
from pathlib import Path
from .owned_api import create_owned_app

state=Path(os.environ.get('CLIPORA_WEB_STATE','/state'))
app=create_owned_app(os.environ.get('CLIPORA_WEB_ORIGIN','http://127.0.0.1:8091'),state,state/'artifacts')
