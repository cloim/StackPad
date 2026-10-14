import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import packageJson from './package.json' with { type: 'json' };

export default defineConfig({
  define: { APP_VERSION: JSON.stringify(packageJson.version) },
  plugins: [react(), VitePWA({
    useCredentials: true,
    injectRegister: false,
    registerType: 'prompt',
    includeAssets: ['apple-touch-icon.png'],
    manifest: {
      id: '/',
      name: 'StackPad',
      short_name: 'StackPad',
      description: 'Start and stop the servers on your PC from any of your devices',
      lang: 'en',
      start_url: '/',
      scope: '/',
      display: 'standalone',
      background_color: '#202122',
      theme_color: '#202122',
      icons: [
        { src: '/pwa-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
        { src: '/pwa-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
        { src: '/pwa-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
      ],
    },
    workbox: {
      globPatterns: ['**/*.{js,css,html,ico,svg}'],
      navigateFallback: '/index.html',
      navigateFallbackDenylist: [/^\/api(?:\/|$)/],
      cleanupOutdatedCaches: true,
      // Only public build assets are cached; authenticated API traffic stays on the network.
      runtimeCaching: [],
    },
  })],
  server: { proxy: { '/api': 'http://127.0.0.1:48731' } },
});
