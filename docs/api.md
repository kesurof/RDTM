# RDTM API Documentation

## Endpoints

### POST /api/torrents/add
Ajouter un torrent à la queue de téléchargement.

**Request Body:**
{
"magnet_link": "magnet:?xt=urn:btih:...",
"name": "Nom du torrent (optionnel)"
}
**Response:**
{
"success": true,
"job_id": "uuid-du-job",
"message": "Torrent ajouté à la queue"
}

### GET /api/torrents/status
Obtenir le statut de la queue des torrents.

**Response:**
{
"queued": 5,
"active": 2,
"max_concurrent": 10,
"jobs": [
{
"id": "job-uuid",
"name": "Nom du torrent",
"status": "downloading",
"progress": 45.5,
"created_at": "2025-07-11T16:13:00Z"
}
]
}

### DELETE /api/torrents/{job_id}
Annuler un torrent en cours ou en queue.

**Response:**

{
"success": true,
"message": "Torrent annulé"
}
undefined