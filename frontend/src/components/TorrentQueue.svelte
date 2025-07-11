<script>
    import { onMount, onDestroy } from 'svelte';
    import { writable } from 'svelte/store';
    
    let queueStatus = writable({
        queued: 0,
        active: 0,
        max_concurrent: 10,
        jobs: []
    });
    
    let interval;
    let newTorrentMagnet = '';
    let newTorrentName = '';
    
    onMount(() => {
        fetchQueueStatus();
        interval = setInterval(fetchQueueStatus, 5000);
    });
    
    onDestroy(() => {
        if (interval) clearInterval(interval);
    });
    
    async function fetchQueueStatus() {
        try {
            const response = await fetch('/api/torrents/status');
            const data = await response.json();
            queueStatus.set(data);
        } catch (error) {
            console.error('Erreur lors de la récupération du statut:', error);
        }
    }
    
    async function addTorrent() {
        if (!newTorrentMagnet.trim()) return;
        
        try {
            const response = await fetch('/api/torrents/add', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    magnet_link: newTorrentMagnet,
                    name: newTorrentName || null
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                newTorrentMagnet = '';
                newTorrentName = '';
                fetchQueueStatus();
            } else {
                alert('Erreur lors de l\'ajout du torrent');
            }
        } catch (error) {
            console.error('Erreur:', error);
            alert('Erreur lors de l\'ajout du torrent');
        }
    }
    
    function getStatusColor(status) {
        const colors = {
            'queued': 'bg-gray-500',
            'processing': 'bg-blue-500',
            'downloading': 'bg-green-500',
            'completed': 'bg-green-700',
            'failed': 'bg-red-500',
            'paused': 'bg-yellow-500'
        };
        return colors[status] || 'bg-gray-400';
    }
</script>

<div class="container mx-auto p-6">
    <h1 class="text-3xl font-bold mb-6">RDTM - Queue des Torrents</h1>
    
    <!-- Statistiques de la queue -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {#each $queueStatus as status}
            <div class="bg-white rounded-lg shadow p-4">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-sm font-medium text-gray-600">En queue</p>
                        <p class="text-2xl font-bold text-gray-900">{status.queued}</p>
                    </div>
                    <div class="text-blue-600">
                        <svg class="w-8 h-8" fill="currentColor" viewBox="0 0 20 20">
                            <path d="M3 4a1 1 0 011-1h12a1 1 0 011 1v2a1 1 0 01-1 1H4a1 1 0 01-1-1V4zM3 10a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H4a1 1 0 01-1-1v-6zM14 9a1 1 0 00-1 1v6a1 1 0 001 1h2a1 1 0 001-1v-6a1 1 0 00-1-1h-2z"/>
                        </svg>
                    </div>
                </div>
            </div>
            
            <div class="bg-white rounded-lg shadow p-4">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-sm font-medium text-gray-600">Actifs</p>
                        <p class="text-2xl font-bold text-gray-900">{status.active}</p>
                    </div>
                    <div class="text-green-600">
                        <svg class="w-8 h-8" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
                        </svg>
                    </div>
                </div>
            </div>
            
            <div class="bg-white rounded-lg shadow p-4">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-sm font-medium text-gray-600">Limite</p>
                        <p class="text-2xl font-bold text-gray-900">{status.max_concurrent}</p>
                    </div>
                    <div class="text-purple-600">
                        <svg class="w-8 h-8" fill="currentColor" viewBox="0 0 20 20">
                            <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                        </svg>
                    </div>
                </div>
            </div>
        {/each}
    </div>
    
    <!-- Formulaire d'ajout -->
    <div class="bg-white rounded-lg shadow p-6 mb-6">
        <h2 class="text-xl font-semibold mb-4">Ajouter un Torrent</h2>
        <div class="space-y-4">
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">
                    Lien Magnet
                </label>
                <input
                    type="text"
                    bind:value={newTorrentMagnet}
                    placeholder="magnet:?xt=urn:btih:..."
                    class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
            </div>
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">
                    Nom (optionnel)
                </label>
                <input
                    type="text"
                    bind:value={newTorrentName}
                    placeholder="Nom du torrent"
                    class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
            </div>
            <button
                on:click={addTorrent}
                class="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
                Ajouter à la Queue
            </button>
        </div>
    </div>
    
    <!-- Liste des torrents -->
    <div class="bg-white rounded-lg shadow">
        <div class="px-6 py-4 border-b border-gray-200">
            <h2 class="text-xl font-semibold">Torrents</h2>
        </div>
        <div class="divide-y divide-gray-200">
            {#each $queueStatus.jobs as job}
                <div class="px-6 py-4 flex items-center justify-between">
                    <div class="flex-1">
                        <div class="flex items-center">
                            <span class="inline-block w-3 h-3 rounded-full {getStatusColor(job.status)} mr-3"></span>
                            <div>
                                <p class="text-sm font-medium text-gray-900">{job.name}</p>
                                <p class="text-sm text-gray-500">
                                    Ajouté le {new Date(job.created_at).toLocaleString()}
                                </p>
                            </div>
                        </div>
                        {#if job.progress > 0}
                            <div class="mt-2 w-full bg-gray-200 rounded-full h-2">
                                <div 
                                    class="bg-blue-600 h-2 rounded-full" 
                                    style="width: {job.progress}%"
                                ></div>
                            </div>
                        {/if}
                    </div>
                    <div class="flex items-center space-x-2">
                        <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                            {job.status}
                        </span>
                        <button class="text-red-600 hover:text-red-800">
                            <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
                            </svg>
                        </button>
                    </div>
                </div>
            {/each}
        </div>
    </div>
</div>
