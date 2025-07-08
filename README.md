# Real-Debrid Torrent Manager

🚀 **Gestionnaire automatique de torrents Real-Debrid** avec détection et réinjection intelligente des torrents en échec.

## 🎯 Fonctionnalités

### ✨ Core Features
- **Détection automatique** des torrents en échec (`magnet_error`, `error`, `virus`, `dead`)
- **Réinjection intelligente** via reconstruction de magnet links
- **Rate limiting adaptatif** pour respecter les limites API Real-Debrid
- **Retry logic** avec délai configurable (3h par défaut)
- **Historique complet** avec rotation automatique (30 jours)
- **Mode dry-run** pour tests sécurisés

### 🛡️ Robustesse
- **Validation stricte** des hashes SHA1 et magnet links
- **Gestion d'erreurs complète** avec retry automatique
- **Logging détaillé** (fichier + console + métriques JSON)
- **Arrêt propre** sur signaux système
- **Base SQLite** thread-safe avec sauvegarde automatique

### 📊 Monitoring
- **Métriques détaillées** pour futur dashboard web
- **Notifications Discord** pour échecs définitifs
- **Statistiques temps réel** (taux de succès, performances)
- **Priorisation des torrents** (taille, âge, statut)

## 🏗️ Architecture

```
real_debrid_manager/
├── config.py              # Configuration et constantes
├── database.py             # SQLite avec historique + métriques  
├── rd_client.py            # Client API + rate limiting adaptatif
├── torrent_manager.py      # Logique métier principale
├── torrent_validator.py    # Validation magnet links + sécurité
├── utils.py                # Logging, UI interactive, helpers
├── main.py                 # Orchestrateur principal
├── requirements.txt        # Dépendances Python
├── .env.example           # Template configuration
├── Dockerfile             # Configuration Docker
├── docker-compose.yml     # Stack complète
└── README.md              # Cette documentation
```

## ⚡ Installation Rapide

### 1. Prérequis
```bash
# Python 3.8+ requis
python3 --version

# Git pour cloner le repo
git --version
```

### 2. Installation
```bash
# Cloner le projet
git clone <repo-url>
cd real_debrid_manager

# Installer les dépendances
pip install -r requirements.txt

# Configuration
cp .env.example .env
nano .env  # Compléter RD_API_TOKEN
```

### 3. Configuration minimale
```bash
# Dans .env - OBLIGATOIRE
RD_API_TOKEN=your_real_debrid_api_token

# Optionnel
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
LOG_LEVEL=INFO
DRY_RUN=true
```

### 4. Premier lancement
```bash
# Mode test (cycle unique)
python main.py --single

# Mode continu avec interface interactive
python main.py
```

## 🐋 Déploiement Docker

### Docker Compose (recommandé)
```bash
# Préparer l'environnement
cp .env.example .env
nano .env  # Configurer RD_API_TOKEN

# Lancer le service
docker-compose up -d

# Vérifier les logs
docker-compose logs -f rd-manager

# Arrêter le service
docker-compose down
```

### Docker manuel
```bash
# Build
docker build -t rd-manager .

# Run
docker run -d \
  --name rd-manager \
  --restart unless-stopped \
  -e RD_API_TOKEN=your_token \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  rd-manager
```

## 🎛️ Utilisation

### Interface Interactive
L'application démarre avec une interface inspirée de votre script `advanced_symlink_checker.py` :

```
🚀 Real-Debrid Torrent Manager
===============================================
🔧 MODE D'EXÉCUTION
1) DRY-RUN  → Analyse sans action + logs détaillés  
2) RÉEL     → Analyse et réinjection automatique

👉 Votre choix (1-2): 
```

### Modes d'exécution

**Mode DRY-RUN** (sécurisé)
- Analyse tous les torrents
- Détecte les échecs et simule les réinjections
- Logs détaillés sans modifications
- Parfait pour tests et validation

**Mode RÉEL** (production)
- Analyse et réinjection automatique
- Rate limiting adaptatif
- Retry logic avec délais
- Notifications Discord

### Ligne de commande
```bash
# Cycle unique (test)
python main.py --single

# Mode continu (production)
python main.py

# Aide
python main.py --help
```

## ⚙️ Configuration Détaillée

