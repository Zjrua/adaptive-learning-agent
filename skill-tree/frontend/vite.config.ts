import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发：前端 :5173，代理 /api 到后端 :8000
// 生产：前端 build 后由后端 StaticFiles 托管（或 nginx）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/projects': { target: 'http://localhost:8000', changeOrigin: true },
      '/resume': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
