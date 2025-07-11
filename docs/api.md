# Documentation API RDTM

## Authentification

### POST /api/auth/login
Authentification utilisateur

**Request:**

{
"username": "string",
"password": "string"
}


**Response:**

{
"access_token": "string",
"token_type": "bearer",
"expires_in": 3600
}


## Gestion des Torrents

### GET /api/torrents/
Liste tous les torrents

**Headers:**
- `Authorization: Bearer {token}`

**Response:**

{
"torrents": [
{
"id": "string",
"name": "string",
"status": "downloading|completed|error",
"progress": 75.5,
"size": 1073741824,
"created_at": "2025-07-11T16:27:00Z"
}
]
}


### POST /api/torrents/
Ajouter un nouveau torrent

**Request:**

{
"magnet_link": "magnet:?xt=urn:btih:...",
"priority": "normal|high|low"
}


### GET /api/torrents/{id}
Détails d'un torrent spécifique

### DELETE /api/torrents/{id}
Supprimer un torrent

## Téléchargements

### GET /api/downloads/
Liste des téléchargements actifs

### GET /api/downloads/{id}/stream
Stream direct d'un fichier

## Statistiques

### GET /api/stats/
Statistiques globales du système

**Response:**

{
"total_downloads": 150,
"active_downloads": 5,
"total_size": 107374182400,
"api_quota_remaining": 85
}

undefined
