"""Tests de l'API REST"""

import pytest
from django.urls import reverse
from rest_framework import status
from app.models import Torrent, Download

@pytest.mark.django_db
class TestTorrentAPI:
    """Tests de l'API des torrents"""
    
    def test_list_torrents_unauthenticated(self, api_client):
        """Test accès non authentifié à la liste des torrents"""
        url = reverse('torrent-list')
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_list_torrents_authenticated(self, authenticated_client, user):
        """Test liste des torrents pour utilisateur authentifié"""
        # Créer quelques torrents de test
        Torrent.objects.create(
            user=user,
            name='Test Torrent 1',
            magnet_link='magnet:?xt=urn:btih:1234',
            status='downloading'
        )
        Torrent.objects.create(
            user=user,
            name='Test Torrent 2',
            magnet_link='magnet:?xt=urn:btih:5678',
            status='completed'
        )
        
        url = reverse('torrent-list')
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 2
    
    def test_create_torrent(self, authenticated_client, mock_real_debrid_api, sample_torrent_data):
        """Test création d'un nouveau torrent"""
        url = reverse('torrent-list')
        response = authenticated_client.post(url, sample_torrent_data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['name'] == sample_torrent_data['name']
        assert response.data['status'] == 'pending'
        
        # Vérifier que l'API Real-Debrid a été appelée
        mock_real_debrid_api.add_magnet.assert_called_once()
    
    def test_create_torrent_invalid_magnet(self, authenticated_client):
        """Test création avec lien magnet invalide"""
        invalid_data = {
            'magnet_link': 'invalid-magnet-link',
            'name': 'Test Torrent'
        }
        
        url = reverse('torrent-list')
        response = authenticated_client.post(url, invalid_data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'magnet_link' in response.data
    
    def test_delete_torrent(self, authenticated_client, user):
        """Test suppression d'un torrent"""
        torrent = Torrent.objects.create(
            user=user,
            name='Test Torrent',
            magnet_link='magnet:?xt=urn:btih:1234',
            status='downloading'
        )
        
        url = reverse('torrent-detail', kwargs={'pk': torrent.pk})
        response = authenticated_client.delete(url)
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Torrent.objects.filter(pk=torrent.pk).exists()

@pytest.mark.django_db
class TestAuthAPI:
    """Tests de l'API d'authentification"""
    
    def test_login_valid_credentials(self, api_client, user):
        """Test connexion avec identifiants valides"""
        url = reverse('auth-login')
        data = {
            'username': user.username,
            'password': 'testpass123'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert 'access_token' in response.data
        assert 'token_type' in response.data
        assert response.data['token_type'] == 'bearer'
    
    def test_login_invalid_credentials(self, api_client):
        """Test connexion avec identifiants invalides"""
        url = reverse('auth-login')
        data = {
            'username': 'wronguser',
            'password': 'wrongpass'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

@pytest.mark.integration
class TestRealDebridIntegration:
    """Tests d'intégration avec Real-Debrid"""
    
    def test_api_quota_monitoring(self, authenticated_client, mock_real_debrid_api):
        """Test monitoring du quota API"""
        # Configurer le mock pour retourner des informations de quota
        mock_real_debrid_api.get_user_info.return_value['points'] = 500
        
        url = reverse('stats')
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'api_quota_remaining' in response.data
