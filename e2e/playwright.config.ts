import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 60000,
  expect: { timeout: 15000 },
  fullyParallel: false,
  use: {
    // Definir APP_URL con la URL de CloudFront del stack (output CloudFrontDomain).
    baseURL: process.env.APP_URL,
    screenshot: 'on',
    trace: 'on-first-retry',
  },
  reporter: [['html'], ['line']],
  outputDir: './screenshots',
});
