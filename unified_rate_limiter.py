#!/usr/bin/env python3

import time
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import deque
import threading

logger = logging.getLogger(__name__)

@dataclass
class APICall:
    """Représentation d'un appel API avec métadonnées"""
    timestamp: float
    operation_type: str  # 'test_injection', 'cleanup_rd', 'notify_media'
    identifier: str      # Hash torrent, ID, etc.
    priority: int = 1    # 1=normal, 2=high, 3=urgent

class UnifiedRateLimiter:
    """Rate limiter global unifié pour toutes les opérations API (250 calls/minute)"""
    
    def __init__(self, max_calls_per_minute: int = 250):
        self.max_calls_per_minute = max_calls_per_minute
        self.calls_window = deque()  # Sliding window des appels
        self.lock = asyncio.Lock()
        
        # Statistiques par type d'opération
        self.stats = {
            'test_injection': {'count': 0, 'avg_response_time': 0},
            'cleanup_rd': {'count': 0, 'avg_response_time': 0},
            'notify_media': {'count': 0, 'avg_response_time': 0}
        }
        
        # Configuration adaptative
        self.adaptive_config = {
            'test_injection': {'weight': 50, 'min_calls': 10},
            'cleanup_rd': {'weight': 30, 'min_calls': 5},
            'notify_media': {'weight': 20, 'min_calls': 5}
        }
        
        logger.info(f"UnifiedRateLimiter initialisé: {max_calls_per_minute} calls/minute max")
    
    async def acquire_slot(self, operation_type: str, identifier: str = "", 
                          priority: int = 1, timeout: float = 60.0) -> bool:
        """
        Acquiert un slot pour effectuer un appel API
        
        Args:
            operation_type: Type d'opération ('test_injection', 'cleanup_rd', 'notify_media')
            identifier: Identifiant de l'élément traité
            priority: Priorité (1=normal, 2=high, 3=urgent)
            timeout: Timeout en secondes
            
        Returns:
            True si slot acquis, False si timeout
        """
        start_time = time.time()
        
        async with self.lock:
            while True:
                now = time.time()
                
                # Nettoyer la fenêtre glissante (garder seulement dernière minute)
                minute_ago = now - 60.0
                while self.calls_window and self.calls_window[0].timestamp < minute_ago:
                    self.calls_window.popleft()
                
                # Vérifier si on peut faire l'appel
                current_calls = len(self.calls_window)
                
                if current_calls < self.max_calls_per_minute:
                    # Slot disponible - enregistrer l'appel
                    api_call = APICall(
                        timestamp=now,
                        operation_type=operation_type,
                        identifier=identifier,
                        priority=priority
                    )
                    self.calls_window.append(api_call)
                    
                    logger.debug(f"Slot acquis pour {operation_type} ({identifier}): "
                               f"{current_calls + 1}/{self.max_calls_per_minute}")
                    return True
                
                # Pas de slot disponible - vérifier timeout
                if now - start_time > timeout:
                    logger.warning(f"Timeout rate limiter pour {operation_type} ({identifier}) "
                                 f"après {timeout}s")
                    return False
                
                # Calculer le délai optimal avant prochain slot
                if self.calls_window:
                    next_available = self.calls_window[0].timestamp + 60.0
                    wait_time = max(0.1, next_available - now)
                else:
                    wait_time = 0.1
                
                # Attente avec logging périodique
                if int(now - start_time) % 10 == 0:  # Log toutes les 10s
                    logger.info(f"Rate limit atteint: {current_calls}/{self.max_calls_per_minute}, "
                               f"attente {wait_time:.1f}s pour {operation_type}")
                
                await asyncio.sleep(min(wait_time, 1.0))  # Max 1s d'attente par itération
    
    def record_completion(self, operation_type: str, response_time_ms: int, success: bool = True):
        """Enregistre la completion d'un appel pour les statistiques"""
        if operation_type in self.stats:
            stats = self.stats[operation_type]
            stats['count'] += 1
            
            # Moyenne mobile du temps de réponse
            if stats['avg_response_time'] == 0:
                stats['avg_response_time'] = response_time_ms
            else:
                stats['avg_response_time'] = (stats['avg_response_time'] * 0.9 + response_time_ms * 0.1)
            
            logger.debug(f"Completion {operation_type}: {response_time_ms}ms, "
                        f"moyenne: {stats['avg_response_time']:.1f}ms")
    
    def get_current_usage(self) -> Dict[str, int]:
        """Retourne l'usage actuel par type d'opération"""
        now = time.time()
        minute_ago = now - 60.0
        
        usage = {
            'total': 0,
            'test_injection': 0,
            'cleanup_rd': 0,
            'notify_media': 0,
            'other': 0
        }
        
        for call in self.calls_window:
            if call.timestamp >= minute_ago:
                usage['total'] += 1
                if call.operation_type in usage:
                    usage[call.operation_type] += 1
                else:
                    usage['other'] += 1
        
        return usage
    
    def get_recommendations(self) -> Dict[str, float]:
        """Recommandations pour ajuster les ratios selon l'usage"""
        usage = self.get_current_usage()
        total = usage['total']
        
        if total == 0:
            return self.adaptive_config
        
        recommendations = {}
        for operation_type, config in self.adaptive_config.items():
            current_usage = usage.get(operation_type, 0)
            current_ratio = (current_usage / total) * 100
            target_ratio = config['weight']
            
            # Ajustement selon la différence
            if current_ratio < target_ratio * 0.8:  # Sous-utilisé
                recommendations[operation_type] = min(100, target_ratio * 1.2)
            elif current_ratio > target_ratio * 1.2:  # Sur-utilisé
                recommendations[operation_type] = max(10, target_ratio * 0.8)
            else:
                recommendations[operation_type] = target_ratio
        
        return recommendations
    
    def get_next_available_time(self) -> float:
        """Retourne le timestamp du prochain slot disponible"""
        if len(self.calls_window) < self.max_calls_per_minute:
            return time.time()  # Disponible maintenant
        
        # Prochain slot = plus ancien appel + 60 secondes
        oldest_call = self.calls_window[0]
        return oldest_call.timestamp + 60.0
    
    def get_stats_summary(self) -> Dict[str, any]:
        """Retourne un résumé des statistiques"""
        usage = self.get_current_usage()
        recommendations = self.get_recommendations()
        next_available = self.get_next_available_time()
        
        return {
            'current_usage': usage,
            'utilization_rate': (usage['total'] / self.max_calls_per_minute) * 100,
            'recommendations': recommendations,
            'next_available_in_seconds': max(0, next_available - time.time()),
            'stats_by_operation': self.stats.copy(),
            'window_size': len(self.calls_window)
        }
    
    async def wait_for_optimal_slot(self, operation_type: str, max_wait: float = 30.0) -> bool:
        """
        Attend le moment optimal pour effectuer un appel selon les recommandations
        
        Args:
            operation_type: Type d'opération
            max_wait: Attente maximum en secondes
            
        Returns:
            True si moment optimal trouvé, False si timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            recommendations = self.get_recommendations()
            current_usage = self.get_current_usage()
            
            # Vérifier si c'est le bon moment pour ce type d'opération
            recommended_ratio = recommendations.get(operation_type, 50)
            current_ratio = (current_usage.get(operation_type, 0) / max(1, current_usage['total'])) * 100
            
            # Si on est en dessous du ratio recommandé, c'est optimal
            if current_ratio <= recommended_ratio:
                return await self.acquire_slot(operation_type, timeout=5.0)
            
            # Attendre un peu avant de re-vérifier
            await asyncio.sleep(1.0)
        
        # Timeout - forcer l'acquisition
        logger.warning(f"Timeout attente slot optimal pour {operation_type}, force acquisition")
        return await self.acquire_slot(operation_type, timeout=5.0)

# Instance globale
_rate_limiter_instance = None
_rate_limiter_lock = threading.Lock()

def get_rate_limiter() -> UnifiedRateLimiter:
    """Retourne l'instance globale du rate limiter (singleton)"""
    global _rate_limiter_instance
    if _rate_limiter_instance is None:
        with _rate_limiter_lock:
            if _rate_limiter_instance is None:
                _rate_limiter_instance = UnifiedRateLimiter()
    return _rate_limiter_instance

async def with_rate_limit(operation_type: str, identifier: str = ""):
    """Décorateur/context manager pour les appels API rate-limités"""
    limiter = get_rate_limiter()
    
    class RateLimitedContext:
        def __init__(self):
            self.start_time = None
        
        async def __aenter__(self):
            success = await limiter.acquire_slot(operation_type, identifier)
            if not success:
                raise Exception(f"Rate limit timeout pour {operation_type}")
            self.start_time = time.time()
            return self
        
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            if self.start_time:
                response_time = int((time.time() - self.start_time) * 1000)
                success = exc_type is None
                limiter.record_completion(operation_type, response_time, success)
    
    return RateLimitedContext()