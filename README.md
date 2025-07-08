# Real-Debrid Torrent Manager (RDTM) - Documentation Complète

## 🎯 Vue d'ensemble

RDTM est un système intelligent de gestion automatique des torrents Real-Debrid qui détecte et traite automatiquement les échecs de téléchargement. Il combine trois approches de détection (API, scan complet, liens symboliques cassés) avec un traitement adaptatif selon le type d'erreur.

### ✨ Fonctionnalités principales

- **Détection hybride** : 3 modes de scan (quick/full/symlinks)
- **Traitement automatique des échecs** :
  - `infringing_file` → Suppression fichiers + scan Sonarr/Radarr
  - `too_many_requests` → Retry différé intelligent (+3h)
- **Rate limiting adaptatif** : Ajustement automatique selon les réponses API
- **Intégration média** : Notifications automatiques Sonarr/Radarr
- **Historique complet** : Base SQLite avec métriques et progression
- **Mode sécurisé** : DRY-RUN pour tests sans modification

---

## 🏗️ Architecture

```
real_debrid_manager/
├── config.py              # Configuration et constantes
├── database.py             # SQLite + historique + métriques
├── rd_client.py            # API Real-Debrid + rate limiting
├── torrent_validator.py    # Validation magnet links + sécurité
├── torrent_manager.py      # Logique métier principale
├── symlink_checker.py      # Détection liens cassés
├── failure_handler.py      # Gestion post-échec automatique
├── utils.py                # Logging + UI interactive + helpers
├── main.py                 # Orchestrateur principal
├── requirements.txt        # Dépendances Python
├── .env.example           # Template configuration
├── Dockerfile             # Configuration Docker
├── docker-compose.yml     # Stack complète
└── README.md              # Documentation basique
```

### 🗄️ Base de données SQLite

```sql
-- Torrents avec historique et statuts
torrents (id, hash, filename, status, size, added_date, attempts_count...)

-- Tentatives de réinjection avec métriques
attempts (torrent_id, attempt_date, success, error_message, response_time...)

-- Échecs permanents (infringing_file)
permanent_failures (torrent_id, error_type, processed, failure_date...)

-- Queue de retry différé (too_many_requests)
retry_queue (torrent_id, scheduled_retry, retry_count, error_type...)

-- Progression des scans
scan_progress (scan_type, current_offset, last_scan_complete...)

-- Métriques pour monitoring
metrics (timestamp, metric_type, metric_name, value, tags...)
```

---

## 🚀 Installation et Configuration

### Prérequis

```bash
# Système
- Linux (Ubuntu/Debian recommandé)
- Python 3.8+
- Git
- Docker (optionnel)

# Services média (optionnel)
- Sonarr/Radarr avec API activée
- Plex (support prévu)
```

### Installation rapide

```bash
# 1. Cloner le projet
git clone https://github.com/kesurof/RDTM.git
cd RDTM

# 2. Environnement Python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configuration
cp .env.example .env
nano .env
```

### Configuration minimale (.env)

```bash
# OBLIGATOIRE
RD_API_TOKEN=your_real_debrid_api_token

# OPTIONNEL
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
LOG_LEVEL=INFO
SCAN_INTERVAL=600
DRY_RUN=true
MAX_WORKERS=4
```

### Configuration avancée

```bash
# Rate limiting
API_RATE_LIMIT=1.0
MAX_RETRY_ATTEMPTS=3
RETRY_DELAY_HOURS=3

# Base de données
DB_BACKUP_INTERVAL=24
HISTORY_RETENTION_DAYS=30

# Monitoring
METRICS_RETENTION_DAYS=90
```

---

## 📚 Guide d'utilisation

### 🎮 Interface interactive

Au lancement, RDTM propose une interface inspirée d'`advanced_symlink_checker.py` :

```
🚀 Real-Debrid Torrent Manager
===============================================

🔧 MODE D'EXÉCUTION
1) DRY-RUN  → Analyse sans action + logs détaillés
2) RÉEL     → Analyse et réinjection automatique

👉 Votre choix (1-2):
```

### 📋 Commandes principales

#### Démarrage et test

