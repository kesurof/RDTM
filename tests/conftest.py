"""Configuration globale des tests pytest"""

import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from unittest.mock import Mock, patch

User = get_user_model()

@pytest.fixture
def api_client():
    """Client API pour les tests"""
    return APIClient()

@pytest.fixture
def user():
    """Utilisateur de test"""
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123'
    )

@pytest.fixture
def admin_user():
    """Utilisateur admin de test"""
    return User.objects.create_superuser(
        username='admin',
        email='admin@example.com',
        password='adminpass123'
    )

@pytest.fixture
def authenticated_client(api_client, user):
    """Client API authentifié"""
    api_client.force_authenticate(user=user)
    return api_client

@pytest.fixture
def mock_real_debrid_api():
    """Mock de l'API Real-Debrid"""
    with patch('app.services.real_debrid.RealDebridAPI') as mock:
        mock_instance = Mock()
        mock.return_value = mock_instance
        
        # Réponses par défaut
        mock_instance.get_user_info.return_value = {
            'id': 12345,
            'username': 'testuser',
            'email': 'test@example.com',
            'points': 1000,
            'locale': 'en',
            'avatar': 'https://example.com/avatar.jpg',
            'type': 'premium',
            'premium': 1640995200,  # timestamp
            'expiration': '2025-12-31T23:59:59.000Z'
        }
        
        mock_instance.add_magnet.return_value = {
            'id': 'ABCD1234',
            'uri': 'https://real-debrid.com/d/ABCD1234'
        }
        
        yield mock_instance

@pytest.fixture
def sample_torrent_data():
    """Données de test pour un torrent"""
    return {
        'magnet_link': 'magnet:?xt=urn:btih:1234567890abcdef1234567890abcdef12345678',
        'name': 'Test Torrent',
        'size': 1073741824,  # 1GB
        'priority': 'normal'
    }

@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(db):
    """Permet l'accès à la DB pour tous les tests"""
    pass
