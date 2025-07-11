#!/bin/bash

set -e  # Exit on error

echo "🚀 Installation complète RDTM"

# Nettoyer si existe
rm -rf backend frontend .env.example .gitignore

# Structure
mkdir -p {backend/app/{api,core,db,services},frontend/src/{routes/{torrents,symlinks,logs},lib},frontend/static,.github/workflows,.devcontainer}

echo "📁 Structure créée"

# Backend pyproject.toml
cat > backend/pyproject.toml << 'EOF'
[tool.poetry]
name = "rdtm-backend"
version = "1.0.0"
description = "RDTM API"
authors = ["RDTM"]
package-mode = false

[tool.poetry.dependencies]
python = "^3.11"
fastapi = "^0.104.0"
uvicorn = {extras = ["standard"], version = "^0.24.0"}
sqlalchemy = "^2.0.0"
pydantic = "^2.5.0"
pydantic-settings = "^2.1.0"
requests = "^2.31.0"
apscheduler = "^3.10.0"
websockets = "^12.0"
aiofiles = "^23.2.0"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
EOF

# Frontend package.json
cat > frontend/package.json << 'EOF'
{
  "name": "rdtm-frontend", 
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite dev",
    "build": "vite build"
  },
  "devDependencies": {
    "@sveltejs/adapter-static": "^3.0.0",
    "@sveltejs/kit": "^2.0.0", 
    "@sveltejs/vite-plugin-svelte": "^3.0.0",
    "svelte": "^4.2.0",
    "vite": "^5.0.0"
  },
  "dependencies": {
    "lucide-svelte": "^0.294.0"
  }
}
EOF

# Frontend vite.config.js
cat > frontend/vite.config.js << 'EOF'
import { sveltekit } from '@sveltejs/kit/vite';
export default {
  plugins: [sveltekit()],
  server: { host: true, port: 5173 }
};
EOF

# Frontend svelte.config.js
cat > frontend/svelte.config.js << 'EOF'
import adapter from '@sveltejs/adapter-static';
export default {
  kit: {
    adapter: adapter({ pages: 'build', assets: 'build' })
  }
};
EOF

# .env.example
cat > .env.example << 'EOF'
RD_API_TOKEN=your_api_token_here
LOG_LEVEL=INFO
MEDIA_PATH=/workspaces/rdtm/medias
SCAN_INTERVAL_MINUTES=10
EOF

# .gitignore
cat > .gitignore << 'EOF'
__pycache__/
*.pyc
.venv/
.env
node_modules/
/frontend/build/
/frontend/.svelte-kit/
*.db
*.log
logs/
data/
EOF

# Créer fichiers vides
touch backend/main.py
touch backend/app/{__init__.py,api/{__init__.py,routes.py},core/{__init__.py,config.py,scheduler.py,websocket.py},db/{__init__.py,database.py,models.py},services/{__init__.py,torrent_service.py,symlink_service.py}}
touch frontend/src/{app.html,lib/{api.js,websocket.js},routes/{+layout.svelte,+page.svelte,torrents/+page.svelte,symlinks/+page.svelte,logs/+page.svelte}}
touch {Dockerfile,docker-compose.yml,README.md}

# Installer Poetry si absent
if ! command -v poetry &> /dev/null; then
    echo "📦 Installation Poetry..."
    curl -sSL https://install.python-poetry.org | python3 -
    export PATH="$HOME/.local/bin:$PATH"
fi

# Backend
echo "🐍 Installation backend..."
cd backend
export PATH="$HOME/.local/bin:$PATH"
poetry install --no-root
cd ..

# Frontend
echo "🎨 Installation frontend..."
cd frontend
npm install
cd ..

# Script de démarrage
cat > start-dev.sh << 'EOF'
#!/bin/bash
if [ ! -f .env ]; then
    echo "❌ Créez .env depuis .env.example"
    exit 1
fi

export PATH="$HOME/.local/bin:$PATH"

echo "🚀 Démarrage RDTM"
echo "Backend: https://$CODESPACE_NAME-8000.preview.app.github.dev"
echo "Frontend: https://$CODESPACE_NAME-5173.preview.app.github.dev"

cd backend && poetry run uvicorn main:app --reload --host 0.0.0.0 &
cd frontend && npm run dev -- --host 0.0.0.0 &

wait
EOF

chmod +x start-dev.sh

echo "✅ Installation terminée!"
echo "Prochaines étapes:"
echo "1. Copier le contenu des artifacts dans les fichiers"
echo "2. cp .env.example .env et configurer RD_API_TOKEN"
echo "3. ./start-dev.sh"