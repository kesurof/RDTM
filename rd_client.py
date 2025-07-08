#!/usr/bin/env python3

import time
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import json
import threading
from dataclasses import dataclass

from config import RD_API_CONFIG, RATE_LIMIT_CONFIG, get_env_config

logger = logging.getLogger(__name__)

@dataclass
class RateLimitState:
    """État du rate limiting"""
    current_delay: float = RATE_LIMIT_CONFIG['initial_delay']
    last_request_time: float = 0
    requests_count: int = 0
    errors_count: int = 0
    success_streak: int = 0
    max_torrents_per_cycle: int = RATE_LIMIT_CONFIG['max_torrents_per_cycle']

class RealDebridClient:
    """Client API Real-Debrid avec rate limiting adaptatif"""
    
    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token or get_env_config()['rd_api_token']
        if not self.api_token:
            raise ValueError("Token API Real-Debrid manquant")
        
        self.base_url = RD_API_CONFIG['base_url']
        self.session = self._create_session()
        self.rate_limit = RateLimitState()
        self._lock = threading.Lock()
        
        logger.info("Client Real-Debrid initialisé")
    
    def _create_session(self) -> requests.Session:
        """Crée une session HTTP avec retry automatique"""
        session = requests.Session()
        
        # Configuration retry (inspirée du script existant)
        retry_strategy = Retry(
            total=RD_API_CONFIG['max_retries'],
            backoff_factor=RD_API_CONFIG['backoff_factor'],
            status_forcelist=[429, 500, 502, 503, 504],
            respect_retry_after_header=True
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Headers par défaut
        session.headers.update({
            'Authorization': f'Bearer {self.api_token}',
            'User-Agent': 'Real-Debrid-Manager/1.0',
            'Content-Type': 'application/json'
        })
        
        return session
    
    def _wait_for_rate_limit(self):
        """Applique le rate limiting"""
        with self._lock:
            now = time.time()
            time_since_last = now - self.rate_limit.last_request_time
            
            if time_since_last < self.rate_limit.current_delay:
                sleep_time = self.rate_limit.current_delay - time_since_last
                logger.debug(f"Rate limiting: attente {sleep_time:.2f}s")
                time.sleep(sleep_time)
            
            self.rate_limit.last_request_time = time.time()
    
    def _update_rate_limit(self, success: bool, response_code: Optional[int] = None):
        """Met à jour le rate limiting basé sur le succès de la requête"""
        with self._lock:
            self.rate_limit.requests_count += 1
            
            if success and response_code not in RD_API_CONFIG['rate_limit_codes']:
                # Succès - on peut accélérer progressivement
                self.rate_limit.success_streak += 1
                self.rate_limit.errors_count = max(0, self.rate_limit.errors_count - 1)
                
                # Réduire le délai après plusieurs succès
                if self.rate_limit.success_streak >= 5:
                    self.rate_limit.current_delay = max(
                        RATE_LIMIT_CONFIG['min_delay'],
                        self.rate_limit.current_delay / RATE_LIMIT_CONFIG['recovery_divisor']
                    )
                    self.rate_limit.success_streak = 0
                    
                    # Augmenter le nombre de torrents par cycle
                    if self.rate_limit.max_torrents_per_cycle < RATE_LIMIT_CONFIG['max_torrents_limit']:
                        self.rate_limit.max_torrents_per_cycle = min(
                            RATE_LIMIT_CONFIG['max_torrents_limit'],
                            self.rate_limit.max_torrents_per_cycle + 1
                        )
                        logger.info(f"Rate limiting: augmentation à {self.rate_limit.max_torrents_per_cycle} torrents/cycle")
                    
            else:
                # Erreur ou rate limit - ralentir
                self.rate_limit.errors_count += 1
                self.rate_limit.success_streak = 0
                
                if response_code in RD_API_CONFIG['rate_limit_codes']:
                    # Rate limit détecté - ralentir drastiquement
                    self.rate_limit.current_delay = min(
                        RATE_LIMIT_CONFIG['max_delay'],
                        self.rate_limit.current_delay * RATE_LIMIT_CONFIG['backoff_multiplier'] * 2
                    )
                    
                    # Réduire le nombre de torrents par cycle
                    self.rate_limit.max_torrents_per_cycle = max(1, self.rate_limit.max_torrents_per_cycle - 2)
                    logger.warning(f"Rate limit détecté! Réduction à {self.rate_limit.max_torrents_per_cycle} torrents/cycle")
                    
                else:
                    # Autre erreur - ralentir modérément
                    self.rate_limit.current_delay = min(
                        RATE_LIMIT_CONFIG['max_delay'],
                        self.rate_limit.current_delay * RATE_LIMIT_CONFIG['backoff_multiplier']
                    )
            
            logger.debug(f"Rate limit state: delay={self.rate_limit.current_delay:.2f}s, "
                        f"max_torrents={self.rate_limit.max_torrents_per_cycle}, "
                        f"errors={self.rate_limit.errors_count}")
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """Effectue une requête HTTP avec gestion des erreurs et rate limiting"""
        self._wait_for_rate_limit()
        
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        start_time = time.time()
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                timeout=RD_API_CONFIG['timeout'],
                **kwargs
            )
            
            response_time = int((time.time() - start_time) * 1000)
            
            # Analyser la réponse
            if response.status_code == 200:
                self._update_rate_limit(True, response.status_code)
                try:
                    data = response.json()
                    logger.debug(f"API {method} {endpoint}: 200 OK ({response_time}ms)")
                    return True, data, None
                except json.JSONDecodeError:
                    error = "Réponse JSON invalide"
                    logger.error(f"API {method} {endpoint}: {error}")
                    return False, None, error
                    
            elif response.status_code in [401, 403]:
                error = "Token API invalide ou expiré"
                logger.error(f"API {method} {endpoint}: {response.status_code} - {error}")
                self._update_rate_limit(False, response.status_code)
                return False, None, error
                
            elif response.status_code in RD_API_CONFIG['rate_limit_codes']:
                error = f"Rate limit (code {response.status_code})"
                logger.warning(f"API {method} {endpoint}: {error}")
                self._update_rate_limit(False, response.status_code)
                return False, None, error
                
            else:
                try:
                    error_data = response.json()
                    error = error_data.get('error', f"HTTP {response.status_code}")
                except:
                    error = f"HTTP {response.status_code}"
                
                logger.error(f"API {method} {endpoint}: {response.status_code} - {error}")
                self._update_rate_limit(False, response.status_code)
                return False, None, error
                
        except requests.exceptions.Timeout:
            error = "Timeout"
            logger.error(f"API {method} {endpoint}: {error}")
            self._update_rate_limit(False)
            return False, None, error
            
        except requests.exceptions.ConnectionError as e:
            error = f"Erreur de connexion: {str(e)}"
            logger.error(f"API {method} {endpoint}: {error}")
            self._update_rate_limit(False)
            return False, None, error
            
        except Exception as e:
            error = f"Erreur inattendue: {str(e)}"
            logger.error(f"API {method} {endpoint}: {error}")
            self._update_rate_limit(False)
            return False, None, error
    
    def get_torrents(self, status_filter: Optional[str] = None, limit: int = 100) -> Tuple[bool, List[Dict], Optional[str]]:
        """Récupère la liste des torrents"""
        params = {'limit': limit}
        if status_filter:
            params['filter'] = status_filter
        
        success, data, error = self._make_request('GET', 'torrents', params=params)
        
        if success and isinstance(data, list):
            logger.info(f"Récupération de {len(data)} torrents")
            return True, data, None
        elif success:
            error = "Format de réponse inattendu"
            logger.error(f"get_torrents: {error}")
            return False, [], error
        else:
            return False, [], error
    
    def get_torrent_info(self, torrent_id: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """Récupère les informations détaillées d'un torrent"""
        success, data, error = self._make_request('GET', f'torrents/info/{torrent_id}')
        
        if success:
            logger.debug(f"Info torrent {torrent_id}: {data.get('filename', 'unknown')}")
            return True, data, None
        else:
            return False, None, error
    
    def add_magnet(self, magnet_link: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """Ajoute un torrent via magnet link"""
        data = {'magnet': magnet_link}
        
        success, response_data, error = self._make_request('POST', 'torrents/addMagnet', data=data)
        
        if success:
            torrent_id = response_data.get('id') if response_data else 'unknown'
            logger.info(f"Torrent ajouté avec succès: {torrent_id}")
            return True, response_data, None
        else:
            logger.error(f"Échec ajout magnet: {error}")
            return False, None, error
    
    def delete_torrent(self, torrent_id: str) -> Tuple[bool, Optional[str]]:
        """Supprime un torrent"""
        success, data, error = self._make_request('DELETE', f'torrents/delete/{torrent_id}')
        
        if success:
            logger.info(f"Torrent supprimé: {torrent_id}")
            return True, None
        else:
            logger.error(f"Échec suppression torrent {torrent_id}: {error}")
            return False, error
    
    def get_user_info(self) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """Récupère les informations utilisateur (test de connectivité)"""
        success, data, error = self._make_request('GET', 'user')
        
        if success:
            username = data.get('username', 'unknown') if data else 'unknown'
            logger.info(f"Connexion API validée pour: {username}")
            return True, data, None
        else:
            return False, None, error
    
    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Retourne l'état actuel du rate limiting"""
        return {
            'current_delay': self.rate_limit.current_delay,
            'requests_count': self.rate_limit.requests_count,
            'errors_count': self.rate_limit.errors_count,
            'success_streak': self.rate_limit.success_streak,
            'max_torrents_per_cycle': self.rate_limit.max_torrents_per_cycle,
            'last_request_ago': time.time() - self.rate_limit.last_request_time
        }
    
    def test_connection(self) -> bool:
        """Test de connectivité API"""
        logger.info("Test de connexion à l'API Real-Debrid...")
        
        success, data, error = self.get_user_info()
        if success:
            premium_until = data.get('premium', 0) if data else 0
            if premium_until > time.time():
                logger.info("✅ Connexion API validée - Compte premium actif")
                return True
            else:
                logger.warning("⚠️ Connexion API OK mais compte premium expiré")
                return False
        else:
            logger.error(f"❌ Échec test connexion: {error}")
            return False
    
    def close(self):
        """Ferme la session HTTP"""
        if hasattr(self, 'session'):
            self.session.close()
            logger.info("Session API fermée")