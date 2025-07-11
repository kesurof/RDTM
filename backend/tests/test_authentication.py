"""
Tests pour le système d'authentification
"""
import pytest
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.cache import cache
from rest_framework.test import APITestCase
from authentication.jwt_auth import jwt_manager
import json
import time

class AuthenticationTestCase(APITestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='TestPassword123!'
        )
        cache.clear()
    
    def test_login_success(self):
        """Test de connexion réussie"""
        response = self.client.post('/api/auth/login/', {
            'username': 'testuser',
            'password': 'TestPassword123!'
        })
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        
        self.assertIn('access_token', data)
        self.assertIn('refresh_token', data)
        self.assertIn('expires_in', data)
        self.assertIn('user', data)
    
    def test_login_invalid_credentials(self):
        """Test de connexion avec identifiants invalides"""
        response = self.client.post('/api/auth/login/', {
            'username': 'testuser',
            'password': 'wrongpassword'
        })
        
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.content)
        self.assertIn('error', data)
    
    def test_rate_limiting(self):
        """Test du rate limiting sur les connexions"""
        # Faire 6 tentatives de connexion échouées
        for i in range(6):
            response = self.client.post('/api/auth/login/', {
                'username': 'testuser',
                'password': 'wrongpassword'
            })
        
        # La 6ème tentative devrait être bloquée
        self.assertEqual(response.status_code, 429)
    
    def test_token_refresh(self):
        """Test du renouvellement de token"""
        # Connexion pour obtenir les tokens
        login_response = self.client.post('/api/auth/login/', {
            'username': 'testuser',
            'password': 'TestPassword123!'
        })
        
        tokens = json.loads(login_response.content)
        
        # Renouveler le token
        refresh_response = self.client.post('/api/auth/refresh/', {
            'refresh_token': tokens['refresh_token']
        })
        
        self.assertEqual(refresh_response.status_code, 200)
        new_tokens = json.loads(refresh_response.content)
        self.assertIn('access_token', new_tokens)
    
    def test_token_blacklist(self):
        """Test de la blacklist des tokens"""
        # Connexion
        login_response = self.client.post('/api/auth/login/', {
            'username': 'testuser',
            'password': 'TestPassword123!'
        })
        
        tokens = json.loads(login_response.content)
        
        # Déconnexion (blacklist du token)
        logout_response = self.client.post('/api/auth/logout/', 
            HTTP_AUTHORIZATION=f'Bearer {tokens["access_token"]}'
        )
        
        self.assertEqual(logout_response.status_code, 200)
        
        # Essayer d'utiliser le token blacklisté
        protected_response = self.client.get('/api/protected/', 
            HTTP_AUTHORIZATION=f'Bearer {tokens["access_token"]}'
        )
        
        self.assertEqual(protected_response.status_code, 401)

class EncryptionTestCase(TestCase):
    def setUp(self):
        from core.encryption import encryption_manager
        self.encryption_manager = encryption_manager
    
    def test_encrypt_decrypt_api_key(self):
        """Test de chiffrement/déchiffrement des clés API"""
        original_key = "test_api_key_123456789"
        
        # Chiffrer
        encrypted_key = self.encryption_manager.encrypt_api_key(original_key)
        self.assertNotEqual(encrypted_key, original_key)
        
        # Déchiffrer
        decrypted_key = self.encryption_manager.decrypt_api_key(encrypted_key)
        self.assertEqual(decrypted_key, original_key)
    
    def test_encrypt_empty_key(self):
        """Test de chiffrement d'une clé vide"""
        encrypted_key = self.encryption_manager.encrypt_api_key("")
        self.assertEqual(encrypted_key, "")
        
        decrypted_key = self.encryption_manager.decrypt_api_key("")
        self.assertEqual(decrypted_key, "")

if __name__ == '__main__':
    pytest.main([__file__])
