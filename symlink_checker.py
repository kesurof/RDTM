#!/usr/bin/env python3

import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import re

from config import CURRENT_USER

logger = logging.getLogger(__name__)

@dataclass
class BrokenSymlink:
    """Représentation d'un lien symbolique cassé"""
    source_path: str
    target_path: str
    torrent_name: str
    status: str  # 'BROKEN', 'IO_ERROR', etc.
    size: int = 0
    error_message: str = ""

class SymlinkChecker:
    """Détecteur de liens symboliques cassés inspiré d'advanced_symlink_checker.py"""
    
    def __init__(self, max_workers: int = 6):
        self.max_workers = max_workers
        self.stats = {
            'total_analyzed': 0,
            'broken_links': 0,
            'io_errors': 0,
            'small_files': 0,
            'valid_links': 0
        }
        
        # Pattern pour extraire le nom de torrent depuis le chemin target
        self.zurg_pattern = re.compile(r'/home/[^/]+/seedbox/zurg/torrents/([^/]+)/')
        
        logger.info("SymlinkChecker initialisé")
    
    def check_symlink_basic(self, path: str) -> Optional[BrokenSymlink]:
        """Vérification basique d'un lien symbolique (inspiré du script existant)"""
        try:
            if not os.path.islink(path):
                return None
                
            target = os.readlink(path)
            
            # Test d'existence
            if not os.path.exists(path):
                torrent_name = self._extract_torrent_name(target)
                return BrokenSymlink(
                    source_path=path,
                    target_path=target,
                    torrent_name=torrent_name,
                    status='BROKEN',
                    size=0
                )
            
            # Test d'accès
            if not os.access(path, os.R_OK):
                torrent_name = self._extract_torrent_name(target)
                return BrokenSymlink(
                    source_path=path,
                    target_path=target,
                    torrent_name=torrent_name,
                    status='INACCESSIBLE',
                    size=0
                )
            
            # Test de taille et lecture
            try:
                file_size = os.path.getsize(path)
                if file_size < 1024:  # < 1KB suspect
                    torrent_name = self._extract_torrent_name(target)
                    return BrokenSymlink(
                        source_path=path,
                        target_path=target,
                        torrent_name=torrent_name,
                        status='SMALL_FILE',
                        size=file_size
                    )
                
                # Test de lecture basique
                with open(path, 'rb') as f:
                    f.read(1024)  # Lecture test
                    
            except OSError as e:
                torrent_name = self._extract_torrent_name(target)
                return BrokenSymlink(
                    source_path=path,
                    target_path=target,
                    torrent_name=torrent_name,
                    status='IO_ERROR',
                    size=0,
                    error_message=str(e)
                )
            
            # Fichier OK
            return None
            
        except Exception as e:
            logger.error(f"Erreur vérification {path}: {e}")
            return BrokenSymlink(
                source_path=path,
                target_path="",
                torrent_name="unknown",
                status='ERROR',
                size=0,
                error_message=str(e)
            )
    
    def _extract_torrent_name(self, target_path: str) -> str:
        """Extrait le nom du torrent depuis le chemin target Zurg"""
        match = self.zurg_pattern.search(target_path)
        if match:
            return match.group(1)
        
        # Fallback: essayer d'extraire depuis le chemin
        try:
            path_parts = Path(target_path).parts
            for i, part in enumerate(path_parts):
                if part == 'torrents' and i + 1 < len(path_parts):
                    return path_parts[i + 1]
        except Exception:
            pass
        
        return "unknown"
    
    def scan_directory(self, directory_path: str) -> List[BrokenSymlink]:
        """Scanne un répertoire pour les liens cassés"""
        logger.info(f"🔍 Scan des liens symboliques dans: {directory_path}")

        # Vérifier si shutdown demandé
        from utils import get_signal_handler
        signal_handler = get_signal_handler()
        
        if not os.path.exists(directory_path):
            logger.error(f"Répertoire inexistant: {directory_path}")
            return []
        
        # Collecter tous les liens symboliques
        all_symlinks = []
        for root, dirs, files in os.walk(directory_path):
            for name in files:
                full_path = os.path.join(root, name)
                if os.path.islink(full_path):
                    all_symlinks.append(full_path)
        
        logger.info(f"📊 {len(all_symlinks)} liens symboliques trouvés")
        
        if not all_symlinks:
            return []
        
        # Traitement parallèle
        broken_links = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_symlink = {
                executor.submit(self.check_symlink_basic, link): link 
                for link in all_symlinks
            }
            
            completed = 0
            for future in as_completed(future_to_symlink):
                # Vérifier shutdown à chaque itération
                if signal_handler.is_shutdown_requested():
                    logger.info("🛑 Arrêt demandé - interruption scan symlinks")
                    # Annuler les futures en attente
                    for remaining_future in future_to_symlink:
                        remaining_future.cancel()
                    break
                try:
                    result = future.result()
                    self.stats['total_analyzed'] += 1
                    completed += 1
                    
                    if result:
                        broken_links.append(result)
                        if result.status == 'BROKEN':
                            self.stats['broken_links'] += 1
                        elif result.status == 'IO_ERROR':
                            self.stats['io_errors'] += 1
                        elif result.status == 'SMALL_FILE':
                            self.stats['small_files'] += 1
                        
                        logger.debug(f"[{result.status}] {os.path.basename(result.source_path)} → {result.torrent_name}")
                    else:
                        self.stats['valid_links'] += 1
                    
                    # Progression
                    if completed % 100 == 0:
                        logger.info(f"📈 Progression: {completed}/{len(all_symlinks)}")
                        
                except Exception as e:
                    logger.error(f"Erreur traitement lien: {e}")
        
        logger.info(f"✅ Scan terminé: {len(broken_links)} liens cassés détectés")
        return broken_links
    
    def scan_media_directories(self, base_path: str = None) -> Dict[str, List[BrokenSymlink]]:
        """Scanne tous les répertoires média pour les liens cassés"""
        if not base_path:
            base_path = f"/home/{CURRENT_USER}/Medias"
        
        logger.info(f"🔍 Scan complet des répertoires média: {base_path}")
        
        results = {}
        
        # Lister les sous-répertoires
        try:
            for item in os.listdir(base_path):
                item_path = os.path.join(base_path, item)
                if os.path.isdir(item_path) and not item.startswith('.'):
                    logger.info(f"📂 Scan de {item}...")
                    broken_links = self.scan_directory(item_path)
                    if broken_links:
                        results[item] = broken_links
                        logger.info(f"  → {len(broken_links)} liens cassés trouvés")
                    else:
                        logger.info(f"  → Aucun lien cassé")
        
        except Exception as e:
            logger.error(f"Erreur scan répertoires média: {e}")
        
        total_broken = sum(len(links) for links in results.values())
        logger.info(f"🎯 Scan complet terminé: {total_broken} liens cassés au total")
        
        return results
    
    def get_unique_torrent_names(self, broken_links: List[BrokenSymlink]) -> Set[str]:
        """Extrait les noms uniques de torrents depuis les liens cassés"""
        torrent_names = set()
        for link in broken_links:
            if link.torrent_name and link.torrent_name != "unknown":
                torrent_names.add(link.torrent_name)
        
        logger.info(f"📋 {len(torrent_names)} torrents uniques identifiés depuis les liens cassés")
        return torrent_names
    
    def get_stats(self) -> Dict[str, int]:
        """Retourne les statistiques du scan"""
        return self.stats.copy()

# Instance globale
_symlink_checker_instance = None

def get_symlink_checker() -> SymlinkChecker:
    """Retourne l'instance du checker (singleton)"""
    global _symlink_checker_instance
    if _symlink_checker_instance is None:
        _symlink_checker_instance = SymlinkChecker()
    return _symlink_checker_instance