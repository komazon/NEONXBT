from __future__ import annotations

import json
import os
from threading import RLock
import time
from socket import gethostname
from pathlib import Path

from fastapi import FastAPI, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import socketio
import uvicorn

from .cert import generate_cert
from ..nxbt import Nxbt, PRO_CONTROLLER

# Create FastAPI app
app: FastAPI = FastAPI()

# Setup CORS and static files
static_dir = Path(__file__).parent / "static"
templates_dir = Path(__file__).parent / "templates"

# Mount static files
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Initialize Nxbt
nxbt: Nxbt = Nxbt()

# Configuring/retrieving secret key
secrets_path = Path(__file__).parent / "secrets.txt"
if not secrets_path.exists():
    secret_key = os.urandom(24).hex()
    secrets_path.write_text(secret_key)
else:
    secret_key = secrets_path.read_text()

# Setup SocketIO server
sio: socketio.AsyncServer = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*"
)

# Wrap FastAPI app with SocketIO
asgi_app = socketio.ASGIApp(sio, app)

user_info_lock: RLock = RLock()
USER_INFO: dict = {}


@app.get("/")
async def index() -> FileResponse:
    """Serve the index.html template."""
    index_path = templates_dir / "index.html"
    return FileResponse(index_path)


@sio.event
async def connect(sid: str, environ: dict) -> None:
    """Handle client connection."""
    with user_info_lock:
        USER_INFO[sid] = {}


@sio.event
async def state(sid: str) -> None:
    """Send current state to client."""
    state_proxy = nxbt.state.copy()
    state_data = {
        controller: state_proxy[controller].copy()
        for controller in state_proxy.keys()
    }
    await sio.emit("state", state_data, to=sid)


@sio.event
async def disconnect(sid: str) -> None:
    """Handle client disconnection."""
    print("Disconnected")
    with user_info_lock:
        try:
            index = USER_INFO[sid]["controller_index"]
            nxbt.remove_controller(index)
        except KeyError:
            pass
        finally:
            USER_INFO.pop(sid, None)


@sio.event
async def shutdown(sid: str, index: int) -> None:
    """Shutdown a controller."""
    nxbt.remove_controller(index)


@sio.event
async def web_create_pro_controller(sid: str) -> None:
    """Create a new Pro Controller."""
    print("Create Controller")

    try:
        reconnect_addresses = nxbt.get_switch_addresses()
        index = nxbt.create_controller(
            PRO_CONTROLLER,
            reconnect_address=reconnect_addresses
        )

        with user_info_lock:
            USER_INFO[sid]["controller_index"] = index

        await sio.emit("create_pro_controller", index, to=sid)
    except Exception as e:
        await sio.emit("error", str(e), to=sid)


@sio.event
async def input(sid: str, message: str) -> None:
    """Handle controller input."""
    data = json.loads(message)
    index = data[0]
    input_packet = data[1]
    nxbt.set_controller_input(index, input_packet)


@sio.event
async def macro(sid: str, message: str) -> None:
    """Handle macro execution."""
    data = json.loads(message)
    index = data[0]
    macro_name = data[1]
    nxbt.macro(index, macro_name)


async def start_web_app(
    ip: str = "0.0.0.0",
    port: int = 8000,
    usessl: bool = False,
    cert_path: str | None = None
) -> None:
    """Start the FastAPI web server."""
    ssl_keyfile: str | None = None
    ssl_certfile: str | None = None

    if usessl:
        if cert_path is None:
            # Store certs in the package directory
            cert_file = Path(__file__).parent / "cert.pem"
            key_file = Path(__file__).parent / "key.pem"
        else:
            # If specified, store certs at the user's preferred location
            cert_file = Path(cert_path) / "cert.pem"
            key_file = Path(cert_path) / "key.pem"

        if not cert_file.exists() or not key_file.exists():
            print(
                "\n"
                "-----------------------------------------\n"
                "---------------->WARNING<----------------\n"
                "The NXBT webapp is being run with self-\n"
                "signed SSL certificates for use on your\n"
                "local network.\n"
                "\n"
                "These certificates ARE NOT safe for\n"
                "production use. Please generate valid\n"
                "SSL certificates if you plan on using the\n"
                "NXBT webapp anywhere other than your own\n"
                "network.\n"
                "-----------------------------------------\n"
                "\n"
                "The above warning will only be shown once\n"
                "on certificate generation."
                "\n"
            )
            print("Generating certificates...")
            cert, key = generate_cert(gethostname())
            cert_file.write_bytes(cert)
            key_file.write_bytes(key)

        ssl_certfile = str(cert_file)
        ssl_keyfile = str(key_file)

    config = uvicorn.Config(
        asgi_app,
        host=ip,
        port=port,
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    import asyncio
    asyncio.run(start_web_app())
