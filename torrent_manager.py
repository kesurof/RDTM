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
from symlink_checker import get_symlink_checker
from failure_handler import FailureHandler

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
        self.symlink_checker = get_symlink_checker()
        self.failure_handler = FailureHandler(dry_run=dry_run)
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
    
    def scan_torrents(self, scan_mode: str = 'auto') -> Tuple[bool, Dict[str, Any]]:
        """Scan hybride des torrents Real-Debrid (quick/full/auto)"""
        logger.info(f"🔍 Début du scan des torrents (mode: {scan_mode})")
        start_time = time.time()
        
        # Déterminer le mode de scan automatiquement
        if scan_mode == 'auto':
            scan_mode = self._determine_scan_mode()
            logger.info(f"Mode auto sélectionné: {scan_mode}")
        
        if scan_mode == 'quick':
            return self._scan_torrents_quick()
        elif scan_mode == 'full':
            return self._scan_torrents_full()
        elif scan_mode == 'symlinks':
            return self._scan_torrents_symlinks()
        else:
            logger.error(f"Mode de scan invalide: {scan_mode}")
            return False, {'error': f'Mode invalide: {scan_mode}'}
    
    def _determine_scan_mode(self) -> str:
        """Détermine le mode de scan selon la stratégie"""
        # Vérifier la dernière fois qu'un scan complet a été fait
        progress = self.database.get_scan_progress('full')
        
        if not progress:
            # Jamais de scan complet, commencer par un scan complet
            return 'full'
        
        last_full_scan = progress.get('last_scan_complete')
        if not last_full_scan:
            return 'full'
        
        # Si le dernier scan complet date de plus de 7 jours, relancer un scan complet
        from datetime import datetime, timedelta
        if isinstance(last_full_scan, str):
            last_full_scan = datetime.fromisoformat(last_full_scan)
        
        if datetime.now() - last_full_scan > timedelta(days=7):
            logger.info("Dernier scan complet > 7 jours, mode full sélectionné")
            return 'full'
        
        # Sinon, scan rapide
        return 'quick'
    
    def _scan_torrents_quick(self) -> Tuple[bool, Dict[str, Any]]:
        """Scan rapide - seulement les torrents en échec"""
        logger.info("⚡ Scan rapide - torrents en échec uniquement")
        
        # Marquer le début du scan
        self.database.update_scan_progress('quick', status='running')
        
        start_time = time.time()
        failed_torrents_data = []
        
        # Scanner chaque statut d'échec séparément
        for status in FAILED_STATUSES:
            success, torrents_data, error = self.rd_client.get_torrents_by_status(status)
            if success:
                failed_torrents_data.extend(torrents_data)
                logger.info(f"Statut {status}: {len(torrents_data)} torrents")
            else:
                logger.warning(f"Erreur scan statut {status}: {error}")
        
        scan_results = {
            'scan_mode': 'quick',
            'total_torrents': len(failed_torrents_data),
            'failed_torrents': len(failed_torrents_data),
            'new_failures': 0,
            'updated_torrents': 0,
            'validation_errors': 0,
            'scan_duration': 0
        }
        
        # Traiter les torrents trouvés
        scan_results['updated_torrents'] = self._process_torrents_batch(failed_torrents_data)
        scan_results['scan_duration'] = time.time() - start_time
        
        # Marquer la fin du scan
        self.database.update_scan_progress('quick', status='completed')
        
        logger.info(f"✅ Scan rapide terminé: {scan_results['total_torrents']} torrents en échec ({scan_results['scan_duration']:.1f}s)")
        return True, scan_results
    
    def _scan_torrents_full(self) -> Tuple[bool, Dict[str, Any]]:
        """Scan complet avec pagination - traite tous les torrents par chunks"""
        logger.info("🔍 Scan complet - pagination de tous les torrents")
        
        # Récupérer la progression actuelle
        progress = self.database.get_scan_progress('full')
        current_offset = progress['current_offset'] if progress else 0
        
        # Si on reprend un scan, sinon commencer à 0
        if not progress or progress.get('status') != 'running':
            current_offset = 0
            self.database.update_scan_progress('full', current_offset=0, status='running')
        
        start_time = time.time()
        total_processed = 0
        total_failed = 0
        chunk_size = 1000
        max_chunks_per_session = 5  # Limiter à 5 chunks par session
        chunks_processed = 0
        
        logger.info(f"Reprise du scan à l'offset {current_offset}")
        
        while chunks_processed < max_chunks_per_session:
            # Récupérer un chunk de torrents
            success, torrents_data, error = self.rd_client.get_torrents(
                limit=chunk_size, 
                offset=current_offset
            )
            
            if not success:
                logger.error(f"Erreur récupération chunk {current_offset}: {error}")
                break
            
            if not torrents_data:
                # Fin des torrents atteinte
                logger.info("Fin des torrents atteinte - scan complet terminé")
                self.database.update_scan_progress('full', 
                                                 current_offset=0, 
                                                 total_expected=total_processed,
                                                 status='completed')
                break
            
            # Traiter ce chunk
            chunk_processed = self._process_torrents_batch(torrents_data)
            chunk_failed = sum(1 for t in torrents_data if t.get('status') in FAILED_STATUSES)
            
            total_processed += len(torrents_data)
            total_failed += chunk_failed
            chunks_processed += 1
            current_offset += chunk_size
            
            # Sauvegarder la progression
            self.database.update_scan_progress('full', 
                                             current_offset=current_offset,
                                             total_expected=total_processed,
                                             status='running')
            
            logger.info(f"Chunk {chunks_processed}/{max_chunks_per_session}: "
                       f"{len(torrents_data)} torrents, {chunk_failed} en échec")
            
            # Petite pause entre chunks pour ne pas surcharger l'API
            time.sleep(1)
        
        scan_duration = time.time() - start_time
        
        scan_results = {
            'scan_mode': 'full',
            'total_torrents': total_processed,
            'failed_torrents': total_failed,
            'chunks_processed': chunks_processed,
            'current_offset': current_offset,
            'scan_duration': scan_duration,
            'completed': chunks_processed < max_chunks_per_session  # False si interrompu
        }
        
        logger.info(f"✅ Scan complet: {total_processed} torrents, "
                   f"{total_failed} en échec, {chunks_processed} chunks ({scan_duration:.1f}s)")
        
        return True, scan_results

    def _scan_torrents_symlinks(self, base_path: str = None) -> Tuple[bool, Dict[str, Any]]:
        """Scan des liens symboliques cassés pour détecter les vrais échecs"""
        logger.info("🔗 Scan des liens symboliques cassés")
        
        start_time = time.time()
        
        # Scanner les répertoires média pour liens cassés
        broken_results = self.symlink_checker.scan_media_directories(base_path)
        
        # Collecter tous les liens cassés
        all_broken_links = []
        for directory, links in broken_results.items():
            all_broken_links.extend(links)
        
        # Extraire les noms de torrents uniques
        torrent_names = self.symlink_checker.get_unique_torrent_names(all_broken_links)
        
        # Rechercher les correspondances dans Real-Debrid
        matched_torrents = []
        if torrent_names:
            logger.info(f"🔍 Recherche des correspondances pour {len(torrent_names)} torrents")
            matched_torrents = self._find_torrents_by_names(list(torrent_names))
            
            # Sauvegarder les torrents trouvés en base avec statut spécial
            for torrent in matched_torrents:
                # Marquer comme trouvé via symlinks cassés
                db_torrent_data = {
                    'id': torrent.id,
                    'hash': torrent.hash,
                    'filename': torrent.filename,
                    'status': 'symlink_broken',  # Statut spécial pour ces torrents
                    'size': torrent.size,
                    'added': torrent.added_date,
                    'priority': 3,  # Haute priorité
                    'metadata': {
                        'source': 'symlink_checker',
                        'broken_links_count': len([link for link in all_broken_links if link.torrent_name in torrent.filename])
                    }
                }
                self.database.upsert_torrent(db_torrent_data)
        
        scan_results = {
            'scan_mode': 'symlinks',
            'total_broken_links': len(all_broken_links),
            'unique_torrents_searched': len(torrent_names),
            'matched_torrents': len(matched_torrents),
            'directories_scanned': list(broken_results.keys()),
            'scan_duration': time.time() - start_time,
            'broken_by_directory': {k: len(v) for k, v in broken_results.items()},
            'torrent_names': list(torrent_names),
            'match_rate': (len(matched_torrents) / len(torrent_names) * 100) if torrent_names else 0
        }
        
        logger.info(f"✅ Scan symlinks terminé: {len(all_broken_links)} liens cassés, "
                   f"{len(matched_torrents)}/{len(torrent_names)} torrents trouvés dans Real-Debrid "
                   f"({scan_results['match_rate']:.1f}% match) ({scan_results['scan_duration']:.1f}s)")
        
        return True, scan_results

    def _find_torrents_by_names(self, torrent_names: List[str]) -> List[TorrentRecord]:
        """Recherche les torrents Real-Debrid correspondant aux noms extraits des symlinks"""
        logger.info(f"🔍 Recherche de {len(torrent_names)} torrents dans Real-Debrid")
        
        if not torrent_names:
            return []
        
        # Récupérer tous les torrents Real-Debrid pour la recherche
        all_rd_torrents = []
        offset = 0
        chunk_size = 1000
        
        while True:
            success, torrents_data, error = self.rd_client.get_torrents(limit=chunk_size, offset=offset)
            if not success or not torrents_data:
                break
            
            all_rd_torrents.extend(torrents_data)
            offset += chunk_size
            
            # Eviter les boucles infinies
            if len(torrents_data) < chunk_size:
                break
        
        logger.info(f"📊 {len(all_rd_torrents)} torrents Real-Debrid récupérés pour la recherche")
        
        # Rechercher les correspondances
        matched_torrents = []
        for target_name in torrent_names:
            best_match = self._find_best_torrent_match(target_name, all_rd_torrents)
            if best_match:
                matched_torrents.append(best_match)
                logger.info(f"✅ Match: {target_name[:50]}... → {best_match.filename[:50]}...")
            else:
                logger.warning(f"❌ Pas de match: {target_name[:50]}...")
        
        logger.info(f"🎯 {len(matched_torrents)} correspondances trouvées sur {len(torrent_names)} recherchées")
        return matched_torrents
    
    def _find_best_torrent_match(self, target_name: str, rd_torrents: List[Dict]) -> Optional[TorrentRecord]:
        """Trouve le meilleur match pour un nom de torrent dans la liste Real-Debrid"""
        from difflib import SequenceMatcher
        
        best_match = None
        best_score = 0.0
        min_score = 0.7  # Seuil de similarité minimum
        
        # Nettoyer le nom cible pour la comparaison
        target_clean = self._clean_torrent_name(target_name)
        
        for rd_torrent in rd_torrents:
            rd_filename = rd_torrent.get('filename', '')
            rd_clean = self._clean_torrent_name(rd_filename)
            
            # Calculer la similarité
            similarity = SequenceMatcher(None, target_clean, rd_clean).ratio()
            
            # Bonus si match exact du début (même release group)
            if rd_clean.startswith(target_clean[:30]) or target_clean.startswith(rd_clean[:30]):
                similarity += 0.1
            
            if similarity > best_score and similarity >= min_score:
                best_score = similarity
                best_match = rd_torrent
        
        if best_match:
            # Convertir en TorrentRecord
            try:
                return TorrentRecord(
                    id=best_match['id'],
                    hash=best_match['hash'],
                    filename=best_match['filename'],
                    status=best_match['status'],
                    size=best_match.get('bytes', 0),
                    added_date=datetime.fromisoformat(best_match['added'].replace('Z', '+00:00')),
                    first_seen=datetime.now(),
                    last_seen=datetime.now(),
                    priority=3  # Haute priorité pour les torrents issus de symlinks cassés
                )
            except Exception as e:
                logger.error(f"Erreur conversion TorrentRecord: {e}")
                return None
        
        return None
    
    def _clean_torrent_name(self, name: str) -> str:
        """Nettoie un nom de torrent pour la comparaison"""
        import re
        
        # Remplacer les séparateurs par des espaces
        cleaned = re.sub(r'[._-]', ' ', name.lower())
        
        # Supprimer les extensions
        cleaned = re.sub(r'\.(mkv|mp4|avi|mov|wmv|flv|m4v|webm)$', '', cleaned)
        
        # Supprimer les informations entre parenthèses/crochets en fin
        cleaned = re.sub(r'\s*[\[\(].*?[\]\)]\s*$', '', cleaned)
        
        # Normaliser les espaces
        cleaned = ' '.join(cleaned.split())
        
        return cleaned.strip()

    def _process_torrents_batch(self, torrents_data: List[Dict]) -> int:
        """Traite un batch de torrents et les sauvegarde en base"""
        processed_count = 0
        
        for torrent_data in torrents_data:
            try:
                # Valider les métadonnées
                valid, validation_error = self.validator.validate_torrent_metadata(torrent_data)
                if not valid:
                    logger.warning(f"Torrent invalide {torrent_data.get('id', 'unknown')}: {validation_error}")
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
                    processed_count += 1
                
                self.stats['torrents_processed'] += 1
                
            except Exception as e:
                logger.error(f"Erreur traitement torrent {torrent_data.get('id', 'unknown')}: {e}")
                continue
        
        return processed_count
    
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
                
                # Traitement post-échec via FailureHandler
                self._handle_post_failure(torrent, api_error)
                
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
    
    def reinject_failed_torrents(self, scan_type: str = 'all', limit: int = None) -> Tuple[bool, Dict[str, Any]]:
        """Réinjection de torrents en échec avec limite et filtrage"""
        logger.info(f"🎯 Réinjection de torrents (type: {scan_type}, limite: {limit})")
        
        try:
            # Récupérer les candidats selon le type de scan
            if scan_type == 'symlinks':
                # Torrents détectés via liens cassés - requête directe
                candidates = []
                try:
                    with self.database.get_cursor() as cursor:
                        cursor.execute("""
                            SELECT * FROM torrents 
                            WHERE status = 'symlink_broken' 
                            AND attempts_count < ?
                            ORDER BY priority DESC, last_seen DESC
                        """, [APP_CONFIG['max_retry_attempts']])
                        rows = cursor.fetchall()
                        
                        from database import TorrentRecord
                        from datetime import datetime
                        for row in rows:
                            candidates.append(TorrentRecord(
                                id=row['id'],
                                hash=row['hash'],
                                filename=row['filename'],
                                status=row['status'],
                                size=row['size'],
                                added_date=datetime.fromisoformat(row['added_date']),
                                first_seen=datetime.fromisoformat(row['first_seen']),
                                last_seen=datetime.fromisoformat(row['last_seen']),
                                attempts_count=row['attempts_count'],
                                last_attempt=datetime.fromisoformat(row['last_attempt']) if row['last_attempt'] else None,
                                last_success=datetime.fromisoformat(row['last_success']) if row['last_success'] else None,
                                priority=row['priority']
                            ))
                except Exception as e:
                    logger.error(f"Erreur récupération torrents symlink_broken: {e}")

            else:
                # Tous les torrents en échec
                candidates = self.get_reinjection_candidates()
            
            if not candidates:
                return True, {
                    'processed': 0,
                    'success': 0,
                    'failed': 0,
                    'message': 'Aucun torrent à réinjecter'
                }
            
            # Limiter le nombre si spécifié
            if limit and limit > 0:
                candidates = candidates[:limit]
                logger.info(f"📊 Limitation à {limit} torrents sur {len(candidates)} candidats")
            
            # Traiter les réinjections
            results = {
                'processed': 0,
                'success': 0,
                'failed': 0,
                'errors': []
            }
            
            for torrent in candidates:
                success, message = self.reinject_torrent(torrent)
                
                results['processed'] += 1
                if success:
                    results['success'] += 1
                    logger.info(f"✅ Réinjection réussie: {torrent.filename[:50]}...")
                else:
                    results['failed'] += 1
                    results['errors'].append({
                        'torrent_id': torrent.id,
                        'filename': torrent.filename,
                        'error': message
                    })
                    logger.error(f"❌ Réinjection échouée: {torrent.filename[:50]}... - {message}")
            
            success_rate = (results['success'] / results['processed'] * 100) if results['processed'] > 0 else 0
            logger.info(f"📊 Réinjection terminée: {results['success']}/{results['processed']} "
                       f"réussies ({success_rate:.1f}%)")
            
            return True, results
            
        except Exception as e:
            error_msg = f"Erreur globale réinjection: {str(e)}"
            logger.error(error_msg)
            return False, {'error': error_msg}

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
    def _handle_post_failure(self, torrent: TorrentRecord, api_error: str):
        """Traite les échecs de réinjection via FailureHandler"""
        try:
            # Identifier le type d'erreur
            error_type = self._classify_api_error(api_error)
            
            if error_type in ['infringing_file', 'too_many_requests']:
                logger.info(f"🔧 Post-traitement {error_type} pour: {torrent.filename[:50]}...")
                
                success = self.failure_handler.handle_failure(
                    torrent_id=torrent.id,
                    filename=torrent.filename,
                    error_type=error_type,
                    error_message=api_error
                )
                
                if success:
                    logger.info(f"✅ Post-traitement {error_type} réussi")
                else:
                    logger.warning(f"⚠️ Post-traitement {error_type} partiellement échoué")
            else:
                logger.debug(f"Type d'erreur non géré pour post-traitement: {api_error}")
                
        except Exception as e:
            logger.error(f"Erreur post-traitement échec: {e}")
    
    def _classify_api_error(self, api_error: str) -> str:
        """Classifie le type d'erreur API"""
        error_lower = api_error.lower()
        
        if 'infringing_file' in error_lower:
            return 'infringing_file'
        elif 'too_many_requests' in error_lower:
            return 'too_many_requests'
        elif 'rate' in error_lower and 'limit' in error_lower:
            return 'too_many_requests'
        else:
            return 'unknown'
    
    def get_pending_retries(self) -> List[Dict]:
        """Récupère les torrents prêts pour retry depuis FailureHandler"""
        return self.failure_handler.get_pending_retries()
    
    def process_pending_retries(self) -> Dict[str, Any]:
        """Traite les retries différés prêts"""
        logger.info("🔄 Traitement des retries différés")
        
        pending_retries = self.get_pending_retries()
        if not pending_retries:
            logger.info("Aucun retry en attente")
            return {'processed': 0, 'successful': 0, 'failed': 0}
        
        logger.info(f"📊 {len(pending_retries)} retries prêts à traiter")
        
        results = {
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'errors': []
        }
        
        for retry in pending_retries:
            try:
                # Reconstituer un TorrentRecord depuis les données retry
                torrent_record = self._retry_to_torrent_record(retry)
                if not torrent_record:
                    continue
                
                # Tenter la réinjection
                success, message = self.reinject_torrent(torrent_record)
                
                results['processed'] += 1
                
                if success:
                    results['successful'] += 1
                    # Supprimer de la queue de retry
                    self.failure_handler._remove_from_retry_queue(retry['torrent_id'], retry['error_type'])
                    logger.info(f"✅ Retry réussi: {retry['filename'][:50]}...")
                else:
                    results['failed'] += 1
                    # Incrémenter le compteur de retry ou reprogrammer
                    self.failure_handler._update_retry_attempt(retry['torrent_id'], retry['error_type'], success=False)
                    logger.warning(f"❌ Retry échoué: {retry['filename'][:50]}... - {message}")
                    
            except Exception as e:
                results['failed'] += 1
                results['errors'].append({
                    'torrent_id': retry['torrent_id'],
                    'error': str(e)
                })
                logger.error(f"Erreur retry {retry['torrent_id']}: {e}")
        
        logger.info(f"📊 Retries traités: {results['successful']}/{results['processed']} réussis")
        return results
    
    def _retry_to_torrent_record(self, retry: Dict) -> Optional[TorrentRecord]:
        """Convertit un retry en TorrentRecord pour réinjection"""
        try:
            # Récupérer le torrent depuis la base
            with self.database.get_cursor() as cursor:
                cursor.execute("SELECT * FROM torrents WHERE id = ?", (retry['torrent_id'],))
                row = cursor.fetchone()
                
                if not row:
                    logger.warning(f"Torrent introuvable pour retry: {retry['torrent_id']}")
                    return None
                
                return TorrentRecord(
                    id=row['id'],
                    hash=row['hash'],
                    filename=row['filename'],
                    status=row['status'],
                    size=row['size'],
                    added_date=datetime.fromisoformat(row['added_date']),
                    first_seen=datetime.fromisoformat(row['first_seen']),
                    last_seen=datetime.fromisoformat(row['last_seen']),
                    attempts_count=row['attempts_count'],
                    last_attempt=datetime.fromisoformat(row['last_attempt']) if row['last_attempt'] else None,
                    last_success=datetime.fromisoformat(row['last_success']) if row['last_success'] else None,
                    priority=row['priority']
                )
                
        except Exception as e:
            logger.error(f"Erreur conversion retry vers TorrentRecord: {e}")
            return None

    def close(self):
        """Fermeture propre"""
        try:
            self.rd_client.close()
            self.failure_handler.close()
            self.database.close()
            logger.info("TorrentManager fermé proprement")
        except Exception as e:
            logger.error(f"Erreur fermeture TorrentManager: {e}")