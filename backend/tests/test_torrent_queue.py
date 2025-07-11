import pytest
import asyncio
from unittest.mock import Mock, patch
from datetime import datetime

from backend.services.torrent_queue import TorrentQueue, TorrentStatus, TorrentJob

@pytest.fixture
def torrent_queue():
    return TorrentQueue()

@pytest.mark.asyncio
async def test_add_torrent(torrent_queue):
    """Test d'ajout d'un torrent à la queue"""
    magnet_link = "magnet:?xt=urn:btih:test"
    name = "Test Torrent"
    
    job_id = await torrent_queue.add_torrent(magnet_link, name)
    
    assert job_id is not None
    assert len(torrent_queue.queue) == 1
    assert torrent_queue.queue[0].magnet_link == magnet_link
    assert torrent_queue.queue[0].name == name
    assert torrent_queue.queue[0].status == TorrentStatus.QUEUED

@pytest.mark.asyncio
async def test_queue_status(torrent_queue):
    """Test du statut de la queue"""
    await torrent_queue.add_torrent("magnet:?xt=urn:btih:test1", "Test 1")
    await torrent_queue.add_torrent("magnet:?xt=urn:btih:test2", "Test 2")
    
    status = torrent_queue.get_queue_status()
    
    assert status["queued"] == 2
    assert status["active"] == 0
    assert len(status["jobs"]) == 2

@pytest.mark.asyncio
async def test_max_concurrent_limit(torrent_queue):
    """Test de la limite de torrents concurrents"""
    torrent_queue.max_concurrent = 2
    
    # Ajouter plus de torrents que la limite
    for i in range(5):
        await torrent_queue.add_torrent(f"magnet:?xt=urn:btih:test{i}", f"Test {i}")
    
    # Simuler le traitement
    await torrent_queue._process_queue()
    
    # Vérifier que seulement 2 torrents sont actifs
    assert len(torrent_queue.active_jobs) <= 2
    assert len(torrent_queue.queue) == 3  # 5 - 2 = 3 restants en queue
