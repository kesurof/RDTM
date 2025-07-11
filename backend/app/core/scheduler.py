from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging
from datetime import datetime

from app.core.config import settings
from app.services.torrent_service import TorrentService
from app.services.symlink_service import SymlinkService
from app.db.database import SessionLocal

logger = logging.getLogger(__name__)

class SchedulerService:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.torrent_service = TorrentService()
        self.symlink_service = SymlinkService()
        
    def start(self):
        """Start the scheduler with periodic tasks"""
        # Quick scan every scan_interval_minutes
        self.scheduler.add_job(
            self._periodic_scan,
            IntervalTrigger(minutes=settings.scan_interval_minutes),
            id="periodic_scan",
            name="Periodic Quick Scan"
        )
        
        # Auto-reinject failed torrents every hour
        self.scheduler.add_job(
            self._auto_reinject,
            IntervalTrigger(hours=1),
            id="auto_reinject",
            name="Auto Reinject Failed Torrents"
        )
        
        # Symlink scan every 6 hours
        self.scheduler.add_job(
            self._periodic_symlink_scan,
            IntervalTrigger(hours=6),
            id="symlink_scan",
            name="Periodic Symlink Scan"
        )
        
        self.scheduler.start()
        logger.info("Scheduler started with periodic tasks")
    
    def shutdown(self):
        """Shutdown the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler shutdown")
    
    async def _periodic_scan(self):
        """Periodic quick scan for failed torrents"""
        db = SessionLocal()
        try:
            logger.info("Starting periodic quick scan")
            await self.torrent_service.scan_torrents(db, "quick")
            logger.info("Periodic quick scan completed")
        except Exception as e:
            logger.error(f"Periodic scan failed: {e}")
        finally:
            db.close()
    
    async def _auto_reinject(self):
        """Auto-reinject failed torrents that haven't been retried recently"""
        db = SessionLocal()
        try:
            failed_torrents = self.torrent_service.get_failed_torrents(db, limit=20)
            
            if failed_torrents:
                logger.info(f"Auto-reinjecting {len(failed_torrents)} failed torrents")
                
                for torrent in failed_torrents:
                    try:
                        await self.torrent_service.reinject_torrent(db, torrent.id)
                    except Exception as e:
                        logger.error(f"Auto-reinject failed for {torrent.id}: {e}")
                        
                logger.info("Auto-reinject completed")
        except Exception as e:
            logger.error(f"Auto-reinject failed: {e}")
        finally:
            db.close()
    
    async def _periodic_symlink_scan(self):
        """Periodic symlink scan"""
        db = SessionLocal()
        try:
            logger.info("Starting periodic symlink scan")
            await self.symlink_service.scan_broken_symlinks(db)
            await self.symlink_service.match_symlinks_to_torrents(db)
            logger.info("Periodic symlink scan completed")
        except Exception as e:
            logger.error(f"Periodic symlink scan failed: {e}")
        finally:
            db.close()

# Global scheduler instance
scheduler = SchedulerService()