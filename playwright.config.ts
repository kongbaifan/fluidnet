import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e', timeout: 60000, expect: { timeout: 25000 }, workers: 1,
  use: { baseURL: 'http://127.0.0.1:8766', headless: true, viewport: { width: 1600, height: 1000 },
    launchOptions: { channel: 'msedge' }, screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: { command: 'npm run preview -- --port 8766 --workspace .cache/e2e-workspace',
    url: 'http://127.0.0.1:8766/api/v1/health', reuseExistingServer: false, timeout: 60000 },
  reporter: [['list']], outputDir: 'test-results',
});
