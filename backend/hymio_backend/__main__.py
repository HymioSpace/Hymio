import argparse

import uvicorn

from .config import Settings
from .server import build_app

parser = argparse.ArgumentParser()
parser.add_argument("--config", required=True)
args = parser.parse_args()
settings = Settings.load(args.config)
uvicorn.run(build_app(settings), host=settings.host, port=settings.port, access_log=False)
