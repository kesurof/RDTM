#!/usr/bin/env python3

import asyncio
import logging
import sys
import signal
from datetime import datetime, timedelta
from typing import Optional

from config import validate_config, get_env_config
from utils import (
    setup_logging, InteractiveUI, get_signal_handler, 
    get_metrics_logger, PerformanceMonitor, validate_environment,
    format_duration
)
from database import get_database
from enhanced_symlink_manager import get_symlink_manager, setup_symlink_tables
from continuous_test_processor import get_test_processor, setup_test_tables
from unified_rate_limiter import get_rate_limiter

# Configuration du logging avant tout
logger = setup_logging()

class DualThreadRDManager:
    """Gestionnaire RDTM avec architecture dual-thread optimisée"""
    
    def __init__(self):
        self.signal_handler = get_signal_handler()
        self.metrics = get_metrics_logger()
        self.performance = PerformanceMonitor()
        self.rate_limiter = get_rate_limiter()
        
        # Composants principaux
        self.symlink_manager: Optional = None
        self.test_processor: Optional = None
        
        # État d'exécution
        self.is_running = False
        self.tasks = []
        
        # Enregistrer le callback d'arrêt
        self.signal_handler.add_shutdown_callback(self.shutdown)
        
        logger.info("DualThreadRDManager initialisé")
    
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
    
    async def initialize_components(self) -> bool:
        """Initialise tous les composants nécessaires"""
        logger.info("🔧 Initialisation des composants")
        
        try:
            # Configurer les tables de base de données
            await setup_symlink_tables()
            await setup_test_tables()
            
            # Initialiser les composants
            self.symlink_manager = get_symlink_manager()
            self.test_processor = get_test_processor()
            
            # Test de connectivité de base
            database = get_database()
            stats = database.get_statistics()
            logger.info(f"✅ Base de données accessible ({len(stats)} statistiques)")
            
            # Test rate limiter
            rate_stats = self.rate_limiter.get_stats_summary()
            logger.info(f"✅ Rate limiter configuré: {rate_stats['current_usage']['total']}/250 calls/min")
            
            logger.info("✅ Composants initialisés avec succès")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur initialisation composants: {e}")
            return False
    
    def interactive_setup(self) -> bool:
        """Configuration interactive utilisateur"""
        InteractiveUI.print_banner()
        
        print("🔄 RDTM Dual-Thread Manager")
        print("="*50)
        print("• Thread 1: Test continu symlinks cassés")
        print("• Thread 2: Cleanup RD + notifications média")
        print("• Rate limiting unifié: 250 calls/minute")
        print("• Persistence complète état + queue")
        print()
        
        # Choix du mode d'exécution
        mode = InteractiveUI.choose_execution_mode()
        dry_run = (mode == 'dry-run')
        
        if dry_run:
            logger.info("⚠️ Mode DRY-RUN: Tests sans actions réelles")
            print("📝 Mode DRY-RUN activé:")
            print("  • Tests d'injection simulés")
            print("  • Pas de suppression RD")
            print("  • Pas de nettoyage local") 
            print("  • Logs détaillés uniquement")
        else:
            print("⚠️ MODE RÉEL - Actions automatiques:")
            print("  • Tests injection Real-Debrid")
            print("  • Suppression torrents infringing")
            print("  • Nettoyage fichiers locaux")
            print("  • Notifications Sonarr/Radarr")
            print()
            
            confirm = input("👉 Confirmer le mode RÉEL ? (y/N): ").strip().lower()
            if confirm not in ['y', 'yes', 'o', 'oui']:
                logger.info("❌ Mode réel annulé par l'utilisateur")
                return False
        
        # Configuration spéciale pour le dual-thread
        self.dry_run = dry_run
        
        logger.info(f"✅ Configuration terminée (mode: {'DRY-RUN' if dry_run else 'RÉEL'})")
        return True
    
    async def display_initial_stats(self):
        """Affiche les statistiques initiales avant démarrage"""
        logger.info("📊 État initial du système")
        
        try:
            # Stats symlink manager
            symlink_stats = await self.symlink_manager.get_processing_stats()
            
            print("\n📊 ÉTAT INITIAL DU SYSTÈME")
            print("="*50)
            print(f"Répertoires média: {symlink_stats['state']['total_directories']}")
            print(f"Symlinks trouvés: {symlink_stats['state']['total_symlinks_found']}")
            print(f"Déjà traités: {symlink_stats['state']['total_processed']}")
            print(f"En attente: {symlink_stats['queue']['symlinks_in_batch']}")
            
            if symlink_stats['state']['last_scan_date']:
                last_scan = datetime.fromisoformat(symlink_stats['state']['last_scan_date'])
                elapsed = datetime.now() - last_scan
                print(f"Dernier scan: {elapsed.days}j {elapsed.seconds//3600}h ago")
            else:
                print("Dernier scan: Jamais")
            
            # Stats test processor
            test_stats = await self.test_processor.get_processing_stats()
            
            print(f"\nTests effectués: {test_stats['test_stats']['tests_performed']}")
            print(f"Infringing détectés: {test_stats['test_stats']['infringing_detected']}")
            print(f"Cleanups terminés: {test_stats['test_stats']['cleanups_completed']}")
            
            cleanup_pending = test_stats['cleanup_queue']['pending']
            if cleanup_pending > 0:
                print(f"⚠️ Queue cleanup: {cleanup_pending} tâches en attente")
            
            # Stats rate limiter
            rate_stats = self.rate_limiter.get_stats_summary()
            print(f"\nUtilisation API: {rate_stats['utilization_rate']:.1f}% (250 calls/min max)")
            
            print("="*50)
            
        except Exception as e:
            logger.error(f"Erreur affichage stats initiales: {e}")
    
    async def run_dual_thread_processing(self):
        """Lance le traitement dual-thread principal"""
        logger.info("🚀 Démarrage traitement dual-thread")
        
        self.is_running = True
        
        try:
            # Afficher l'état initial
            await self.display_initial_stats()
            
            print("\n🚀 DÉMARRAGE THREADS PARALLÈLES")
            print("Thread 1: Tests continus (symlinks → injection → détection infringing)")
            print("Thread 2: Cleanup continu (suppression RD + local + notifications)")
            print("Ctrl+C pour arrêt propre")
            print("-" * 60)
            
            # Créer les tâches asynchrones
            self.tasks = [
                asyncio.create_task(self._run_testing_thread(), name="testing_thread"),
                asyncio.create_task(self._run_cleanup_thread(), name="cleanup_thread"),
                asyncio.create_task(self._run_monitoring_thread(), name="monitoring_thread")
            ]
            
            # Lancer toutes les tâches en parallèle
            await asyncio.gather(*self.tasks, return_exceptions=True)
            
        except KeyboardInterrupt:
            logger.info("🛑 Interruption clavier détectée")
        except Exception as e:
            logger.error(f"❌ Erreur traitement dual-thread: {e}")
        finally:
            self.is_running = False
            await self._cancel_all_tasks()
    
    async def _run_testing_thread(self):
        """Thread 1: Tests continus des symlinks"""
        logger.info("🧪 Thread 1: Démarrage tests continus")
        
        try:
            await self.test_processor.run_continuous_testing()
        except Exception as e:
            logger.error(f"❌ Erreur thread testing: {e}")
            raise
    
    async def _run_cleanup_thread(self):
        """Thread 2: Cleanup continu"""
        logger.info("🧹 Thread 2: Démarrage cleanup continu")
        
        try:
            await self.test_processor.run_continuous_cleanup()
        except Exception as e:
            logger.error(f"❌ Erreur thread cleanup: {e}")
            raise
    
    async def _run_monitoring_thread(self):
        """Thread 3: Monitoring et statistiques périodiques"""
        logger.info("📊 Thread 3: Démarrage monitoring")
        
        try:
            while self.is_running and not self.signal_handler.is_shutdown_requested():
                await asyncio.sleep(300)  # Stats toutes les 5 minutes
                
                # Affichage des statistiques
                await self._display_runtime_stats()
                
                # Métriques pour monitoring externe
                await self._record_metrics()
                
        except Exception as e:
            logger.error(f"❌ Erreur thread monitoring: {e}")
    
    async def _display_runtime_stats(self):
        """Affiche les statistiques de runtime"""
        try:
            test_stats = await self.test_processor.get_processing_stats()
            symlink_stats = await self.symlink_manager.get_processing_stats()
            rate_stats = self.rate_limiter.get_stats_summary()
            
            runtime_hours = test_stats['runtime_hours']
            tests_per_hour = test_stats['avg_tests_per_hour']
            infringing_rate = test_stats['infringing_rate']
            
            logger.info(f"📊 Stats runtime ({runtime_hours:.1f}h): "
                       f"{tests_per_hour:.1f} tests/h, "
                       f"{infringing_rate:.1f}% infringing, "
                       f"API {rate_stats['utilization_rate']:.1f}%")
            
            # Cleanup queue status
            cleanup_queue = test_stats['cleanup_queue']
            if cleanup_queue['pending'] > 0:
                logger.info(f"🧹 Cleanup queue: {cleanup_queue['pending']} pending, "
                           f"{cleanup_queue['completed']} completed")
            
            # Symlinks progress
            completion_rate = symlink_stats['queue']['completion_rate']
            if completion_rate < 100:
                logger.info(f"🔗 Symlinks: {completion_rate:.1f}% traités, "
                           f"{symlink_stats['queue']['symlinks_in_batch']} en attente")
            
        except Exception as e:
            logger.error(f"Erreur affichage stats runtime: {e}")
    
    async def _record_metrics(self):
        """Enregistre les métriques pour monitoring"""
        try:
            test_stats = await self.test_processor.get_processing_stats()
            rate_stats = self.rate_limiter.get_stats_summary()
            
            # Métriques principales
            self.metrics.log_metric('test', 'tests_performed', test_stats['test_stats']['tests_performed'])
            self.metrics.log_metric('test', 'infringing_detected', test_stats['test_stats']['infringing_detected'])
            self.metrics.log_metric('test', 'tests_per_hour', test_stats['avg_tests_per_hour'])
            self.metrics.log_metric('test', 'infringing_rate', test_stats['infringing_rate'])
            
            self.metrics.log_metric('cleanup', 'pending', test_stats['cleanup_queue']['pending'])
            self.metrics.log_metric('cleanup', 'completed', test_stats['cleanup_queue']['completed'])
            
            self.metrics.log_metric('api', 'utilization_rate', rate_stats['utilization_rate'])
            self.metrics.log_metric('api', 'calls_total', rate_stats['current_usage']['total'])
            
        except Exception as e:
            logger.error(f"Erreur enregistrement métriques: {e}")
    
    async def _cancel_all_tasks(self):
        """Annule toutes les tâches en cours"""
        logger.info("🛑 Arrêt des threads en cours...")
        
        for task in self.tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        logger.info("✅ Tous les threads arrêtés")
    
    async def run_single_cycle(self) -> bool:
        """Exécute un cycle unique de test (mode debug)"""
        logger.info("🧪 Mode cycle unique (debug)")
        
        try:
            # Obtenir quelques symlinks pour test
            symlinks_batch = await self.symlink_manager.get_next_symlink_batch(5)
            
            if not symlinks_batch:
                logger.info("Aucun symlink à tester")
                return True
            
            logger.info(f"Test de {len(symlinks_batch)} symlinks...")
            
            success_count = 0
            infringing_count = 0
            
            for symlink in symlinks_batch:
                result = await self.test_processor.test_single_symlink(symlink)
                
                if result.success:
                    success_count += 1
                    logger.info(f"✅ {result.filename[:50]}... - OK")
                else:
                    if result.error_type == 'infringing_file':
                        infringing_count += 1
                        logger.warning(f"🚫 {result.filename[:50]}... - INFRINGING")
                    else:
                        logger.error(f"❌ {result.filename[:50]}... - {result.error_type}")
            
            logger.info(f"📊 Résultats: {success_count} OK, {infringing_count} infringing, "
                       f"{len(symlinks_batch) - success_count - infringing_count} autres erreurs")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur cycle unique: {e}")
            return False
    
    async def shutdown(self):
        """Arrêt propre de l'application"""
        logger.info("🛑 Arrêt en cours...")
        
        self.is_running = False
        
        try:
            # Arrêter les threads
            await self._cancel_all_tasks()
            
            # Sauvegarder l'état final
            if self.test_processor:
                final_stats = await self.test_processor.get_processing_stats()
                self.metrics.log_event('shutdown', {
                    'total_runtime_hours': final_stats['runtime_hours'],
                    'total_tests': final_stats['test_stats']['tests_performed'],
                    'total_infringing': final_stats['test_stats']['infringing_detected'],
                    'total_cleanups': final_stats['test_stats']['cleanups_completed']
                })
                
                logger.info("✅ État final sauvegardé")
            
            # Fermeture base de données
            database = get_database()
            database.close()
            logger.info("✅ Base de données fermée")
            
        except Exception as e:
            logger.error(f"Erreur lors de l'arrêt: {e}")
        
        logger.info("✅ Arrêt terminé")

