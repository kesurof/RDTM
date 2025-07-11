<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';

  let torrents = [];
  let loading = true;
  let selectedTorrents = new Set();
  let filter = '';
  let statusFilter = '';
  let processing = false;

  const statusLabels = {
    'downloaded': '✅ Downloaded',
    'downloading': '⬇️ Downloading', 
    'waiting_files_selection': '⏳ Waiting',
    'magnet_error': '❌ Magnet Error',
    'error': '❌ Error',
    'virus': '🦠 Virus',
    'dead': '💀 Dead'
  };

  const statusColors = {
    'downloaded': 'success',
    'downloading': 'info',
    'waiting_files_selection': 'warning',
    'magnet_error': 'error',
    'error': 'error', 
    'virus': 'error',
    'dead': 'error'
  };

  onMount(async () => {
    await loadTorrents();
  });

  async function loadTorrents() {
    loading = true;
    try {
      const params = {};
      if (statusFilter) params.status = statusFilter;
      torrents = await api.getTorrents(params);
    } catch (error) {
      console.error('Failed to load torrents:', error);
      alert(`Failed to load torrents: ${error.message}`);
    }
    loading = false;
  }

  function toggleSelection(torrentId) {
    if (selectedTorrents.has(torrentId)) {
      selectedTorrents.delete(torrentId);
    } else {
      selectedTorrents.add(torrentId);
    }
    selectedTorrents = selectedTorrents;
  }

  function selectAll() {
    selectedTorrents = new Set(filteredTorrents.map(t => t.id));
  }

  function clearSelection() {
    selectedTorrents = new Set();
  }

  async function reinjectSelected() {
    if (selectedTorrents.size === 0) return;
    
    processing = true;
    try {
      const result = await api.reinjectTorrents([...selectedTorrents]);
      const successful = result.results.filter(r => r.success).length;
      alert(`Reinjected ${successful}/${result.results.length} torrents`);
      clearSelection();
      await loadTorrents();
    } catch (error) {
      alert(`Reinject failed: ${error.message}`);
    }
    processing = false;
  }

  async function deleteSelected() {
    if (selectedTorrents.size === 0) return;
    if (!confirm(`Delete ${selectedTorrents.size} torrents?`)) return;
    
    processing = true;
    let deleted = 0;
    for (const torrentId of selectedTorrents) {
      try {
        await api.deleteTorrent(torrentId);
        deleted++;
      } catch (error) {
        console.error(`Failed to delete ${torrentId}:`, error);
      }
    }
    alert(`Deleted ${deleted}/${selectedTorrents.size} torrents`);
    clearSelection();
    await loadTorrents();
    processing = false;
  }

  function formatSize(bytes) {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  function formatDate(dateStr) {
    return new Date(dateStr).toLocaleDateString();
  }

  $: filteredTorrents = torrents.filter(torrent => {
    const matchesFilter = !filter || 
      torrent.filename.toLowerCase().includes(filter.toLowerCase());
    const matchesStatus = !statusFilter || torrent.status === statusFilter;
    return matchesFilter && matchesStatus;
  });

  $: failedCount = filteredTorrents.filter(t => 
    ['magnet_error', 'error', 'virus', 'dead'].includes(t.status)
  ).length;
</script>

<svelte:head>
  <title>Torrents - RDTM</title>
</svelte:head>

<div class="torrents-page">
  <div class="header">
    <h1>📁 Torrents ({filteredTorrents.length})</h1>
    <div class="actions">
      <button 
        class="btn primary" 
        on:click={loadTorrents}
        disabled={loading}
      >
        🔄 Refresh
      </button>
    </div>
  </div>

  <!-- Filters -->
  <div class="filters">
    <input 
      type="text" 
      placeholder="Search torrents..."
      bind:value={filter}
      class="search-input"
    />
    
    <select bind:value={statusFilter} class="status-filter">
      <option value="">All Status</option>
      <option value="failed">❌ Failed Only</option>
      <option value="downloaded">✅ Downloaded</option>
      <option value="downloading">⬇️ Downloading</option>
      <option value="magnet_error">❌ Magnet Error</option>
      <option value="error">❌ Error</option>
      <option value="virus">🦠 Virus</option>
      <option value="dead">💀 Dead</option>
    </select>
  </div>

  <!-- Bulk Actions -->
  {#if selectedTorrents.size > 0}
    <div class="bulk-actions">
      <span class="selection-info">
        {selectedTorrents.size} selected
      </span>
      
      <div class="bulk-buttons">
        <button class="btn secondary" on:click={clearSelection}>
          Clear
        </button>
        <button 
          class="btn primary" 
          on:click={reinjectSelected}
          disabled={processing}
        >
          🔄 Reinject Selected
        </button>
        <button 
          class="btn danger" 
          on:click={deleteSelected}
          disabled={processing}
        >
          🗑️ Delete Selected
        </button>
      </div>
    </div>
  {:else}
    <div class="quick-actions">
      <button class="btn secondary" on:click={selectAll}>
        Select All
      </button>
      {#if failedCount > 0}
        <button 
          class="btn secondary" 
          on:click={() => {
            selectedTorrents = new Set(
              filteredTorrents
                .filter(t => ['magnet_error', 'error', 'virus', 'dead'].includes(t.status))
                .map(t => t.id)
            );
          }}
        >
          Select Failed ({failedCount})
        </button>
      {/if}
    </div>
  {/if}

  <!-- Torrents Table -->
  {#if loading}
    <div class="loading">Loading torrents...</div>
  {:else if filteredTorrents.length === 0}
    <div class="empty">
      {filter || statusFilter ? 'No torrents match filters' : 'No torrents found'}
    </div>
  {:else}
    <div class="table-container">
      <table class="torrents-table">
        <thead>
          <tr>
            <th class="checkbox-col">
              <input 
                type="checkbox" 
                checked={selectedTorrents.size === filteredTorrents.length}
                on:change={selectedTorrents.size === filteredTorrents.length ? clearSelection : selectAll}
              />
            </th>
            <th>Status</th>
            <th>Filename</th>
            <th>Size</th>
            <th>Attempts</th>
            <th>Priority</th>
            <th>Last Seen</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {#each filteredTorrents as torrent}
            <tr class:selected={selectedTorrents.has(torrent.id)}>
              <td class="checkbox-col">
                <input 
                  type="checkbox" 
                  checked={selectedTorrents.has(torrent.id)}
                  on:change={() => toggleSelection(torrent.id)}
                />
              </td>
              <td>
                <span class="status {statusColors[torrent.status]}">
                  {statusLabels[torrent.status] || torrent.status}
                </span>
              </td>
              <td class="filename">
                <span title={torrent.filename}>
                  {torrent.filename}
                </span>
              </td>
              <td>{formatSize(torrent.size)}</td>
              <td>
                <span class="attempts" class:high={torrent.attempts_count >= 3}>
                  {torrent.attempts_count}
                </span>
              </td>
              <td>
                <span class="priority priority-{torrent.priority}">
                  {torrent.priority === 3 ? 'High' : torrent.priority === 2 ? 'Normal' : 'Low'}
                </span>
              </td>
              <td>{formatDate(torrent.last_seen)}</td>
              <td class="actions-cell">
                {#if ['magnet_error', 'error', 'virus', 'dead'].includes(torrent.status)}
                  <button 
                    class="btn-small primary"
                    on:click={() => reinjectSelected()} 
                    disabled={processing}
                    on:click|preventDefault={() => {
                      selectedTorrents = new Set([torrent.id]);
                      reinjectSelected();
                    }}
                  >
                    🔄
                  </button>
                {/if}
                <button 
                  class="btn-small danger"
                  on:click|preventDefault={() => {
                    if (confirm(`Delete "${torrent.filename}"?`)) {
                      selectedTorrents = new Set([torrent.id]);
                      deleteSelected();
                    }
                  }}
                  disabled={processing}
                >
                  🗑️
                </button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<style>
  .torrents-page {
    max-width: 1400px;
  }

  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 2rem;
  }

  .header h1 {
    margin: 0;
    color: #4f9eff;
  }

  .filters {
    display: flex;
    gap: 1rem;
    margin-bottom: 1.5rem;
  }

  .search-input, .status-filter {
    padding: 0.5rem;
    border: 1px solid #2d3748;
    border-radius: 0.375rem;
    background: #1a1f29;
    color: #e6e6e6;
  }

  .search-input {
    flex: 1;
    max-width: 300px;
  }

  .bulk-actions, .quick-actions {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
    padding: 0.75rem;
    background: #1a1f29;
    border-radius: 0.5rem;
    border: 1px solid #2d3748;
  }

  .selection-info {
    color: #4f9eff;
    font-weight: 500;
  }

  .bulk-buttons {
    display: flex;
    gap: 0.5rem;
  }

  .btn {
    padding: 0.5rem 1rem;
    border: none;
    border-radius: 0.375rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn.primary {
    background: #4f9eff;
    color: white;
  }

  .btn.primary:hover:not(:disabled) {
    background: #3182ce;
  }

  .btn.secondary {
    background: #2d3748;
    color: #a0aec0;
    border: 1px solid #4a5568;
  }

  .btn.secondary:hover:not(:disabled) {
    background: #4a5568;
    color: #e6e6e6;
  }

  .btn.danger {
    background: #ef4444;
    color: white;
  }

  .btn.danger:hover:not(:disabled) {
    background: #dc2626;
  }

  .btn-small {
    padding: 0.25rem 0.5rem;
    font-size: 0.875rem;
    margin-right: 0.25rem;
  }

  .table-container {
    background: #1a1f29;
    border-radius: 0.75rem;
    border: 1px solid #2d3748;
    overflow: hidden;
  }

  .torrents-table {
    width: 100%;
    border-collapse: collapse;
  }

  .torrents-table th,
  .torrents-table td {
    padding: 0.75rem;
    text-align: left;
    border-bottom: 1px solid #2d3748;
  }

  .torrents-table th {
    background: #2d3748;
    color: #a0aec0;
    font-weight: 500;
    font-size: 0.875rem;
  }

  .checkbox-col {
    width: 40px;
  }

  .filename {
    max-width: 300px;
  }

  .filename span {
    display: block;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .actions-cell {
    width: 100px;
  }

  tr.selected {
    background: rgba(79, 158, 255, 0.1);
  }

  .status {
    padding: 0.25rem 0.5rem;
    border-radius: 0.25rem;
    font-size: 0.875rem;
    font-weight: 500;
  }

  .status.success { background: rgba(16, 185, 129, 0.2); color: #10b981; }
  .status.info { background: rgba(79, 158, 255, 0.2); color: #4f9eff; }
  .status.warning { background: rgba(245, 158, 11, 0.2); color: #f59e0b; }
  .status.error { background: rgba(239, 68, 68, 0.2); color: #ef4444; }

  .attempts.high {
    color: #ef4444;
    font-weight: bold;
  }

  .priority {
    font-size: 0.875rem;
    font-weight: 500;
  }

  .priority-3 { color: #ef4444; }
  .priority-2 { color: #4f9eff; }
  .priority-1 { color: #a0aec0; }

  .loading, .empty {
    text-align: center;
    padding: 3rem;
    color: #a0aec0;
  }
</style>