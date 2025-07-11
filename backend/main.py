from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os
import logging

from app.api.routes import router as api_router
from app.core.websocket import websocket_manager
from app.core.config import settings
from app.db.database import init_db

# Configuration logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logging.info("Starting RDTM application...")
    
    # Créer répertoires data si nécessaire
    os.makedirs("./data", exist_ok=True)
    
    # Initialiser base de données
    await init_db()
    
    logging.info("RDTM application started successfully")
    
    yield
    
    # Shutdown
    logging.info("Shutting down RDTM application...")
    logging.info("RDTM application stopped")

app = FastAPI(
    title="Real-Debrid Torrent Manager",
    description="Gestionnaire intelligent de torrents Real-Debrid",
    version="1.0.0",
    lifespan=lifespan
)

# API routes
app.include_router(api_router, prefix="/api")

# WebSocket endpoint avec gestion d'erreurs
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket_manager.connect(websocket)
    try:
        while True:
            # Heartbeat pour maintenir la connexion
            await websocket.receive_text()
    except Exception as e:
        logging.error(f"WebSocket error: {e}")
    finally:
        websocket_manager.disconnect(websocket)

# Servir l'application Svelte compilée
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
    
    @app.get("/")
    async def read_index():
        return FileResponse("static/index.html")

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        file_path = f"static/{path}"
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse("static/index.html")
else:
    @app.get("/")
    async def dev_info():
        return {
            "message": "RDTM API running",
            "frontend": "Run 'cd frontend && npm run dev' for development"
        }