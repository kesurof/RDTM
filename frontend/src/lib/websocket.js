import { writable } from 'svelte/stores';

function createWebSocketStore() {
  const { subscribe, set, update } = writable({});
  
  let socket = null;
  let connected = false;
  let reconnectTimeout = null;

  function connect() {
    try {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/ws`;
      
      socket = new WebSocket(wsUrl);
      
      socket.onopen = () => {
        connected = true;
        console.log('WebSocket connected');
        clearTimeout(reconnectTimeout);
      };
      
      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          set(data);
          
          // Auto-clear notification after 5 seconds
          setTimeout(() => {
            set({});
          }, 5000);
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e);
        }
      };
      
      socket.onclose = () => {
        connected = false;
        console.log('WebSocket disconnected');
        
        // Reconnect after 3 seconds
        reconnectTimeout = setTimeout(() => {
          connect();
        }, 3000);
      };
      
      socket.onerror = (error) => {
        console.error('WebSocket error:', error);
      };
      
    } catch (error) {
      console.error('Failed to connect WebSocket:', error);
    }
  }

  function disconnect() {
    if (socket) {
      socket.close();
      socket = null;
    }
    clearTimeout(reconnectTimeout);
    connected = false;
  }

  return {
    subscribe,
    connect,
    disconnect,
    get connected() {
      return connected;
    }
  };
}

export const websocketStore = createWebSocketStore();