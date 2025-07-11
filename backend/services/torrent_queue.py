import asyncio
from typing import List, Dict, Optional
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
import uuid

from backend.utils.logger import RDTMLogger, log_errors
from backend.config.settings import settings

class TorrentStatus(Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"

@dataclass
class TorrentJob:
    id: str
    magnet_link: str
    name: str
    status: TorrentStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    progress: float = 0.0
    rd_torrent_id: Optional[str] = None

class TorrentQueue:
    def __init__(self):
        self.logger = RDTMLogger(__name__).get_logger()
        self.queue: List[TorrentJob] = []
        self.active_jobs: Dict[str, TorrentJob] = {}
        self.max_concurrent = settings.max_concurrent_torrents
        self.is_running = False
    
    @log_errors
    async def add_torrent(self, magnet_link: str, name: str) -> str:
        """Ajouter un torrent à la queue"""
        job_id = str(uuid.uuid4())
        job = TorrentJob(
            id=job_id,
            magnet_link=magnet_link,
            name=name,
            status=TorrentStatus.QUEUED,
            created_at=datetime.now()
        )
        
        self.queue.append(job)
        self.logger.info(f"Torrent ajouté à la queue: {name} (ID: {job_id})")
        return job_id
    
    @log_errors
    async def start_queue_processor(self):
        """Démarrer le processeur de queue"""
        self.is_running = True
        self.logger.info("Processeur de queue démarré")
        
        while self.is_running:
            try:
                await self._process_queue()
                await asyncio.sleep(settings.torrent_check_interval)
            except Exception as e:
                self.logger.error(f"Erreur dans le processeur de queue: {e}")
                await asyncio.sleep(5)
    
    async def _process_queue(self):
        """Traiter la queue des torrents"""
        # Nettoyer les jobs terminés
        self._cleanup_completed_jobs()
        
        # Démarrer de nouveaux jobs si possible
        available_slots = self.max_concurrent - len(self.active_jobs)
        
        if available_slots > 0 and self.queue:
            jobs_to_start = self.queue[:available_slots]
            for job in jobs_to_start:
                await self._start_torrent_job(job)
                self.queue.remove(job)
    
    async def _start_torrent_job(self, job: TorrentJob):
        """Démarrer un job de torrent"""
        try:
            job.status = TorrentStatus.PROCESSING
            job.started_at = datetime.now()
            self.active_jobs[job.id] = job
            
            # Ici, intégrer avec l'API Real-Debrid
            # rd_torrent_id = await self.rd_client.add_magnet(job.magnet_link)
            # job.rd_torrent_id = rd_torrent_id
            
            self.logger.info(f"Job démarré: {job.name}")
            
        except Exception as e:
            job.status = TorrentStatus.FAILED
            job.error_message = str(e)
            self.logger.error(f"Échec du démarrage du job {job.name}: {e}")
    
    def _cleanup_completed_jobs(self):
        """Nettoyer les jobs terminés"""
        if settings.auto_delete_completed:
            completed_jobs = [
                job_id for job_id, job in self.active_jobs.items()
                if job.status in [TorrentStatus.COMPLETED, TorrentStatus.FAILED]
            ]
            
            for job_id in completed_jobs:
                del self.active_jobs[job_id]
    
    def get_queue_status(self) -> Dict:
        """Obtenir le statut de la queue"""
        return {
            "queued": len(self.queue),
            "active": len(self.active_jobs),
            "max_concurrent": self.max_concurrent,
            "jobs": [
                {
                    "id": job.id,
                    "name": job.name,
                    "status": job.status.value,
                    "progress": job.progress,
                    "created_at": job.created_at.isoformat()
                }
                for job in self.queue + list(self.active_jobs.values())
            ]
        }

# Instance globale
torrent_queue = TorrentQueue()
