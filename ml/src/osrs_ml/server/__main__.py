import argparse

import uvicorn

from .app import create_app

parser = argparse.ArgumentParser(description="OSRS research HTTP server")
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", type=int, default=8787)
args = parser.parse_args()
uvicorn.run(create_app(), host=args.host, port=args.port)