async def main():
    """Point d'entrée principal asynchrone"""
    manager = None
    
    try:
        # Initialiser le gestionnaire
        manager = DualThreadRDManager()
        
        # Vérifications de démarrage
        if not manager.startup_checks():
            sys.exit(1)
        
        # Initialiser les composants asynchrones
        if not await manager.initialize_components():
            sys.exit(1)
        
        # Configuration interactive
        if not manager.interactive_setup():
            sys.exit(1)
        
        # Déterminer le mode d'exécution
        if len(sys.argv) > 1:
            mode_arg = sys.argv[1].lower()
            if mode_arg == '--single':
                # Mode cycle unique (pour tests)
                success = await manager.run_single_cycle()
                sys.exit(0 if success else 1)
            elif mode_arg == '--help':
                print("Usage: python main_dual_thread.py [--single|--help]")
                print("  --single  : Exécute un cycle de test puis s'arrête")
                print("  (défaut)  : Mode continu dual-thread")
                sys.exit(0)
        
        # Mode dual-thread par défaut
        await manager.run_dual_thread_processing()
        
    except KeyboardInterrupt:
        logger.info("🛑 Interruption utilisateur")
        if manager:
            await manager.shutdown()
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"❌ Erreur fatale: {e}")
        if manager:
            await manager.shutdown()
        sys.exit(1)

def run_main():
    """Point d'entrée synchrone pour compatibility"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Interruption finale")
        sys.exit(0)

if __name__ == "__main__":
    run_main()