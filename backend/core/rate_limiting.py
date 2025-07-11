"""
Système de rate limiting avancé pour l'API
"""
import time
import hashlib
from functools import wraps
from django.core.cache import cache
from django.http import JsonResponse
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self):
        self.cache = cache
    
    def get_client_identifier(self, request):
        """Identifie le client (IP + User-Agent + User ID si connecté)"""
        ip = self.get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        user_id = getattr(request.user, 'id', 'anonymous') if hasattr(request, 'user') else 'anonymous'
        
        identifier = f"{ip}:{user_id}:{hashlib.md5(user_agent.encode()).hexdigest()[:8]}"
        return identifier
    
    def get_client_ip(self, request):
        """Récupère l'IP réelle du client"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def is_rate_limited(self, request, key, rate, method=None):
        """Vérifie si la requête dépasse la limite"""
        if method and request.method != method:
            return False
        
        client_id = self.get_client_identifier(request)
        cache_key = f"rate_limit:{key}:{client_id}"
        
        # Parser le rate (ex: "5/m" = 5 par minute)
        count, period = rate.split('/')
        count = int(count)
        
        period_seconds = {
            's': 1,
            'm': 60,
            'h': 3600,
            'd': 86400
        }.get(period, 60)
        
        # Récupérer les données du cache
        data = self.cache.get(cache_key, {'count': 0, 'reset_time': time.time() + period_seconds})
        
        current_time = time.time()
        
        # Réinitialiser si la période est écoulée
        if current_time >= data['reset_time']:
            data = {'count': 0, 'reset_time': current_time + period_seconds}
        
        # Vérifier la limite
        if data['count'] >= count:
            logger.warning(f"Rate limit dépassé pour {client_id} sur {key}")
            return True
        
        # Incrémenter le compteur
        data['count'] += 1
        self.cache.set(cache_key, data, timeout=period_seconds)
        
        return False
    
    def get_rate_limit_status(self, request, key, rate):
        """Retourne le statut actuel du rate limiting"""
        client_id = self.get_client_identifier(request)
        cache_key = f"rate_limit:{key}:{client_id}"
        
        count, period = rate.split('/')
        count = int(count)
        
        data = self.cache.get(cache_key, {'count': 0, 'reset_time': time.time()})
        
        return {
            'limit': count,
            'remaining': max(0, count - data['count']),
            'reset_time': data['reset_time']
        }

rate_limiter = RateLimiter()

def rate_limit(key, rate, method=None):
    """Décorateur pour appliquer le rate limiting"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if rate_limiter.is_rate_limited(request, key, rate, method):
                status_info = rate_limiter.get_rate_limit_status(request, key, rate)
                
                return JsonResponse({
                    'error': 'Limite de taux dépassée',
                    'limit': status_info['limit'],
                    'remaining': status_info['remaining'],
                    'reset_time': status_info['reset_time']
                }, status=429)
            
            response = view_func(request, *args, **kwargs)
            
            # Ajouter les en-têtes de rate limiting
            if hasattr(response, 'headers'):
                status_info = rate_limiter.get_rate_limit_status(request, key, rate)
                response.headers['X-RateLimit-Limit'] = str(status_info['limit'])
                response.headers['X-RateLimit-Remaining'] = str(status_info['remaining'])
                response.headers['X-RateLimit-Reset'] = str(int(status_info['reset_time']))
            
            return response
        return wrapper
    return decorator
