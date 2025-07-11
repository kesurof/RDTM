<script>
  import { onMount } from 'svelte';
  import { api } from '$lib/api.js';

  let stats = {
    torrents: {
      total_torrents: 0,
      failed_torrents: 0,
      recent_attempts_24h: 0,
      successful_attempts_24h: 0,
      success_rate: 0
    },
    symlinks: {
      total_broken: 0,
      matched: 0,
      unprocessed: 0
    }
  };
  
  let loading = true;
  let scanning = false;

  onMount(async () => {
    await loadStats();
    
    // Refresh stats every 30 seconds
    setInterval(loadStats, 30000);
  });

  async function loadStats() {
    try {
      stats = await api.getStats();
      loading = false;
    } catch (error) {
      console.error('Failed to load stats:', error);
      loading = false;
    }
  }

  async function startScan(mode) {
    scanning = true;
    try {
      await api.scanTorrents(mode);
      // Stats will be updated via WebSocket
    } catch (error) {
      console.error('Scan failed:', error);
      alert(`Scan failed: ${error.message}`);
    }
    scanning = false;
  }
</script>

<svelte:head>
  <title>Dashboard - RDTM</title>
</svelte:head>

<div class="dashboard">
  <h1>📊 Dashboard</h1>

  {#if loading}
    <div class="loading">Loading...</div>
  {:else}
    <!-- Stats Cards -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-header">
          <h3>📁 Torrents</h3>
        </div>
        <div class="stat-content">
          <div class="stat-number">{stats.torrents.total_torrents}</div>
          <div class="stat-label">Total</div>
          <div class="stat-detail">
            <span class="failed">{stats.torrents.failed_torrents} failed</span>
          </div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <h3>🔄 Attempts (24h)</h3>
        </div>
        <div class="stat-content">
          <div class="stat-number">{stats.torrents.recent_attempts_24h}</div>
          <div class="stat-label">Total attempts</div>
          <div class="stat-detail">
            <span class="success">{stats.torrents.successful_attempts_24h} successful</span>
            <span class="rate">({stats.torrents.success_rate.toFixed(1)}%)</span>
          </div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <h3>🔗 Broken Symlinks</h3>
        </div>
        <div class="stat-content">
          <div class="stat-number">{stats.symlinks.total_broken || 0}</div>
          <div class="stat-label">Detected</div>
          <div class="stat-detail">
            <span class="matched">{stats.symlinks.matched || 0} matched</span>
          </div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-header">
          <h3>⚡ System</h3>
        </div>
        <div class="stat-content">
          <div class="stat-indicator healthy">●</div>
          <div class="stat-label">Healthy</div>
          <div class="stat-detail">
            <span>All services running</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Quick Actions -->
    <div class="actions-section">
      <h2>⚡ Quick Actions</h2>
      
      <div class="action-buttons">
        <button 
          class="action-btn primary" 
          on:click={() => startScan('quick')}
          disabled={scanning}
        >
          🔍 Quick Scan
        </button>
        
        <button 
          class="action-btn secondary" 
          on:click={() => startScan('full')}
          disabled={scanning}
        >
          📊 Full Scan
        </button>
        
        <button 
          class="action-btn secondary" 
          on:click={() => startScan('symlinks')}
          disabled={scanning}
        >
          🔗 Symlinks Scan
        </button>
      </div>
      
      {#if scanning}
        <div class="scanning-indicator">
          <div class="spinner"></div>
          <span>Scanning in progress...</span>
        </div>
      {/if}
    </div>

    <!-- Recent Activity -->
    <div class="activity-section">
      <h2>📋 System Status</h2>
      
      <div class="status-grid">
        <div class="status-item">
          <span class="status-label">API Connection</span>
          <span class="status-value connected">Connected</span>
        </div>
        <div class="status-item">
          <span class="status-label">Database</span>
          <span class="status-value connected">Online</span>
        </div>
        <div class="status-item">
          <span class="status-label">Scheduler</span>
          <span class="status-value connected">Running</span>
        </div>
        <div class="status-item">
          <span class="status-label">Last Full Scan</span>
          <span class="status-value">2 hours ago</span>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .dashboard {
    max-width: 1200px;
  }

  h1 {
    margin: 0 0 2rem 0;
    color: #4f9eff;
  }

  .loading {
    text-align: center;
    padding: 2rem;
    color: #a0aec0;
  }

  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 1.5rem;
    margin-bottom: 3rem;
  }

  .stat-card {
    background: #1a1f29;
    border: 1px solid #2d3748;
    border-radius: 0.75rem;
    padding: 1.5rem;
  }

  .stat-header h3 {
    margin: 0 0 1rem 0;
    color: #a0aec0;
    font-size: 0.875rem;
    font-weight: 500;
  }

  .stat-number {
    font-size: 2.5rem;
    font-weight: bold;
    color: #4f9eff;
    margin-bottom: 0.5rem;
  }

  .stat-label {
    color: #a0aec0;
    font-size: 0.875rem;
    margin-bottom: 0.5rem;
  }

  .stat-detail {
    font-size: 0.875rem;
  }

  .failed { color: #ef4444; }
  .success { color: #10b981; }
  .matched { color: #f59e0b; }
  .rate { color: #a0aec0; }

  .stat-indicator {
    font-size: 2rem;
    margin-bottom: 0.5rem;
  }

  .healthy { color: #10b981; }

  .actions-section {
    margin-bottom: 3rem;
  }

  .actions-section h2 {
    margin: 0 0 1.5rem 0;
    color: #e6e6e6;
  }

  .action-buttons {
    display: flex;
    gap: 1rem;
    margin-bottom: 1rem;
  }

  .action-btn {
    padding: 0.75rem 1.5rem;
    border: none;
    border-radius: 0.5rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }

  .action-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .action-btn.primary {
    background: #4f9eff;
    color: white;
  }

  .action-btn.primary:hover:not(:disabled) {
    background: #3182ce;
  }

  .action-btn.secondary {
    background: #2d3748;
    color: #a0aec0;
    border: 1px solid #4a5568;
  }

  .action-btn.secondary:hover:not(:disabled) {
    background: #4a5568;
    color: #e6e6e6;
  }

  .scanning-indicator {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    color: #4f9eff;
  }

  .spinner {
    width: 16px;
    height: 16px;
    border: 2px solid #2d3748;
    border-top: 2px solid #4f9eff;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }

  .activity-section h2 {
    margin: 0 0 1.5rem 0;
    color: #e6e6e6;
  }

  .status-grid {
    background: #1a1f29;
    border: 1px solid #2d3748;
    border-radius: 0.75rem;
    padding: 1.5rem;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
  }

  .status-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .status-label {
    color: #a0aec0;
    font-size: 0.875rem;
  }

  .status-value {
    font-weight: 500;
  }

  .status-value.connected {
    color: #10b981;
  }
</style>