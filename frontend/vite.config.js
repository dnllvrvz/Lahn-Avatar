import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: true, // allow external connections
    port: 5173, // or whatever you're using
    allowedHosts: ['lahn-server.eastus.cloudapp.azure.com', "lahn-avatar.uni-giessen.de"], // ✅ add this line

    // proxy: {
    //   // forward any request that starts with /api
    //   '/api': {
    //     target: 'http://localhost:5001',
    //     changeOrigin: true,
    //   }
    // }
  },
})
