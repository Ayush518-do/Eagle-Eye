import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Without the React plugin the page crashes with "React is not defined".
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
});
