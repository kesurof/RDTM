import logging
import sys
from datetime import datetime
from pathlib import Path

class RDTMLogger:
    def __init__(self, name: str, log_level: str = "INFO"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, log_level.upper()))
        
        # Créer le dossier de logs s'il n'existe pas
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Handler pour fichier
        file_handler = logging.FileHandler(
            log_dir / f"rdtm_{datetime.now().strftime('%Y%m%d')}.log"
        )
        file_handler.setLevel(logging.DEBUG)
        
        # Handler pour console
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        # Format des logs
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    def get_logger(self):
        return self.logger

# Décorateur pour logging automatique
def log_errors(func):
    def wrapper(*args, **kwargs):
        logger = RDTMLogger(func.__module__).get_logger()
        try:
            result = func(*args, **kwargs)
            logger.info(f"Fonction {func.__name__} exécutée avec succès")
            return result
        except Exception as e:
            logger.error(f"Erreur dans {func.__name__}: {str(e)}")
            raise
    return wrapper
