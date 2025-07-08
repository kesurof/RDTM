#!/usr/bin/env python3

import os
import time
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import CURRENT_USER
from database import get_database

logger = logging.getLogger(__name__)

class FailureHandler:
    """Gestionnaire post-échec pour infringing_file et too_many_requests"""
    
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.database = get_database()
        self.session = self._create_session()
        
        # Configuration des serveurs média (depuis advanced_symlink_checker)
        self.media_config = {
            'sonarr': {'port': 8989, 'api_version': 'v3'},
            'radarr': {'port': 7878, 'api_version': 'v3'}
        }
        
        logger.info(f"FailureHandler initialisé (mode: {'DRY-RUN' if dry_run else 'RÉEL'})")
    
    def _create_session(self) -> requests.Session:
        """Crée une session HTTP avec retry automatique"""
        session = requests.Session()
        retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session
    
    def handle_failure(self, torrent_id: str, filename: str, error_type: str, error_message: str) -> bool:
        """Point d'entrée principal pour gérer les échecs"""
        logger.info(f"🔧 Traitement échec {error_type} pour: {filename[:50]}...")
        
        if error_type == 'infringing_file':
            return self._handle_infringing_file(torrent_id, filename, error_message)
        elif error_type == 'too_many_requests':
            return self._handle_rate_limit(torrent_id, filename, error_message)
        else:
            logger.warning(f"Type d'erreur non géré: {error_type}")
            return False
    
    def _handle_infringing_file(self, torrent_id: str, filename: str, error_message: str) -> bool:
        """Gestion des fichiers censurés - suppression + scan Sonarr/Radarr"""
        logger.info(f"📛 Traitement infringing_file: {filename[:50]}")
        
        try:
            # 1. Marquer comme à traiter (processed = 0)
            self._record_permanent_failure(torrent_id, filename, 'infringing_file', error_message, processed=False)
            
            # 2. Trouver et supprimer les liens cassés
            deleted_files = self._find_and_delete_broken_symlinks(filename)
            
            # 3. Déclencher scan Sonarr/Radarr si des fichiers supprimés
            if deleted_files:
                self._trigger_media_rescan()
                # 4. Marquer comme traité (processed = 1)
                self._mark_as_processed(torrent_id, 'infringing_file')
                logger.info(f"✅ infringing_file traité: {len(deleted_files)} fichiers supprimés")
                return True
            else:
                logger.warning(f"⚠️ Aucun fichier trouvé pour: {filename[:50]}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Erreur traitement infringing_file {torrent_id}: {e}")
            return False
    
    def _handle_rate_limit(self, torrent_id: str, filename: str, error_message: str) -> bool:
        """Gestion rate limit - historisation pour retry dans 3h"""
        logger.info(f"⏰ Programmation retry pour: {filename[:50]}")
        
        try:
            # Calculer le moment du retry (dans 3h)
            retry_time = datetime.now() + timedelta(hours=3)
            
            # Enregistrer pour retry différé
            self._schedule_retry(torrent_id, filename, 'too_many_requests', retry_time, error_message)
            
            logger.info(f"✅ Retry programmé pour {retry_time.strftime('%H:%M:%S')}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur programmation retry {torrent_id}: {e}")
            return False
    
    def _find_and_delete_broken_symlinks(self, filename: str) -> List[str]:
        """Trouve et supprime les liens cassés pour un fichier donné"""
        deleted_files = []
        base_path = f"/home/{CURRENT_USER}/Medias"
        
        if not os.path.exists(base_path):
            logger.warning(f"Chemin média inexistant: {base_path}")
            return []
        
        # Nettoyer le nom de fichier pour la recherche
        clean_filename = self._clean_filename_for_search(filename)
        
        logger.info(f"🔍 Recherche liens cassés pour: {clean_filename}")
        
        try:
            # Parcourir tous les liens symboliques
            for root, dirs, files in os.walk(base_path):
                for file in files:
                    full_path = os.path.join(root, file)
                    
                    # Vérifier si c'est un lien symbolique
                    if os.path.islink(full_path):
                        # Vérifier si le nom correspond
                        if self._filename_matches(file, clean_filename):
                            # Vérifier si le lien est cassé
                            if not os.path.exists(full_path):
                                if self._delete_symlink(full_path):
                                    deleted_files.append(full_path)
                                    logger.info(f"🗑️ Supprimé: {full_path}")
        
        except Exception as e:
            logger.error(f"Erreur recherche liens cassés: {e}")
        
        return deleted_files
    
    def _clean_filename_for_search(self, filename: str) -> str:
        """Nettoie le nom de fichier pour la recherche"""
        import re
        # Supprimer l'extension et nettoyer
        clean = os.path.splitext(filename)[0]
        # Supprimer les informations techniques et groupes
        clean = re.sub(r'\b(x264|x265|AC3|EAC3|DTS|AAC|BluRay|WEBRip|WEBDL|1080p|720p|Multi|VFQ|VFF)\b', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\b(JiHEFF|Winks|EXTREME|NEO|ACOOL|GOLD)\b', '', clean, flags=re.IGNORECASE)
        # Normaliser les séparateurs
        clean = re.sub(r'[._-]', ' ', clean.lower())
        # Supprimer les caractères spéciaux et dates entre parenthèses
        clean = re.sub(r'\([^)]*\)', '', clean)
        clean = re.sub(r'[{}[\]<>]', '', clean)
        # Normaliser les espaces
        clean = ' '.join(clean.split())
        return clean.strip()
    
    def _filename_matches(self, link_name: str, target_name: str) -> bool:
        """Vérifie si un nom de lien correspond au fichier cible"""
        from difflib import SequenceMatcher
        
        link_clean = self._clean_filename_for_search(link_name)
        
        # Extraire les mots clés importants du nom cible
        target_words = set(target_name.split())
        link_words = set(link_clean.split())
        
        # Vérifier que les mots principaux correspondent
        common_words = target_words.intersection(link_words)
        
        # Si au moins 70% des mots du target sont dans le lien
        if len(target_words) > 0:
            word_match_rate = len(common_words) / len(target_words)
            if word_match_rate >= 0.7:
                return True
        
        # Fallback sur similarité globale
        similarity = SequenceMatcher(None, link_clean, target_name).ratio()
        return similarity > 0.6  # Seuil réduit de 0.8 à 0.6
    
    def _delete_symlink(self, file_path: str) -> bool:
        """Supprime un lien symbolique"""
        try:
            if self.dry_run:
                logger.info(f"[DRY-RUN] Suppression simulée: {file_path}")
                return True
            else:
                os.remove(file_path)
                return True
        except Exception as e:
            logger.error(f"Erreur suppression {file_path}: {e}")
            return False
    
    def _get_container_ip(self, container_name: str) -> Optional[str]:
        """Récupère l'IP d'un conteneur Docker"""
        try:
            cmd = f"docker inspect {container_name} --format='{{{{.NetworkSettings.Networks.traefik_proxy.IPAddress}}}}'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception as e:
            logger.error(f"Erreur IP container {container_name}: {e}")
        return None
    
    def _get_api_key(self, service: str) -> Optional[str]:
        """Récupère la clé API d'un service"""
        try:
            settings_storage = os.environ.get('SETTINGS_STORAGE', '/opt/seedbox/docker')
            config_path = f"{settings_storage}/docker/{CURRENT_USER}/{service}/config/config.xml"
            
            if not os.path.exists(config_path):
                return None
                
            cmd = f"sed -n 's/.*<ApiKey>\\(.*\\)<\\/ApiKey>.*/\\1/p' '{config_path}'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            return result.stdout.strip() if result.returncode == 0 else None
            
        except Exception as e:
            logger.error(f"Erreur API key {service}: {e}")
            return None
    
    def _trigger_media_rescan(self) -> bool:
        """Déclenche les scans Sonarr/Radarr"""
        logger.info("🔄 Déclenchement scans Sonarr/Radarr")
        
        success = True
        
        for service, config in self.media_config.items():
            try:
                ip = self._get_container_ip(service)
                api_key = self._get_api_key(service)
                
                if not ip or not api_key:
                    logger.warning(f"⚠️ {service}: IP ou API key manquante")
                    continue
                
                url = f"http://{ip}:{config['port']}/api/{config['api_version']}/command"
                headers = {"Content-Type": "application/json", "X-Api-Key": api_key}
                
                # Commandes de scan selon le service
                commands = {
                    'sonarr': ['RescanSeries', 'missingEpisodeSearch'],
                    'radarr': ['RescanMovie', 'MissingMoviesSearch']
                }
                
                for command in commands.get(service, []):
                    data = {"name": command}
                    
                    if self.dry_run:
                        logger.info(f"[DRY-RUN] {service}: {command} simulé")
                    else:
                        response = self.session.post(url, json=data, headers=headers, timeout=30)
                        response.raise_for_status()
                        logger.info(f"✅ {service}: {command} lancé")
                    
                    time.sleep(2)
                    
            except Exception as e:
                logger.error(f"❌ {service} scan: {e}")
                success = False
        
        return success
    
    def _record_permanent_failure(self, torrent_id: str, filename: str, error_type: str, error_message: str, processed: bool = True):
        """Enregistre un échec permanent en base"""
        try:
            with self.database.get_cursor() as cursor:
                cursor.execute("""
                    INSERT OR REPLACE INTO permanent_failures (
                        torrent_id, filename, error_type, error_message, 
                        failure_date, processed
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (torrent_id, filename, error_type, error_message, datetime.now(), processed))
                
                logger.debug(f"Échec permanent enregistré: {torrent_id} (processed={processed})")
                
        except Exception as e:
            logger.error(f"Erreur enregistrement échec permanent: {e}")
    
    def _mark_as_processed(self, torrent_id: str, error_type: str):
        """Marque un échec comme traité"""
        try:
            with self.database.get_cursor() as cursor:
                cursor.execute("""
                    UPDATE permanent_failures 
                    SET processed = 1 
                    WHERE torrent_id = ? AND error_type = ?
                """, (torrent_id, error_type))
                
                logger.debug(f"Échec marqué comme traité: {torrent_id}")
                
        except Exception as e:
            logger.error(f"Erreur marquage traité: {e}")
    
    def _schedule_retry(self, torrent_id: str, filename: str, error_type: str, retry_time: datetime, error_message: str):
        """Programme un retry différé"""
        try:
            with self.database.get_cursor() as cursor:
                cursor.execute("""
                    INSERT OR REPLACE INTO retry_queue (
                        torrent_id, filename, error_type, error_message,
                        original_failure, scheduled_retry, retry_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (torrent_id, filename, error_type, error_message, 
                     datetime.now(), retry_time, 0))
                
                logger.debug(f"Retry programmé: {torrent_id} pour {retry_time}")
                
        except Exception as e:
            logger.error(f"Erreur programmation retry: {e}")
    
    def get_pending_retries(self) -> List[Dict]:
        """Récupère les torrents prêts pour retry"""
        try:
            with self.database.get_cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM retry_queue 
                    WHERE scheduled_retry <= ? 
                    AND retry_count < 3
                    ORDER BY scheduled_retry ASC
                """, (datetime.now(),))
                
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"Erreur récupération retries: {e}")
            return []
    
    def _remove_from_retry_queue(self, torrent_id: str, error_type: str):
        """Supprime un torrent de la queue de retry après succès"""
        try:
            with self.database.get_cursor() as cursor:
                cursor.execute("""
                    DELETE FROM retry_queue 
                    WHERE torrent_id = ? AND error_type = ?
                """, (torrent_id, error_type))
                
                logger.debug(f"Retry supprimé de la queue: {torrent_id}")
                
        except Exception as e:
            logger.error(f"Erreur suppression retry queue: {e}")
    
    def _update_retry_attempt(self, torrent_id: str, error_type: str, success: bool):
        """Met à jour une tentative de retry"""
        try:
            with self.database.get_cursor() as cursor:
                if success:
                    # Supprimer de la queue si succès
                    self._remove_from_retry_queue(torrent_id, error_type)
                else:
                    # Incrémenter le compteur et reprogrammer si < 3 tentatives
                    cursor.execute("""
                        UPDATE retry_queue 
                        SET retry_count = retry_count + 1,
                            last_retry_attempt = ?,
                            scheduled_retry = CASE 
                                WHEN retry_count < 2 THEN datetime(?, '+3 hours')
                                ELSE scheduled_retry 
                            END
                        WHERE torrent_id = ? AND error_type = ?
                    """, (datetime.now(), datetime.now(), torrent_id, error_type))
                    
                    logger.debug(f"Retry attempt mis à jour: {torrent_id}")
                
        except Exception as e:
            logger.error(f"Erreur mise à jour retry attempt: {e}")

    def close(self):
        """Fermeture propre"""
        if hasattr(self, 'session'):
            self.session.close()