import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
import logging

logger = logging.getLogger(__name__)

class SchedulerManager:
    def __init__(self):
        # Configuration APScheduler avec persistance SQLite
        jobstores = {
            'default': SQLAlchemyJobStore(url='sqlite:///./data/jobs.sqlite')
        }
        
        executors = {
            'default': AsyncIOExecutor()
        }
        
        job_defaults = {
            'coalesce': False,
            'max_instances': 1
        }
        
        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone='UTC'
        )
        
        self._started = False

    async def start(self):
        if not self._started:
            self.scheduler.start()
            self._started = True
            logger.info("APScheduler started")

    async def shutdown(self):
        if self._started:
            self.scheduler.shutdown(wait=True)
            self._started = False
            logger.info("APScheduler stopped")

    def add_scan_job(self, scan_interval_minutes: int):
        """Ajoute le job de scan périodique"""
        from app.services.torrent_service import TorrentService
        from app.db.database import SessionLocal
        
        async def scan_job():
            service = TorrentService()
            with SessionLocal() as db:
                try:
                    await service.scan_torrents(db, mode="quick")
                    logger.info("Scheduled scan completed")
                except Exception as e:
                    logger.error(f"Scheduled scan failed: {e}")
        
        self.scheduler.add_job(
            scan_job,
            'interval',
            minutes=scan_interval_minutes,
            id='torrent_scan',
            replace_existing=True
        )
        logger.info(f"Scheduled torrent scan every {scan_interval_minutes} minutes")

# Global instance
scheduler = SchedulerManager()