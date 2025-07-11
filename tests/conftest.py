import pytest
import asyncio
import os
from unittest.mock import Mock, AsyncMock
import redis
from backend.core.security import SecurityManager
from backend.services.real_debrid_service import RealDebridService

@pytest.fixture
def event_loop():
    """Fixture pour les tests async"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_redis():
    """Mock Redis pour les tests"""
    mock_redis = Mock(spec=redis.Redis)
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.setex.return_value = True
    mock_redis.incr.return_value = 1
    mock_redis.expire.return_value = True
    return mock_redis

@pytest.fixture
def security_manager():
    """Fixture pour SecurityManager"""
    os.environ.update({
        'JWT_SECRET_KEY': 'test_secret_key_for_testing_only',
        'JWT_ALGORITHM': 'HS256',
        'JWT_EXPIRATION_HOURS': '24',
        'ENCRYPTION_KEY': 'test_encryption_key_32_bytes_long!',
        'REDIS_URL': 'redis://localhost:6379'
    })
    return SecurityManager()

@pytest.fixture
def mock_real_debrid_service():
    """Mock pour RealDebridService"""
    service = Mock(spec=RealDebridService)
    service.get_user_info = AsyncMock(return_value={'id': 123, 'username': 'testuser'})
    service.get_torrents = AsyncMock(return_value={'torrents': []})
    service.add_torrent = AsyncMock(return_value={'id': 'torrent123'})
    return service

@pytest.fixture
def sample_user_data():
    """Données utilisateur de test"""
    return {
        'id': 1,
        'username': 'testuser',
        'email': 'test@example.com',
        'api_key': 'test_api_key'
    }

@pytest.fixture
def sample_torrent_data():
    """Données torrent de test"""
    return {
        'id': 'torrent123',
        'filename': 'test_torrent.torrent',
        'status': 'downloaded',
        'progress': 100,
        'files': [
            {'id': 1, 'path': '/test/file1.mp4', 'bytes': 1024000},
            {'id': 2, 'path': '/test/file2.mp4', 'bytes': 2048000}
        ]
    }
