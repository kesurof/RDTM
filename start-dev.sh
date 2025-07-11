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
