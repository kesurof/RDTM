import os
import time
import asyncio
import aiofiles
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from difflib import SequenceMatcher

from app.db.models import BrokenSymlink, Torrent
from app.core.config import settings
from app.core.websocket import websocket_manager
import logging

logger = logging.getLogger(__name__)

class SymlinkService:
    def __init__(self):
        self.media_path = settings.media_path
    
    async def scan_broken_symlinks(self, db: Session, path: str = None) -> Dict:
        """Scan for broken symlinks with async I/O"""
        scan_path = path or self.media_path
        
        await websocket_manager.broadcast({"type": "symlink_scan_start", "path": scan_path})
        
        start_time = time.time()
        broken_links = []
        
        try:
            # Use asyncio for concurrent file system operations
            tasks = []
            for root, dirs, files in os.walk(scan_path):
                for file in files:
                    full_path = os.path.join(root, file)
                    if os.path.islink(full_path):
                        tasks.append(self._check_symlink(full_path))
            
            # Process symlinks concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, dict) and result.get("broken"):
                    # Check if already exists
                    existing = db.query(BrokenSymlink).filter_by(
                        source_path=result["source_path"]
                    ).first()
                    
                    if not existing:
                        broken_link = BrokenSymlink(
                            source_path=result["source_path"],
                            target_path=result["target_path"],
                            torrent_name=result["torrent_name"],
                            status="BROKEN",
                            size=result.get("size", 0)
                        )
                        db.add(broken_link)
                        broken_links.append(broken_link)
            
            db.commit()
            duration = time.time() - start_time
            
            result = {
                "total_broken": len(broken_links),
                "scan_duration": duration,
                "scan_path": scan_path,
                "success": True
            }
            
            await websocket_manager.broadcast({
                "type": "symlink_scan_complete",
                **result
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Symlink scan failed: {e}")
            await websocket_manager.broadcast({
                "type": "symlink_scan_error",
                "error": str(e)
            })
            raise
    
    async def _check_symlink(self, symlink_path: str) -> Dict:
        """Check if symlink is broken with async I/O"""
        try:
            target = os.readlink(symlink_path)
            
            # Check if target exists
            if not os.path.exists(symlink_path):
                torrent_name = self._extract_torrent_name(target)
                
                # Try to get file size asynchronously
                size = 0
                try:
                    if os.path.exists(target):
                        stat = await asyncio.get_event_loop().run_in_executor(
                            None, os.stat, target
                        )
                        size = stat.st_size
                except:
                    pass
                
                return {
                    "broken": True,
                    "source_path": symlink_path,
                    "target_path": target,
                    "torrent_name": torrent_name,
                    "size": size
                }
            
            return {"broken": False}
            
        except Exception as e:
            logger.error(f"Error checking symlink {symlink_path}: {e}")
            return {"broken": False}
    
    def _extract_torrent_name(self, target_path: str) -> str:
        """Extract torrent name from Zurg path"""
        parts = target_path.split('/')
        
        try:
            torrents_index = parts.index('torrents')
            if torrents_index + 1 < len(parts):
                return parts[torrents_index + 1]
        except ValueError:
            pass
        
        return os.path.basename(os.path.dirname(target_path))
    
    async def match_symlinks_to_torrents(self, db: Session) -> Dict:
        """Match broken symlinks to Real-Debrid torrents with batch processing"""
        await websocket_manager.broadcast({"type": "symlink_match_start"})
        
        start_time = time.time()
        
        # Get unprocessed broken symlinks
        broken_symlinks = db.query(BrokenSymlink).filter_by(
            processed=False,
            matched_torrent_id=None
        ).all()
        
        # Get all torrents once for efficiency
        all_torrents = db.query(Torrent).all()
        torrent_lookup = {self._clean_name(t.filename): t for t in all_torrents}
        
        matched_count = 0
        batch_size = 100
        
        # Process symlinks in batches
        for i in range(0, len(broken_symlinks), batch_size):
            batch = broken_symlinks[i:i + batch_size]
            
            for symlink in batch:
                # Find matching torrent
                torrent = self._find_matching_torrent_optimized(
                    symlink.torrent_name, 
                    torrent_lookup, 
                    all_torrents
                )
                
                if torrent:
                    symlink.matched_torrent_id = torrent.id
                    matched_count += 1
                    
                    # Update torrent status for processing
                    torrent.status = "symlink_broken"
                    torrent.priority = 3  # High priority
            
            #