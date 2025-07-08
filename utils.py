#!/usr/bin/env python3

import os
import logging
import json
import time
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Any, Optional, List
import signal
import sys

from config import LOGGING_CONFIG, LOGS_DIR, USER_MESSAGES, get_env_config

class ColoredFormatter(logging.Formatter):
    """Formatter avec couleurs pour la console"""
    
    # Codes couleur ANSI
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Vert
        'WARNING': '\033[33m',  # Jaune
        'ERROR': '\033[31m',    # Rouge
        'CRITICAL': '\033[35m', # Magenta
        'RESET': '\033[0m'      # Reset
    }
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        record.levelname = f"{log_color}{record.levelname}{self.COLORS['RESET']}"
        return super().format(record)

def setup_logging() -> logging.Logger:
    """Configuration complète du logging"""
    # Créer le répertoire de logs
    LOGS_DIR.mkdir(exist_ok=True)
    
    # Logger principal
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, LOGGING_CONFIG['level']))
    
    # Éviter les doublons si déjà configuré
    if logger.handlers:
        return logger
    
    # Handler fichier avec rotation
    file_handler = RotatingFileHandler(
        filename=LOGS_DIR / 'rd_manager.log',
        maxBytes=LOGGING_CONFIG['file_max_bytes'],
        backupCount=LOGGING_CONFIG['file_backup_count'],
        encoding='utf-8'
    )
    file_handler.setLevel(getattr(logging, LOGGING_CONFIG['file_level']))
    file_formatter = logging.Formatter(
        LOGGING_CONFIG['format'],
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # Handler console avec couleurs
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, LOGGING_CONFIG['console_level']))
    console_formatter = ColoredFormatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # Handler pour métriques (JSON)
    metrics_handler = RotatingFileHandler(
        filename=LOGS_DIR / 'metrics.jsonl',
        maxBytes=LOGGING_CONFIG['file_max_bytes'],
        backupCount=3,
        encoding='utf-8'
    )
    metrics_handler.setLevel(logging.INFO)
    metrics_formatter = logging.Formatter('%(message)s')
    metrics_handler.setFormatter(metrics_formatter)
    
    # Logger spécifique pour métriques
    metrics_logger = logging.getLogger('metrics')
    metrics_logger.addHandler(metrics_handler)
    metrics_logger.setLevel(logging.INFO)
    metrics_logger.propagate = False
    
    return logger

class MetricsLogger:
    """Logger spécialisé pour les métriques JSON"""
    
    def __init__(self):
        self.logger = logging.getLogger('metrics')
    
    def log_metric(self, metric_type: str, metric_name: str, value: Any, 
                   tags: Optional[Dict] = None):
        """Log une métrique au format JSON"""
        metric_data = {
            'timestamp': datetime.now().isoformat(),
            'type': metric_type,
            'name': metric_name,
            'value': value,
            'tags': tags or {}
        }
        
        self.logger.info(json.dumps(metric_data))
    
    def log_event(self, event_type: str, event_data: Dict[str, Any]):
        """Log un événement"""
        event = {
            'timestamp': datetime.now().isoformat(),
            'type': 'event',
            'event_type': event_type,
            'data': event_data
        }
        
        self.logger.info(json.dumps(event))

class InteractiveUI:
    """Interface utilisateur interactive inspirée du script existant"""
    
    @staticmethod
    def print_banner():
        """Affiche la bannière de démarrage"""
        print(USER_MESSAGES['startup_banner'])
    
    @staticmethod
    def choose_execution_mode() -> str:
        """Choix du mode d'exécution (inspiré du script symlink)"""
        print("\n" + "="*60)
        print("🔧 MODE D'EXÉCUTION")
        print("="*60)
        print(USER_MESSAGES['mode_selection'])
        
        while True:
            try:
                choice = input(f"\n👉 Votre choix (1-2): ").strip()
                if choice == '1':
                    print("✅ Mode DRY-RUN sélectionné")
                    return 'dry-run'
                elif choice == '2':
                    print("⚠️  Mode RÉEL sélectionné")
                    return 'real'
                else:
                    print("❌ Choix invalide. Utilisez 1 ou 2")
            except KeyboardInterrupt:
                print("\n❌ Opération annulée")
                sys.exit(0)
    
    @staticmethod
    def confirm_real_mode() -> bool:
        """Confirmation pour le mode réel"""
        print(USER_MESSAGES['confirmation_real_mode'], end="")
        try:
            response = input().strip().lower()
            return response in ['y', 'yes', 'o', 'oui']
        except KeyboardInterrupt:
            print("\n❌ Opération annulée")
            return False
    
    @staticmethod
    def display_scan_summary(summary: Dict[str, Any]):
        """Affiche le résumé du scan"""
        print(f"\n{USER_MESSAGES['scan_summary'].format(**summary)}")
    
    @staticmethod
    def display_progress(current: int, total: int, prefix: str = "Progression"):
        """Affiche une barre de progression simple"""
        if total == 0:
            return
        
        percentage = (current / total) * 100
        bar_length = 40
        filled_length = int(bar_length * current / total)
        bar = '█' * filled_length + '-' * (bar_length - filled_length)
        
        print(f"\r{prefix}: |{bar}| {current}/{total} ({percentage:.1f}%)", end="", flush=True)
        
        if current == total:
            print()  # Nouvelle ligne à la fin

