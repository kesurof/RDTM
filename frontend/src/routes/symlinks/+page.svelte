<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';

  let symlinks = [];
  let loading = true;
  let scanning = false;
  let matching = false;
  let showProcessed = false;

  const statusColors = {
    'BROKEN': 'text-red-400',
    'MATCHED': 'text-yellow-400', 
    'PROCESSED': 'text-green-400'
  };

  onMount(async () => {
    await loadSymlinks();
    
    // Auto-refresh every 60 seconds
    setInterval(loadSymlinks, 60000);
  });

  async function loadSymlinks() {
    try {
      const params = {};
      if (!showProcessed) params.processed = false;
      
      symlinks = await api.getBrokenSymlinks(params);
      loading = false;
    } catch (error) {
      console.error('Failed to load symlinks:', error);
      loading = false;
    }
  }

  async function scanSymlinks() {
    scanning = true;
    try {
      await api.scanSymlinks();
      setTimeout(loadSymlinks, 2000);
    } catch (error) {
      console.error('Symlink scan failed:', error);
      alert(`Scan failed: ${error.message}`);
    }
    scanning = false;
  }

  async function matchSymlinks() {
    matching = true;
    try {
      await api.matchSymlinks();
      setTimeout(loadSymlinks, 2000);
    } catch (error) {
      console.error('Symlink matching failed:', error);
      alert(`Matching failed: ${error.message}`);
    }
    matching = false;
  }

  function formatPath(path) {
    // Show only last 3 parts of path for readability
    const parts = path.split('/');
    if (parts.length > 3) {
      return '.../' + parts.slice(-3).join('/');
    }
    return path;
  }

  function formatDate(dateString) {
    return new Date(dateString).toLocaleDateString();
  }

  function getStatusIcon(status) {
    switch (status) {
      case 'BROKEN': return '💥';
      case 'MATCHED': return '🔗';
      case 'PROCESSED': return '✅';
      default: return '❓';
    }
  }

  $: filteredSymlinks = showProcessed 
    ? symlinks 
    : symlinks.filter(s => !s.processed);
</script>

<svelte:head>
  <title>Symlinks - RDTM</title>
</svelte:head>

