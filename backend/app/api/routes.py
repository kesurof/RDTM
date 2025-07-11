from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.db.database import get_db
from app.services.torrent_service import TorrentService
from app.services.symlink_service import SymlinkService
from app.db.models import Torrent, BrokenSymlink

router = APIRouter()
torrent_service = TorrentService()
symlink_service = SymlinkService()

# Pydantic models
class ScanRequest(BaseModel):
    mode: str = "quick"  # quick, full, symlinks

class ReinjectRequest(BaseModel):
    torrent_ids: List[str]

class TorrentResponse(BaseModel):
    id: str
    filename: str
    status: str
    size: int
    attempts_count: int
    priority: int
    last_seen: str

# Health check
@router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": "2024-01-01T00:00:00Z"}

# Torrents endpoints
@router.get("/torrents", response_model=List[TorrentResponse])
async def get_torrents(
    status: Optional[str] = None,
    limit: int = Query(50, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db)
):
    query = db.query(Torrent)
    
    if status:
        if status == "failed":
            query = query.filter(Torrent.status.in_(["magnet_error", "error", "virus", "dead"]))
        else:
            query = query.filter(Torrent.status == status)
    
    torrents = query.offset(offset).limit(limit).all()
    
    return [
        TorrentResponse(
            id=t.id,
            filename=t.filename,
            status=t.status,
            size=t.size,
            attempts_count=t.attempts_count,
            priority=t.priority,
            last_seen=t.last_seen.isoformat()
        ) for t in torrents
    ]

@router.post("/torrents/scan")
async def scan_torrents(request: ScanRequest, db: Session = Depends(get_db)):
    try:
        result = await torrent_service.scan_torrents(db, request.mode)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/torrents/reinject")
async def reinject_torrents(request: ReinjectRequest, db: Session = Depends(get_db)):
    results = []
    
    for torrent_id in request.torrent_ids:
        try:
            result = await torrent_service.reinject_torrent(db, torrent_id)
            results.append(result)
        except Exception as e:
            results.append({
                "success": False,
                "torrent_id": torrent_id,
                "error": str(e)
            })
    
    return {"results": results}

@router.delete("/torrents/{torrent_id}")
async def delete_torrent(torrent_id: str, db: Session = Depends(get_db)):
    torrent = db.query(Torrent).filter_by(id=torrent_id).first()
    if not torrent:
        raise HTTPException(status_code=404, detail="Torrent not found")
    
    db.delete(torrent)
    db.commit()
    
    return {"success": True, "message": "Torrent deleted"}

# Symlinks endpoints
@router.get("/symlinks/broken")
async def get_broken_symlinks(
    limit: int = Query(100, le=1000),
    processed: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    query = db.query(BrokenSymlink)
    
    if processed is not None:
        query = query.filter(BrokenSymlink.processed == processed)
    
    symlinks = query.limit(limit).all()
    
    return [
        {
            "id": s.id,
            "source_path": s.source_path,
            "torrent_name": s.torrent_name,
            "status": s.status,
            "matched_torrent_id": s.matched_torrent_id,
            "processed": s.processed,
            "detected_date": s.detected_date.isoformat()
        } for s in symlinks
    ]

@router.post("/symlinks/scan")
async def scan_symlinks(db: Session = Depends(get_db)):
    try:
        result = await symlink_service.scan_broken_symlinks(db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/symlinks/match")
async def match_symlinks(db: Session = Depends(get_db)):
    try:
        result = await symlink_service.match_symlinks_to_torrents(db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Stats
@router.get("/stats")
async def get_stats(db: Session = Depends(get_db)):
    try:
        torrent_stats = torrent_service.get_stats(db)
        symlink_stats = await symlink_service.get_stats(db)
        
        return {
            "torrents": torrent_stats,
            "symlinks": symlink_stats,
            "timestamp": "2024-01-01T00:00:00Z"
        }
    except Exception as e:
        return {
            "torrents": {"total_torrents": 0, "failed_torrents": 0},
            "symlinks": {"total_broken": 0, "matched": 0},
            "timestamp": "2024-01-01T00:00:00Z"
        }

