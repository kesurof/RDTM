#!/usr/bin/env python3

import os
from pathlib import Path
from typing import Set, Dict, Any

# Détection automatique de l'utilisateur
CURRENT_USER = os.environ.get('USER', os.environ.get('USERNAME', 'user'))

# Configuration des chemins
BASE_DIR = Path(__file__).parent
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"
CONFIG_DIR = BASE_DIR / "config"

# Créer les répertoires nécessaires
LOGS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
CONFIG_DIR.mkdir(exist_ok=True)

# Configuration Real-Debrid API
RD_API_CONFIG = {
    'base_url': 'https://api.real-debrid.com/rest/1.0/',
    'timeout': 30,
    'max_retries': 3,
    'backoff_factor': 2,
    'rate_limit_codes': [5, 34],  # "Slow down", "Too many requests"
}

# Statuts de torrents à traiter (échecs)
FAILED_STATUSES = {
    'magnet_error',
    'error', 
    'virus',
    'dead'
}

# Statuts de torrents OK (ne pas traiter)
SUCCESS_STATUSES = {
    'downloaded',
    'downloading', 
    'queued',
    'uploading',
    'compressing'
}

# Configuration du rate limiting
RATE_LIMIT_CONFIG = {
    'initial_delay': 1.0,           # Délai initial entre requêtes (secondes)
    'min_delay': 0.5,               # Délai minimum
    'max_delay': 30.0,              # Délai maximum
    'backoff_multiplier': 1.5,      # Multiplicateur en cas d'erreur
    'recovery_divisor': 1.1,        # Diviseur pour récupération
    'max_torrents_per_cycle': 1,    # Démarrage conservateur
    'max_torrents_limit': 50,       # Limite absolue par cycle
}

# Configuration de l'application
APP_CONFIG = {
    'scan_interval': 600,           # 10 minutes entre scans
    'retry_delay_hours': 3,         # Délai entre tentatives de réinjection
    'max_retry_attempts': 3,        # Nombre max de tentatives
    'history_retention_days': 30,   # Conservation historique
    'parallel_workers': 4,          # Workers parallèles
    'dry_run_mode': True,          # Mode dry-run par défaut
}

# Configuration de la base de données
DATABASE_CONFIG = {
    'db_path': DATA_DIR / 'rd_manager.db',
    'backup_interval_hours': 24,
    'cleanup_interval_hours': 6,
    'connection_timeout': 30,
}

# Configuration du logging
LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file_max_bytes': 10 * 1024 * 1024,  # 10MB
    'file_backup_count': 5,
    'console_level': 'INFO',
    'file_level': 'DEBUG',
}

# Configuration Discord webhook
DISCORD_CONFIG = {
    'enabled': False,               # Activé via variable d'environnement
    'webhook_url': '',              # URL du webhook Discord
    'username': 'Real-Debrid Manager',
    'avatar_url': '',
    'color_success': 0x00ff00,     # Vert
    'color_warning': 0xff9900,     # Orange  
    'color_error': 0xff0000,       # Rouge
}

# Configuration des métriques
METRICS_CONFIG = {
    'collection_interval': 300,    # 5 minutes
    'retention_days': 90,          # 3 mois de métriques
    'aggregation_intervals': [
        '1h', '6h', '1d', '7d', '30d'
    ],
}

# Validation des magnet links
MAGNET_VALIDATION = {
    'min_hash_length': 40,         # SHA1 = 40 caractères
    'max_hash_length': 40,
    'required_scheme': 'magnet:',
    'required_param': 'xt=urn:btih:',
    'min_file_size': 1024,         # 1KB minimum
}

# Messages utilisateur
USER_MESSAGES = {
    'startup_banner': """
🚀 Real-Debrid Torrent Manager
===============================================
Gestionnaire automatique de torrents en échec
Détection et réinjection intelligente
===============================================
""",
    
    'mode_selection': """
Mode d'exécution:
1) DRY-RUN  → Analyse sans action + logs détaillés
2) RÉEL     → Analyse et réinjection automatique
""",
    
    'confirmation_real_mode': """
⚠️  MODE RÉEL ACTIVÉ
Cette session va automatiquement:
- Scanner les torrents en échec
- Les réinjecter via l'API Real-Debrid
- Respecter les rate limits et retry logic

Continuer ? (y/N): """,
    
    'scan_summary': """
📊 RÉSUMÉ DU SCAN
Total torrents: {total}
En échec: {failed}
À réinjecter: {to_reinject}
Déjà traités: {already_processed}
""",
}

# Configuration des priorités de torrents
PRIORITY_CONFIG = {
    'high_priority': {
        'statuses': ['magnet_error'],
        'min_size_gb': 1.0,
        'max_age_hours': 24,
        'weight': 3
    },
    'normal_priority': {
        'statuses': ['error', 'virus', 'dead'],
        'min_size_mb': 100,
        'max_age_days': 7,
        'weight': 2
    },
    'low_priority': {
        'max_size_mb': 100,
        'min_age_days': 7,
        'max_retry_count': 2,
        'weight': 1
    }
}

def get_env_config() -> Dict[str, Any]:
    """Récupère la configuration depuis les variables d'environnement"""
    return {
        'rd_api_token': os.environ.get('RD_API_TOKEN'),
        'discord_webhook': os.environ.get('DISCORD_WEBHOOK_URL'),
        'log_level': os.environ.get('LOG_LEVEL', 'INFO'),
        'scan_interval': int(os.environ.get('SCAN_INTERVAL', '600')),
        'dry_run': os.environ.get('DRY_RUN', 'true').lower() == 'true',
        'max_workers': int(os.environ.get('MAX_WORKERS', '4')),
    }

def validate_config() -> bool:
    """Valide la configuration de base"""
    env_config = get_env_config()
    
    if not env_config['rd_api_token']:
        print("❌ Variable RD_API_TOKEN manquante")
        return False
    
    if len(env_config['rd_api_token']) < 20:
        print("❌ RD_API_TOKEN semble invalide (trop court)")
        return False
    
    return True

def get_database_url() -> str:
    """Retourne l'URL de la base de données"""
    return f"sqlite:///{DATABASE_CONFIG['db_path']}"

# Export des constantes principales
__all__ = [
    'CURRENT_USER', 'BASE_DIR', 'LOGS_DIR', 'DATA_DIR',
    'RD_API_CONFIG', 'FAILED_STATUSES', 'SUCCESS_STATUSES',
    'RATE_LIMIT_CONFIG', 'APP_CONFIG', 'DATABASE_CONFIG',
    'LOGGING_CONFIG', 'DISCORD_CONFIG', 'METRICS_CONFIG',
    'MAGNET_VALIDATION', 'USER_MESSAGES', 'PRIORITY_CONFIG',
    'get_env_config', 'validate_config', 'get_database_url'
]