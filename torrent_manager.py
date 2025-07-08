#!/usr/bin/env python3

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from config import FAILED_STATUSES, SUCCESS_STATUSES, APP_CONFIG, PRIORITY_CONFIG
from database import get_database, TorrentRecord, AttemptRecord
from rd_client import RealDebridClient
from torrent_validator import get_validator

logger = logging.getLogger(__name__)

class TorrentPriorityCalculator:
    """Calculateur de priorité pour les torrents"""
    
    @staticmethod
    def calculate_priority(torrent_data: Dict[str, Any]) -> int:
        """Calcule la priorité d'un torrent (1=low, 2=normal, 3=high)"""
        status = torrent_data.get('status', '').lower()
        size_bytes = torrent_data.get('bytes', 0)
        added_date = torrent_data.get('added')
        
        # Convertir la date si c'est une string
        if isinstance(added_date, str):
            try:
                added_date = datetime.fromisoformat(added_date.replace('Z', '+00:00'))
            except:
                added_date = datetime.now()
        elif not isinstance(added_date, datetime):
            added_date = datetime.now()
        
        age_hours = (datetime.now() - added_date.replace(tzinfo=None)).total_seconds() / 3600
        size_gb = size_bytes / (1024**3) if size_bytes else 0
        size_mb = size_bytes / (1024**2) if size_bytes else 0
        
        # Priorité haute
        high_config = PRIORITY_CONFIG['high_priority']
        if (status in high_config['statuses'] or 
            size_gb >= high_config['min_size_gb'] or 
            age_hours <= high_config['max_age_hours']):
            return 3
        
        # Priorité basse
        low_config = PRIORITY_CONFIG['low_priority']
        if (size_mb <= low_config['max_size_mb'] and 
            age_hours >= low_config['min_age_days'] * 24):
            return 1
        
        # Priorité normale par défaut
        return 2

