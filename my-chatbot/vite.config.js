import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [react()],
  root: '.',          
  base: '/',        
  build: {
    outDir: 'build',  
    emptyOutDir: true
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 5173,                    
    strictPort: true,               
    proxy: {
      '/api': {
        target: 'http://localhost:10000',
        changeOrigin: true,
        secure: false,
        timeout: 10000
      }
    }
  }
})