class SignalHandler:
    """Gestionnaire de signaux pour arrêt propre"""
    
    def __init__(self):
        self.shutdown_requested = False
        self.callbacks = []
        
        # Enregistrer les handlers
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, self._handle_signal)
    
    def _handle_signal(self, signum, frame):
        """Handler pour les signaux"""
        signal_names = {
            signal.SIGINT: 'SIGINT (Ctrl+C)',
            signal.SIGTERM: 'SIGTERM',
        }
        if hasattr(signal, 'SIGHUP'):
            signal_names[signal.SIGHUP] = 'SIGHUP'
        
        signal_name = signal_names.get(signum, f'Signal {signum}')
        print(f"\n🛑 Signal reçu: {signal_name}")
        print("⏳ Arrêt en cours...")
        
        self.shutdown_requested = True
        
        # Exécuter les callbacks d'arrêt
        for callback in self.callbacks:
            try:
                callback()
            except Exception as e:
                print(f"Erreur callback arrêt: {e}")
    
    def add_shutdown_callback(self, callback):
        """Ajoute une fonction à exécuter lors de l'arrêt"""
        self.callbacks.append(callback)
    
    def is_shutdown_requested(self) -> bool:
        """Vérifie si un arrêt a été demandé"""
        return self.shutdown_requested

class PerformanceMonitor:
    """Moniteur de performance simple"""
    
    def __init__(self):
        self.start_time = time.time()
        self.checkpoints = {}
        self.metrics = MetricsLogger()
    
    def checkpoint(self, name: str):
        """Enregistre un checkpoint de temps"""
        self.checkpoints[name] = time.time()
    
    def get_elapsed(self, checkpoint_name: Optional[str] = None) -> float:
        """Retourne le temps écoulé depuis le début ou un checkpoint"""
        if checkpoint_name and checkpoint_name in self.checkpoints:
            return time.time() - self.checkpoints[checkpoint_name]
        return time.time() - self.start_time
    
    def log_performance(self, operation: str, duration: float, details: Optional[Dict] = None):
        """Log les métriques de performance"""
        self.metrics.log_metric(
            'performance',
            f'{operation}_duration',
            duration,
            tags={'operation': operation, **(details or {})}
        )

class RetryHelper:
    """Utilitaire pour les tentatives avec backoff"""
    
    @staticmethod
    def exponential_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
        """Calcule le délai avec backoff exponentiel"""
        delay = base_delay * (2 ** attempt)
        return min(delay, max_delay)
    
    @staticmethod
    def should_retry(attempt: int, max_attempts: int, exception: Exception = None) -> bool:
        """Détermine si une nouvelle tentative doit être faite"""
        if attempt >= max_attempts:
            return False
        
        # Logique spécifique selon le type d'exception
        if exception:
            # Ne pas retry sur certaines erreurs définitives
            if "Token API invalide" in str(exception):
                return False
            if "401" in str(exception) or "403" in str(exception):
                return False
        
        return True

def format_bytes(bytes_count: int) -> str:
    """Formate une taille en bytes de manière lisible"""
    if bytes_count == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while bytes_count >= 1024 and i < len(size_names) - 1:
        bytes_count /= 1024.0
        i += 1
    
    return f"{bytes_count:.1f} {size_names[i]}"

def format_duration(seconds: float) -> str:
    """Formate une durée en secondes de manière lisible"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"

def safe_filename(filename: str) -> str:
    """Nettoie un nom de fichier pour le système de fichiers"""
    # Caractères interdits
    forbidden_chars = '<>:"/\\|?*'
    for char in forbidden_chars:
        filename = filename.replace(char, '_')
    
    # Limiter la longueur
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        max_name_length = 255 - len(ext)
        filename = name[:max_name_length] + ext
    
    return filename.strip()

def validate_environment() -> List[str]:
    """Valide l'environnement et retourne les erreurs"""
    errors = []
    
    # Vérifier les variables d'environnement requises
    env_config = get_env_config()
    
    if not env_config['rd_api_token']:
        errors.append("Variable RD_API_TOKEN manquante")
    
    # Vérifier les permissions d'écriture
    test_dirs = [LOGS_DIR, Path.cwd()]
    for dir_path in test_dirs:
        try:
            test_file = dir_path / f'.test_write_{int(time.time())}'
            test_file.write_text('test')
            test_file.unlink()
        except Exception as e:
            errors.append(f"Pas d'écriture dans {dir_path}: {e}")
    
    # Vérifier l'espace disque (basique)
    try:
        import shutil
        free_space = shutil.disk_usage(Path.cwd()).free
        if free_space < 100 * 1024 * 1024:  # 100MB minimum
            errors.append(f"Espace disque faible: {format_bytes(free_space)}")
    except Exception:
        pass  # Non critique
    
    return errors

# Instances globales
signal_handler = SignalHandler()
metrics_logger = MetricsLogger()

def get_signal_handler() -> SignalHandler:
    """Retourne l'instance globale du gestionnaire de signaux"""
    return signal_handler

def get_metrics_logger() -> MetricsLogger:
    """Retourne l'instance globale du logger de métriques"""
    return metrics_logger