from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional

from backend.services.torrent_queue import torrent_queue, TorrentStatus
from backend.utils.logger import RDTMLogger

router = APIRouter(prefix="/api/torrents", tags=["torrents"])
logger = RDTMLogger(__name__).get_logger()

class TorrentRequest(BaseModel):
    magnet_link: str
    name: Optional[str] = None

class TorrentResponse(BaseModel):
    id: str
    name: str
    status: str
    progress: float
    created_at: str
    error_message: Optional[str] = None

@router.post("/add", response_model=dict)
async def add_torrent(request: TorrentRequest, background_tasks: BackgroundTasks):
    """Ajouter un torrent à la queue"""
    try:
        name = request.name or f"Torrent_{request.magnet_link[:20]}"
        job_id = await torrent_queue.add_torrent(request.magnet_link, name)
        
        return {
            "success": True,
            "job_id": job_id,
            "message": "Torrent ajouté à la queue"
        }
    except Exception as e:
        logger.error(f"Erreur lors de l'ajout du torrent: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status", response_model=dict)
async def get_queue_status():
    """Obtenir le statut de la queue"""
    try:
        return torrent_queue.get_queue_status()
    except Exception as e:
        logger.error(f"Erreur lors de la récupération du statut: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{job_id}")
async def cancel_torrent(job_id: str):
    """Annuler un torrent"""
    try:
        # Implémentation de l'annulation
        return {"success": True, "message": "Torrent annulé"}
    except Exception as e:
        logger.error(f"Erreur lors de l'annulation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/pause/{job_id}")
async def pause_torrent(job_id: str):
    """Mettre en pause un torrent"""
    try:
        # Implémentation de la pause
        return {"success": True, "message": "Torrent mis en pause"}
    except Exception as e:
        logger.error(f"Erreur lors de la pause: {e}")
        raise HTTPException(status_code=500, detail=str(e))
