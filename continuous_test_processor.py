#!/usr/bin/env python3

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import json
from pathlib import Path

from config import DATA_DIR, APP_CONFIG
from database import get_database, AttemptRecord
from rd_client import RealDebridClient
from torrent_validator import get_validator
from enhanced_symlink_manager import get_symlink_manager
from unified_rate_limiter import get_rate_limiter, with_rate_limit
from utils import get_signal_handler

logger = logging.getLogger(__name__)

@dataclass
class TestResult:
    """Résultat d'un test d'injection"""
    torrent_hash: str
    filename: str
    success: bool
    error_type: str = ""
    error_message: str = ""
    rd_torrent_id: str = ""
    response_time_ms: int = 0
    test_timestamp: datetime = None

@dataclass
class CleanupTask:
    """Tâche de nettoyage à traiter"""
    torrent_hash: str
    rd_torrent_id: str
    filename: str
    local_paths: List[str]
    error_type: str
    discovery_date: datetime
    retry_count: int = 0
    status: str = "pending"  # pending/processing/completed/failed

class ContinuousTestProcessor:
    """Processeur de tests continus avec gestion des symlinks et cleanup"""
    
    def __init__(self):
        self.database = get_database()
        self.rd_client = RealDebridClient()
        self.validator = get_validator()
        self.symlink_manager = get_symlink_manager()
        self.rate_limiter = get_rate_limiter()
        self.signal_handler = get_signal_handler()
        
        # État persistant
        self.state_file = DATA_DIR / "continuous_test_state.json"
        self.cleanup_queue_file = DATA_DIR / "cleanup_queue.json"
        
        # Queues en mémoire
        self.cleanup_queue: List[CleanupTask] = []
        self.test_results_buffer: List[TestResult] = []
        
        # Configuration
        self.batch_size = 10
        self.test_interval_seconds = 1.0  # Base interval, ajusté par rate limiter
        self.cleanup_retry_limit = 3
        
        # Statistiques
        self.stats = {
            'tests_performed': 0,
            'infringing_detected': 0,
            'cleanups_completed': 0,
            'errors_encountered': 0,
            'start_time': datetime.now()
        }
        
        # Charger l'état persistant
        self._load_state()
        self._load_cleanup_queue()
        
        logger.info("ContinuousTestProcessor initialisé")
    
    def _load_state(self):
        """Charge l'état persistant"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self.stats.update(data.get('stats', {}))
                    # Convertir start_time string vers datetime
                    if 'start_time' in data.get('stats', {}):
                        self.stats['start_time'] = datetime.fromisoformat(data['stats']['start_time'])
        except Exception as e:
            logger.warning(f"Erreur chargement état test processor: {e}")
    
    def _save_state(self):
        """Sauvegarde l'état persistant"""
        try:
            data = {
                'stats': {
                    **self.stats,
                    'start_time': self.stats['start_time'].isoformat()
                },
                'last_save': datetime.now().isoformat()
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Erreur sauvegarde état test processor: {e}")
    
    def _load_cleanup_queue(self):
        """Charge la queue de cleanup depuis le fichier"""
        try:
            if self.cleanup_queue_file.exists():
                with open(self.cleanup_queue_file, 'r') as f:
                    data = json.load(f)
                    self.cleanup_queue = []
                    for item in data:
                        task = CleanupTask(
                            torrent_hash=item['torrent_hash'],
                            rd_torrent_id=item['rd_torrent_id'],
                            filename=item['filename'],
                            local_paths=item['local_paths'],
                            error_type=item['error_type'],
                            discovery_date=datetime.fromisoformat(item['discovery_date']),
                            retry_count=item.get('retry_count', 0),
                            status=item.get('status', 'pending')
                        )
                        self.cleanup_queue.append(task)
                logger.info(f"Cleanup queue chargée: {len(self.cleanup_queue)} tâches")
        except Exception as e:
            logger.warning(f"Erreur chargement cleanup queue: {e}")
    
    def _save_cleanup_queue(self):
        """Sauvegarde la queue de cleanup"""
        try:
            data = []
            for task in self.cleanup_queue:
                data.append({
                    'torrent_hash': task.torrent_hash,
                    'rd_torrent_id': task.rd_torrent_id,
                    'filename': task.filename,
                    'local_paths': task.local_paths,
                    'error_type': task.error_type,
                    'discovery_date': task.discovery_date.isoformat(),
                    'retry_count': task.retry_count,
                    'status': task.status
                })
            with open(self.cleanup_queue_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Erreur sauvegarde cleanup queue: {e}")
    
    async def test_single_symlink(self, symlink) -> TestResult:
        """
        Teste l'injection d'un symlink cassé et retourne le résultat
        
        Args:
            symlink: BrokenSymlink à tester
            
        Returns:
            TestResult avec les détails du test
        """
        start_time = time.time()
        
        # Chercher le torrent correspondant dans la base
        torrent_record = await self._find_torrent_by_name(symlink.torrent_name)
        if not torrent_record:
            return TestResult(
                torrent_hash="unknown",
                filename=symlink.torrent_name,
                success=False,
                error_type="torrent_not_found",
                error_message=f"Torrent non trouvé pour: {symlink.torrent_name}",
                test_timestamp=datetime.now()
            )
        
        # Utiliser le rate limiter
        async with with_rate_limit("test_injection", torrent_record.hash):
            try:
                # Valider le hash
                hash_valid, hash_error = self.validator.validate_sha1_hash(torrent_record.hash)
                if not hash_valid:
                    return TestResult(
                        torrent_hash=torrent_record.hash,
                        filename=torrent_record.filename,
                        success=False,
                        error_type="invalid_hash",
                        error_message=hash_error,
                        response_time_ms=int((time.time() - start_time) * 1000),
                        test_timestamp=datetime.now()
                    )
                
                # Construire le magnet link
                magnet_valid, magnet_link, magnet_error = self.validator.construct_magnet_from_hash(
                    torrent_record.hash, torrent_record.filename
                )
                if not magnet_valid:
                    return TestResult(
                        torrent_hash=torrent_record.hash,
                        filename=torrent_record.filename,
                        success=False,
                        error_type="invalid_magnet",
                        error_message=magnet_error,
                        response_time_ms=int((time.time() - start_time) * 1000),
                        test_timestamp=datetime.now()
                    )
                
                # Test injection Real-Debrid
                api_success, api_response, api_error = self.rd_client.add_magnet(magnet_link)
                response_time = int((time.time() - start_time) * 1000)
                
                if api_success:
                    rd_torrent_id = api_response.get('id', '') if api_response else ''
                    
                    return TestResult(
                        torrent_hash=torrent_record.hash,
                        filename=torrent_record.filename,
                        success=True,
                        rd_torrent_id=rd_torrent_id,
                        response_time_ms=response_time,
                        test_timestamp=datetime.now()
                    )
                else:
                    # Analyser le type d'erreur
                    error_type = self._classify_api_error(api_error)
                    
                    result = TestResult(
                        torrent_hash=torrent_record.hash,
                        filename=torrent_record.filename,
                        success=False,
                        error_type=error_type,
                        error_message=api_error,
                        response_time_ms=response_time,
                        test_timestamp=datetime.now()
                    )
                    
                    # Si infringing_file, créer une tâche de cleanup
                    if error_type == "infringing_file":
                        await self._queue_cleanup_task(result, symlink)
                    
                    return result
                    
            except Exception as e:
                return TestResult(
                    torrent_hash=torrent_record.hash,
                    filename=torrent_record.filename,
                    success=False,
                    error_type="exception",
                    error_message=str(e),
                    response_time_ms=int((time.time() - start_time) * 1000),
                    test_timestamp=datetime.now()
                )
    
    async def _find_torrent_by_name(self, torrent_name: str):
        """Trouve un torrent par nom dans la base de données"""
        try:
            with self.database.get_cursor() as cursor:
                # Recherche exacte d'abord
                cursor.execute("""
                    SELECT * FROM torrents 
                    WHERE filename LIKE ? 
                    ORDER BY last_seen DESC 
                    LIMIT 1
                """, (f"%{torrent_name}%",))
                
                row = cursor.fetchone()
                if row:
                    from database import TorrentRecord
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
                return None
                
        except Exception as e:
            logger.error(f"Erreur recherche torrent par nom: {e}")
            return None
    
    def _classify_api_error(self, api_error: str) -> str:
        """Classifie le type d'erreur API"""
        error_lower = api_error.lower()
        
        if 'infringing_file' in error_lower:
            return 'infringing_file'
        elif 'too_many_requests' in error_lower or '429' in error_lower:
            return 'too_many_requests'
        elif 'magnet' in error_lower and 'error' in error_lower:
            return 'magnet_error'
        elif 'virus' in error_lower:
            return 'virus'
        else:
            return 'unknown_error'
    
    async def _queue_cleanup_task(self, test_result: TestResult, symlink):
        """Ajoute une tâche de cleanup à la queue"""
        try:
            # Trouver tous les chemins locaux pour ce torrent
            local_paths = [symlink.source_path]
            
            # Chercher d'autres symlinks cassés pour le même torrent
            additional_paths = await self._find_related_symlinks(symlink.torrent_name)
            local_paths.extend(additional_paths)
            
            cleanup_task = CleanupTask(
                torrent_hash=test_result.torrent_hash,
                rd_torrent_id=test_result.rd_torrent_id,
                filename=test_result.filename,
                local_paths=local_paths,
                error_type=test_result.error_type,
                discovery_date=test_result.test_timestamp
            )
            
            self.cleanup_queue.append(cleanup_task)
            self._save_cleanup_queue()
            
            logger.info(f"🧹 Tâche cleanup ajoutée: {test_result.filename[:50]}... "
                       f"({len(local_paths)} fichiers locaux)")
            
        except Exception as e:
            logger.error(f"Erreur ajout tâche cleanup: {e}")
    
    async def _find_related_symlinks(self, torrent_name: str) -> List[str]:
        """Trouve d'autres symlinks cassés pour le même torrent"""
        try:
            # Cette fonction pourrait être améliorée pour chercher dans la base
            # des symlinks récemment scannés
            return []
        except Exception as e:
            logger.error(f"Erreur recherche symlinks liés: {e}")
            return []
    
    async def process_cleanup_task(self, task: CleanupTask) -> bool:
        """
        Traite une tâche de cleanup
        
        Args:
            task: CleanupTask à traiter
            
        Returns:
            True si succès, False sinon
        """
        task.status = "processing"
        logger.info(f"🧹 Traitement cleanup: {task.filename[:50]}...")
        
        try:
            success = True
            
            # 1. Supprimer le torrent de Real-Debrid (si ID disponible)
            if task.rd_torrent_id and task.rd_torrent_id != "unknown":
                rd_success = await self._cleanup_rd_torrent(task.rd_torrent_id)
                if not rd_success:
                    success = False
                    logger.warning(f"Échec suppression RD: {task.rd_torrent_id}")
            
            # 2. Supprimer les fichiers locaux
            local_success = await self._cleanup_local_files(task.local_paths)
            if not local_success:
                success = False
                logger.warning(f"Échec nettoyage local pour: {task.filename[:50]}")
            
            # 3. Notifier Sonarr/Radarr pour chaque fichier
            notification_success = await self._notify_media_servers(task)
            if not notification_success:
                success = False
                logger.warning(f"Échec notifications média pour: {task.filename[:50]}")
            
            # Marquer le résultat
            if success:
                task.status = "completed"
                logger.info(f"✅ Cleanup réussi: {task.filename[:50]}...")
                self.stats['cleanups_completed'] += 1
            else:
                task.retry_count += 1
                if task.retry_count >= self.cleanup_retry_limit:
                    task.status = "failed"
                    logger.error(f"❌ Cleanup échoué définitivement: {task.filename[:50]}...")
                    self.stats['errors_encountered'] += 1
                else:
                    task.status = "pending"
                    logger.warning(f"⚠️ Cleanup à retenter ({task.retry_count}/{self.cleanup_retry_limit}): "
                                 f"{task.filename[:50]}...")
            
            self._save_cleanup_queue()
            self._save_state()
            return success
            
        except Exception as e:
            logger.error(f"Erreur traitement cleanup: {e}")
            task.status = "failed"
            task.retry_count += 1
            self.stats['errors_encountered'] += 1
            self._save_cleanup_queue()
            return False
    
    async def _cleanup_rd_torrent(self, rd_torrent_id: str) -> bool:
        """Supprime un torrent de Real-Debrid"""
        try:
            async with with_rate_limit("cleanup_rd", rd_torrent_id):
                success, error = self.rd_client.delete_torrent(rd_torrent_id)
                if success:
                    logger.info(f"🗑️ Torrent RD supprimé: {rd_torrent_id}")
                    return True
                else:
                    logger.error(f"Erreur suppression RD {rd_torrent_id}: {error}")
                    return False
                    
        except Exception as e:
            logger.error(f"Exception suppression RD {rd_torrent_id}: {e}")
            return False
    
    async def _cleanup_local_files(self, local_paths: List[str]) -> bool:
        """Supprime les fichiers locaux (symlinks cassés)"""
        success = True
        
        for path in local_paths:
            try:
                if os.path.exists(path) and os.path.islink(path):
                    os.remove(path)
                    logger.info(f"🗑️ Symlink supprimé: {path}")
                elif os.path.exists(path):
                    logger.warning(f"⚠️ Fichier existe mais n'est pas un symlink: {path}")
            except Exception as e:
                logger.error(f"Erreur suppression {path}: {e}")
                success = False
        
        return success
    
    async def _notify_media_servers(self, task: CleanupTask) -> bool:
        """Notifie Sonarr/Radarr pour rescan après cleanup"""
        try:
            # Import du FailureHandler pour utiliser ses méthodes de notification
            from failure_handler import FailureHandler
            
            failure_handler = FailureHandler(dry_run=False)
            
            # Notification individuelle pour chaque fichier
            success = True
            
            async with with_rate_limit("notify_media", task.torrent_hash):
                # Utiliser la méthode existante de trigger scan
                notification_success = failure_handler._trigger_media_rescan()
                if not notification_success:
                    success = False
                    
            if success:
                logger.info(f"📡 Notifications média envoyées pour: {task.filename[:50]}...")
            else:
                logger.error(f"Erreur notifications média pour: {task.filename[:50]}...")
                
            return success
            
        except Exception as e:
            logger.error(f"Erreur notifications média: {e}")
            return False
    
    async def run_continuous_testing(self):
        """Boucle principale de test continu"""
        logger.info("🚀 Démarrage tests continus")
        
        while not self.signal_handler.is_shutdown_requested():
            try:
                # Obtenir le prochain batch de symlinks
                symlinks_batch = await self.symlink_manager.get_next_symlink_batch(self.batch_size)
                
                if not symlinks_batch:
                    logger.info("📝 Aucun symlink à traiter, attente de nouveau scan...")
                    await asyncio.sleep(60)  # Attendre 1 minute avant retry
                    continue
                
                # Traiter chaque symlink du batch
                for symlink in symlinks_batch:
                    if self.signal_handler.is_shutdown_requested():
                        break
                    
                    try:
                        # Test du symlink
                        result = await self.test_single_symlink(symlink)
                        
                        # Enregistrer le résultat
                        await self._record_test_result(result)
                        
                        # Marquer le symlink comme traité
                        await self.symlink_manager.mark_symlink_processed(symlink, result.success)
                        
                        # Mettre à jour les stats
                        self.stats['tests_performed'] += 1
                        if result.error_type == 'infringing_file':
                            self.stats['infringing_detected'] += 1
                        
                        # Log du résultat
                        if result.success:
                            logger.info(f"✅ Test réussi: {result.filename[:50]}... "
                                       f"({result.response_time_ms}ms)")
                        else:
                            logger.warning(f"❌ Test échoué: {result.filename[:50]}... "
                                         f"({result.error_type}: {result.error_message})")
                        
                        # Pause adaptative selon rate limiting
                        await asyncio.sleep(self.test_interval_seconds)
                        
                    except Exception as e:
                        logger.error(f"Erreur test symlink {symlink.source_path}: {e}")
                        continue
                
                # Sauvegarder l'état après chaque batch
                self._save_state()
                
            except Exception as e:
                logger.error(f"Erreur boucle test continue: {e}")
                await asyncio.sleep(10)  # Pause avant retry
    
    async def run_continuous_cleanup(self):
        """Boucle principale de cleanup continu"""
        logger.info("🧹 Démarrage cleanup continu")
        
        while not self.signal_handler.is_shutdown_requested():
            try:
                # Filtrer les tâches pending
                pending_tasks = [task for task in self.cleanup_queue if task.status == "pending"]
                
                if not pending_tasks:
                    await asyncio.sleep(30)  # Attendre 30s si rien à traiter
                    continue
                
                # Traiter les tâches pending
                for task in pending_tasks[:self.batch_size]:  # Limiter le batch
                    if self.signal_handler.is_shutdown_requested():
                        break
                    
                    success = await self.process_cleanup_task(task)
                    
                    # Retirer les tâches terminées de la queue
                    if task.status in ["completed", "failed"]:
                        self.cleanup_queue.remove(task)
                
                # Sauvegarder après traitement
                self._save_cleanup_queue()
                
                # Pause avant prochain cycle
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"Erreur boucle cleanup continue: {e}")
                await asyncio.sleep(10)
    
    async def _record_test_result(self, result: TestResult):
        """Enregistre un résultat de test en base"""
        try:
            # Enregistrer dans la table test_history
            with self.database.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO test_history (
                        torrent_hash, filename, test_date, result_type,
                        error_type, error_message, rd_torrent_id, response_time_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    result.torrent_hash,
                    result.filename,
                    result.test_timestamp,
                    "success" if result.success else "failure",
                    result.error_type,
                    result.error_message,
                    result.rd_torrent_id,
                    result.response_time_ms
                ))
            
            # Aussi enregistrer comme attempt classique si trouvé
            if result.torrent_hash != "unknown":
                attempt = AttemptRecord(
                    torrent_id=result.torrent_hash,  # Utiliser hash comme ID
                    attempt_date=result.test_timestamp,
                    success=result.success,
                    error_message=result.error_message,
                    response_time_ms=result.response_time_ms,
                    api_response=result.rd_torrent_id
                )
                self.database.record_attempt(attempt)
                
        except Exception as e:
            logger.error(f"Erreur enregistrement résultat test: {e}")
    
    async def get_processing_stats(self) -> Dict[str, any]:
        """Retourne les statistiques de traitement"""
        cleanup_stats = {
            'pending': len([t for t in self.cleanup_queue if t.status == "pending"]),
            'processing': len([t for t in self.cleanup_queue if t.status == "processing"]),
            'completed': len([t for t in self.cleanup_queue if t.status == "completed"]),
            'failed': len([t for t in self.cleanup_queue if t.status == "failed"])
        }
        
        runtime = datetime.now() - self.stats['start_time']
        
        return {
            'test_stats': self.stats,
            'cleanup_queue': cleanup_stats,
            'runtime_hours': runtime.total_seconds() / 3600,
            'avg_tests_per_hour': self.stats['tests_performed'] / max(1, runtime.total_seconds() / 3600),
            'infringing_rate': (self.stats['infringing_detected'] / max(1, self.stats['tests_performed'])) * 100,
            'symlink_manager': await self.symlink_manager.get_processing_stats(),
            'rate_limiter': self.rate_limiter.get_stats_summary()
        }

# Mise à jour du schéma base de données
async def setup_test_tables():
    """Crée les tables nécessaires pour le test continu"""
    database = get_database()
    
    try:
        with database.get_cursor() as cursor:
            # Table historique des tests
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS test_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    torrent_hash TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    test_date TIMESTAMP NOT NULL,
                    result_type TEXT NOT NULL,  -- success/failure
                    error_type TEXT,
                    error_message TEXT,
                    rd_torrent_id TEXT,
                    response_time_ms INTEGER,
                    INDEX(torrent_hash),
                    INDEX(test_date),
                    INDEX(result_type)
                )
            """)
            
        logger.info("Tables test continu configurées")
        
    except Exception as e:
        logger.error(f"Erreur setup tables test: {e}")

# Instance globale
_test_processor_instance = None

def get_test_processor() -> ContinuousTestProcessor:
    """Retourne l'instance globale du processeur de tests (singleton)"""
    global _test_processor_instance
    if _test_processor_instance is None:
        _test_processor_instance = ContinuousTestProcessor()
    return _test_processor_instance