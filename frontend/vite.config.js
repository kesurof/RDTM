import { sveltekit } from '@sveltejs/kit/vite';
export default {
  plugins: [sveltekit()],
  server: { host: true, port: 5173 }
};
