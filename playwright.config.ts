import { defineConfig, devices } from '@playwright/test';
const external = process.env.CELEBRY_BROWSER_BASE_URL;
export default defineConfig({
  testDir: './tests/browser',
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 8_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { baseURL: external || 'http://127.0.0.1:3100', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: external ? undefined : { command: 'CELEBRY_BUILD_DIR=.next-e2e npm run dev -- --hostname 127.0.0.1 --port 3100', url: 'http://127.0.0.1:3100', reuseExistingServer: false, timeout: 60_000 },
  projects: [
    { name: 'desktop', use: { viewport: {width: 1280, height: 800}, browserName: 'chromium' } },
    { name: 'mobile', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } },
  ],
});