<div class="symlinks-page">
  <div class="header">
    <h1>🔗 Broken Symlinks</h1>
    
    <div class="actions">
      <label class="toggle">
        <input type="checkbox" bind:checked={showProcessed} on:change={loadSymlinks} />
        Show Processed
      </label>

      <button 
        class="btn secondary" 
        on:click={scanSymlinks}
        disabled={scanning}
      >
        {scanning ? '🔍 Scanning...' : '🔍 Scan Symlinks'}
      </button>
      
      <button 
        class="btn primary" 
        on:click={matchSymlinks}
        disabled={matching}
      >
        {matching ? '🔗 Matching...' : '🔗 Match Torrents'}
      </button>
    </div>
  </div>

  {#if loading}
    <div class="loading">Loading symlinks...</div>
  {:else if filteredSymlinks.length === 0}
    <div class="empty">
      <div class="empty-icon">🎉</div>
      <h3>No broken symlinks found</h3>
      <p>All your symlinks are working correctly!</p>
      <button class="btn secondary" on:click={scanSymlinks}>
        🔍 Scan for Issues
      </button>
    </div>
  {:else}
    <div class="stats-bar">
      <div class="stat">
        <span class="stat-number">{filteredSymlinks.length}</span>
        <span class="stat-label">Total</span>
      </div>
      <div class="stat">
        <span class="stat-number">{filteredSymlinks.filter(s => s.matched_torrent_id).length}</span>
        <span class="stat-label">Matched</span>
      </div>
      <div class="stat">
        <span class="stat-number">{filteredSymlinks.filter(s => s.processed).length}</span>
        <span class="stat-label">Processed</span>
      </div>
    </div>

    <div class="table-container">
      <table class="symlinks-table">
        <thead>
          <tr>
            <th>Status</th>
            <th>Source Path</th>
            <th>Target Path</th>
            <th>Torrent Name</th>
            <th>Matched Torrent</th>
            <th>Detected</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {#each filteredSymlinks as symlink (symlink.id)}
            <tr class:matched={symlink.matched_torrent_id} class:processed={symlink.processed}>
              <td>
                <div class="status-cell">
                  <span class="status-icon">{getStatusIcon(symlink.status)}</span>
                  <span class="status {statusColors[symlink.status] || 'text-gray-400'}">
                    {symlink.status}
                  </span>
                </div>
              </td>
              <td class="path-cell" title={symlink.source_path}>
                {formatPath(symlink.source_path)}
              </td>
              <td class="path-cell" title={symlink.target_path}>
                {formatPath(symlink.target_path)}
              </td>
              <td class="torrent-name" title={symlink.torrent_name}>
                {symlink.torrent_name}
              </td>
              <td>
                {#if symlink.matched_torrent_id}
                  <span class="matched-id" title={symlink.matched_torrent_id}>
                    ✅ {symlink.matched_torrent_id.slice(0, 8)}...
                  </span>
                {:else}
                  <span class="no-match">No match</span>
                {/if}
              </td>
              <td>{formatDate(symlink.detected_date)}</td>
              <td>
                <div class="row-actions">
                  {#if symlink.matched_torrent_id && !symlink.processed}
                    <button 
                      class="btn-icon" 
                      on:click={() => api.reinjectTorrents([symlink.matched_torrent_id])}
                      title="Reinject matched torrent"
                    >
                      🔄
                    </button>
                  {/if}
                  <button 
                    class="btn-icon info" 
                    title="View details"
                  >
                    ℹ️
                  </button>
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <!-- Help Section -->
    <div class="help-section">
      <h3>🛠️ Understanding Symlinks</h3>
      <div class="help-grid">
        <div class="help-card">
          <h4>💥 Broken</h4>
          <p>Symlink points to missing file. Usually means torrent was removed from Real-Debrid.</p>
        </div>
        <div class="help-card">
          <h4>🔗 Matched</h4>
          <p>Broken symlink matched to existing torrent. Can be reinjected to fix the link.</p>
        </div>
        <div class="help-card">
          <h4>✅ Processed</h4>
          <p>Symlink has been handled and either fixed or marked for cleanup.</p>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .symlinks-page {
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

  .actions {
    display: flex;
    gap: 1rem;
    align-items: center;
  }

  .toggle {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: #a0aec0;
    font-size: 0.875rem;
    cursor: pointer;
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

  .loading {
    text-align: center;
    padding: 3rem;
    color: #a0aec0;
  }

  .empty {
    text-align: center;
    padding: 4rem 2rem;
    background: #1a1f29;
    border-radius: 0.75rem;
    border: 1px solid #2d3748;
  }

  .empty-icon {
    font-size: 4rem;
    margin-bottom: 1rem;
  }

  .empty h3 {
    color: #4f9eff;
    margin: 0 0 0.5rem 0;
  }

  .empty p {
    color: #a0aec0;
    margin: 0 0 2rem 0;
  }

  .stats-bar {
    display: flex;
    gap: 2rem;
    background: #1a1f29;
    padding: 1rem 2rem;
    border-radius: 0.75rem;
    border: 1px solid #2d3748;
    margin-bottom: 1rem;
  }

  .stat {
    display: flex;
    flex-direction: column;
    align-items: center;
  }

  .stat-number {
    font-size: 1.5rem;
    font-weight: bold;
    color: #4f9eff;
  }

  .stat-label {
    font-size: 0.875rem;
    color: #a0aec0;
  }

  .table-container {
    background: #1a1f29;
    border-radius: 0.75rem;
    border: 1px solid #2d3748;
    overflow: hidden;
    margin-bottom: 2rem;
  }

  .symlinks-table {
    width: 100%;
    border-collapse: collapse;
  }

  .symlinks-table th,
  .symlinks-table td {
    padding: 0.75rem;
    text-align: left;
    border-bottom: 1px solid #2d3748;
  }

  .symlinks-table th {
    background: #2d3748;
    font-weight: 600;
    color: #a0aec0;
    font-size: 0.875rem;
  }

  .symlinks-table tr:hover {
    background: #2d3748;
  }

  .symlinks-table tr.matched {
    background: rgba(245, 158, 11, 0.1);
  }

  .symlinks-table tr.processed {
    opacity: 0.6;
  }

  .status-cell {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .status-icon {
    font-size: 1.2rem;
  }

  .status {
    font-weight: 500;
    font-size: 0.875rem;
  }

  .path-cell {
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: monospace;
    font-size: 0.875rem;
  }

  .torrent-name {
    max-width: 250px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .matched-id {
    color: #10b981;
    font-family: monospace;
    font-size: 0.875rem;
  }

  .no-match {
    color: #ef4444;
    font-size: 0.875rem;
  }

  .row-actions {
    display: flex;
    gap: 0.5rem;
  }

  .btn-icon {
    background: none;
    border: none;
    padding: 0.25rem;
    cursor: pointer;
    border-radius: 0.25rem;
    transition: background 0.2s;
  }

  .btn-icon:hover {
    background: #4a5568;
  }

  .btn-icon.info:hover {
    background: #3182ce;
  }

  .help-section {
    background: #1a1f29;
    border-radius: 0.75rem;
    border: 1px solid #2d3748;
    padding: 1.5rem;
  }

  .help-section h3 {
    margin: 0 0 1rem 0;
    color: #4f9eff;
  }

  .help-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 1rem;
  }

  .help-card {
    background: #2d3748;
    padding: 1rem;
    border-radius: 0.5rem;
  }

  .help-card h4 {
    margin: 0 0 0.5rem 0;
    font-size: 0.875rem;
  }

  .help-card p {
    margin: 0;
    color: #a0aec0;
    font-size: 0.875rem;
    line-height: 1.4;
  }

  /* Responsive */
  @media (max-width: 768px) {
    .header {
      flex-direction: column;
      gap: 1rem;
      align-items: flex-start;
    }

    .actions {
      width: 100%;
      justify-content: space-between;
    }

    .stats-bar {
      flex-direction: column;
      gap: 1rem;
    }

    .table-container {
      overflow-x: auto;
    }

    .symlinks-table {
      min-width: 1000px;
    }
  }
</style>