from fastapi import WebSocket
from typing import List, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def send_personal_message(self, message: Dict[Any, Any], websocket: WebSocket):
        """Send message to specific WebSocket"""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"Failed to send personal message: {e}")
            self.disconnect(websocket)
    
    async def broadcast(self, message: Dict[Any, Any]):
        """Broadcast message to all connected clients"""
        if not self.active_connections:
            return
            
        message_text = json.dumps(message)
        disconnected = []
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message_text)
            except Exception as e:
                logger.error(f"Failed to broadcast to client: {e}")
                disconnected.append(connection)
        
        # Remove disconnected clients
        for connection in disconnected:
            self.disconnect(connection)
    
    async def broadcast_scan_start(self, mode: str):
        """Broadcast scan start event"""
        await self.broadcast({
            "type": "scan_start",
            "mode": mode,
            "timestamp": "2024-01-01T00:00:00Z"
        })
    
    async def broadcast_scan_progress(self, processed: int, failed: int):
        """Broadcast scan progress"""
        await self.broadcast({
            "type": "scan_progress",
            "processed": processed,
            "failed": failed,
            "timestamp": "2024-01-01T00:00:00Z"
        })
    
    async def broadcast_scan_complete(self, result: Dict[Any, Any]):
        """Broadcast scan completion"""
        await self.broadcast({
            "type": "scan_complete",
            **result,
            "timestamp": "2024-01-01T00:00:00Z"
        })
    
    async def broadcast_reinject_start(self, torrent_id: str, filename: str):
        """Broadcast reinject start"""
        await self.broadcast({
            "type": "reinject_start",
            "torrent_id": torrent_id,
            "filename": filename[:50],
            "timestamp": "2024-01-01T00:00:00Z"
        })
    
    async def broadcast_reinject_complete(self, result: Dict[Any, Any]):
        """Broadcast reinject completion"""
        await self.broadcast({
            "type": "reinject_complete",
            **result,
            "timestamp": "2024-01-01T00:00:00Z"
        })
    
    async def broadcast_symlink_scan_start(self, path: str):
        """Broadcast symlink scan start"""
        await self.broadcast({
            "type": "symlink_scan_start",
            "path": path,
            "timestamp": "2024-01-01T00:00:00Z"
        })
    
    async def broadcast_symlink_scan_complete(self, result: Dict[Any, Any]):
        """Broadcast symlink scan completion"""
        await self.broadcast({
            "type": "symlink_scan_complete",
            **result,
            "timestamp": "2024-01-01T00:00:00Z"
        })

# Global WebSocket manager instance
websocket_manager = WebSocketManager()