class TorrentManager:
    """Gestionnaire principal des torrents Real-Debrid"""
    
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.rd_client = RealDebridClient()
        self.validator = get_validator()
        self.database = get_database()
        self.stats = {
            'scans_completed': 0,
            'torrents_processed': 0,
            'reinjections_attempted': 0,
            'reinjections_successful': 0,
            'reinjections_failed': 0,
            'validation_errors': 0
        }
        self._lock = threading.Lock()
        
        logger.info(f"TorrentManager initialisé (mode: {'DRY-RUN' if dry_run else 'RÉEL'})")
    
    def scan_torrents(self) -> Tuple[bool, Dict[str, Any]]:
        """Scan complet des torrents Real-Debrid"""
        logger.info("🔍 Début du scan des torrents")
        start_time = time.time()
        
        # Récupérer tous les torrents
        success, torrents_data, error = self.rd_client.get_torrents(limit=1000)
        if not success:
            logger.error(f"Échec récupération torrents: {error}")
            return False, {'error': error}
        
        scan_results = {
            'total_torrents': len(torrents_data),
            'failed_torrents': 0,
            'new_failures': 0,
            'updated_torrents': 0,
            'validation_errors': 0,
            'scan_duration': 0
        }
        
        # Traiter chaque torrent
        for torrent_data in torrents_data:
            try:
                # Valider les métadonnées
                valid, validation_error = self.validator.validate_torrent_metadata(torrent_data)
                if not valid:
                    logger.warning(f"Torrent invalide {torrent_data.get('id', 'unknown')}: {validation_error}")
                    scan_results['validation_errors'] += 1
                    self.stats['validation_errors'] += 1
                    continue
                
                # Calculer la priorité
                priority = TorrentPriorityCalculator.calculate_priority(torrent_data)
                
                # Préparer les données pour la base
                db_torrent_data = {
                    'id': torrent_data['id'],
                    'hash': torrent_data['hash'],
                    'filename': torrent_data['filename'],
                    'status': torrent_data['status'],
                    'size': torrent_data.get('bytes', 0),
                    'added': datetime.fromisoformat(torrent_data['added'].replace('Z', '+00:00')),
                    'priority': priority,
                    'metadata': {
                        'host': torrent_data.get('host', ''),
                        'split': torrent_data.get('split', 0),
                        'progress': torrent_data.get('progress', 0)
                    }
                }
                
                # Sauvegarder en base
                if self.database.upsert_torrent(db_torrent_data):
                    scan_results['updated_torrents'] += 1
                    
                    # Compter les échecs
                    if torrent_data['status'] in FAILED_STATUSES:
                        scan_results['failed_torrents'] += 1
                
                self.stats['torrents_processed'] += 1
                
            except Exception as e:
                logger.error(f"Erreur traitement torrent {torrent_data.get('id', 'unknown')}: {e}")
                continue
        
        scan_results['scan_duration'] = time.time() - start_time
        self.stats['scans_completed'] += 1
        
        logger.info(f"✅ Scan terminé: {scan_results['total_torrents']} torrents, "
                   f"{scan_results['failed_torrents']} en échec ({scan_results['scan_duration']:.1f}s)")
        
        return True, scan_results
    
    def get_reinjection_candidates(self) -> List[TorrentRecord]:
        """Récupère les torrents candidats à la réinjection"""
        logger.info("📋 Recherche des torrents à réinjecter")
        
        # Récupérer depuis la base avec les règles de délai
        candidates = self.database.get_failed_torrents(exclude_recent_attempts=True)
        
        if not candidates:
            logger.info("Aucun torrent à réinjecter pour le moment")
            return []
        
        # Trier par priorité puis par date
        candidates.sort(key=lambda t: (-t.priority, t.last_seen), reverse=True)
        
        # Limiter selon le rate limiting
        rate_limit_status = self.rd_client.get_rate_limit_status()
        max_candidates = rate_limit_status['max_torrents_per_cycle']
        
        selected_candidates = candidates[:max_candidates]
        
        logger.info(f"📊 {len(selected_candidates)} torrents sélectionnés pour réinjection "
                   f"(sur {len(candidates)} candidats)")
        
        if selected_candidates:
            priority_counts = {}
            for candidate in selected_candidates:
                priority_counts[candidate.priority] = priority_counts.get(candidate.priority, 0) + 1
            
            priority_names = {1: 'basse', 2: 'normale', 3: 'haute'}
            priority_summary = ', '.join([f"{count} {priority_names[p]}" for p, count in priority_counts.items()])
            logger.info(f"Priorités: {priority_summary}")
        
        return selected_candidates
    
    def reinject_torrent(self, torrent: TorrentRecord) -> Tuple[bool, str]:
        """Réinjection d'un torrent spécifique"""
        logger.info(f"🔄 Réinjection torrent: {torrent.filename[:50]}...")
        
        attempt_start = time.time()
        attempt = AttemptRecord(
            torrent_id=torrent.id,
            attempt_date=datetime.now()
        )
        
        try:
            # Valider le hash du torrent
            hash_valid, hash_error = self.validator.validate_sha1_hash(torrent.hash)
            if not hash_valid:
                error = f"Hash invalide: {hash_error}"
                logger.error(f"Torrent {torrent.id}: {error}")
                attempt.success = False
                attempt.error_message = error
                return False, error
            
            # Construire le magnet link
            magnet_valid, magnet_link, magnet_error = self.validator.construct_magnet_from_hash(
                torrent.hash, torrent.filename
            )
            if not magnet_valid:
                error = f"Magnet invalide: {magnet_error}"
                logger.error(f"Torrent {torrent.id}: {error}")
                attempt.success = False
                attempt.error_message = error
                return False, error
            
            # Mode dry-run
            if self.dry_run:
                logger.info(f"[DRY-RUN] Réinjection simulée: {torrent.id}")
                attempt.success = True
                attempt.api_response = "DRY-RUN simulation"
                attempt.response_time_ms = int((time.time() - attempt_start) * 1000)
                
                # Enregistrer la tentative
                self.database.record_attempt(attempt)
                self.stats['reinjections_successful'] += 1
                return True, "Simulation réussie"
            
            # Mode réel - appel API
            api_success, api_response, api_error = self.rd_client.add_magnet(magnet_link)
            attempt.response_time_ms = int((time.time() - attempt_start) * 1000)
            
            if api_success:
                new_torrent_id = api_response.get('id', 'unknown') if api_response else 'unknown'
                success_msg = f"Réinjection réussie: {new_torrent_id}"
                
                attempt.success = True
                attempt.api_response = str(api_response)
                
                logger.info(f"✅ {success_msg}")
                self.stats['reinjections_successful'] += 1
                
                # Enregistrer la tentative
                self.database.record_attempt(attempt)
                return True, success_msg
            else:
                error = f"Échec API: {api_error}"
                attempt.success = False
                attempt.error_message = error
                attempt.api_response = str(api_error)
                
                logger.error(f"❌ Torrent {torrent.id}: {error}")
                self.stats['reinjections_failed'] += 1
                
                # Enregistrer la tentative
                self.database.record_attempt(attempt)
                return False, error
                
        except Exception as e:
            error = f"Erreur inattendue: {str(e)}"
            attempt.success = False
            attempt.error_message = error
            attempt.response_time_ms = int((time.time() - attempt_start) * 1000)
            
            logger.error(f"❌ Torrent {torrent.id}: {error}")
            self.stats['reinjections_failed'] += 1
            
            # Enregistrer la tentative même en cas d'erreur
            try:
                self.database.record_attempt(attempt)
            except:
                pass
                
            return False, error
        finally:
            self.stats['reinjections_attempted'] += 1
    
    def process_reinjections(self) -> Dict[str, Any]:
        """Traite tous les torrents candidats à la réinjection"""
        logger.info("🚀 Début du traitement des réinjections")
        
        candidates = self.get_reinjection_candidates()
        if not candidates:
            return {
                'processed': 0,
                'successful': 0,
                'failed': 0,
                'errors': []
            }
        
        results = {
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'errors': [],
            'details': []
        }
        
        # Traitement séquentiel pour respecter le rate limiting
        for torrent in candidates:
            try:
                success, message = self.reinject_torrent(torrent)
                
                results['processed'] += 1
                if success:
                    results['successful'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append({
                        'torrent_id': torrent.id,
                        'filename': torrent.filename,
                        'error': message
                    })
                
                results['details'].append({
                    'torrent_id': torrent.id,
                    'filename': torrent.filename[:50],
                    'success': success,
                    'message': message
                })
                
            except Exception as e:
                logger.error(f"Erreur traitement torrent {torrent.id}: {e}")
                results['failed'] += 1
                results['errors'].append({
                    'torrent_id': torrent.id,
                    'filename': torrent.filename,
                    'error': f"Erreur inattendue: {str(e)}"
                })
        
        # Log du résumé
        if results['processed'] > 0:
            success_rate = (results['successful'] / results['processed']) * 100
            logger.info(f"📊 Réinjections terminées: {results['successful']}/{results['processed']} "
                       f"réussies ({success_rate:.1f}%)")
        
        return results
    
    def get_failed_torrents_summary(self) -> Dict[str, Any]:
        """Résumé des torrents en échec"""
        try:
            stats = self.database.get_statistics()
            
            summary = {
                'by_status': {},
                'pending_reinjection': stats.get('pending_reinjection', 0),
                'total_failed': 0
            }
            
            # Compter les échecs par statut
            torrents_by_status = stats.get('torrents_by_status', {})
            for status, data in torrents_by_status.items():
                if status in FAILED_STATUSES:
                    summary['by_status'][status] = data['count']
                    summary['total_failed'] += data['count']
            
            return summary
            
        except Exception as e:
            logger.error(f"Erreur résumé torrents échoués: {e}")
            return {'error': str(e)}
    
    def cleanup_and_maintenance(self):
        """Tâches de maintenance périodique"""
        logger.info("🧹 Maintenance périodique")
        
        try:
            # Nettoyage base de données
            deleted_attempts, deleted_metrics = self.database.cleanup_old_data()
            
            # Nettoyage cache validateur
            self.validator.clear_cache()
            
            # Statistiques validation
            validation_stats = self.validator.get_validation_stats()
            logger.info(f"Cache validation: {validation_stats['cache_size']} entrées")
            
            # Sauvegarde périodique
            backup_success = self.database.backup_database()
            if backup_success:
                logger.info("✅ Sauvegarde base de données créée")
            
            logger.info(f"✅ Maintenance terminée: {deleted_attempts} tentatives, "
                       f"{deleted_metrics} métriques supprimées")
                       
        except Exception as e:
            logger.error(f"Erreur maintenance: {e}")
    
    def get_manager_stats(self) -> Dict[str, Any]:
        """Statistiques du gestionnaire"""
        rate_limit_status = self.rd_client.get_rate_limit_status()
        
        return {
            'mode': 'DRY-RUN' if self.dry_run else 'RÉEL',
            'scans_completed': self.stats['scans_completed'],
            'torrents_processed': self.stats['torrents_processed'],
            'reinjections': {
                'attempted': self.stats['reinjections_attempted'],
                'successful': self.stats['reinjections_successful'],
                'failed': self.stats['reinjections_failed'],
                'success_rate': (self.stats['reinjections_successful'] / max(1, self.stats['reinjections_attempted'])) * 100
            },
            'validation_errors': self.stats['validation_errors'],
            'rate_limiting': rate_limit_status
        }
    
    def test_connectivity(self) -> bool:
        """Test de connectivité complète"""
        logger.info("🔧 Test de connectivité")
        
        # Test API Real-Debrid
        if not self.rd_client.test_connection():
            return False
        
        # Test base de données
        try:
            test_stats = self.database.get_statistics()
            logger.info(f"✅ Base de données accessible ({len(test_stats)} statistiques)")
        except Exception as e:
            logger.error(f"❌ Erreur base de données: {e}")
            return False
        
        # Test validation
        try:
            test_hash = "a" * 40
            valid, error = self.validator.validate_sha1_hash(test_hash)
            logger.info(f"✅ Validateur fonctionnel")
        except Exception as e:
            logger.error(f"❌ Erreur validateur: {e}")
            return False
        
        return True
    
    def close(self):
        """Fermeture propre"""
        try:
            self.rd_client.close()
            self.database.close()
            logger.info("TorrentManager fermé proprement")
        except Exception as e:
            logger.error(f"Erreur fermeture TorrentManager: {e}")