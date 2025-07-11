import os
import time
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from difflib import SequenceMatcher

from app.db.models import BrokenSymlink, Torrent
from app.core.config import settings
from app.core.websocket import websocket_manager


class SymlinkService:
    def __init__(self):
        self.media_path = settings.media_path
    
    async def scan_broken_symlinks(self, db: Session, path: str = None) -> Dict:
        """Scan for broken symlinks in media directories"""
        scan_path = path or self.media_path
        
        await websocket_manager.broadcast({"type": "symlink_scan_start", "path": scan_path})
        
        start_time = time.time()
        broken_links = []
        
        try:
            for root, dirs, files in os.walk(scan_path):
                for file in files:
                    full_path = os.path.join(root, file)
                    
                    if os.path.islink(full_path):
                        target = os.readlink(full_path)
                        
                        # Check if broken
                        if not os.path.exists(full_path):
                            torrent_name = self._extract_torrent_name(target)
                            
                            broken_link = BrokenSymlink(
                                source_path=full_path,
                                target_path=target,
                                torrent_name=torrent_name,
                                status="BROKEN",
                                size=0
                            )
                            
                            # Check if already exists
                            existing = db.query(BrokenSymlink).filter_by(
                                source_path=full_path
                            ).first()
                            
                            if not existing:
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
            await websocket_manager.broadcast({
                "type": "symlink_scan_error",
                "error": str(e)
            })
            raise
    
    def _extract_torrent_name(self, target_path: str) -> str:
        """Extract torrent name from Zurg path"""
        # Pattern: /path/to/zurg/torrents/TORRENT_NAME/file
        parts = target_path.split('/')
        
        try:
            torrents_index = parts.index('torrents')
            if torrents_index + 1 < len(parts):
                return parts[torrents_index + 1]
        except ValueError:
            pass
        
        # Fallback: use directory name
        return os.path.basename(os.path.dirname(target_path))
    
    async def match_symlinks_to_torrents(self, db: Session) -> Dict:
        """Match broken symlinks to Real-Debrid torrents"""
        await websocket_manager.broadcast({"type": "symlink_match_start"})
        
        start_time = time.time()
        
        # Get unprocessed broken symlinks
        broken_symlinks = db.query(BrokenSymlink).filter_by(
            processed=False,
            matched_torrent_id=None
        ).all()
        
        matched_count = 0
        
        for symlink in broken_symlinks:
            # Find matching torrent
            torrent = self._find_matching_torrent(db, symlink.torrent_name)
            
            if torrent:
                symlink.matched_torrent_id = torrent.id
                matched_count += 1
                
                # Update torrent status for processing
                torrent.status = "symlink_broken"
                torrent.priority = 3  # High priority
        
        db.commit()
        
        duration = time.time() - start_time
        
        result = {
            "total_symlinks": len(broken_symlinks),
            "matched_count": matched_count,
            "match_rate": (matched_count / len(broken_symlinks) * 100) if broken_symlinks else 0,
            "duration": duration,
            "success": True
        }
        
        await websocket_manager.broadcast({
            "type": "symlink_match_complete",
            **result
        })
        
        return result
    
    def _find_matching_torrent(self, db: Session, torrent_name: str) -> Optional[Torrent]:
        """Find matching torrent by name similarity"""
        # Clean torrent name
        clean_name = self._clean_name(torrent_name)
        
        # Get all torrents
        torrents = db.query(Torrent).all()
        
        best_match = None
        best_score = 0.0
        threshold = 0.7
        
        for torrent in torrents:
            clean_torrent = self._clean_name(torrent.filename)
            
            # Calculate similarity
            similarity = SequenceMatcher(None, clean_name, clean_torrent).ratio()
            
            if similarity > best_score and similarity >= threshold:
                best_score = similarity
                best_match = torrent
        
        return best_match
    
    def _clean_name(self, name: str) -> str:
        """Clean filename for comparison"""
        import re
        
        # Remove file extensions
        clean = os.path.splitext(name)[0]
        
        # Replace separators with spaces
        clean = re.sub(r'[._-]', ' ', clean.lower())
        
        # Remove common release tags
        clean = re.sub(r'\b(x264|x265|1080p|720p|webrip|bluray|hdtv)\b', '', clean)
        
        # Remove extra spaces
        clean = ' '.join(clean.split())
        
        return clean.strip()
    
    async def get_stats(self, db: Session) -> Dict:
        """Get symlink statistics"""
        total_broken = db.query(BrokenSymlink).count()
        matched = db.query(BrokenSymlink).filter(
            BrokenSymlink.matched_torrent_id.isnot(None)
        ).count()
        processed = db.query(BrokenSymlink).filter_by(processed=True).count()
        
        return {
            "total_broken": total_broken,
            "matched": matched,
            "processed": processed,
            "unprocessed": total_broken - processed,
            "match_rate": (matched / total_broken * 100) if total_broken > 0 else 0
        }