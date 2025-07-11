<script>
  import { onMount } from 'svelte';
  import { websocketStore } from '$lib/websocket.js';
  import { page } from '$app/stores';

  let wsData = {};
  
  onMount(() => {
    websocketStore.connect();
    return websocketStore.subscribe((data) => {
      wsData = data;
    });
  });
</script>

<div class="app">
  <nav class="sidebar">
    <div class="logo">
      <h2>🚀 RDTM</h2>
    </div>
    
    <ul class="nav-items">
      <li>
        <a href="/" class:active={$page.url.pathname === '/'}>
          📊 Dashboard
        </a>
      </li>
      <li>
        <a href="/torrents" class:active={$page.url.pathname === '/torrents'}>
          📁 Torrents
        </a>
      </li>
      <li>
        <a href="/symlinks" class:active={$page.url.pathname === '/symlinks'}>
          🔗 Symlinks
        </a>
      </li>
      <li>
        <a href="/logs" class:active={$page.url.pathname === '/logs'}>
          📋 Logs
        </a>
      </li>
    </ul>

    <!-- Connection Status -->
    <div class="connection-status">
      <div class="status-dot" class:connected={websocketStore.connected}></div>
      <span>{websocketStore.connected ? 'Connected' : 'Disconnected'}</span>
    </div>
  </nav>

  <main class="content">
    <!-- Real-time notifications -->
    {#if wsData.type}
      <div class="notification {wsData.type}">
        {#if wsData.type === 'scan_start'}
          🔍 Starting {wsData.mode} scan...
        {:else if wsData.type === 'scan_progress'}
          📈 Processed: {wsData.processed}, Failed: {wsData.failed}
        {:else if wsData.type === 'scan_complete'}
          ✅ Scan complete: {wsData.total_processed} torrents ({wsData.duration.toFixed(1)}s)
        {:else if wsData.type === 'reinject_start'}
          🔄 Reinjecting: {wsData.filename}...
        {:else if wsData.type === 'reinject_complete'}
          {wsData.success ? '✅' : '❌'} Reinject {wsData.success ? 'success' : 'failed'}: {wsData.torrent_id}
        {/if}
      </div>
    {/if}

    <slot />
  </main>
</div>

<style>
  .app {
    display: flex;
    height: 100vh;
  }

  .sidebar {
    width: 250px;
    background: #1a1f29;
    padding: 1rem;
    border-right: 1px solid #2d3748;
  }

  .logo h2 {
    margin: 0 0 2rem 0;
    color: #4f9eff;
  }

  .nav-items {
    list-style: none;
    padding: 0;
    margin: 0;
  }

  .nav-items li {
    margin-bottom: 0.5rem;
  }

  .nav-items a {
    display: block;
    padding: 0.75rem 1rem;
    color: #a0aec0;
    text-decoration: none;
    border-radius: 0.5rem;
    transition: all 0.2s;
  }

  .nav-items a:hover, .nav-items a.active {
    background: #2d3748;
    color: #4f9eff;
  }

  .connection-status {
    position: absolute;
    bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.875rem;
    color: #a0aec0;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #ef4444;
  }

  .status-dot.connected {
    background: #10b981;
  }

  .content {
    flex: 1;
    padding: 2rem;
    overflow-y: auto;
  }

  .notification {
    position: fixed;
    top: 1rem;
    right: 1rem;
    background: #2d3748;
    padding: 1rem;
    border-radius: 0.5rem;
    border-left: 4px solid #4f9eff;
    z-index: 1000;
    animation: slideIn 0.3s ease-out;
  }

  @keyframes slideIn {
    from {
      transform: translateX(100%);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }
</style>