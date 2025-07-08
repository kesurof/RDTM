#!/usr/bin/env python3

import time
import logging
import sys
from datetime import datetime, timedelta
from typing import Optional

from config import validate_config, APP_CONFIG, get_env_config
from utils import (
    setup_logging, InteractiveUI, get_signal_handler, 
    get_metrics_logger, PerformanceMonitor, validate_environment,
    format_duration
)
from torrent_manager import TorrentManager
from database import get_database

# Configuration du logging avant tout
logger = setup_logging()

class RealDebridManager:
    """Gestionnaire principal de l'application"""
    
    def __init__(self):
        self.signal_handler = get_signal_handler()
        self.metrics = get_metrics_logger()
        self.performance = PerformanceMonitor()
        self.torrent_manager: Optional[TorrentManager] = None
        self.is_running = False
        
        # Enregistrer le callback d'arrêt
        self.signal_handler.add_shutdown_callback(self.shutdown)
        
        logger.info("Real-Debrid Manager initialisé")
    
    def startup_checks(self) -> bool:
        """Vérifications de démarrage"""
        logger.info("🔧 Vérifications de démarrage")
        
        # Validation configuration
        if not validate_config():
            logger.error("❌ Configuration invalide")
            return False
        
        # Validation environnement
        env_errors = validate_environment()
        if env_errors:
            logger.error("❌ Problèmes environnement:")
            for error in env_errors:
                logger.error(f"  - {error}")
            return False
        
        logger.info("✅ Vérifications de démarrage réussies")
        return True
    
    def interactive_setup(self) -> bool:
        """Configuration interactive utilisateur"""
        InteractiveUI.print_banner()
        
        # Choix du mode d'exécution
        mode = InteractiveUI.choose_execution_mode()
        dry_run = (mode == 'dry-run')
        
        # Confirmation pour le mode réel
        if not dry_run:
            if not InteractiveUI.confirm_real_mode():
                logger.info("❌ Mode réel annulé par l'utilisateur")
                return False
        
        # Initialiser le gestionnaire de torrents
        try:
            self.torrent_manager = TorrentManager(dry_run=dry_run)
            
            # Test de connectivité
            if not self.torrent_manager.test_connectivity():
                logger.error("❌ Échec test de connectivité")
                return False
            
            logger.info(f"✅ TorrentManager prêt (mode: {'DRY-RUN' if dry_run else 'RÉEL'})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur initialisation TorrentManager: {e}")
            return False
    
    def single_cycle(self) -> bool:
        """Exécute un cycle complet de traitement"""
        if not self.torrent_manager:
            logger.error("TorrentManager non initialisé")
            return False
        
        cycle_start = time.time()
        logger.info("🔄 Début du cycle de traitement")
        
        try:
            # 1. Scanner les torrents
            self.performance.checkpoint('scan_start')
            scan_success, scan_results = self.torrent_manager.scan_torrents()
            scan_duration = self.performance.get_elapsed('scan_start')
            
            if not scan_success:
                logger.error(f"❌ Échec du scan: {scan_results.get('error', 'unknown')}")
                return False
            
            # Log métriques du scan
            self.metrics.log_metric('scan', 'duration', scan_duration)
            self.metrics.log_metric('scan', 'torrents_total', scan_results['total_torrents'])
            self.metrics.log_metric('scan', 'torrents_failed', scan_results['failed_torrents'])
            
            # Afficher le résumé du scan
            InteractiveUI.display_scan_summary({
                'total': scan_results['total_torrents'],
                'failed': scan_results['failed_torrents'],
                'to_reinject': scan_results['failed_torrents'],  # Approximation
                'already_processed': scan_results['total_torrents'] - scan_results['failed_torrents']
            })
            
            # 2. Traiter les réinjections
            if scan_results['failed_torrents'] > 0:
                self.performance.checkpoint('reinjection_start')
                reinjection_results = self.torrent_manager.process_reinjections()
                reinjection_duration = self.performance.get_elapsed('reinjection_start')
                
                # Log métriques des réinjections
                self.metrics.log_metric('reinjection', 'duration', reinjection_duration)
                self.metrics.log_metric('reinjection', 'attempted', reinjection_results['processed'])
                self.metrics.log_metric('reinjection', 'successful', reinjection_results['successful'])
                self.metrics.log_metric('reinjection', 'failed', reinjection_results['failed'])
                
                if reinjection_results['processed'] > 0:
                    success_rate = (reinjection_results['successful'] / reinjection_results['processed']) * 100
                    logger.info(f"📊 Réinjections: {reinjection_results['successful']}/{reinjection_results['processed']} "
                               f"réussies ({success_rate:.1f}%)")
                    
                    # Log des erreurs si présentes
                    if reinjection_results['errors']:
                        logger.warning(f"⚠️ {len(reinjection_results['errors'])} erreurs de réinjection:")
                        for error in reinjection_results['errors'][:5]:  # Limiter à 5 erreurs
                            logger.warning(f"  - {error['filename'][:50]}: {error['error']}")
                        
                        if len(reinjection_results['errors']) > 5:
                            logger.warning(f"  ... et {len(reinjection_results['errors']) - 5} autres erreurs")
            else:
                logger.info("✅ Aucun torrent en échec à traiter")
            
            # 3. Traiter les retries différés
            self.performance.checkpoint('retries_start')
            retries_results = self.torrent_manager.process_pending_retries()
            retries_duration = self.performance.get_elapsed('retries_start')
            
            # Log métriques des retries
            self.metrics.log_metric('retries', 'duration', retries_duration)
            self.metrics.log_metric('retries', 'processed', retries_results['processed'])
            self.metrics.log_metric('retries', 'successful', retries_results['successful'])
            
            if retries_results['processed'] > 0:
                success_rate = (retries_results['successful'] / retries_results['processed']) * 100
                logger.info(f"🔄 Retries traités: {retries_results['successful']}/{retries_results['processed']} "
                           f"réussis ({success_rate:.1f}%)")

            # 4. Statistiques du cycle
            cycle_duration = time.time() - cycle_start
            manager_stats = self.torrent_manager.get_manager_stats()
            
            self.metrics.log_metric('cycle', 'duration', cycle_duration)
            self.metrics.log_event('cycle_completed', {
                'duration': cycle_duration,
                'scan_results': scan_results,
                'manager_stats': manager_stats
            })
            
            logger.info(f"✅ Cycle terminé en {format_duration(cycle_duration)}")
            return True
            
        except Exception as e:
            cycle_duration = time.time() - cycle_start
            logger.error(f"❌ Erreur durant le cycle: {e}")
            self.metrics.log_event('cycle_error', {
                'duration': cycle_duration,
                'error': str(e)
            })
            return False
    
    def maintenance_cycle(self):
        """Cycle de maintenance périodique"""
        logger.info("🧹 Cycle de maintenance")
        
        try:
            if self.torrent_manager:
                self.torrent_manager.cleanup_and_maintenance()
            
            # Log des statistiques globales
            if self.torrent_manager:
                stats = self.torrent_manager.get_manager_stats()
                self.metrics.log_event('maintenance_stats', stats)
                
                logger.info("📊 Statistiques globales:")
                logger.info(f"  - Mode: {stats['mode']}")
                logger.info(f"  - Scans: {stats['scans_completed']}")
                logger.info(f"  - Torrents traités: {stats['torrents_processed']}")
                logger.info(f"  - Réinjections: {stats['reinjections']['successful']}/{stats['reinjections']['attempted']}")
                
        except Exception as e:
            logger.error(f"Erreur maintenance: {e}")
    
    def run_continuous(self):
        """Boucle principale en mode continu"""
        logger.info("🚀 Démarrage du mode continu")
        
        self.is_running = True
        last_maintenance = datetime.now()
        maintenance_interval = timedelta(hours=6)  # Maintenance toutes les 6h
        cycle_count = 0
        
        try:
            while self.is_running and not self.signal_handler.is_shutdown_requested():
                cycle_count += 1
                logger.info(f"🔄 Cycle #{cycle_count}")
                
                # Exécuter un cycle de traitement
                cycle_success = self.single_cycle()
                
                # Maintenance périodique
                now = datetime.now()
                if now - last_maintenance > maintenance_interval:
                    self.maintenance_cycle()
                    last_maintenance = now
                
                # Attendre avant le prochain cycle (sauf si arrêt demandé)
                if self.is_running and not self.signal_handler.is_shutdown_requested():
                    scan_interval = APP_CONFIG['scan_interval']
                    logger.info(f"⏸️ Attente {format_duration(scan_interval)} avant le prochain scan")
                    
                    # Attente interruptible
                    start_wait = time.time()
                    while (time.time() - start_wait) < scan_interval:
                        if self.signal_handler.is_shutdown_requested():
                            break
                        time.sleep(1)  # Vérifier l'arrêt chaque seconde
                
        except KeyboardInterrupt:
            logger.info("🛑 Interruption clavier détectée")
        except Exception as e:
            logger.error(f"❌ Erreur fatale dans la boucle principale: {e}")
        finally:
            self.is_running = False
            logger.info(f"📊 Session terminée après {cycle_count} cycles")
    
    def run_single(self) -> bool:
        """Exécute un seul cycle (mode test)"""
        logger.info("🧪 Mode cycle unique")
        
        success = self.single_cycle()
        
        if success:
            logger.info("✅ Cycle unique terminé avec succès")
        else:
            logger.error("❌ Cycle unique échoué")
        
        return success
    
    def shutdown(self):
        """Arrêt propre de l'application"""
        logger.info("🛑 Arrêt en cours...")
        
        self.is_running = False
        
        if self.torrent_manager:
            try:
                # Sauvegarder les statistiques finales
                final_stats = self.torrent_manager.get_manager_stats()
                self.metrics.log_event('shutdown', {
                    'total_runtime': self.performance.get_elapsed(),
                    'final_stats': final_stats
                })
                
                # Fermeture propre
                self.torrent_manager.close()
                logger.info("✅ TorrentManager fermé")
            except Exception as e:
                logger.error(f"Erreur fermeture TorrentManager: {e}")
        
        # Fermeture base de données
        try:
            db = get_database()
            db.close()
            logger.info("✅ Base de données fermée")
        except Exception as e:
            logger.error(f"Erreur fermeture base de données: {e}")
        
        logger.info("✅ Arrêt terminé")

