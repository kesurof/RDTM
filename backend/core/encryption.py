"""
Gestionnaire de chiffrement pour les données sensibles
"""
import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class EncryptionManager:
    def __init__(self):
        self.fernet = self._get_fernet_instance()
    
    def _get_fernet_instance(self):
        """Initialise l'instance Fernet avec la clé de chiffrement"""
        try:
            encryption_key = settings.ENCRYPTION_KEY
            if isinstance(encryption_key, str):
                encryption_key = encryption_key.encode()
            return Fernet(encryption_key)
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation du chiffrement: {e}")
            raise
    
    def encrypt_api_key(self, api_key: str) -> str:
        """Chiffre une clé API"""
        try:
            if not api_key:
                return ""
            
            encrypted_key = self.fernet.encrypt(api_key.encode())
            return base64.b64encode(encrypted_key).decode()
        except Exception as e:
            logger.error(f"Erreur lors du chiffrement de la clé API: {e}")
            raise
    
    def decrypt_api_key(self, encrypted_key: str) -> str:
        """Déchiffre une clé API"""
        try:
            if not encrypted_key:
                return ""
            
            encrypted_data = base64.b64decode(encrypted_key.encode())
            decrypted_key = self.fernet.decrypt(encrypted_data)
            return decrypted_key.decode()
        except Exception as e:
            logger.error(f"Erreur lors du déchiffrement de la clé API: {e}")
            raise
    
    def rotate_encryption_key(self, old_key: str, new_key: str):
        """Rotation des clés de chiffrement"""
        # Implémentation pour la rotation des clés
        # À utiliser lors de la maintenance de sécurité
        pass

# Instance globale
encryption_manager = EncryptionManager()
