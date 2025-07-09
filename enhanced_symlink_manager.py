#!/usr/bin/env python3

import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Set
from pathlib import Path
from dataclasses import dataclass
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

from config import CURRENT_USER, DATA_DIR
from symlink_checker import get_symlink_checker, BrokenSymlink
from database import get_database
from unified_rate_limiter import get_rate_limiter, with_rate_limit

logger = logging.getLogger(__name__)

@dataclass
class SymlinkProcessingState:
    """État de traitement des symlinks cassés"""
    current_directory: str = ""
    current_index: int = 0
    total_directories: int = 0
    total_symlinks_found: int = 0
    total_processed: int = 0
    last_scan_date: datetime = None
    scan_in_progress: bool = False

class EnhancedSymlinkManager:
    """Gestionnaire avancé des symlinks cassés avec traitement continu et persistence"""
    
    def __init__(self, base_path: str = None):
        self.base_path = base_path or f"/home/{CURRENT_USER}/Medias"
        self.database = get_database()
        self.symlink_checker = get_symlink_checker()
        self.rate_limiter = get_rate_limiter()
        
        # État persistant
        self.state_file = DATA_DIR / "symlink_processing_state.json"
        self.state = self._load_state()
        
        # Configuration
        self.max_concurrent_scans = 3
        self.rescan_interval_hours = 24
        
        # Queue de traitement ordonnée alphabétiquement
        self.processing_queue: List[Tuple[str, List[BrokenSymlink]]] = []
        self.current_batch: List[BrokenSymlink] = []
        
        logger.info(f"EnhancedSymlinkManager initialisé: {self.base_path}")
        logger.info(f"État actuel: {self.state.current_directory} ({self.state.current_index})")
    
    def _load_state(self) -> SymlinkProcessingState:
        """Charge l'état persistant depuis le fichier"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    return SymlinkProcessingState(
                        current_directory=data.get('current_directory', ''),
                        current_index=data.get('current_index', 0),
                        total_directories=data.get('total_directories', 0),
                        total_symlinks_found=data.get('total_symlinks_found', 0),
                        total_processed=data.get('total_processed', 0),
                        last_scan_date=datetime.fromisoformat(data['last_scan_date']) if data.get('last_scan_date') else None,
                        scan_in_progress=data.get('scan_in_progress', False)
                    )
        except Exception as e:
            logger.warning(f"Erreur chargement état symlinks: {e}")
        
        return SymlinkProcessingState()
    
    def _save_state(self):
        """Sauvegarde l'état persistant"""
        try:
            data = {
                'current_directory': self.state.current_directory,
                'current_index': self.state.current_index,
                'total_directories': self.state.total_directories,
                'total_symlinks_found': self.state.total_symlinks_found,
                'total_processed': self.state.total_processed,
                'last_scan_date': self.state.last_scan_date.isoformat() if self.state.last_scan_date else None,
                'scan_in_progress': self.state.scan_in_progress
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Erreur sauvegarde état symlinks: {e}")
    
    async def get_ordered_directories(self) -> List[str]:
        """Retourne la liste des répertoires triés alphabétiquement"""
        try:
            directories = []
            
            if not os.path.exists(self.base_path):
                logger.error(f"Base path inexistant: {self.base_path}")
                return []
            
            for item in sorted(os.listdir(self.base_path)):
                item_path = os.path.join(self.base_path, item)
                if os.path.isdir(item_path) and not item.startswith('.'):
                    directories.append(item)
            
            logger.info(f"Répertoires trouvés: {len(directories)} (triés alphabétiquement)")
            return directories
            
        except Exception as e:
            logger.error(f"Erreur listage répertoires: {e}")
            return []
    
    async def scan_directory_for_symlinks(self, directory_name: str) -> List[BrokenSymlink]:
        """Scanne un répertoire spécifique pour les symlinks cassés"""
        directory_path = os.path.join(self.base_path, directory_name)
        
        logger.info(f"🔍 Scan symlinks: {directory_name}")
        
        try:
            # Utiliser le symlink_checker existant
            broken_links = self.symlink_checker.scan_directory(directory_path)
            
            logger.info(f"✅ {directory_name}: {len(broken_links)} symlinks cassés trouvés")
            return broken_links
            
        except Exception as e:
            logger.error(f"❌ Erreur scan {directory_name}: {e}")
            return []
    
    async def should_rescan(self) -> bool:
        """Détermine s'il faut relancer un scan complet"""
        if not self.state.last_scan_date:
            return True
        
        elapsed = datetime.now() - self.state.last_scan_date
        
        # Rescan si plus de 24h OU si scan incomplet
        if elapsed > timedelta(hours=self.rescan_interval_hours):
            logger.info(f"Rescan nécessaire: {elapsed.total_seconds()/3600:.1f}h écoulées")
            return True
        
        if self.state.scan_in_progress or self.state.current_index == 0:
            logger.info("Rescan nécessaire: scan incomplet")
            return True
        
        return False
    
    async def perform_full_scan(self) -> List[Tuple[str, List[BrokenSymlink]]]:
        """Effectue un scan complet de tous les répertoires"""
        logger.info("🚀 Début scan complet symlinks")
        
        self.state.scan_in_progress = True
        self.state.last_scan_date = datetime.now()
        self._save_state()
        
        try:
            directories = await self.get_ordered_directories()
            self.state.total_directories = len(directories)
            
            results = []
            total_symlinks = 0
            
            # Reprendre depuis la position sauvegardée
            start_index = 0
            if self.state.current_directory:
                try:
                    start_index = directories.index(self.state.current_directory)
                    logger.info(f"Reprise scan depuis: {self.state.current_directory} (index {start_index})")
                except ValueError:
                    logger.warning(f"Répertoire de reprise non trouvé: {self.state.current_directory}")
                    start_index = 0
            
            # Scanner les répertoires restants
            for i, directory in enumerate(directories[start_index:], start_index):
                self.state.current_directory = directory
                self.state.current_index = i
                self._save_state()
                
                broken_links = await self.scan_directory_for_symlinks(directory)
                
                if broken_links:
                    results.append((directory, broken_links))
                    total_symlinks += len(broken_links)
                    
                    logger.info(f"📊 Progression: {i+1}/{len(directories)} répertoires, "
                               f"{total_symlinks} symlinks cassés")
                
                # Pause pour éviter la surcharge
                await asyncio.sleep(0.1)
            
            self.state.total_symlinks_found = total_symlinks
            self.state.scan_in_progress = False
            self.state.current_index = 0  # Reset pour prochain cycle
            self.state.current_directory = ""
            self._save_state()
            
            logger.info(f"✅ Scan complet terminé: {len(results)} répertoires avec symlinks cassés, "
                       f"{total_symlinks} symlinks au total")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Erreur scan complet: {e}")
            self.state.scan_in_progress = False
            self._save_state()
            return []
    
    async def get_next_symlink_batch(self, batch_size: int = 10) -> List[BrokenSymlink]:
        """
        Retourne le prochain batch de symlinks cassés à traiter
        
        Args:
            batch_size: Taille du batch à retourner
            
        Returns:
            Liste des symlinks cassés à traiter
        """
        # Si plus de symlinks dans le batch actuel, recharger
        if not self.current_batch:
            await self._reload_symlink_queue()
        
        # Extraire le batch demandé
        batch = self.current_batch[:batch_size]
        self.current_batch = self.current_batch[batch_size:]
        
        if batch:
            logger.info(f"📦 Nouveau batch: {len(batch)} symlinks (reste: {len(self.current_batch)})")
        
        return batch
    
    async def _reload_symlink_queue(self):
        """Recharge la queue des symlinks à traiter"""
        logger.info("🔄 Rechargement queue symlinks")
        
        # Vérifier s'il faut faire un nouveau scan
        if await self.should_rescan() or not self.processing_queue:
            logger.info("Lancement nouveau scan complet")
            self.processing_queue = await self.perform_full_scan()
        
        # Construire la liste plate des symlinks triés par répertoire
        self.current_batch = []
        for directory, symlinks in self.processing_queue:
            # Trier les symlinks du répertoire par nom de fichier
            sorted_symlinks = sorted(symlinks, key=lambda s: os.path.basename(s.source_path))
            self.current_batch.extend(sorted_symlinks)
        
        logger.info(f"📊 Queue rechargée: {len(self.current_batch)} symlinks de "
                   f"{len(self.processing_queue)} répertoires")
    
    async def mark_symlink_processed(self, symlink: BrokenSymlink, success: bool = True):
        """Marque un symlink comme traité"""
        try:
            # Mettre à jour les statistiques
            self.state.total_processed += 1
            self._save_state()
            
            # Enregistrer en base de données pour historique
            await self._record_symlink_processing(symlink, success)
            
            logger.debug(f"Symlink marqué comme traité: {os.path.basename(symlink.source_path)} "
                        f"(succès: {success})")
            
        except Exception as e:
            logger.error(f"Erreur marquage symlink traité: {e}")
    
    async def _record_symlink_processing(self, symlink: BrokenSymlink, success: bool):
        """Enregistre le traitement d'un symlink en base"""
        try:
            with self.database.get_cursor() as cursor:
                cursor.execute("""
                    INSERT OR REPLACE INTO symlink_processing_history (
                        source_path, target_path, torrent_name, status,
                        processing_date, success, file_size
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    symlink.source_path,
                    symlink.target_path,
                    symlink.torrent_name,
                    symlink.status,
                    datetime.now(),
                    success,
                    symlink.size
                ))
                
        except Exception as e:
            logger.error(f"Erreur enregistrement historique symlink: {e}")
    
    async def get_processing_stats(self) -> Dict[str, any]:
        """Retourne les statistiques de traitement"""
        rate_stats = self.rate_limiter.get_stats_summary()
        
        return {
            'state': {
                'current_directory': self.state.current_directory,
                'current_index': self.state.current_index,
                'total_directories': self.state.total_directories,
                'total_symlinks_found': self.state.total_symlinks_found,
                'total_processed': self.state.total_processed,
                'scan_in_progress': self.state.scan_in_progress,
                'last_scan_date': self.state.last_scan_date.isoformat() if self.state.last_scan_date else None
            },
            'queue': {
                'directories_remaining': len(self.processing_queue),
                'symlinks_in_batch': len(self.current_batch),
                'completion_rate': (self.state.total_processed / max(1, self.state.total_symlinks_found)) * 100
            },
            'rate_limiting': rate_stats,
            'next_rescan_in_hours': max(0, self.rescan_interval_hours - 
                                      ((datetime.now() - (self.state.last_scan_date or datetime.now())).total_seconds() / 3600))
        }
    
    async def force_rescan(self):
        """Force un nouveau scan complet"""
        logger.info("🔄 Force rescan demandé")
        
        # Reset de l'état
        self.state.current_directory = ""
        self.state.current_index = 0
        self.state.scan_in_progress = False
        self.state.last_scan_date = None
        self._save_state()
        
        # Vider les queues
        self.processing_queue = []
        self.current_batch = []
        
        # Relancer le scan
        await self._reload_symlink_queue()

# Mise à jour du schéma de base de données
async def setup_symlink_tables():
    """Crée les tables nécessaires pour le tracking des symlinks"""
    database = get_database()
    
    try:
        with database.get_cursor() as cursor:
            # Table historique des traitements symlinks
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS symlink_processing_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_path TEXT NOT NULL,
                    target_path TEXT NOT NULL,
                    torrent_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    processing_date TIMESTAMP NOT NULL,
                    success BOOLEAN NOT NULL,
                    file_size INTEGER DEFAULT 0,
                    UNIQUE(source_path, processing_date)
                )
            """)
            
            # Index pour les performances
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_symlink_processing_date ON symlink_processing_history(processing_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_symlink_torrent_name ON symlink_processing_history(torrent_name)")
            
        logger.info("Tables symlinks configurées")
        
    except Exception as e:
        logger.error(f"Erreur setup tables symlinks: {e}")

# Instance globale
_symlink_manager_instance = None

def get_symlink_manager() -> EnhancedSymlinkManager:
    """Retourne l'instance globale du gestionnaire de symlinks (singleton)"""
    global _symlink_manager_instance
    if _symlink_manager_instance is None:
        _symlink_manager_instance = EnhancedSymlinkManager()
    return _symlink_manager_instance