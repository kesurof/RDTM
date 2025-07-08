#!/usr/bin/env python3

import os
import time
import logging
from pathlib import Path
from typing import Dict, List
from torrent_manager import TorrentManager
from config import CURRENT_USER

# Configuration du logging simple pour ce script
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SymlinksScanner:
    """Scanner avancé de liens symboliques avec interface interactive"""
    
    def __init__(self, base_path: str = None):
        self.base_path = base_path or f"/home/{CURRENT_USER}/Medias"
        self.stats = {
            'total_scanned': 0,
            'total_broken': 0,
            'torrents_detected': 0,
            'scan_duration': 0
        }
    
    def print_banner(self):
        """Bannière de démarrage"""
        print("\n" + "="*70)
        print("🔗 RDTM - Scanner Avancé de Liens Symboliques")
        print("="*70)
        print("Détection intelligente des torrents en échec via liens cassés")
        print("Intégration automatique dans le workflow RDTM")
        print("="*70)
    
    def count_symlinks_by_directory(self) -> Dict[str, int]:
        """Compte les liens symboliques par répertoire"""
        print(f"\n📊 Analyse des répertoires dans: {self.base_path}")
        directory_counts = {}
        
        if not os.path.exists(self.base_path):
            print(f"❌ Répertoire inexistant: {self.base_path}")
            return {}
        
        print("🔍 Comptage des liens symboliques...")
        for item in os.listdir(self.base_path):
            item_path = os.path.join(self.base_path, item)
            if os.path.isdir(item_path) and not item.startswith('.'):
                link_count = 0
                try:
                    for root, dirs, files in os.walk(item_path):
                        for name in files:
                            full_path = os.path.join(root, name)
                            if os.path.islink(full_path):
                                link_count += 1
                except Exception as e:
                    logger.warning(f"Erreur dans {item}: {e}")
                    link_count = -1
                
                directory_counts[item] = link_count
                
                # Affichage progression
                status = self._get_status_emoji(link_count)
                print(f"  📁 {item:<35} {status}")
        
        return directory_counts
    
    def _get_status_emoji(self, count: int) -> str:
        """Retourne le statut avec emoji selon le nombre de liens"""
        if count == -1:
            return "❌ Erreur"
        elif count == 0:
            return "⚪ Aucun lien"
        elif count < 100:
            return f"🟢 {count:,} liens"
        elif count < 1000:
            return f"🟡 {count:,} liens"
        else:
            return f"🔴 {count:,} liens"
    
    def display_directory_selection(self, directory_counts: Dict[str, int]) -> List[str]:
        """Affiche l'interface de sélection avancée"""
        if not directory_counts:
            return []
        
        print("\n" + "="*70)
        print("📊 RÉPERTOIRES DISPONIBLES")
        print("-" * 70)
        
        sorted_dirs = sorted(directory_counts.items(), key=lambda x: x[1], reverse=True)
        total_links = sum(count for count in directory_counts.values() if count > 0)
        
        # Affichage numéroté avec statistiques
        for i, (dirname, count) in enumerate(sorted_dirs, 1):
            status = self._get_status_emoji(count)
            print(f"{i:2d}. {dirname:<30} {status}")
        
        print("-" * 70)
        print(f"📈 TOTAL: {total_links:,} liens symboliques dans {len([c for c in directory_counts.values() if c > 0])} répertoires")
        
        # Options avancées
        print(f"\n🎯 OPTIONS DE SÉLECTION:")
        print("  'all' ou 'a'     → Scanner tous les répertoires")
        print("  '1,3,5'          → Scanner les répertoires 1, 3 et 5")
        print("  '1-5'            → Scanner les répertoires 1 à 5")
        print("  'big'            → Gros répertoires seulement (>1000 liens)")
        print("  'medium'         → Répertoires moyens (100-1000 liens)")
        print("  'small'          → Petits répertoires (<100 liens)")
        print("  'problematic'    → Répertoires avec erreurs")
        print("  'exit' ou 'q'    → Annuler")
        
        return self._get_user_selection(sorted_dirs)
    
    def _get_user_selection(self, sorted_dirs: List) -> List[str]:
        """Gère la sélection utilisateur avec syntaxe avancée"""
        while True:
            try:
                choice = input(f"\n👉 Votre sélection: ").strip().lower()
                
                if choice in ['exit', 'q', '']:
                    print("❌ Scan annulé par l'utilisateur")
                    return []
                
                if choice in ['all', 'a']:
                    selected_dirs = [dirname for dirname, count in sorted_dirs if count > 0]
                    break
                
                elif choice == 'big':
                    selected_dirs = [dirname for dirname, count in sorted_dirs if count > 1000]
                    break
                
                elif choice == 'medium':
                    selected_dirs = [dirname for dirname, count in sorted_dirs if 100 <= count <= 1000]
                    break
                
                elif choice == 'small':
                    selected_dirs = [dirname for dirname, count in sorted_dirs if 0 < count < 100]
                    break
                
                elif choice == 'problematic':
                    selected_dirs = [dirname for dirname, count in sorted_dirs if count == -1]
                    break
                
                elif '-' in choice:
                    start, end = map(int, choice.split('-'))
                    selected_indices = list(range(start-1, min(end, len(sorted_dirs))))
                    selected_dirs = [sorted_dirs[i][0] for i in selected_indices if sorted_dirs[i][1] > 0]
                    break
                
                elif ',' in choice:
                    indices = [int(x.strip()) - 1 for x in choice.split(',')]
                    selected_dirs = []
                    for idx in indices:
                        if 0 <= idx < len(sorted_dirs) and sorted_dirs[idx][1] > 0:
                            selected_dirs.append(sorted_dirs[idx][0])
                    break
                
                elif choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(sorted_dirs) and sorted_dirs[idx][1] > 0:
                        selected_dirs = [sorted_dirs[idx][0]]
                        break
                    else:
                        raise ValueError("Numéro invalide")
                
                else:
                    raise ValueError("Format non reconnu")
                    
            except (ValueError, IndexError):
                print("❌ Choix invalide. Formats acceptés:")
                print("   • Numéros: 1, 5, 12")
                print("   • Plages: 1-5, 3-8") 
                print("   • Listes: 1,3,5,7")
                print("   • Mots-clés: all, big, medium, small")
                continue
        
        if not selected_dirs:
            print("❌ Aucun répertoire valide sélectionné")
            return []
        
        # Affichage de la sélection
        total_selected_links = sum(
            count for dirname, count in sorted_dirs 
            if dirname in selected_dirs and count > 0
        )
        
        print(f"\n✅ SÉLECTION CONFIRMÉE ({len(selected_dirs)} répertoires):")
        for dirname in selected_dirs:
            count = next(count for name, count in sorted_dirs if name == dirname)
            status = self._get_status_emoji(count)
            print(f"   📁 {dirname:<30} {status}")
        
        print(f"\n📊 TOTAL À SCANNER: {total_selected_links:,} liens symboliques")
        
        # Estimation du temps
        estimated_minutes = max(1, total_selected_links // 1000)  # ~1000 liens/minute
        time_str = f"~{estimated_minutes}min" if estimated_minutes < 60 else f"~{estimated_minutes//60}h{estimated_minutes%60}min"
        print(f"⏱️  TEMPS ESTIMÉ: {time_str}")
        
        return selected_dirs
    
    def run_scan(self, selected_dirs: List[str]):
        """Exécute le scan sur les répertoires sélectionnés"""
        if not selected_dirs:
            return
        
        print(f"\n🚀 DÉMARRAGE DU SCAN")
        print("="*50)
        
        start_time = time.time()
        tm = TorrentManager(dry_run=False)
        
        # Construire les chemins complets
        selected_paths = [os.path.join(self.base_path, dirname) for dirname in selected_dirs]
        
        if len(selected_dirs) == 1:
            # Scan d'un seul répertoire
            print(f"🔍 Scan de: {selected_dirs[0]}")
            success, results = tm._scan_torrents_symlinks(selected_paths[0])
            
            # Enregistrer le scan manuel
            if success:
                tm.database.update_scan_progress('symlinks', status='completed')
        else:
            # Scan multiple -> utiliser le scan complet
            print(f"🔍 Scan de {len(selected_dirs)} répertoires")
            success, results = tm.scan_torrents(scan_mode='symlinks')
            # Le scan complet enregistre déjà automatiquement
            
            # Filtrer les résultats pour les répertoires sélectionnés
            if success and 'broken_by_directory' in results:
                filtered_broken = {k: v for k, v in results['broken_by_directory'].items() 
                                 if k in selected_dirs}
                results['broken_by_directory'] = filtered_broken
        
        scan_duration = time.time() - start_time
        
        # Affichage des résultats
        self._display_results(success, results, scan_duration, selected_dirs)
    
    def _display_results(self, success: bool, results: Dict, duration: float, selected_dirs: List[str]):
        """Affiche les résultats détaillés du scan"""
        print(f"\n{'='*70}")
        print("📊 RÉSULTATS DU SCAN")
        print("="*70)
        
        if not success:
            print(f"❌ ERREUR: {results}")
            return
        
        # Statistiques globales
        total_broken = results.get('total_broken_links', 0)
        torrents_found = results.get('matched_torrents', 0)
        match_rate = results.get('match_rate', 0)
        
        print(f"⏱️  DURÉE: {duration/60:.1f} minutes")
        print(f"🔗 LIENS CASSÉS TROUVÉS: {total_broken:,}")
        print(f"🎯 TORRENTS DÉTECTÉS: {torrents_found:,}")
        print(f"📈 TAUX DE CORRESPONDANCE: {match_rate:.1f}%")
        
        # Détail par répertoire
        if 'broken_by_directory' in results and results['broken_by_directory']:
            print(f"\n📁 DÉTAIL PAR RÉPERTOIRE:")
            print("-" * 50)
            for repo, count in results['broken_by_directory'].items():
                if repo in selected_dirs:
                    percentage = (count / total_broken * 100) if total_broken > 0 else 0
                    print(f"  {repo:<30} {count:>6,} liens ({percentage:>5.1f}%)")
        
        # Actions entreprises
        if torrents_found > 0:
            print(f"\n✅ ACTIONS AUTOMATIQUES:")
            print(f"  • {torrents_found} torrents marqués 'symlink_broken'")
            print(f"  • Priorité HAUTE attribuée")
            print(f"  • Intégration dans le workflow de réinjection")
            print(f"  • Traitement au prochain cycle RDTM (~10 min)")
            
            print(f"\n🔄 WORKFLOW AUTOMATIQUE:")
            print(f"  1. Réinjection → Détection 'infringing_file'")
            print(f"  2. Suppression automatique des liens cassés")
            print(f"  3. Scan Sonarr/Radarr pour nouvelle recherche")
            print(f"  4. Archivage définitif")
        else:
            print(f"\nℹ️  AUCUN NOUVEAU TORRENT À TRAITER")
            if total_broken > 0:
                print(f"   Les {total_broken} liens cassés détectés ne correspondent")
                print(f"   à aucun torrent Real-Debrid actuel")
        
        # Statistiques techniques
        if results.get('scan_duration'):
            api_duration = results['scan_duration']
            print(f"\n🔧 DÉTAILS TECHNIQUES:")
            print(f"  • Scan API Real-Debrid: {api_duration:.1f}s")
            print(f"  • Correspondance symlinks: {duration-api_duration:.1f}s")
            print(f"  • Répertoires traités: {len(selected_dirs)}")
        
        # Recommandations
        print(f"\n💡 RECOMMANDATIONS:")
        if torrents_found > 0:
            print(f"  • Surveiller les logs RDTM pour le traitement automatique")
            print(f"  • Vérifier Sonarr/Radarr dans ~30 minutes")
        print(f"  • Relancer ce scan après nettoyage pour validation")
        print(f"  • Programmer scan automatique toutes les 24h (déjà actif)")
    
    def run_interactive(self):
        """Lance le scanner en mode interactif"""
        try:
            self.print_banner()
            
            # Étape 1: Comptage
            directory_counts = self.count_symlinks_by_directory()
            if not directory_counts:
                return
            
            # Étape 2: Sélection
            selected_dirs = self.display_directory_selection(directory_counts)
            if not selected_dirs:
                return
            
            # Étape 3: Confirmation
            print(f"\n⚠️  CONFIRMATION")
            print("Ce scan va:")
            print("• Analyser les liens symboliques cassés")
            print("• Détecter les torrents Real-Debrid correspondants") 
            print("• Les marquer pour réinjection automatique")
            print("• Déclencher le workflow de nettoyage automatique")
            
            confirm = input("\n👉 Continuer? (y/N): ").strip().lower()
            if confirm not in ['y', 'yes', 'o', 'oui']:
                print("❌ Scan annulé")
                return
            
            # Étape 4: Scan
            self.run_scan(selected_dirs)
            
        except KeyboardInterrupt:
            print("\n\n❌ Scan interrompu par l'utilisateur")
        except Exception as e:
            print(f"\n❌ Erreur inattendue: {e}")
            logger.error(f"Erreur scanner: {e}")

def main():
    """Point d'entrée principal"""
    scanner = SymlinksScanner()
    scanner.run_interactive()

if __name__ == '__main__':
    main()