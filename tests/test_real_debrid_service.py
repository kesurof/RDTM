import pytest
import asyncio
import aiohttp
from unittest.mock import AsyncMock, Mock, patch
from backend.services.real_debrid_service import (
    RealDebridService, 
    RequestPriority, 
    QueuedRequest
)

class TestRealDebridService:
    
    @pytest.fixture
    def service(self):
        """Fixture pour RealDebridService"""
        with patch.dict('os.environ', {'REDIS_URL': 'redis://localhost:6379'}):
            return RealDebridService('test_api_key')

    @pytest.mark.asyncio
    async def test_ensure_session(self, service):
        """Test de création de session"""
        assert service.session is None
        await service._ensure_session()
        assert service.session is not None
        assert isinstance(service.session, aiohttp.ClientSession)
        await service.close()

    @pytest.mark.asyncio
    async def test_rate_limiter_per_second(self, service):
        """Test du rate limiting par seconde"""
        # Simulation de requêtes rapides
        service.rate_limiter['last_request_time'] = asyncio.get_event_loop().time()
        
        start_time = asyncio.get_event_loop().time()
        await service._wait_for_rate_limit()
        end_time = asyncio.get_event_loop().time()
        
        # Devrait attendre au moins 1/4 seconde
        assert end_time - start_time >= 0.2

    @pytest.mark.asyncio
    async def test_cache_operations(self, service):
        """Test des opérations de cache"""
        cache_key = service._get_cache_key('/test', {'param': 'value'})
        test_data = {'result': 'test_data'}
        
        # Test de stockage en cache
        await service._set_cache(cache_key, test_data, 60)
        
        # Test de récupération du cache
        with patch.object(service.redis_client, 'get') as mock_get:
            mock_get.return_value = '{"result": "test_data"}'
            cached_data = await service._get_from_cache(cache_key)
            assert cached_data == test_data

    @pytest.mark.asyncio
    async def test_queue_request_with_cache_hit(self, service):
        """Test de requête avec cache hit"""
        endpoint = '/user'
        expected_data = {'id': 123, 'username': 'testuser'}
        
        with patch.object(service, '_get_from_cache') as mock_cache:
            mock_cache.return_value = expected_data
            
            result = await service.queue_request(endpoint, use_cache=True)
            assert result == expected_data
            mock_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_queue_request_cache_miss(self, service):
        """Test de requête avec cache miss"""
        endpoint = '/user'
        expected_data = {'id': 123, 'username': 'testuser'}
        
        with patch.object(service, '_get_from_cache') as mock_cache, \
             patch.object(service, '_make_request_with_retry') as mock_request, \
             patch.object(service, '_set_cache') as mock_set_cache:
            
            mock_cache.return_value = None  # Cache miss
            mock_request.return_value = expected_data
            
            result = await service.queue_request(endpoint, use_cache=True)
            
            assert result == expected_data
            mock_cache.assert_called_once()
            mock_set_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_critical_priority_request(self, service):
        """Test de requête avec priorité critique"""
        endpoint = '/urgent'
        expected_data = {'status': 'urgent_processed'}
        
        with patch.object(service, '_make_request_with_retry') as mock_request:
            mock_request.return_value = expected_data
            
            result = await service.queue_request(
                endpoint, 
                priority=RequestPriority.CRITICAL,
                use_cache=False
            )
            
            assert result == expected_data
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_with_retry_success(self, service):
        """Test de requête avec succès au premier essai"""
        request = QueuedRequest(
            url='/test',
            method='GET',
            data={},
            priority=RequestPriority.NORMAL,
            timestamp=asyncio.get_event_loop().time()
        )
        
        mock_response = AsyncMock()
        mock_response.json.return_value = {'success': True}
        mock_response.raise_for_status.return_value = None
        
        with patch.object(service, '_ensure_session'), \
             patch.object(service, '_wait_for_rate_limit'), \
             patch.object(service.session, 'get') as mock_get:
            
            mock_get.return_value.__aenter__.return_value = mock_response
            
            result = await service._make_request_with_retry(request)
            assert result == {'success': True}

    @pytest.mark.asyncio
    async def test_request_with_retry_failure_then_success(self, service):
        """Test de requête avec échec puis succès"""
        request = QueuedRequest(
            url='/test',
            method='GET',
            data={},
            priority=RequestPriority.NORMAL,
            timestamp=asyncio.get_event_loop().time(),
            max_retries=2
        )
        
        # Premier appel échoue, deuxième réussit
        mock_response_success = AsyncMock()
        mock_response_success.json.return_value = {'success': True}
        mock_response_success.raise_for_status.return_value = None
        
        with patch.object(service, '_ensure_session'), \
             patch.object(service, '_wait_for_rate_limit'), \
             patch.object(service.session, 'get') as mock_get, \
             patch('asyncio.sleep'):  # Mock sleep pour accélérer les tests
            
            mock_get.side_effect = [
                aiohttp.ClientError("Network error"),  # Premier échec
                mock_response_success.__aenter__.return_value  # Deuxième succès
            ]
            
            result = await service._make_request_with_retry(request)
            assert result == {'success': True}
            assert mock_get.call_count == 2

    @pytest.mark.asyncio
    async def test_api_methods(self, service):
        """Test des méthodes spécifiques à l'API"""
        expected_user_info = {'id': 123, 'username': 'testuser'}
        expected_torrents = {'torrents': []}
        
        with patch.object(service, 'queue_request') as mock_queue:
            mock_queue.return_value = expected_user_info
            result = await service.get_user_info()
            assert result == expected_user_info
            mock_queue.assert_called_with('user', cache_ttl=600)
            
            mock_queue.return_value = expected_torrents
            result = await service.get_torrents(offset=10, limit=25)
            assert result == expected_torrents
            mock_queue.assert_called_with(
                'torrents', 
                data={'offset': 10, 'limit': 25}, 
                cache_ttl=60
            )

    @pytest.mark.asyncio
    async def test_add_torrent(self, service):
        """Test d'ajout de torrent"""
        torrent_data = "magnet:?xt=urn:btih:test"
        expected_result = {'id': 'torrent123'}
        
        with patch.object(service, 'queue_request') as mock_queue:
            mock_queue.return_value = expected_result
            
            result = await service.add_torrent(torrent_data)
            
            assert result == expected_result
            mock_queue.assert_called_with(
                'torrents/addTorrent',
                method='POST',
                data={'torrent': torrent_data},
                priority=RequestPriority.HIGH,
                use_cache=False
            )

    @pytest.mark.asyncio
    async def test_select_files(self, service):
        """Test de sélection de fichiers"""
        torrent_id = 'torrent123'
        file_ids = ['1', '2', '3']
        expected_result = {'status': 'files_selected'}
        
        with patch.object(service, 'queue_request') as mock_queue:
            mock_queue.return_value = expected_result
            
            result = await service.select_files(torrent_id, file_ids)
            
            assert result == expected_result
            mock_queue.assert_called_with(
                f'torrents/selectFiles/{torrent_id}',
                method='POST',
                data={'files': '1,2,3'},
                priority=RequestPriority.HIGH,
                use_cache=False
            )

    @pytest.mark.asyncio
    async def test_close_session(self, service):
        """Test de fermeture de session"""
        await service._ensure_session()
        assert service.session is not None
        
        await service.close()
        assert service.session.closed
