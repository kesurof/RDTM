import requests
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.db.models import Torrent, Attempt, ScanProgress
from app.core.config import settings
from app.core.websocket import websocket_manager


class TorrentService:
    def __init__(self):
        self.base_url = "https://api.real-debrid.com/rest/1.0/"
        self.headers = {
            "Authorization": f"Bearer {settings.rd_api_token}",
            "Content-Type": "application/json"
        }
    
    async def scan_torrents(self, db: Session, mode: str = "quick") -> Dict:
        """Scan torrents from Real-Debrid API"""
        await websocket_manager.broadcast({"type": "scan_start", "mode": mode})
        
        start_time = time.time()
        total_processed = 0
        failed_count = 0
        
        try:
            if mode == "quick":
                # Only failed torrents
                failed_statuses = ["magnet_error", "error", "virus", "dead"]
                all_torrents = []
                
                for status in failed_statuses:
                    torrents = await self._fetch_torrents_by_status(status)
                    all_torrents.extend(torrents)
                    
            else:  # full scan
                all_torrents = await self._fetch_all_torrents()
            
            # Process torrents
            for torrent_data in all_torrents:
                await self._process_torrent(db, torrent_data)
                total_processed += 1
                
                if torrent_data.get("status") in ["magnet_error", "error", "virus", "dead"]:
                    failed_count += 1
                
                # Progress update every 100 torrents
                if total_processed % 100 == 0:
                    await websocket_manager.broadcast({
                        "type": "scan_progress",
                        "processed": total_processed,
                        "failed": failed_count
                    })
            
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
            await websocket_manager.broadcast({
                "type": "scan_error", 
                "error": str(e)
            })
            raise
    
    async def _fetch_torrents_by_status(self, status: str) -> List[Dict]:
        """Fetch torrents by specific status"""
        response = requests.get(
            f"{self.base_url}torrents",
            headers=self.headers,
            params={"filter": status, "limit": 1000}
        )
        response.raise_for_status()
        return response.json()
    
    async def _fetch_all_torrents(self) -> List[Dict]:
        """Fetch all torrents with pagination"""
        all_torrents = []
        offset = 0
        limit = 1000
        
        while True:
            response = requests.get(
                f"{self.base_url}torrents",
                headers=self.headers,
                params={"limit": limit, "offset": offset}
            )
            response.raise_for_status()
            
            torrents = response.json()
            if not torrents:
                break
                
            all_torrents.extend(torrents)
            offset += limit
            
            if len(torrents) < limit:
                break
        
        return all_torrents
    
    async def _process_torrent(self, db: Session, torrent_data: Dict):
        """Process single torrent and save to DB"""
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
    
    def _calculate_priority(self, torrent_data: Dict) -> int:
        """Calculate torrent priority (1=low, 2=normal, 3=high)"""
        status = torrent_data.get("status", "").lower()
        size_gb = torrent_data.get("bytes", 0) / (1024**3)
        
        if status == "magnet_error" or size_gb > 1:
            return 3  # High
        elif size_gb < 0.1:
            return 1  # Low
        return 2  # Normal
    
    async def reinject_torrent(self, db: Session, torrent_id: str) -> Dict:
        """Reinject failed torrent"""
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
            # Construct magnet link
            magnet_link = f"magnet:?xt=urn:btih:{torrent.hash}&dn={torrent.filename}"
            
            # API call to Real-Debrid
            response = requests.post(
                f"{self.base_url}torrents/addMagnet",
                headers=self.headers,
                data={"magnet": magnet_link}
            )
            
            response_time = int((time.time() - start_time) * 1000)
            success = response.status_code in [200, 201]
            
            # Record attempt
            attempt = Attempt(
                torrent_id=torrent_id,
                success=success,
                response_time_ms=response_time,
                error_message=response.text if not success else None,
                api_response=response.text
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
                "error": response.text if not success else None
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