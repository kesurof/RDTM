"""
Système d'authentification JWT sécurisé avec refresh tokens
"""
import jwt
import uuid
from datetime import datetime, timedelta
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework import authentication, exceptions
import logging

logger = logging.getLogger(__name__)

class JWTAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return None
        
        token = auth_header.split(' ')[1]
        
        try:
            payload = self.verify_token(token)
            user = User.objects.get(id=payload['user_id'])
            
            # Vérifier si le token est dans la blacklist
            if self.is_token_blacklisted(payload['jti']):
                raise exceptions.AuthenticationFailed('Token révoqué')
            
            return (user, token)
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed('Token expiré')
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed('Token invalide')
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed('Utilisateur non trouvé')
    
    def verify_token(self, token):
        """Vérifie et décode un token JWT"""
        return jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=['HS256']
        )
    
    def is_token_blacklisted(self, jti):
        """Vérifie si un token est dans la blacklist"""
        return cache.get(f'blacklisted_token_{jti}') is not None

class JWTManager:
    def __init__(self):
        self.secret_key = settings.JWT_SECRET_KEY
        self.algorithm = 'HS256'
        self.access_token_lifetime = timedelta(minutes=15)
        self.refresh_token_lifetime = timedelta(days=7)
    
    def generate_tokens(self, user):
        """Génère une paire de tokens (access + refresh)"""
        now = datetime.utcnow()
        jti = str(uuid.uuid4())
        
        # Access token
        access_payload = {
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'exp': now + self.access_token_lifetime,
            'iat': now,
            'jti': jti,
            'type': 'access'
        }
        
        # Refresh token
        refresh_jti = str(uuid.uuid4())
        refresh_payload = {
            'user_id': user.id,
            'exp': now + self.refresh_token_lifetime,
            'iat': now,
            'jti': refresh_jti,
            'type': 'refresh'
        }
        
        access_token = jwt.encode(access_payload, self.secret_key, algorithm=self.algorithm)
        refresh_token = jwt.encode(refresh_payload, self.secret_key, algorithm=self.algorithm)
        
        # Stocker les JTI pour la gestion de la blacklist
        cache.set(f'refresh_token_{refresh_jti}', user.id, timeout=self.refresh_token_lifetime.total_seconds())
        
        return {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_in': self.access_token_lifetime.total_seconds()
        }
    
    def refresh_access_token(self, refresh_token):
        """Génère un nouveau token d'accès à partir du refresh token"""
        try:
            payload = jwt.decode(refresh_token, self.secret_key, algorithms=[self.algorithm])
            
            if payload.get('type') != 'refresh':
                raise jwt.InvalidTokenError('Token de type incorrect')
            
            # Vérifier si le refresh token est valide
            if not cache.get(f'refresh_token_{payload["jti"]}'):
                raise jwt.InvalidTokenError('Refresh token révoqué')
            
            user = User.objects.get(id=payload['user_id'])
            return self.generate_tokens(user)
            
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed('Refresh token expiré')
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed('Refresh token invalide')
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed('Utilisateur non trouvé')
    
    def blacklist_token(self, token):
        """Ajoute un token à la blacklist"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            jti = payload['jti']
            exp = payload['exp']
            
            # Calculer le TTL jusqu'à l'expiration
            ttl = exp - datetime.utcnow().timestamp()
            if ttl > 0:
                cache.set(f'blacklisted_token_{jti}', True, timeout=int(ttl))
            
        except jwt.InvalidTokenError:
            pass  # Token déjà invalide

# Instance globale
jwt_manager = JWTManager()
