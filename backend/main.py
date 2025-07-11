from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os

from app.api.routes import router as api_router
from app.core.scheduler import scheduler
from app.core.websocket import websocket_manager
from app.db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    scheduler.start()
    yield
    # Shutdown
    scheduler.shutdown()


app = FastAPI(
    title="Real-Debrid Torrent Manager",
    description="Gestionnaire intelligent de torrents Real-Debrid",
    version="1.0.0",
    lifespan=lifespan
)

# API routes
app.include_router(api_router, prefix="/api")

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        websocket_manager.disconnect(websocket)

# Static files (Svelte build)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve Svelte app
@app.get("/")
async def read_index():
    return FileResponse("static/index.html")

@app.get("/{path:path}")
async def serve_spa(path: str):
    file_path = f"static/{path}"
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    return FileResponse("static/index.html")