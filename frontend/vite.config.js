import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => {
  const serverConfig = {
    host: true, // allow external connections
    port: 5174, // or whatever you're using
    allowedHosts: [
      'lahn-server.eastus.cloudapp.azure.com',
      'lahn-avatar.uni-giessen.de',
    ],
  };

  // Apply proxy only when running in 'mac' mode (npm run mac)
  if (mode === 'mac') {
    serverConfig.proxy = {
      '/api': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      }
    };
  }

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
        '@components': path.resolve(__dirname, './src/components'),
        '@ui': path.resolve(__dirname, './src/components/ui'),
        '@lib': path.resolve(__dirname, './src/lib'),
        '@hooks': path.resolve(__dirname, './src/hooks'),
      },
    },
    server: serverConfig,
  };
});
