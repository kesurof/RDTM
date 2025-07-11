import os
import jwt
import bcrypt
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from functools import wraps
from flask import request, jsonify, current_app
import redis
import time

class SecurityManager:
    def __init__(self):
        self.jwt_secret = os.getenv('JWT_SECRET_KEY')
        self.jwt_algorithm = os.getenv('JWT_ALGORITHM', 'HS256')
        self.jwt_expiration = int(os.getenv('JWT_EXPIRATION_HOURS', 24))
        self.encryption_key = os.getenv('ENCRYPTION_KEY').encode()
        self.cipher_suite = Fernet(self.encryption_key)
        self.redis_client = redis.Redis.from_url(os.getenv('REDIS_URL'))

    def hash_password(self, password: str) -> str:
        """Hash un mot de passe avec bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def verify_password(self, password: str, hashed: str) -> bool:
        """Vérifie un mot de passe contre son hash"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

    def encrypt_sensitive_data(self, data: str) -> str:
        """Chiffre des données sensibles"""
        return self.cipher_suite.encrypt(data.encode()).decode()

    def decrypt_sensitive_data(self, encrypted_data: str) -> str:
        """Déchiffre des données sensibles"""
        return self.cipher_suite.decrypt(encrypted_data.encode()).decode()

    def generate_jwt_token(self, user_id: int, additional_claims: dict = None) -> str:
        """Génère un token JWT"""
        payload = {
            'user_id': user_id,
            'exp': datetime.utcnow() + timedelta(hours=self.jwt_expiration),
            'iat': datetime.utcnow()
        }
        if additional_claims:
            payload.update(additional_claims)
        
        return jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)

    def verify_jwt_token(self, token: str) -> dict:
        """Vérifie et décode un token JWT"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise Exception("Token expiré")
        except jwt.InvalidTokenError:
            raise Exception("Token invalide")

def require_auth(f):
    """Décorateur pour protéger les routes avec JWT"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token manquant'}), 401
        
        try:
            if token.startswith('Bearer '):
                token = token[7:]
            
            security_manager = SecurityManager()
            payload = security_manager.verify_jwt_token(token)
            request.current_user = payload
            
        except Exception as e:
            return jsonify({'error': str(e)}), 401
        
        return f(*args, **kwargs)
    return decorated_function

class RateLimiter:
    def __init__(self):
        self.redis_client = redis.Redis.from_url(os.getenv('REDIS_URL'))
        self.rate_limit_per_minute = int(os.getenv('RATE_LIMIT_PER_MINUTE', 250))
        self.rate_limit_per_second = int(os.getenv('RATE_LIMIT_PER_SECOND', 4))

    def is_rate_limited(self, identifier: str) -> bool:
        """Vérifie si un utilisateur/IP est rate limited"""
        current_time = int(time.time())
        
        # Vérification par seconde
        second_key = f"rate_limit:second:{identifier}:{current_time}"
        second_count = self.redis_client.get(second_key)
        if second_count and int(second_count) >= self.rate_limit_per_second:
            return True
        
        # Vérification par minute
        minute_key = f"rate_limit:minute:{identifier}:{current_time // 60}"
        minute_count = self.redis_client.get(minute_key)
        if minute_count and int(minute_count) >= self.rate_limit_per_minute:
            return True
        
        return False

    def increment_rate_limit(self, identifier: str):
        """Incrémente les compteurs de rate limiting"""
        current_time = int(time.time())
        
        # Compteur par seconde
        second_key = f"rate_limit:second:{identifier}:{current_time}"
        self.redis_client.incr(second_key)
        self.redis_client.expire(second_key, 1)
        
        # Compteur par minute
        minute_key = f"rate_limit:minute:{identifier}:{current_time // 60}"
        self.redis_client.incr(minute_key)
        self.redis_client.expire(minute_key, 60)

def rate_limit(f):
    """Décorateur pour appliquer le rate limiting"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        rate_limiter = RateLimiter()
        identifier = request.remote_addr
        
        if hasattr(request, 'current_user'):
            identifier = f"user:{request.current_user['user_id']}"
        
        if rate_limiter.is_rate_limited(identifier):
            return jsonify({'error': 'Rate limit dépassé'}), 429
        
        rate_limiter.increment_rate_limit(identifier)
        return f(*args, **kwargs)
    
    return decorated_function