```bash
# Test connectivité et configuration
python main.py --single
# → Choisir mode 1 (DRY-RUN) pour validation

# Mode production continu
python main.py
# → Choisir mode 2 (RÉEL) pour production

# Aide
python main.py --help
```

#### Sessions persistantes

```bash
# Créer session screen
screen -S rdtm-production
python main.py
# → Choisir le mode
# → Ctrl+A puis D pour détacher

# Reconnecter à la session
screen -r rdtm-production

# Lister les sessions
screen -ls

# Arrêter le service
screen -r rdtm-production
# → Ctrl+C dans la session
```

#### Monitoring et logs

```bash
# Suivre les logs en temps réel
tail -f logs/rd_manager.log

# Voir les métriques JSON
tail -f logs/metrics.jsonl

# Statistiques base de données
python -c "
from database import get_database
db = get_database()
stats = db.get_statistics()
print(stats)
"
```

### 🔧 Commandes avancées

#### Force refresh complet

```bash
# Forcer nouveau scan depuis le début
python -c "
from torrent_manager import TorrentManager
tm = TorrentManager()
success = tm.force_full_rescan()
print(f'Reset: {\"✅\" if success else \"❌\"}')
"
```

#### État du système

```bash
# Vérifier progression scan
python -c "
from database import get_database
db = get_database()
progress = db.get_scan_progress('full')
print(f'Offset: {progress.get(\"current_offset\", 0)}')
print(f'Statut: {progress.get(\"status\", \"unknown\")}')
"

# Retries en attente
python -c "
from torrent_manager import TorrentManager
tm = TorrentManager()
retries = tm.get_pending_retries()
print(f'Retries: {len(retries)} en attente')
"
```

#### Test réinjection ciblée

```bash
# Test sur torrents symlink_broken seulement
python -c "
from torrent_manager import TorrentManager
import logging
logging.basicConfig(level=logging.INFO)
tm = TorrentManager(dry_run=True)
success, results = tm.reinject_failed_torrents(scan_type='symlinks', limit=5)
print(f'Test: {results.get(\"success\", 0)}/{results.get(\"processed\", 0)} réussis')
"
```

---

## 🔄 Workflow détaillé

### Cycle principal (toutes les 10 minutes)

```
1. 🔍 SCAN AUTOMATIQUE
   ├── Auto: Détermine quick/full selon dernière exécution
   ├── Quick: Scan API torrents en échec uniquement
   ├── Full: Pagination complète (5000 torrents/session)
   └── Symlinks: Détection liens cassés + mapping RD

2. 🎯 RÉINJECTION INTELLIGENTE
   ├── Sélection candidats (priorité + rate limiting)
   ├── Validation hash + construction magnet
   ├── Appel API Real-Debrid
   └── Enregistrement tentative

3. 🛠️ POST-TRAITEMENT AUTOMATIQUE
   ├── infringing_file:
   │   ├── Recherche fichiers correspondants
   │   ├── Suppression liens cassés
   │   ├── Scan Sonarr/Radarr
   │   └── Archivage (processed=1)
   └── too_many_requests:
       ├── Programmation retry +3h
       ├── Enregistrement queue
       └── Retry automatique différé

4. 🔄 RETRIES DIFFÉRÉS
   ├── Vérification queue retry
   ├── Traitement torrents prêts
   └── Gestion échecs répétés (max 3 tentatives)

5. 🧹 MAINTENANCE
   ├── Nettoyage anciennes données
   ├── Sauvegarde base SQLite
   ├── Rotation logs
   └── Métriques performance
```

### Modes de scan

| Mode | Fréquence | Description | Performance |
|------|-----------|-------------|-------------|
| **Quick** | Continue | API échecs uniquement | ~2s |
| **Full** | 24h | Pagination complète | ~30s |
| **Symlinks** | Manuel | Détection liens cassés | ~5min |

### Gestion des échecs

| Type d'erreur | Action | Délai | Retry |
|---------------|---------|-------|--------|
| `infringing_file` | Suppression + scan | Immédiat | Non |
| `too_many_requests` | Queue différée | 3h | Oui (3x) |
| `virus` | Suppression | Immédiat | Non |
| `magnet_error` | Reconstruction | 3h | Oui (3x) |
| `error` | Analyse | 3h | Oui (3x) |