### Variables d'environnement
| Variable | Défaut | Description |
|----------|--------|-------------|
| `RD_API_TOKEN` | *(requis)* | Token API Real-Debrid |
| `DISCORD_WEBHOOK_URL` | *(optionnel)* | Webhook pour notifications |
| `LOG_LEVEL` | `INFO` | Niveau de logging |
| `SCAN_INTERVAL` | `600` | Intervalle entre scans (secondes) |
| `DRY_RUN` | `true` | Mode dry-run par défaut |
| `MAX_WORKERS` | `4` | Workers parallèles |
| `MAX_RETRY_ATTEMPTS` | `3` | Tentatives max par torrent |
| `RETRY_DELAY_HOURS` | `3` | Délai entre tentatives |

### Statuts de torrents traités
- `magnet_error` : Erreur magnet link (priorité haute)
- `error` : Erreur générale
- `virus` : Détection virus
- `dead` : Torrent mort/inaccessible

### Priorisation automatique
- **Haute** : magnet_error, fichiers >1GB, récents (<24h)
- **Normale** : erreurs standard, taille moyenne
- **Basse** : petits fichiers (<100MB), anciens (>7j)

## 📊 Monitoring et Logs

### Structure des logs
```
logs/
├── rd_manager.log          # Logs applicatifs rotatifs
├── metrics.jsonl           # Métriques JSON pour dashboard
└── rd_manager.log.1        # Archives automatiques
```

### Métriques collectées
- Durée des scans et réinjections
- Taux de succès/échec
- Performance API (temps de réponse)
- Rate limiting (délais, ajustements)
- Statistiques par priorité

### Base de données
```
data/
├── rd_manager.db           # Base SQLite principale
└── rd_manager_backup_*.db  # Sauvegardes automatiques
```

Tables principales :
- `torrents` : Historique complet des torrents
- `attempts` : Tentatives de réinjection
- `metrics` : Métriques pour dashboard
- `config` : Configuration runtime

## 🔧 Maintenance

### Nettoyage automatique
- **Tentatives** : Suppression après 30 jours
- **Métriques** : Conservation 90 jours
- **Sauvegardes** : Création quotidienne
- **Cache validation** : Nettoyage périodique

### Commandes utiles
```bash
# Vérifier l'état Docker
docker-compose ps
docker-compose logs -f

# Accéder aux logs
tail -f logs/rd_manager.log

# Vérifier la base de données
sqlite3 data/rd_manager.db ".tables"

# Backup manuel
cp data/rd_manager.db data/backup_$(date +%Y%m%d).db
```

## 🔍 Dépannage

### Problèmes courants

**❌ Token API invalide**
```
ERROR - API GET user: 401 - Token API invalide ou expiré
```
→ Vérifier `RD_API_TOKEN` dans `.env`

**⚠️ Rate limit détecté**
```
WARNING - Rate limit détecté! Réduction à 1 torrents/cycle
```
→ Normal, l'application s'adapte automatiquement

**🔄 Aucun torrent à réinjecter**
```
INFO - Aucun torrent à réinjecter pour le moment
```
→ Tous les torrents fonctionnent ou sont en délai de retry

### Logs de débogage
```bash
# Activer debug
echo "LOG_LEVEL=DEBUG" >> .env
docker-compose restart rd-manager

# Suivre les logs détaillés
docker-compose logs -f rd-manager | grep DEBUG
```

### Validation manuelle
```bash
# Test connectivité API
python -c "from rd_client import RealDebridClient; print(RealDebridClient().test_connection())"

# Test base de données
python -c "from database import get_database; print(get_database().get_statistics())"

# Cycle unique avec debug
LOG_LEVEL=DEBUG python main.py --single
```

## 🚀 Évolutions Prévues

### Dashboard Web
- Interface monitoring temps réel
- Graphiques métriques historiques
- Configuration via interface
- Gestion manuelle des torrents

### Intégrations
- **Sonarr/Radarr** : Notification échecs + re-recherche
- **Webhook générique** : Intégration systèmes tiers
- **Telegram/Slack** : Notifications alternatives

### Optimisations
- **Parallélisation** : Réinjections simultanées
- **Cache intelligent** : Éviter re-scan torrents OK
- **Machine Learning** : Prédiction échecs torrents

## 🤝 Contribution

Architecture modulaire permettant extensions faciles :
- Nouveaux providers (Real-Debrid, AllDebrid, etc.)
- Validators personnalisés
- Stratégies de retry avancées
- Notifications multicanaux

## 📄 Licence

*(À définir selon vos préférences)*

---

**Inspiré par l'excellence du script `advanced_symlink_checker.py`** - Même philosophie de robustesse, logging détaillé et interface utilisateur claire ! 🎯