def main():
    """Point d'entrée principal"""
    manager = None
    
    try:
        # Initialiser le gestionnaire
        manager = RealDebridManager()
        
        # Vérifications de démarrage
        if not manager.startup_checks():
            sys.exit(1)
        
        # Configuration interactive
        if not manager.interactive_setup():
            sys.exit(1)
        
        # Lire la configuration pour le mode d'exécution
        env_config = get_env_config()
        
        # Déterminer le mode d'exécution
        if len(sys.argv) > 1:
            mode_arg = sys.argv[1].lower()
            if mode_arg == '--single':
                # Mode cycle unique (pour tests)
                success = manager.run_single()
                sys.exit(0 if success else 1)
            elif mode_arg == '--help':
                print("Usage: python main.py [--single|--help]")
                print("  --single  : Exécute un seul cycle puis s'arrête")
                print("  (défaut)  : Mode continu avec boucle infinie")
                sys.exit(0)
        
        # Mode continu par défaut
        manager.run_continuous()
        
    except KeyboardInterrupt:
        logger.info("🛑 Interruption utilisateur")
        if manager:
            manager.shutdown()
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"❌ Erreur fatale: {e}")
        if manager:
            manager.shutdown()
        sys.exit(1)
    
    finally:
        # Nettoyage final
        if manager:
            manager.shutdown()

if __name__ == "__main__":
    main()