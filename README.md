# RDTM - Real-Debrid Torrent Manager

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Security](https://img.shields.io/badge/security-policy-green.svg)](SECURITY.md)

RDTM est un gestionnaire de torrents moderne pour Real-Debrid, offrant une interface web intuitive et des fonctionnalités avancées de monitoring.

## 🚀 Fonctionnalités

- **Interface Web Moderne** : Interface Svelte responsive et intuitive
- **Intégration Real-Debrid** : Gestion complète des téléchargements
- **Monitoring Avancé** : Métriques Prometheus et dashboards Grafana
- **API REST** : API complète pour l'intégration
- **Déploiement Docker** : Containerisation complète
- **Sécurité Renforcée** : Chiffrement et authentification

## 📋 Prérequis

- Docker 20.10+
- Docker Compose 2.0+
- Compte Real-Debrid actif
- 2GB RAM minimum
- 10GB espace disque

## 🛠️ Installation

### Installation Rapide

Cloner le repository
git clone https://github.com/kesurof/RDTM.git
cd RDTM

Générer les secrets
python3 scripts/generate_secrets.py > .env.local

Configurer l'environnement
cp .env.template .env

Éditer .env avec vos paramètres
Démarrer les services
docker-compose up -d


### Configuration Détaillée

1. **Variables d'Environnement**

Copier le template
cp .env.template .env

Configurer les variables obligatoires
REAL_DEBRID_API_KEY=votre_cle_api
DB_PASSWORD=mot_de_passe_securise
SECRET_KEY=cle_secrete_generee


2. **Base de Données**

Initialiser la base de données
docker-compose exec backend python manage.py migrate

Créer un utilisateur admin
docker-compose exec backend python manage.py createsuperuser


3. **Accès aux Services**
- **Application Web** : http://localhost:8000
- **API** : http://localhost:8000/api/
- **Grafana** : http://localhost:3000 (admin/password_configuré)
- **Prometheus** : http://localhost:9090

## 📖 Utilisation

### Interface Web

1. Connectez-vous à http://localhost:8000
2. Configurez votre clé API Real-Debrid
3. Ajoutez des torrents via l'interface
4. Surveillez les téléchargements en temps réel

### API REST

Authentification
curl -X POST http://localhost:8000/api/auth/login
-H "Content-Type: application/json"
-d '{"username": "admin", "password": "password"}'

Ajouter un torrent
curl -X POST http://localhost:8000/api/torrents/
-H "Authorization: Bearer YOUR_TOKEN"
-H "Content-Type: application/json"
-d '{"magnet_link": "magnet:?xt=..."}'

Lister les téléchargements
curl -X GET http://localhost:8000/api/downloads/
-H "Authorization: Bearer YOUR_TOKEN"


## 🔧 Développement

### Configuration de Développement

Installer les dépendances
pip install -r requirements-dev.txt
npm install

Variables d'environnement de développement
export APP_ENV=development
export APP_DEBUG=true

Démarrer en mode développement
docker-compose -f docker-compose.dev.yml up


### Tests

Tests backend
docker-compose exec backend pytest

Tests frontend
docker-compose exec frontend npm test

Tests d'intégration
docker-compose exec backend pytest tests/integration/

Couverture de code
docker-compose exec backend pytest --cov=app tests/


### Contribution

1. Fork le projet
2. Créez une branche feature (`git checkout -b feature/nouvelle-fonctionnalite`)
3. Commitez vos changements (`git commit -am 'Ajout nouvelle fonctionnalité'`)
4. Pushez la branche (`git push origin feature/nouvelle-fonctionnalite`)
5. Ouvrez une Pull Request

Consultez [CONTRIBUTING.md](CONTRIBUTING.md) pour plus de détails.

## 📊 Monitoring

### Métriques Disponibles

- **Performance Application** : Temps de réponse, throughput
- **Real-Debrid API** : Latence, taux d'erreur, quotas
- **Système** : CPU, mémoire, disque, réseau
- **Base de Données** : Connexions, requêtes, performance

### Dashboards Grafana

- **Vue d'Ensemble** : Métriques système et application
- **Real-Debrid** : Monitoring API et téléchargements
- **Performance** : Analyse détaillée des performances
- **Alertes** : Surveillance proactive des incidents

## 🔒 Sécurité

- Consultez [SECURITY.md](SECURITY.md) pour la politique de sécurité
- Utilisez toujours HTTPS en production
- Changez les mots de passe par défaut
- Maintenez les dépendances à jour

## 📝 Licence

Ce projet est sous licence MIT. Voir [LICENSE](LICENSE) pour plus de détails.

## 🆘 Support

- **Documentation** : [docs/](docs/)
- **Issues** : [GitHub Issues](https://github.com/kesurof/RDTM/issues)
- **Discussions** : [GitHub Discussions](https://github.com/kesurof/RDTM/discussions)
- **Email** : support@rdtm-project.com

## 🙏 Remerciements

- [Real-Debrid](https://real-debrid.com/) pour leur API
- La communauté open source pour les outils utilisés
- Tous les contributeurs du projet

