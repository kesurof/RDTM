#!/usr/bin/env python3

import re
import hashlib
import logging
from typing import Optional, Tuple, Dict, Set
from urllib.parse import parse_qs, urlparse
import time

from config import MAGNET_VALIDATION

logger = logging.getLogger(__name__)

class TorrentValidator:
    """Validateur de magnet links et hashes avec sécurité"""
    
    def __init__(self):
        # Patterns de validation
        self.magnet_pattern = re.compile(r'^magnet:\?xt=urn:btih:([a-fA-F0-9]{40})', re.IGNORECASE)
        self.sha1_pattern = re.compile(r'^[a-fA-F0-9]{40}$', re.IGNORECASE)
        
        # Blacklist de hashes malveillants (exemple)
        self.hash_blacklist: Set[str] = set()
        
        # Cache de validation pour éviter les re-validations
        self.validation_cache: Dict[str, Tuple[bool, str]] = {}
        self.cache_max_size = 1000
        
        logger.info("Validateur de torrents initialisé")
    
    def validate_sha1_hash(self, hash_str: str) -> Tuple[bool, str]:
        """Valide un hash SHA1"""
        if not hash_str:
            return False, "Hash vide"
        
        # Nettoyer le hash
        hash_clean = hash_str.strip().lower()
        
        # Vérifier la longueur
        if len(hash_clean) != MAGNET_VALIDATION['min_hash_length']:
            return False, f"Longueur invalide: {len(hash_clean)} (attendu: 40)"
        
        # Vérifier le format hexadécimal
        if not self.sha1_pattern.match(hash_clean):
            return False, "Format hexadécimal invalide"
        
        # Vérifier la blacklist
        if hash_clean in self.hash_blacklist:
            return False, "Hash dans la blacklist"
        
        # Vérifications de sécurité basiques
        if hash_clean == '0' * 40:
            return False, "Hash null détecté"
        
        if len(set(hash_clean)) < 3:
            return False, "Hash suspect (trop peu de caractères différents)"
        
        return True, "Hash SHA1 valide"
    
    def extract_hash_from_magnet(self, magnet_link: str) -> Tuple[bool, Optional[str], str]:
        """Extrait et valide le hash depuis un magnet link"""
        if not magnet_link:
            return False, None, "Magnet link vide"
        
        # Vérifier le cache
        cache_key = hashlib.md5(magnet_link.encode()).hexdigest()
        if cache_key in self.validation_cache:
            cached_result = self.validation_cache[cache_key]
            if cached_result[0]:  # Si valide dans le cache
                match = self.magnet_pattern.search(magnet_link)
                return True, match.group(1) if match else None, cached_result[1]
            else:
                return False, None, cached_result[1]
        
        # Validation du format magnet
        if not magnet_link.startswith(MAGNET_VALIDATION['required_scheme']):
            error = f"Schéma invalide (attendu: {MAGNET_VALIDATION['required_scheme']})"
            self._cache_result(cache_key, False, error)
            return False, None, error
        
        # Extraire le hash avec regex
        match = self.magnet_pattern.search(magnet_link)
        if not match:
            error = "Format magnet invalide ou hash manquant"
            self._cache_result(cache_key, False, error)
            return False, None, error
        
        extracted_hash = match.group(1)
        
        # Valider le hash extrait
        hash_valid, hash_error = self.validate_sha1_hash(extracted_hash)
        if not hash_valid:
            self._cache_result(cache_key, False, f"Hash invalide: {hash_error}")
            return False, None, f"Hash invalide: {hash_error}"
        
        # Validation supplémentaire du magnet link complet
        magnet_valid, magnet_error = self.validate_magnet_structure(magnet_link)
        if not magnet_valid:
            self._cache_result(cache_key, False, magnet_error)
            return False, None, magnet_error
        
        self._cache_result(cache_key, True, "Magnet link valide")
        return True, extracted_hash.lower(), "Magnet link valide"
    
    def validate_magnet_structure(self, magnet_link: str) -> Tuple[bool, str]:
        """Valide la structure complète d'un magnet link"""
        try:
            # Parser l'URL magnet
            parsed = urlparse(magnet_link)
            
            if parsed.scheme != 'magnet':
                return False, "Schéma non-magnet détecté"
            
            # Analyser les paramètres
            params = parse_qs(parsed.query)
            
            # Vérifier la présence du paramètre xt (exact topic)
            if 'xt' not in params:
                return False, "Paramètre 'xt' manquant"
            
            xt_values = params['xt']
            if not xt_values:
                return False, "Valeur 'xt' vide"
            
            # Vérifier le format urn:btih
            btih_found = False
            for xt in xt_values:
                if xt.startswith('urn:btih:'):
                    btih_found = True
                    break
            
            if not btih_found:
                return False, "Format 'urn:btih:' manquant"
            
            # Validation optionnelle: présence de nom (dn)
            if 'dn' in params and params['dn']:
                display_name = params['dn'][0]
                if len(display_name) > 200:
                    logger.warning(f"Nom de fichier très long: {len(display_name)} caractères")
            
            return True, "Structure magnet valide"
            
        except Exception as e:
            return False, f"Erreur parsing magnet: {str(e)}"
    
    def construct_magnet_from_hash(self, hash_str: str, display_name: Optional[str] = None) -> Tuple[bool, Optional[str], str]:
        """Construit un magnet link depuis un hash SHA1"""
        # Valider le hash d'abord
        hash_valid, hash_error = self.validate_sha1_hash(hash_str)
        if not hash_valid:
            return False, None, f"Hash invalide: {hash_error}"
        
        hash_clean = hash_str.strip().lower()
        
        # Construire le magnet link basique
        magnet_link = f"magnet:?xt=urn:btih:{hash_clean}"
        
        # Ajouter le nom si fourni
        if display_name:
            # Nettoyer le nom pour URL
            safe_name = display_name.replace(' ', '%20').replace('&', '%26')
            magnet_link += f"&dn={safe_name}"
        
        # Valider le magnet construit
        magnet_valid, validation_error = self.validate_magnet_structure(magnet_link)
        if not magnet_valid:
            return False, None, f"Magnet construit invalide: {validation_error}"
        
        logger.debug(f"Magnet construit: {magnet_link[:50]}...")
        return True, magnet_link, "Magnet link construit avec succès"
    
    def validate_torrent_metadata(self, torrent_data: Dict) -> Tuple[bool, str]:
        """Valide les métadonnées d'un torrent Real-Debrid"""
        required_fields = ['id', 'hash', 'filename', 'status']
        
        # Vérifier les champs requis
        for field in required_fields:
            if field not in torrent_data:
                return False, f"Champ requis manquant: {field}"
            
            if not torrent_data[field]:
                return False, f"Champ requis vide: {field}"
        
        # Valider le hash
        hash_valid, hash_error = self.validate_sha1_hash(torrent_data['hash'])
        if not hash_valid:
            return False, f"Hash torrent invalide: {hash_error}"
        
        # Valider la taille si présente
        if 'bytes' in torrent_data:
            size = torrent_data['bytes']
            if not isinstance(size, (int, float)) or size < 0:
                return False, "Taille de fichier invalide"
            
            if size < MAGNET_VALIDATION['min_file_size']:
                logger.warning(f"Fichier très petit: {size} bytes")
        
        # Valider le nom de fichier
        filename = torrent_data['filename']
        if len(filename) > 255:
            return False, "Nom de fichier trop long"
        
        # Caractères suspects dans le nom
        suspicious_chars = ['<', '>', '|', '\0', '\n', '\r']
        if any(char in filename for char in suspicious_chars):
            return False, "Caractères suspects dans le nom de fichier"
        
        return True, "Métadonnées valides"
    
    def add_to_blacklist(self, hash_str: str, reason: str = ""):
        """Ajoute un hash à la blacklist"""
        hash_clean = hash_str.strip().lower()
        if self.validate_sha1_hash(hash_clean)[0]:
            self.hash_blacklist.add(hash_clean)
            logger.warning(f"Hash ajouté à la blacklist: {hash_clean[:8]}... ({reason})")
    
    def remove_from_blacklist(self, hash_str: str):
        """Retire un hash de la blacklist"""
        hash_clean = hash_str.strip().lower()
        if hash_clean in self.hash_blacklist:
            self.hash_blacklist.remove(hash_clean)
            logger.info(f"Hash retiré de la blacklist: {hash_clean[:8]}...")
    
    def is_blacklisted(self, hash_str: str) -> bool:
        """Vérifie si un hash est en blacklist"""
        hash_clean = hash_str.strip().lower()
        return hash_clean in self.hash_blacklist
    
    def _cache_result(self, cache_key: str, success: bool, message: str):
        """Met en cache un résultat de validation"""
        # Nettoyer le cache si trop plein
        if len(self.validation_cache) >= self.cache_max_size:
            # Supprimer les 100 plus anciens (approximation simple)
            keys_to_remove = list(self.validation_cache.keys())[:100]
            for key in keys_to_remove:
                del self.validation_cache[key]
        
        self.validation_cache[cache_key] = (success, message)
    
    def get_validation_stats(self) -> Dict[str, int]:
        """Retourne les statistiques de validation"""
        cache_hits = len([r for r in self.validation_cache.values() if r[0]])
        cache_misses = len([r for r in self.validation_cache.values() if not r[0]])
        
        return {
            'cache_size': len(self.validation_cache),
            'cache_hits': cache_hits,
            'cache_misses': cache_misses,
            'blacklist_size': len(self.hash_blacklist)
        }
    
    def clear_cache(self):
        """Vide le cache de validation"""
        self.validation_cache.clear()
        logger.info("Cache de validation vidé")

# Instance globale
_validator_instance = None

def get_validator() -> TorrentValidator:
    """Retourne l'instance du validateur (singleton)"""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = TorrentValidator()
    return _validator_instance