"""
Vues d'authentification avec sécurité renforcée
"""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache
from .jwt_auth import jwt_manager
from .rate_limiting import rate_limit
import logging

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([AllowAny])
@method_decorator(csrf_exempt)
@method_decorator(never_cache)
@rate_limit(key='login', rate='5/m', method='POST')
def login(request):
    """Connexion utilisateur avec rate limiting"""
    username = request.data.get('username')
    password = request.data.get('password')
    
    if not username or not password:
        return Response({
            'error': 'Nom d\'utilisateur et mot de passe requis'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Vérifier les tentatives de connexion échouées
    failed_attempts_key = f'failed_login_{request.META.get("REMOTE_ADDR")}_{username}'
    failed_attempts = cache.get(failed_attempts_key, 0)
    
    if failed_attempts >= 5:
        return Response({
            'error': 'Trop de tentatives de connexion échouées. Réessayez dans 15 minutes.'
        }, status=status.HTTP_429_TOO_MANY_REQUESTS)
    
    user = authenticate(username=username, password=password)
    
    if user is None:
        # Incrémenter les tentatives échouées
        cache.set(failed_attempts_key, failed_attempts + 1, timeout=900)  # 15 minutes
        
        logger.warning(f'Tentative de connexion échouée pour {username} depuis {request.META.get("REMOTE_ADDR")}')
        
        return Response({
            'error': 'Identifiants invalides'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    if not user.is_active:
        return Response({
            'error': 'Compte désactivé'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    # Réinitialiser les tentatives échouées
    cache.delete(failed_attempts_key)
    
    # Générer les tokens
    tokens = jwt_manager.generate_tokens(user)
    
    logger.info(f'Connexion réussie pour {username}')
    
    return Response({
        'access_token': tokens['access_token'],
        'refresh_token': tokens['refresh_token'],
        'expires_in': tokens['expires_in'],
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email
        }
    })

@api_view(['POST'])
@permission_classes([AllowAny])
@method_decorator(csrf_exempt)
def refresh_token(request):
    """Renouvellement du token d'accès"""
    refresh_token = request.data.get('refresh_token')
    
    if not refresh_token:
        return Response({
            'error': 'Refresh token requis'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        tokens = jwt_manager.refresh_access_token(refresh_token)
        return Response(tokens)
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_401_UNAUTHORIZED)

@api_view(['POST'])
def logout(request):
    """Déconnexion avec révocation du token"""
    auth_header = request.META.get('HTTP_AUTHORIZATION')
    
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        jwt_manager.blacklist_token(token)
    
    return Response({'message': 'Déconnexion réussie'})