---

## 📊 Monitoring et métriques

### Logs structurés

```bash
# Logs applicatifs
logs/rd_manager.log          # Rotation 10MB, 5 fichiers
logs/rd_manager.log.1        # Archives automatiques

# Métriques JSON
logs/metrics.jsonl           # Format JSONL pour dashboard
```

### Métriques collectées

```json
{
  "timestamp": "2025-01-08T18:46:51",
  "type": "scan",
  "name": "duration",
  "value": 8.2,
  "tags": {"mode": "full", "torrents": 5000}
}
```

### Dashboard monitoring (prévu)

- Graphiques temps réel
- Taux de succès/échec
- Performance API
- Historique scans
- Alertes automatiques

---

## 🐳 Déploiement Docker

### Docker Compose (recommandé)

```yaml
# docker-compose.yml
version: '3.8'
services:
  rdtm:
    build: .
    container_name: rdtm
    restart: unless-stopped
    environment:
      - RD_API_TOKEN=${RD_API_TOKEN}
      - DRY_RUN=false
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./.env:/app/.env:ro
```

```bash
# Déploiement
cp .env.example .env
nano .env  # Configurer RD_API_TOKEN
docker-compose up -d

# Monitoring
docker-compose logs -f rdtm
docker-compose exec rdtm python -c "from database import get_database; print(get_database().get_statistics())"
```

---

## 🔧 Maintenance

### Sauvegardes automatiques

```bash
# Sauvegarde quotidienne automatique
data/rd_manager_backup_YYYYMMDD_HHMMSS.db

# Sauvegarde manuelle
python -c "
from database import get_database
db = get_database()
success = db.backup_database()
print(f'Backup: {\"✅\" if success else \"❌\"}')
"
```

### Nettoyage périodique

```bash
# Nettoyage automatique (6h)
- Tentatives > 30 jours
- Métriques > 90 jours
- Cache validation
- Logs rotatifs

# Nettoyage manuel
python -c "
from database import get_database
db = get_database()
deleted = db.cleanup_old_data()
print(f'Nettoyé: {deleted[0]} tentatives, {deleted[1]} métriques')
"
```

### Optimisation performance

```bash
# VACUUM base de données
sqlite3 data/rd_manager.db "VACUUM;"

# Réindexation
sqlite3 data/rd_manager.db "REINDEX;"

# Statistiques SQLite
sqlite3 data/rd_manager.db ".dbinfo"
```

---

## 🚨 Dépannage

### Problèmes courants

#### Token API invalide
```
ERROR - API GET user: 401 - Token API invalide ou expiré
```
**Solution** : Vérifier `RD_API_TOKEN` dans `.env`

#### Rate limit permanent
```
WARNING - Rate limit détecté! Réduction à 1 torrents/cycle
```
**Solution** : Normal, le système s'adapte automatiquement

#### Base corrompue
```
ERROR - database disk image is malformed
```
**Solution** :
```bash
cp data/rd_manager.db data/rd_manager_broken.db
sqlite3 data/rd_manager_broken.db ".recover" | sqlite3 data/rd_manager.db
```

#### Interface bloquée en nohup
```
ERROR - ❌ Erreur fatale: [Errno 9] Bad file descriptor
```
**Solution** : Utiliser screen au lieu de nohup

### Logs de debug

```bash
# Activer debug
echo "LOG_LEVEL=DEBUG" >> .env

# Debug API spécifique
python -c "
import logging
logging.basicConfig(level=logging.DEBUG)
from rd_client import RealDebridClient
client = RealDebridClient()
success, data, error = client.get_user_info()
print(f'API: {success}, User: {data.get(\"username\") if data else \"N/A\"}')
"
```

### Validation manuelle

```bash
# Test connectivité complète
python -c "
from torrent_manager import TorrentManager
tm = TorrentManager()
success = tm.test_connectivity()
print(f'Connectivité: {\"✅\" if success else \"❌\"}')
"

# État détaillé
python -c "
from torrent_manager import TorrentManager
tm = TorrentManager()
stats = tm.get_manager_stats()
print(f'Mode: {stats[\"mode\"]}')
print(f'Scans: {stats[\"scans_completed\"]}')
print(f'Rate limit: {stats[\"rate_limiting\"][\"current_delay\"]}s')
"
```

