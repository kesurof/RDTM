import asyncio
import aiohttp
import time
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import redis
import json
import logging

logger = logging.getLogger(__name__)

class RequestPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4

@dataclass
class QueuedRequest:
    url: str
    method: str
    data: dict
    priority: RequestPriority
    timestamp: float
    retry_count: int = 0
    max_retries: int = 3

class RealDebridService:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.real-debrid.com/rest/1.0"
        self.redis_client = redis.Redis.from_url(os.getenv('REDIS_URL'))
        self.request_queue = asyncio.Queue()
        self.rate_limiter = self._init_rate_limiter()
        self.session = None
        
    def _init_rate_limiter(self):
        """Initialise le rate limiter avec les limites Real-Debrid"""
        return {
            'per_second': 4,
            'per_minute': 250,
            'last_request_time': 0,
            'requests_this_minute': 0,
            'minute_start': time.time()
        }

    async def _ensure_session(self):
        """S'assure qu'une session aiohttp est disponible"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={'Authorization': f'Bearer {self.api_key}'},
                timeout=aiohttp.ClientTimeout(total=30)
            )

    async def _wait_for_rate_limit(self):
        """Attend si nécessaire pour respecter les limites de taux"""
        current_time = time.time()
        
        # Reset du compteur par minute si nécessaire
        if current_time - self.rate_limiter['minute_start'] >= 60:
            self.rate_limiter['requests_this_minute'] = 0
            self.rate_limiter['minute_start'] = current_time
        
        # Vérification limite par seconde
        time_since_last = current_time - self.rate_limiter['last_request_time']
        if time_since_last < (1.0 / self.rate_limiter['per_second']):
            await asyncio.sleep((1.0 / self.rate_limiter['per_second']) - time_since_last)
        
        # Vérification limite par minute
        if self.rate_limiter['requests_this_minute'] >= self.rate_limiter['per_minute']:
            sleep_time = 60 - (current_time - self.rate_limiter['minute_start'])
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
                self.rate_limiter['requests_this_minute'] = 0
                self.rate_limiter['minute_start'] = time.time()

    def _get_cache_key(self, endpoint: str, params: dict = None) -> str:
        """Génère une clé de cache pour la requête"""
        cache_data = f"{endpoint}:{json.dumps(params or {}, sort_keys=True)}"
        return f"rd_cache:{hash(cache_data)}"

    async def _get_from_cache(self, cache_key: str) -> Optional[dict]:
        """Récupère des données du cache Redis"""
        try:
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Erreur lors de la lecture du cache: {e}")
        return None

    async def _set_cache(self, cache_key: str, data: dict, ttl: int = 300):
        """Stocke des données dans le cache Redis"""
        try:
            self.redis_client.setex(
                cache_key, 
                ttl, 
                json.dumps(data, default=str)
            )
        except Exception as e:
            logger.warning(f"Erreur lors de l'écriture du cache: {e}")

    async def _make_request_with_retry(self, request: QueuedRequest) -> dict:
        """Effectue une requête avec retry et backoff exponentiel"""
        await self._ensure_session()
        
        for attempt in range(request.max_retries + 1):
            try:
                await self._wait_for_rate_limit()
                
                # Mise à jour des compteurs
                self.rate_limiter['last_request_time'] = time.time()
                self.rate_limiter['requests_this_minute'] += 1
                
                url = f"{self.base_url}/{request.url.lstrip('/')}"
                
                if request.method.upper() == 'GET':
                    async with self.session.get(url, params=request.data) as response:
                        response.raise_for_status()
                        return await response.json()
                elif request.method.upper() == 'POST':
                    async with self.session.post(url, data=request.data) as response:
                        response.raise_for_status()
                        return await response.json()
                        
            except aiohttp.ClientError as e:
                if attempt < request.max_retries:
                    # Backoff exponentiel
                    wait_time = (2 ** attempt) + (attempt * 0.1)
                    logger.warning(f"Tentative {attempt + 1} échouée, retry dans {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Échec définitif après {request.max_retries} tentatives: {e}")
                    raise
            except Exception as e:
                logger.error(f"Erreur inattendue: {e}")
                raise

    async def queue_request(self, endpoint: str, method: str = 'GET', 
                          data: dict = None, priority: RequestPriority = RequestPriority.NORMAL,
                          use_cache: bool = True, cache_ttl: int = 300) -> dict:
        """Ajoute une requête à la file d'attente"""
        
        # Vérification du cache pour les requêtes GET
        if method.upper() == 'GET' and use_cache:
            cache_key = self._get_cache_key(endpoint, data)
            cached_result = await self._get_from_cache(cache_key)
            if cached_result:
                logger.info(f"Cache hit pour {endpoint}")
                return cached_result
        
        request = QueuedRequest(
            url=endpoint,
            method=method,
            data=data or {},
            priority=priority,
            timestamp=time.time()
        )
        
        # Traitement immédiat pour les requêtes critiques
        if priority == RequestPriority.CRITICAL:
            result = await self._make_request_with_retry(request)
        else:
            await self.request_queue.put(request)
            result = await self._process_queue_item()
        
        # Mise en cache du résultat pour les GET
        if method.upper() == 'GET' and use_cache and result:
            cache_key = self._get_cache_key(endpoint, data)
            await self._set_cache(cache_key, result, cache_ttl)
        
        return result

    async def _process_queue_item(self) -> dict:
        """Traite un élément de la file d'attente"""
        request = await self.request_queue.get()
        try:
            result = await self._make_request_with_retry(request)
            self.request_queue.task_done()
            return result
        except Exception as e:
            self.request_queue.task_done()
            raise

    # Méthodes spécifiques à l'API Real-Debrid
    async def get_user_info(self) -> dict:
        """Récupère les informations utilisateur"""
        return await self.queue_request('user', cache_ttl=600)

    async def get_torrents(self, offset: int = 0, limit: int = 50) -> dict:
        """Récupère la liste des torrents"""
        params = {'offset': offset, 'limit': limit}
        return await self.queue_request('torrents', data=params, cache_ttl=60)

    async def add_torrent(self, torrent_data: str) -> dict:
        """Ajoute un nouveau torrent"""
        data = {'torrent': torrent_data}
        return await self.queue_request(
            'torrents/addTorrent', 
            method='POST', 
            data=data, 
            priority=RequestPriority.HIGH,
            use_cache=False
        )

    async def get_torrent_info(self, torrent_id: str) -> dict:
        """Récupère les informations d'un torrent spécifique"""
        return await self.queue_request(f'torrents/info/{torrent_id}', cache_ttl=30)

    async def select_files(self, torrent_id: str, file_ids: List[str]) -> dict:
        """Sélectionne les fichiers d'un torrent"""
        data = {'files': ','.join(file_ids)}
        return await self.queue_request(
            f'torrents/selectFiles/{torrent_id}',
            method='POST',
            data=data,
            priority=RequestPriority.HIGH,
            use_cache=False
        )

    async def close(self):
        """Ferme la session aiohttp"""
        if self.session and not self.session.closed:
            await self.session.close()

# Service singleton
_real_debrid_service = None

def get_real_debrid_service() -> RealDebridService:
    """Retourne l'instance singleton du service Real-Debrid"""
    global _real_debrid_service
    if _real_debrid_service is None:
        api_key = os.getenv('REAL_DEBRID_API_KEY')
        if not api_key:
            raise ValueError("REAL_DEBRID_API_KEY non configuré")
        _real_debrid_service = RealDebridService(api_key)
    return _real_debrid_service
