import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 60000,
  expect: { timeout: 15000 },
  fullyParallel: false,
  use: {
    baseURL: process.env.APP_URL || 'https://da5wlutxahcar.cloudfront.net',
    screenshot: 'on',
    trace: 'on-first-retry',
  },
  reporter: [['html'], ['line']],
  outputDir: './screenshots',
});
