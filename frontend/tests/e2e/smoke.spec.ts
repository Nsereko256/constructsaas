import { expect, test } from '@playwright/test';

test('login page renders the ConstructSaaS shell', async ({ page }) => {
  await page.goto('/login');
  await expect(page.getByRole('heading', { name: /sign in/i })).toBeVisible();
  await expect(page.getByLabel(/username/i)).toBeVisible();
  await expect(page.getByRole('textbox', { name: /password/i })).toBeVisible();
});

test('seeded admin can follow the operational workflow surfaces', async ({ page }) => {
  const username = process.env.E2E_USER || 'demo_admin';
  const password = process.env.E2E_PASSWORD || 'Demo123!';
  await page.goto('/login');
  await page.getByLabel(/username/i).fill(username);
  await page.getByRole('textbox', { name: /password/i }).fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();

  const takeover = page.getByRole('button', { name: /sign out other device and continue/i });
  await takeover.waitFor({ state: 'visible', timeout: 2500 }).catch(() => undefined);
  if (await takeover.isVisible().catch(() => false)) await takeover.click();
  await expect(page).toHaveURL(/\/dashboard$/);

  const workflowRoutes = [
    ['/procurement/requests', /purchase requests/i],
    ['/procurement/purchase-orders', /purchase orders/i],
    ['/procurement/deliveries', /deliveries/i],
    ['/inventory', /inventory/i],
    ['/finance/payables', /supplier invoices/i],
    ['/finance/payments', /supplier payments/i],
    ['/notifications', /notifications/i],
  ] as const;
  for (const [path, heading] of workflowRoutes) {
    await page.goto(path);
    await expect(page.getByRole('heading', { name: heading }).first()).toBeVisible();
    await expect(page.locator('body')).not.toContainText('Something went wrong');
    await expect(page.locator('body')).not.toContainText('Cannot read properties');
  }

  await page.goto('/inventory');
  await expect(page.getByRole('link', { name: /issue stock/i })).toBeVisible();

  // The toggle flow is available for environments with a dedicated writable
  // E2E database. Keep it opt-in so a shared long-running dev server cannot
  // make the workflow smoke test flaky by persisting to a different database.
  if (process.env.E2E_FINANCE_TOGGLE === '1') {
    await page.goto('/finance/settings');
    const financeToggle = page.getByRole('checkbox', { name: /enable soft finance/i });
    await expect(financeToggle).toBeVisible();
    if (await financeToggle.isChecked()) {
      await financeToggle.uncheck();
      await page.getByRole('button', { name: /save module/i }).click();
      await expect(page.getByText(/soft finance module policy updated/i)).toBeVisible({ timeout: 10000 });
    }
    await page.goto('/finance/payables');
    await page.reload();
    await expect(page.getByRole('heading', { name: /soft finance is disabled/i })).toBeVisible();
    await page.goto('/finance/settings');
    if (!(await financeToggle.isChecked())) {
      await financeToggle.check();
      await page.getByRole('button', { name: /save module/i }).click();
      await expect(page.getByText(/soft finance module policy updated/i)).toBeVisible({ timeout: 10000 });
    }
    await page.goto('/finance');
    await page.reload();
    await expect(page.getByRole('heading', { name: /financial command centre/i })).toBeVisible();
  }

  await page.goto('/work-orders');
  await expect(page.getByRole('heading', { name: /coming in a later release/i })).toBeVisible();
  await page.goto('/messages');
  await expect(page.getByRole('heading', { name: /coming in a later release/i })).toBeVisible();
});