---

## 🔮 Évolutions prévues

### 🌟 Roadmap immédiate

#### Dashboard Web (Q1 2025)
- Interface monitoring temps réel
- Graphiques métriques historiques
- Configuration via interface
- Gestion manuelle torrents
- Alertes visuelles

#### Intégrations étendues (Q2 2025)
- **Plex** : Scan refresh automatique
- **Webhook générique** : Intégration systèmes tiers
- **Telegram/Slack** : Notifications alternatives
- **API REST** : Contrôle externe

### 🚀 Évolutions avancées

#### Intelligence artificielle (Q3 2025)
- **Prédiction échecs** : ML sur patterns historiques
- **Optimisation timing** : IA pour meilleurs moments retry
- **Détection anomalies** : Alertes proactives
- **Auto-tuning** : Optimisation paramètres automatique

#### Fonctionnalités premium (Q4 2025)
- **Multi-providers** : Support AllDebrid, Premiumize
- **Clustering** : Déploiement multi-serveurs
- **Cache intelligent** : Évitement re-scan torrents OK
- **Backup cloud** : Synchronisation configuration

### 🛠️ Extensions techniques

#### Performance
```python
# Parallélisation réinjections
async def parallel_reinjections(torrents):
    tasks = [reinject_torrent(t) for t in torrents]
    return await asyncio.gather(*tasks)

# Cache Redis pour métriques
import redis
cache = redis.Redis()
cache.setex(f"torrent:{id}", 3600, json.dumps(data))
```

#### Monitoring avancé
```python
# Métriques Prometheus
from prometheus_client import Counter, Histogram
reinjection_counter = Counter('rdtm_reinjections_total')
scan_duration = Histogram('rdtm_scan_duration_seconds')

# Alerting automatique
if error_rate > 0.1:
    send_alert("RDTM error rate > 10%")
```

#### Sécurité renforcée
```python
# Chiffrement tokens
from cryptography.fernet import Fernet
key = Fernet.generate_key()
encrypted_token = Fernet(key).encrypt(token.encode())

# Rate limiting global
from ratelimit import limits
@limits(calls=100, period=3600)
def api_call():
    pass
```

### 💡 Idées d'amélioration

#### Architecture
- **Microservices** : Séparation scan/reinjection/monitoring
- **Message queue** : RabbitMQ pour jobs asynchrones
- **Event sourcing** : Historique complet des événements
- **CQRS** : Séparation lecture/écriture optimisée

#### Fonctionnalités
- **Profiles utilisateur** : Configurations personnalisées
- **Règles métier** : Conditions custom pour actions
- **Workflows visuels** : Éditeur graphique de règles
- **API GraphQL** : Interface moderne pour dashboard

#### DevOps
- **CI/CD automatisé** : Tests + déploiement continu
- **Infrastructure as Code** : Terraform pour cloud
- **Monitoring complet** : ELK stack + Grafana
- **Tests automatisés** : Coverage > 90%

---

## 📞 Support et communauté

### Documentation technique
- **Code source** : https://github.com/kesurof/RDTM
- **Issues** : GitHub Issues pour bugs/features
- **Wiki** : Documentation développeurs
- **API Reference** : Swagger/OpenAPI (prévu)

### Contribution
```bash
# Fork et clone
git clone https://github.com/your-fork/RDTM.git
cd RDTM

# Branche feature
git checkout -b feature/awesome-feature

# Tests
python -m pytest tests/
python -m flake8 --max-line-length=88

# Pull request
git push origin feature/awesome-feature
```

### Communauté
- **Discord** : Serveur communautaire (prévu)
- **Documentation** : Wiki collaboratif
- **Meetups** : Événements utilisateurs (prévu)

---

### Remerciements
- **Inspiration** : `advanced_symlink_checker.py` pour l'UI et l'approche
- **APIs** : Real-Debrid, Sonarr, Radarr pour les intégrations
- **Technologies** : Python, SQLite, Docker pour la stack technique

---

**🎉 RDTM v1.0 - Le gestionnaire intelligent de torrents Real-Debrid**
