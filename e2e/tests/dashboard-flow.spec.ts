import { test, expect } from '@playwright/test';

const DEMO_EMAIL = process.env.DEMO_EMAIL || 'peccy@example.com';
const DEMO_PASSWORD = process.env.DEMO_PASSWORD || 'PharmAssist2026!';

test.describe('PharmAssist E2E', () => {
  test('login and view dashboard', async ({ page }) => {
    await page.goto('/');

    // Login
    await page.fill('input[type="email"], input[required]:first-of-type', DEMO_EMAIL);
    await page.fill('input[type="password"], input[required]:nth-of-type(2)', DEMO_PASSWORD);
    await page.click('button:has-text("INICIAR SESIÓN")');

    // Wait for dashboard
    await expect(page.getByText('Visitas del Mes')).toBeVisible({ timeout: 15000 });

    // Screenshot
    await page.screenshot({ path: 'e2e/screenshots/dashboard.png', fullPage: true });
  });

  test('suggestion chips visible in empty chat', async ({ page }) => {
    await page.goto('/');
    await page.fill('input[required]:first-of-type', DEMO_EMAIL);
    await page.fill('input[required]:nth-of-type(2)', DEMO_PASSWORD);
    await page.click('button:has-text("INICIAR SESIÓN")');
    await expect(page.getByText('Visitas del Mes')).toBeVisible({ timeout: 15000 });

    // Check suggestion chips
    const chips = page.locator('[data-testid="suggestion-chip"]');
    await expect(chips.first()).toBeVisible({ timeout: 5000 });
    expect(await chips.count()).toBeGreaterThanOrEqual(3);
  });

  test('chat sends message and gets response', async ({ page }) => {
    await page.goto('/');
    await page.fill('input[required]:first-of-type', DEMO_EMAIL);
    await page.fill('input[required]:nth-of-type(2)', DEMO_PASSWORD);
    await page.click('button:has-text("INICIAR SESIÓN")');
    await expect(page.getByText('Visitas del Mes')).toBeVisible({ timeout: 15000 });

    // Send chat message
    await page.fill('[placeholder*="consulta"]', '¿Cuáles son mis productos foco?');
    await page.press('[placeholder*="consulta"]', 'Enter');

    // Wait for response (up to 60s for cold start)
    await expect(
      page.locator('text=Hiperfoco').or(page.locator('text=Foco')).or(page.locator('text=producto'))
    ).toBeVisible({ timeout: 60000 });

    await page.screenshot({ path: 'e2e/screenshots/chat-response.png', fullPage: true });
  });
});
