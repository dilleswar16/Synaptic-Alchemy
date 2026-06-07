import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor':    ['react', 'react-dom', 'react-router-dom'],
          'query-vendor':    ['@tanstack/react-query'],
          'chart-vendor':    ['recharts', '@nivo/core', '@nivo/pie', '@nivo/heatmap'],
          'flow-vendor':     ['@xyflow/react'],
          'pdf-vendor':      ['jspdf', 'html2canvas'],
          'mermaid-vendor':  ['mermaid'],
          'motion-vendor':   ['framer-motion'],
          'markdown-vendor': ['react-markdown', 'remark-gfm'],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Forward /api/* to the Python FastAPI backend during local dev.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/api/, ''),
      },
    },
  },
})
