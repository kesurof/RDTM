const BASE_URL = '/api';

class ApiClient {
  async request(endpoint, options = {}) {
    const url = `${BASE_URL}${endpoint}`;
    const config = {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    };

    if (config.body && typeof config.body === 'object') {
      config.body = JSON.stringify(config.body);
    }

    try {
      const response = await fetch(url, config);
      
      if (!response.ok) {
        const error = await response.text();
        throw new Error(`HTTP ${response.status}: ${error}`);
      }

      return await response.json();
    } catch (error) {
      console.error(`API request failed: ${endpoint}`, error);
      throw error;
    }
  }

  // Torrents
  async getTorrents(params = {}) {
    const searchParams = new URLSearchParams(params);
    return this.request(`/torrents?${searchParams}`);
  }

  async scanTorrents(mode = 'quick') {
    return this.request('/torrents/scan', {
      method: 'POST',
      body: { mode }
    });
  }

  async reinjectTorrents(torrentIds) {
    return this.request('/torrents/reinject', {
      method: 'POST',
      body: { torrent_ids: torrentIds }
    });
  }

  async deleteTorrent(torrentId) {
    return this.request(`/torrents/${torrentId}`, {
      method: 'DELETE'
    });
  }

  // Symlinks
  async getBrokenSymlinks(params = {}) {
    const searchParams = new URLSearchParams(params);
    return this.request(`/symlinks/broken?${searchParams}`);
  }

  async scanSymlinks() {
    return this.request('/symlinks/scan', {
      method: 'POST'
    });
  }

  async matchSymlinks() {
    return this.request('/symlinks/match', {
      method: 'POST'
    });
  }

  // Stats & Health
  async getStats() {
    return this.request('/stats');
  }

  async getHealth() {
    return this.request('/health');
  }
}

export const api = new ApiClient();