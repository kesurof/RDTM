import aiohttp
import asyncio
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.db.models import Torrent, Attempt, ScanProgress
from app.core.config import settings
from app.core.websocket import websocket_manager
import logging

logger = logging.getLogger(__name__)

class TorrentService:
    def __init__(self):
        self.base_url = "https://api.real-debrid.com/rest/1.0/"
        self.headers = {
            "Authorization": f"Bearer {settings.rd_api_token}",
            "Content-Type": "application/json"
        }
        self.session = None
    
    async def _get_session(self):
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self.session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=timeout
            )
        return self.session
    
    async def _close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def scan_torrents(self, db: Session, mode: str = "quick") -> Dict:
        """Scan torrents with async HTTP requests"""
        await websocket_manager.broadcast({"type": "scan_start", "mode": mode})
        
        start_time = time.time()
        total_processed = 0
        failed_count = 0
        
        try:
            session = await self._get_session()
            
            if mode == "quick":
                failed_statuses = ["magnet_error", "error", "virus", "dead"]
                all_torrents = []
                
                # Fetch failed torrents concurrently
                tasks = [
                    self._fetch_torrents_by_status(session, status) 
                    for status in failed_statuses
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in results:
                    if not isinstance(result, Exception):
                        all_torrents.extend(result)
                    else:
                        logger.error(f"Failed to fetch torrents: {result}")
                        
            else:  # full scan
                all_torrents = await self._fetch_all_torrents(session)
            
            # Process torrents in batches
            batch_size = 50
            for i in range(0, len(all_torrents), batch_size):
                batch = all_torrents[i:i + batch_size]
                
                # Process batch
                for torrent_data in batch:
                    await self._process_torrent(db, torrent_data)
                    total_processed += 1
                    
                    if torrent_data.get("status") in ["magnet_error", "error", "virus", "dead"]:
                        failed_count += 1
                
                # Progress update
                await websocket_manager.broadcast({
                    "type": "scan_progress",
                    "processed": total_processed,
                    "failed": failed_count
                })
                
                # Small delay to prevent overwhelming the database
                await asyncio.sleep(0.1)
            
            duration = time.time() - start_time
            
            # Update scan progress
            progress = db.query(ScanProgress).filter_by(scan_type=mode).first()
            if not progress:
                progress = ScanProgress(scan_type=mode)
                db.add(progress)
            
            progress.last_scan_complete = datetime.utcnow()
            progress.status = "completed"
            progress.total_expected = total_processed
            db.commit()
            
            result = {
                "mode": mode,
                "total_processed": total_processed,
                "failed_count": failed_count,
                "duration": duration,
                "success": True
            }
            
            await websocket_manager.broadcast({"type": "scan_complete", **result})
            return result
            
        except Exception as e:
            logger.error(f"Scan failed: {e}")
            await websocket_manager.broadcast({
                "type": "scan_error", 
                "error": str(e)
            })
            raise
        finally:
            await self._close_session()
    
    async def _fetch_torrents_by_status(self, session: aiohttp.ClientSession, status: str) -> List[Dict]:
        """Fetch torrents by status with async HTTP"""
        try:
            async with session.get(
                f"{self.base_url}torrents",
                params={"filter": status, "limit": 1000}
            ) as response:
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            logger.error(f"Failed to fetch torrents with status {status}: {e}")
            return []
    
    async def _fetch_all_torrents(self, session: aiohttp.ClientSession) -> List[Dict]:
        """Fetch all torrents with pagination"""
        all_torrents = []
        offset = 0
        limit = 1000
        
        while True:
            try:
                async with session.get(
                    f"{self.base_url}torrents",
                    params={"limit": limit, "offset": offset}
                ) as response:
                    response.raise_for_status()
                    torrents = await response.json()
                    
                    if not torrents:
                        break
                        
                    all_torrents.extend(torrents)
                    offset += limit
                    
                    if len(torrents) < limit:
                        break
                        
            except Exception as e:
                logger.error(f"Failed to fetch torrents at offset {offset}: {e}")
                break
        
        return all_torrents
    
    async def _process_torrent(self, db: Session, torrent_data: Dict):
        """Process single torrent with error handling"""
        try:
            torrent = db.query(Torrent).filter_by(id=torrent_data["id"]).first()
            
            if not torrent:
                torrent = Torrent(
                    id=torrent_data["id"],
                    hash=torrent_data["hash"],
                    filename=torrent_data["filename"],
                    status=torrent_data["status"],
                    size=torrent_data.get("bytes", 0),
                    added_date=datetime.fromisoformat(torrent_data["added"].replace("Z", "+00:00")),
                    priority=self._calculate_priority(torrent_data)
                )
                db.add(torrent)
            else:
                # Update existing
                torrent.status = torrent_data["status"]
                torrent.last_seen = datetime.utcnow()
                torrent.size = torrent_data.get("bytes", 0)
            
            db.commit()
        except Exception as e:
            logger.error(f"Failed to process torrent {torrent_data.get('id', 'unknown')}: {e}")
            db.rollback()
    
    def _calculate_priority(self, torrent_data: Dict) -> int:
        """Calculate torrent priority"""
        status = torrent_data.get("status", "").lower()
        size_gb = torrent_data.get("bytes", 0) / (1024**3)
        
        if status == "magnet_error" or size_gb > 1:
            return 3  # High
        elif size_gb < 0.1:
            return 1  # Low
        return 2  # Normal
    
    async def reinject_torrent(self, db: Session, torrent_id: str) -> Dict:
        """Reinject failed torrent with async HTTP"""
        torrent = db.query(Torrent).filter_by(id=torrent_id).first()
        if not torrent:
            raise ValueError("Torrent not found")
        
        await websocket_manager.broadcast({
            "type": "reinject_start",
            "torrent_id": torrent_id,
            "filename": torrent.filename[:50]
        })
        
        start_time = time.time()
        
        try:
            session = await self._get_session()
            magnet_link = f"magnet:?xt=urn:btih:{torrent.hash}&dn={torrent.filename}"
            
            async with session.post(
                f"{self.base_url}torrents/addMagnet",
                data={"magnet": magnet_link}
            ) as response:
                response_time = int((time.time() - start_time) * 1000)
                success = response.status in [200, 201]
                response_text = await response.text()
                
                # Record attempt
                attempt = Attempt(
                    torrent_id=torrent_id,
                    success=success,
                    response_time_ms=response_time,
                    error_message=response_text if not success else None,
                    api_response=response_text
                )
                db.add(attempt)
                
                # Update torrent
                torrent.attempts_count += 1
                torrent.last_attempt = datetime.utcnow()
                if success:
                    torrent.last_success = datetime.utcnow()
                
                db.commit()
                
                result = {
                    "success": success,
                    "torrent_id": torrent_id,
                    "response_time": response_time,
                    "error": response_text if not success else None
                }
                
                await websocket_manager.broadcast({
                    "type": "reinject_complete",
                    **result
                })
                
                return result
                
        except Exception as e:
            # Record failed attempt
            attempt = Attempt(
                torrent_id=torrent_id,
                success=False,
                error_message=str(e),
                response_time_ms=int((time.time() - start_time) * 1000)
            )
            db.add(attempt)
            torrent.attempts_count += 1
            db.commit()
            
            await websocket_manager.broadcast({
                "type": "reinject_error",
                "torrent_id": torrent_id,
                "error": str(e)
            })
            
            raise
        finally:
            await self._close_session()
    
    def get_failed_torrents(self, db: Session, limit: int = 50) -> List[Torrent]:
        """Get torrents that need reinjection"""
        failed_statuses = ["magnet_error", "error", "virus", "dead"]
        
        return db.query(Torrent).filter(
            and_(
                Torrent.status.in_(failed_statuses),
                Torrent.attempts_count < 3,
                or_(
                    Torrent.last_attempt.is_(None),
                    Torrent.last_attempt < datetime.utcnow() - timedelta(hours=3)
                )
            )
        ).order_by(Torrent.priority.desc(), Torrent.last_seen.desc()).limit(limit).all()
    
    def get_stats(self, db: Session) -> Dict:
        """Get torrent statistics"""
        total = db.query(Torrent).count()
        failed = db.query(Torrent).filter(
            Torrent.status.in_(["magnet_error", "error", "virus", "dead"])
        ).count()
        
        recent_attempts = db.query(Attempt).filter(
            Attempt.attempt_date > datetime.utcnow() - timedelta(hours=24)
        ).count()
        
        successful_attempts = db.query(Attempt).filter(
            and_(
                Attempt.attempt_date > datetime.utcnow() - timedelta(hours=24),
                Attempt.success == True
            )
        ).count()
        
        return {
            "total_torrents": total,
            "failed_torrents": failed,
            "recent_attempts_24h": recent_attempts,
            "successful_attempts_24h": successful_attempts,
            "success_rate": (successful_attempts / recent_attempts * 100) if recent_attempts > 0 else 0
        }