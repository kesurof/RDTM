#!/usr/bin/env python3

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from contextlib import contextmanager
from dataclasses import dataclass
import threading

from config import DATABASE_CONFIG, APP_CONFIG, METRICS_CONFIG

logger = logging.getLogger(__name__)

@dataclass
class TorrentRecord:
    """Représentation d'un enregistrement de torrent"""
    id: str
    hash: str
    filename: str
    status: str
    size: int
    added_date: datetime
    first_seen: datetime
    last_seen: datetime
    attempts_count: int = 0
    last_attempt: Optional[datetime] = None
    last_success: Optional[datetime] = None
    priority: int = 2  # 1=low, 2=normal, 3=high

@dataclass
class AttemptRecord:
    """Représentation d'une tentative de réinjection"""
    id: Optional[int] = None
    torrent_id: str = ""
    attempt_date: datetime = None
    success: bool = False
    error_message: str = ""
    response_time_ms: int = 0
    api_response: str = ""

class DatabaseManager:
    """Gestionnaire de base de données SQLite avec threading safety et migrations automatiques"""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DATABASE_CONFIG['db_path']
        self._local = threading.local()
        self._lock = threading.Lock()
        self.current_version = 2  # Version actuelle du schéma
        self.setup_database()
        
    def _get_connection(self) -> sqlite3.Connection:
        """Obtient une connexion thread-safe"""
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(
                str(self.db_path),
                timeout=DATABASE_CONFIG['connection_timeout'],
                check_same_thread=False
            )
            self._local.connection.row_factory = sqlite3.Row
            # Optimisations SQLite
            self._local.connection.execute("PRAGMA journal_mode=WAL")
            self._local.connection.execute("PRAGMA synchronous=NORMAL")
            self._local.connection.execute("PRAGMA cache_size=10000")
            self._local.connection.execute("PRAGMA temp_store=MEMORY")
            
        return self._local.connection
    
    @contextmanager
    def get_cursor(self):
        """Context manager pour les opérations de base de données"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Erreur base de données: {e}")
            raise
        finally:
            cursor.close()
    
    def get_schema_version(self) -> int:
        """Récupère la version actuelle du schéma"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute("PRAGMA user_version")
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception:
            return 0
    
    def set_schema_version(self, version: int):
        """Définit la version du schéma"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute(f"PRAGMA user_version = {version}")
        except Exception as e:
            logger.error(f"Erreur mise à jour version schéma: {e}")
    
    def migrate_database(self):
        """Effectue les migrations nécessaires"""
        current_version = self.get_schema_version()
        logger.info(f"Version schéma actuelle: {current_version}, cible: {self.current_version}")
        
        if current_version < self.current_version:
            logger.info("🔄 Migration de la base de données nécessaire")
            
            try:
                with self._lock:
                    # Migration de v0/v1 vers v2 (ajout needs_symlink_cleanup)
                    if current_version < 2:
                        self._migrate_to_v2()
                    
                    # Ici on pourra ajouter d'autres migrations futures
                    # if current_version < 3:
                    #     self._migrate_to_v3()
                    
                    # Mettre à jour la version
                    self.set_schema_version(self.current_version)
                    logger.info(f"✅ Migration terminée vers version {self.current_version}")
                    
            except Exception as e:
                logger.error(f"❌ Erreur during migration: {e}")
                raise
        else:
            logger.debug("Base de données à jour")
    
    def _migrate_to_v2(self):
        """Migration vers version 2 - ajoute needs_symlink_cleanup"""
        logger.info("📝 Migration v2: ajout colonne needs_symlink_cleanup")
        
        with self.get_cursor() as cursor:
            # Vérifier si la colonne existe déjà
            cursor.execute("PRAGMA table_info(torrents)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'needs_symlink_cleanup' not in columns:
                # Ajouter la nouvelle colonne
                cursor.execute("""
                    ALTER TABLE torrents 
                    ADD COLUMN needs_symlink_cleanup BOOLEAN DEFAULT 0
                """)
                
                # Créer l'index pour cette colonne
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_torrents_symlink_cleanup 
                    ON torrents(needs_symlink_cleanup)
                """)
                
                logger.info("✅ Colonne needs_symlink_cleanup ajoutée")
            else:
                logger.info("ℹ️ Colonne needs_symlink_cleanup déjà présente")
    
    def setup_database(self):
        """Initialise la structure de la base de données avec migrations automatiques"""
        with self._lock:
            # Créer les tables de base (version initiale)
            self._create_base_tables()
            
            # Effectuer les migrations si nécessaire
            self.migrate_database()
            
            logger.info("Base de données initialisée avec succès")
    
    def _create_base_tables(self):
        """Crée les tables de base (sans les nouvelles colonnes pour éviter les conflits)"""
        with self.get_cursor() as cursor:
            # Table des torrents (structure de base)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS torrents (
                    id TEXT PRIMARY KEY,
                    hash TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    status TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    added_date TIMESTAMP NOT NULL,
                    first_seen TIMESTAMP NOT NULL,
                    last_seen TIMESTAMP NOT NULL,
                    attempts_count INTEGER DEFAULT 0,
                    last_attempt TIMESTAMP,
                    last_success TIMESTAMP,
                    priority INTEGER DEFAULT 2,
                    metadata TEXT  -- JSON pour infos supplémentaires
                )
            """)
            
            # Table des tentatives de réinjection
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    torrent_id TEXT NOT NULL,
                    attempt_date TIMESTAMP NOT NULL,
                    success BOOLEAN NOT NULL,
                    error_message TEXT,
                    response_time_ms INTEGER,
                    api_response TEXT,
                    FOREIGN KEY (torrent_id) REFERENCES torrents (id)
                )
            """)
            
            # Table des métriques
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP NOT NULL,
                    metric_type TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    value REAL NOT NULL,
                    tags TEXT,  -- JSON pour tags additionnels
                    aggregation_period TEXT  -- 1h, 6h, 1d, etc.
                )
            """)
            
            # Table de progression des scans
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scan_progress (
                    id INTEGER PRIMARY KEY,
                    scan_type TEXT NOT NULL,  -- 'quick' ou 'full'
                    current_offset INTEGER DEFAULT 0,
                    total_expected INTEGER DEFAULT 0,
                    last_scan_start TIMESTAMP,
                    last_scan_complete TIMESTAMP,
                    status TEXT DEFAULT 'idle'  -- 'idle', 'running', 'completed'
                )
            """)

            # Table des échecs permanents (infringing_file, etc.)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS permanent_failures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    torrent_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    error_message TEXT,
                    failure_date TIMESTAMP NOT NULL,
                    processed BOOLEAN DEFAULT FALSE,
                    UNIQUE(torrent_id, error_type)
                )
            """)
            
            # Table de retry différé (too_many_requests, etc.)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS retry_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    torrent_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    error_message TEXT,
                    original_failure TIMESTAMP NOT NULL,
                    scheduled_retry TIMESTAMP NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    last_retry_attempt TIMESTAMP,
                    UNIQUE(torrent_id, error_type)
                )
            """)
            
            # Index pour les performances (de base)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_torrents_status ON torrents(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_torrents_last_seen ON torrents(last_seen)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_torrents_hash ON torrents(hash)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_attempts_torrent_id ON attempts(torrent_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_attempts_date ON attempts(attempt_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_type_name ON metrics(metric_type, metric_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_progress_type ON scan_progress(scan_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_permanent_failures_date ON permanent_failures(failure_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_retry_queue_scheduled ON retry_queue(scheduled_retry)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_retry_queue_torrent ON retry_queue(torrent_id)")
    
    def upsert_torrent(self, torrent_data: Dict[str, Any]) -> bool:
        """Insert ou update d'un torrent"""
        try:
            with self.get_cursor() as cursor:
                now = datetime.now()
                
                # Vérifier si le torrent existe
                cursor.execute("SELECT id, first_seen FROM torrents WHERE id = ?", (torrent_data['id'],))
                existing = cursor.fetchone()
                
                # Préparer les champs dynamiquement selon la structure actuelle
                base_fields = {
                    'hash': torrent_data['hash'],
                    'filename': torrent_data['filename'],
                    'status': torrent_data['status'],
                    'size': torrent_data['size'],
                    'added_date': torrent_data['added'],
                    'last_seen': now,
                    'metadata': json.dumps(torrent_data.get('metadata', {}))
                }
                
                # Ajouter les champs optionnels s'ils existent dans la table
                cursor.execute("PRAGMA table_info(torrents)")
                available_columns = [col[1] for col in cursor.fetchall()]
                
                if 'needs_symlink_cleanup' in available_columns:
                    base_fields['needs_symlink_cleanup'] = torrent_data.get('needs_symlink_cleanup', False)
                
                if existing:
                    # Update - construire la requête dynamiquement
                    set_clause = ', '.join([f"{field} = ?" for field in base_fields.keys()])
                    values = list(base_fields.values()) + [torrent_data['id']]
                    
                    cursor.execute(f"""
                        UPDATE torrents SET {set_clause}
                        WHERE id = ?
                    """, values)
                else:
                    # Insert - construire la requête dynamiquement
                    insert_fields = {
                        'id': torrent_data['id'],
                        'first_seen': now,
                        'attempts_count': 0,
                        'priority': torrent_data.get('priority', 2),
                        **base_fields
                    }
                    
                    fields = ', '.join(insert_fields.keys())
                    placeholders = ', '.join(['?'] * len(insert_fields))
                    values = list(insert_fields.values())
                    
                    cursor.execute(f"""
                        INSERT INTO torrents ({fields}) VALUES ({placeholders})
                    """, values)
                
                return True
                
        except Exception as e:
            logger.error(f"Erreur upsert torrent {torrent_data.get('id', 'unknown')}: {e}")
            return False
    
    def get_failed_torrents(self, exclude_recent_attempts: bool = True) -> List[TorrentRecord]:
        """Récupère les torrents en échec à traiter"""
        try:
            with self.get_cursor() as cursor:
                query = """
                    SELECT * FROM torrents 
                    WHERE status IN ('magnet_error', 'error', 'virus', 'dead')
                    AND attempts_count < ?
                """
                params = [APP_CONFIG['max_retry_attempts']]
                
                if exclude_recent_attempts:
                    # Exclure les torrents tentés récemment
                    retry_threshold = datetime.now() - timedelta(hours=APP_CONFIG['retry_delay_hours'])
                    query += " AND (last_attempt IS NULL OR last_attempt < ?)"
                    params.append(retry_threshold)
                
                query += " ORDER BY priority DESC, last_seen DESC"
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                torrents = []
                for row in rows:
                    torrents.append(TorrentRecord(
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
                
                return torrents
                
        except Exception as e:
            logger.error(f"Erreur récupération torrents en échec: {e}")
            return []
    
    def record_attempt(self, attempt: AttemptRecord) -> bool:
        """Enregistre une tentative de réinjection"""
        try:
            with self.get_cursor() as cursor:
                # Insérer la tentative
                cursor.execute("""
                    INSERT INTO attempts (
                        torrent_id, attempt_date, success, error_message,
                        response_time_ms, api_response
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    attempt.torrent_id,
                    attempt.attempt_date or datetime.now(),
                    attempt.success,
                    attempt.error_message,
                    attempt.response_time_ms,
                    attempt.api_response
                ))
                
                # Mettre à jour le torrent
                update_fields = [
                    "attempts_count = attempts_count + 1",
                    "last_attempt = ?"
                ]
                update_params = [attempt.attempt_date or datetime.now()]
                
                if attempt.success:
                    update_fields.append("last_success = ?")
                    update_params.append(attempt.attempt_date or datetime.now())
                
                update_params.append(attempt.torrent_id)
                
                cursor.execute(f"""
                    UPDATE torrents SET {', '.join(update_fields)}
                    WHERE id = ?
                """, update_params)
                
                return True
                
        except Exception as e:
            logger.error(f"Erreur enregistrement tentative {attempt.torrent_id}: {e}")
            return False
    
    def record_metric(self, metric_type: str, metric_name: str, value: float, 
                     tags: Optional[Dict] = None, aggregation_period: str = None) -> bool:
        """Enregistre une métrique"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO metrics (
                        timestamp, metric_type, metric_name, value, tags, aggregation_period
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    datetime.now(),
                    metric_type,
                    metric_name,
                    value,
                    json.dumps(tags or {}),
                    aggregation_period
                ))
                return True
                
        except Exception as e:
            logger.error(f"Erreur enregistrement métrique {metric_type}.{metric_name}: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """Récupère les statistiques générales"""
        try:
            with self.get_cursor() as cursor:
                stats = {}
                
                # Statistiques des torrents
                cursor.execute("""
                    SELECT status, COUNT(*) as count, AVG(size) as avg_size
                    FROM torrents 
                    GROUP BY status
                """)
                stats['torrents_by_status'] = {row['status']: {
                    'count': row['count'], 
                    'avg_size': row['avg_size']
                } for row in cursor.fetchall()}
                
                # Statistiques des tentatives (dernières 24h)
                yesterday = datetime.now() - timedelta(days=1)
                cursor.execute("""
                    SELECT success, COUNT(*) as count, AVG(response_time_ms) as avg_response_time
                    FROM attempts 
                    WHERE attempt_date > ?
                    GROUP BY success
                """, (yesterday,))
                stats['attempts_24h'] = {
                    ('success' if row['success'] else 'failure'): {
                        'count': row['count'],
                        'avg_response_time': row['avg_response_time']
                    } for row in cursor.fetchall()
                }
                
                # Torrents nécessitant intervention
                cursor.execute("""
                    SELECT COUNT(*) as count FROM torrents 
                    WHERE status IN ('magnet_error', 'error', 'virus', 'dead')
                    AND attempts_count < ?
                """, (APP_CONFIG['max_retry_attempts'],))
                stats['pending_reinjection'] = cursor.fetchone()['count']
                
                return stats
            
        except Exception as e:
            logger.error(f"Erreur récupération statistiques: {e}")
            return {}

    def get_scan_progress(self, scan_type: str) -> Optional[Dict[str, Any]]:
        """Récupère la progression d'un type de scan"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM scan_progress WHERE scan_type = ?
                """, (scan_type,))
                row = cursor.fetchone()
                
                if row:
                    return {
                        'scan_type': row['scan_type'],
                        'current_offset': row['current_offset'],
                        'total_expected': row['total_expected'],
                        'last_scan_start': row['last_scan_start'],
                        'last_scan_complete': row['last_scan_complete'],
                        'status': row['status']
                    }
                return None
                
        except Exception as e:
            logger.error(f"Erreur récupération progression scan {scan_type}: {e}")
            return None
    
    def update_scan_progress(self, scan_type: str, current_offset: int = 0, 
                            total_expected: int = 0, status: str = 'idle') -> bool:
        """Met à jour la progression d'un scan"""
        try:
            with self.get_cursor() as cursor:
                now = datetime.now()
                
                # Upsert de la progression
                cursor.execute("""
                    INSERT OR REPLACE INTO scan_progress (
                        id, scan_type, current_offset, total_expected, status,
                        last_scan_start, last_scan_complete
                    ) VALUES (
                        (SELECT id FROM scan_progress WHERE scan_type = ?),
                        ?, ?, ?, ?,
                        CASE WHEN ? = 'running' THEN ? ELSE 
                            (SELECT last_scan_start FROM scan_progress WHERE scan_type = ?) END,
                        CASE WHEN ? = 'completed' THEN ? ELSE 
                            (SELECT last_scan_complete FROM scan_progress WHERE scan_type = ?) END
                    )
                """, (scan_type, scan_type, current_offset, total_expected, status,
                     status, now, scan_type, status, now, scan_type))
                
                return True
                
        except Exception as e:
            logger.error(f"Erreur mise à jour progression scan {scan_type}: {e}")
            return False
    
    def cleanup_old_data(self) -> Tuple[int, int]:
        """Nettoie les anciennes données selon la configuration"""
        try:
            with self.get_cursor() as cursor:
                now = datetime.now()
                
                # Nettoyer les anciens torrents (gardés pour historique)
                history_threshold = now - timedelta(days=APP_CONFIG['history_retention_days'])
                
                # Supprimer les tentatives anciennes
                cursor.execute("""
                    DELETE FROM attempts 
                    WHERE attempt_date < ?
                """, (history_threshold,))
                attempts_deleted = cursor.rowcount
                
                # Supprimer les métriques anciennes
                metrics_threshold = now - timedelta(days=METRICS_CONFIG['retention_days'])
                cursor.execute("""
                    DELETE FROM metrics 
                    WHERE timestamp < ?
                """, (metrics_threshold,))
                metrics_deleted = cursor.rowcount
                
                # Vacuum pour récupérer l'espace
                cursor.execute("VACUUM")
                
                logger.info(f"Nettoyage: {attempts_deleted} tentatives, {metrics_deleted} métriques supprimées")
                return attempts_deleted, metrics_deleted
                
        except Exception as e:
            logger.error(f"Erreur nettoyage base de données: {e}")
            return 0, 0
    
    def backup_database(self, backup_path: Optional[Path] = None) -> bool:
        """Crée une sauvegarde de la base de données"""
        try:
            if not backup_path:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_path = self.db_path.parent / f"rd_manager_backup_{timestamp}.db"
            
            with self.get_cursor() as cursor:
                cursor.execute(f"VACUUM INTO '{backup_path}'")
            
            logger.info(f"Sauvegarde créée: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur sauvegarde base de données: {e}")
            return False
    
    def close(self):
        """Ferme toutes les connexions"""
        if hasattr(self._local, 'connection'):
            self._local.connection.close()
            delattr(self._local, 'connection')

# Instance globale (singleton thread-safe)
_db_instance = None
_db_lock = threading.Lock()

def get_database() -> DatabaseManager:
    """Retourne l'instance de base de données (singleton)"""
    global _db_instance
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                _db_instance = DatabaseManager()
    return _db_instance