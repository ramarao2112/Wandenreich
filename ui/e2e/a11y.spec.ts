import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('Real-Browser Rendered Accessibility Suite (Axe)', () => {
  test('01. Ready state has 0 axe accessibility violations', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('header[role="banner"]')).toBeVisible();

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    expect(accessibilityScanResults.violations).toEqual([]);
  });

  test('02. Diagnostics state with actionable issue has 0 axe violations', async ({ page }) => {
    await page.goto('/');
    const exampleSelect = page.locator('#example-select');
    await exampleSelect.selectOption('F1');
    await page.locator('#btn-action-check').click();
    await expect(page.locator('text=Actionable Issues')).toBeVisible({ timeout: 15000 });

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();

    expect(accessibilityScanResults.violations).toEqual([]);
  });

  test('03. Fix preview state has 0 axe violations', async ({ page }) => {
    await page.goto('/');
    const exampleSelect = page.locator('#example-select');
    await exampleSelect.selectOption('F1');
    await page.locator('#btn-action-check').click();
    await expect(page.locator('text=Actionable Issues')).toBeVisible({ timeout: 15000 });

    const previewFixBtn = page.locator('button:has-text("Preview fix")');
    await previewFixBtn.click();
    await expect(page.locator('div[role="region"][aria-label="Fix preview"]')).toBeVisible();

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();

    expect(accessibilityScanResults.violations).toEqual([]);
  });

  test('04. Clean check state has 0 axe violations', async ({ page }) => {
    await page.goto('/');
    const exampleSelect = page.locator('#example-select');
    await exampleSelect.selectOption('F2');
    await page.locator('#btn-action-check').click();
    await expect(page.locator('h2:has-text("Specification checks passed.")')).toBeVisible({ timeout: 15000 });

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();

    expect(accessibilityScanResults.violations).toEqual([]);
  });

  test('05. Access tests results state has 0 axe violations', async ({ page }) => {
    await page.goto('/');
    const exampleSelect = page.locator('#example-select');
    await exampleSelect.selectOption('F2');
    await page.locator('#btn-action-check').click();
    await expect(page.locator('h2:has-text("Specification checks passed.")')).toBeVisible({ timeout: 15000 });

    await page.locator('#btn-action-build').click();
    await expect(page.locator('#tab-code')).toHaveAttribute('aria-selected', 'true', { timeout: 20000 });

    await page.locator('#btn-action-test-access').click();
    await expect(page.locator('#tab-tests')).toHaveAttribute('aria-selected', 'true', { timeout: 25000 });
    await expect(page.locator('text=Other users were blocked. The owner received access.')).toBeVisible({ timeout: 20000 });

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();

    expect(accessibilityScanResults.violations).toEqual([]);
  });

  test('06. Build evidence tab has 0 axe violations', async ({ page }) => {
    await page.goto('/');
    const exampleSelect = page.locator('#example-select');
    await exampleSelect.selectOption('F2');
    await page.locator('#btn-action-check').click();
    await expect(page.locator('h2:has-text("Specification checks passed.")')).toBeVisible({ timeout: 15000 });

    await page.locator('#btn-action-build').click();
    await expect(page.locator('#tab-code')).toHaveAttribute('aria-selected', 'true', { timeout: 20000 });

    await page.locator('#tab-evidence').click();
    await expect(page.locator('text=Build Evidence & Verification Report')).toBeVisible();

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();

    expect(accessibilityScanResults.violations).toEqual([]);
  });

  test('07. Keyboard navigation and shortcuts work without mouse', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('#btn-action-check')).toBeVisible();

    // Focus editor and trigger Ctrl+Enter
    const cmContent = page.locator('.cm-content');
    await cmContent.focus();
    await page.keyboard.press('Control+Enter');

    // Should trigger check and show diagnostics
    await expect(page.locator('text=Actionable Issues')).toBeVisible({ timeout: 15000 });

    // Tab navigation through tabs
    const tabCode = page.locator('#tab-code');
    await tabCode.focus();
    await page.keyboard.press('Enter');
    await expect(tabCode).toHaveAttribute('aria-selected', 'true');
  });
});
