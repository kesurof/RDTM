import pytest
import jwt
from datetime import datetime, timedelta
from backend.core.security import SecurityManager, RateLimiter
from unittest.mock import patch, Mock

class TestSecurityManager:
    
    def test_hash_password(self, security_manager):
        """Test du hashage de mot de passe"""
        password = "test_password_123"
        hashed = security_manager.hash_password(password)
        
        assert hashed != password
        assert len(hashed) > 50  # bcrypt hash length
        assert security_manager.verify_password(password, hashed)

    def test_verify_password_invalid(self, security_manager):
        """Test de vérification avec mauvais mot de passe"""
        password = "test_password_123"
        wrong_password = "wrong_password"
        hashed = security_manager.hash_password(password)
        
        assert not security_manager.verify_password(wrong_password, hashed)

    def test_encrypt_decrypt_data(self, security_manager):
        """Test du chiffrement/déchiffrement"""
        sensitive_data = "api_key_secret_123"
        encrypted = security_manager.encrypt_sensitive_data(sensitive_data)
        decrypted = security_manager.decrypt_sensitive_data(encrypted)
        
        assert encrypted != sensitive_data
        assert decrypted == sensitive_data

    def test_generate_jwt_token(self, security_manager):
        """Test de génération de token JWT"""
        user_id = 123
        token = security_manager.generate_jwt_token(user_id)
        
        assert isinstance(token, str)
        assert len(token) > 100  # JWT token length
        
        # Vérification du contenu
        payload = security_manager.verify_jwt_token(token)
        assert payload['user_id'] == user_id
        assert 'exp' in payload
        assert 'iat' in payload

    def test_jwt_token_with_additional_claims(self, security_manager):
        """Test JWT avec claims additionnels"""
        user_id = 123
        additional_claims = {'role': 'admin', 'permissions': ['read', 'write']}
        token = security_manager.generate_jwt_token(user_id, additional_claims)
        
        payload = security_manager.verify_jwt_token(token)
        assert payload['user_id'] == user_id
        assert payload['role'] == 'admin'
        assert payload['permissions'] == ['read', 'write']

    def test_verify_expired_token(self, security_manager):
        """Test de vérification d'un token expiré"""
        user_id = 123
        
        # Création d'un token expiré
        expired_payload = {
            'user_id': user_id,
            'exp': datetime.utcnow() - timedelta(hours=1),  # Expiré
            'iat': datetime.utcnow() - timedelta(hours=2)
        }
        
        expired_token = jwt.encode(
            expired_payload, 
            security_manager.jwt_secret, 
            algorithm=security_manager.jwt_algorithm
        )
        
        with pytest.raises(Exception, match="Token expiré"):
            security_manager.verify_jwt_token(expired_token)

    def test_verify_invalid_token(self, security_manager):
        """Test de vérification d'un token invalide"""
        invalid_token = "invalid.token.here"
        
        with pytest.raises(Exception, match="Token invalide"):
            security_manager.verify_jwt_token(invalid_token)

class TestRateLimiter:
    
    @patch('backend.core.security.redis.Redis.from_url')
    def test_rate_limiter_init(self, mock_redis_from_url, mock_redis):
        """Test d'initialisation du rate limiter"""
        mock_redis_from_url.return_value = mock_redis
        
        rate_limiter = RateLimiter()
        assert rate_limiter.rate_limit_per_minute == 250
        assert rate_limiter.rate_limit_per_second == 4

    @patch('backend.core.security.redis.Redis.from_url')
    def test_rate_limit_not_exceeded(self, mock_redis_from_url, mock_redis):
        """Test quand le rate limit n'est pas dépassé"""
        mock_redis_from_url.return_value = mock_redis
        mock_redis.get.return_value = None  # Pas de limite atteinte
        
        rate_limiter = RateLimiter()
        assert not rate_limiter.is_rate_limited("test_user")

    @patch('backend.core.security.redis.Redis.from_url')
    def test_rate_limit_exceeded_per_second(self, mock_redis_from_url, mock_redis):
        """Test quand le rate limit par seconde est dépassé"""
        mock_redis_from_url.return_value = mock_redis
        mock_redis.get.side_effect = lambda key: b'5' if 'second' in key else None
        
        rate_limiter = RateLimiter()
        assert rate_limiter.is_rate_limited("test_user")

    @patch('backend.core.security.redis.Redis.from_url')
    def test_rate_limit_exceeded_per_minute(self, mock_redis_from_url, mock_redis):
        """Test quand le rate limit par minute est dépassé"""
        mock_redis_from_url.return_value = mock_redis
        mock_redis.get.side_effect = lambda key: b'251' if 'minute' in key else None
        
        rate_limiter = RateLimiter()
        assert rate_limiter.is_rate_limited("test_user")

    @patch('backend.core.security.redis.Redis.from_url')
    def test_increment_rate_limit(self, mock_redis_from_url, mock_redis):
        """Test d'incrémentation des compteurs"""
        mock_redis_from_url.return_value = mock_redis
        
        rate_limiter = RateLimiter()
        rate_limiter.increment_rate_limit("test_user")
        
        # Vérification des appels Redis
        assert mock_redis.incr.call_count == 2  # Une fois par seconde, une fois par minute
        assert mock_redis.expire.call_count == 2
