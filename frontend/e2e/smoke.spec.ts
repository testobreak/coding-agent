import { expect, test } from '@playwright/test';

test('home page renders HRMS heading', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'HRMS' })).toBeVisible();
});

test('shows sign-in when anonymous', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('button', { name: /sign in with keycloak/i })).toBeVisible();
});
