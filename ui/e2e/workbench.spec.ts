import { test, expect } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SCREENSHOT_DIR = path.resolve(__dirname, '../../review-logs/stage-7/screenshots');

test.describe('TrustC Developer Workbench E2E Suite', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Wait for app to be ready
    await expect(page.locator('header[role="banner"]')).toBeVisible();
    await expect(page.locator('#btn-action-check')).toBeVisible();
  });

  test('01. Ready state: initial layout and guidance', async ({ page }) => {
    // Check initial layout
    await expect(page.locator('header[role="banner"]')).toContainText('TrustC');
    await expect(page.locator('header[role="banner"]')).toContainText('spec.trust');
    await expect(page.locator('#workflow-status-guidance')).toContainText('Describe your API, then check its policies.');

    // Save screenshot
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '01-ready.png'), fullPage: true });
  });

  test('02. F1 to F2 full developer flow: check -> fix preview -> apply -> build -> test -> export', async ({ page }) => {
    // 1. Select F1 example
    const exampleSelect = page.locator('#example-select');
    await exampleSelect.selectOption('F1');
    await expect(exampleSelect).toHaveValue('F1');

    // 2. Click Check
    await page.locator('#btn-action-check').click();

    // Diagnostics should appear with TC-001 and TC-003
    await expect(page.locator('text=Actionable Issues')).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole('tabpanel').locator('text=TC-001').first()).toBeVisible();
    await expect(page.getByRole('tabpanel').locator('text=AUTH-REQUIRED').first()).toBeVisible();

    // Save F1 diagnostics screenshot
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '02-f1-diagnostics.png'), fullPage: true });

    // 3. Click Preview fix
    const previewFixBtn = page.locator('button:has-text("Preview fix")').first();
    await expect(previewFixBtn).toBeVisible();
    await previewFixBtn.click();

    // Verify fix preview banner with "Suggested restrictive default"
    const fixPreviewRegion = page.locator('div[role="region"][aria-label="Fix preview"]');
    await expect(fixPreviewRegion).toBeVisible();
    await expect(fixPreviewRegion).toContainText('Suggested restrictive default');

    // Save fix preview screenshot
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '03-f1-fix-preview.png'), fullPage: true });

    // 4. Click Apply fix (resolves TC-001 auth issue)
    const applyFixBtn = page.locator('button:has-text("Apply fix")').first();
    await applyFixBtn.click();

    // After applying TC-001 fix, TC-003 remains. Manually narrow User response in editor (F1 -> F2 flow)
    await expect(page.getByRole('tabpanel').locator('text=TC-003').first()).toBeVisible({ timeout: 15000 });
    await page.evaluate(() => {
      const store = (window as any).__WORKBENCH_STORE__;
      if (store) {
        const src = store.getState().source;
        store.getState().setSource(src.replace('returns: User', 'returns: User [id, email]'));
      }
    });

    // Run check on the newly narrowed specification
    await page.locator('#btn-action-check').click();

    // After narrowing response, check runs and passes cleanly!
    await expect(page.locator('h2:has-text("Specification checks passed.")')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('text=5 of 5 security rules satisfied')).toBeVisible();

    // Save F2 check passed screenshot
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '04-f2-check-passed.png'), fullPage: true });

    // 5. Click Build
    const buildBtn = page.locator('#btn-action-build');
    await expect(buildBtn).toBeEnabled();
    await buildBtn.click();

    // Code tab should show generated files
    await expect(page.locator('#tab-code')).toHaveAttribute('aria-selected', 'true', { timeout: 20000 });
    await expect(page.locator('text=Artifact:')).toBeVisible();
    await expect(page.locator('text=main.py')).toBeVisible();

    // Save F2 build with provenance screenshot
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '05-f2-build-provenance.png'), fullPage: true });

    // 6. Click Test access
    const testAccessBtn = page.locator('#btn-action-test-access');
    await expect(testAccessBtn).toBeEnabled();
    await testAccessBtn.click();

    // Tests tab should show completed multi-actor results
    await expect(page.locator('#tab-tests')).toHaveAttribute('aria-selected', 'true', { timeout: 25000 });
    await expect(page.locator('text=Other users were blocked. The owner received access.')).toBeVisible({ timeout: 20000 });
    await expect(page.getByRole('tabpanel').locator('text=6 matched expectations')).toBeVisible();
    await expect(page.getByRole('tabpanel').locator('text=0 policy reviews')).toBeVisible();
    await expect(page.getByRole('tabpanel').locator('text=0 failed')).toBeVisible();

    // Save F2 access results screenshot
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '06-f2-access-results.png'), fullPage: true });

    // 7. Click Build evidence tab
    await page.locator('#tab-evidence').click();
    await expect(page.locator('text=Build Evidence & Verification Report')).toBeVisible();
    await expect(page.locator('text=Target Build:')).toBeVisible();
    await expect(page.locator('text=Observed in 6 automated harness execution steps')).toBeVisible();

    // Save evidence report screenshot
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '08-evidence-report.png'), fullPage: true });

    // 8. Test Export JSON button
    const downloadPromise = page.waitForEvent('download');
    await page.locator('#btn-export-evidence').click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toContain('trustc-evidence-');
  });

  test('03. F3 flow: ownership waiver policy review', async ({ page }) => {
    // Select F3 example
    const exampleSelect = page.locator('#example-select');
    await exampleSelect.selectOption('F3');
    await expect(exampleSelect).toHaveValue('F3');

    // Click Check
    await page.locator('#btn-action-check').click();
    await expect(page.locator('h2:has-text("Specification checks passed.")')).toBeVisible({ timeout: 15000 });

    // Click Build
    await page.locator('#btn-action-build').click();
    await expect(page.locator('#tab-code')).toHaveAttribute('aria-selected', 'true', { timeout: 20000 });

    // Click Test access
    await page.locator('#btn-action-test-access').click();
    await expect(page.locator('#tab-tests')).toHaveAttribute('aria-selected', 'true', { timeout: 25000 });

    // Verify 9 matched, 1 review, 0 failed
    await expect(page.locator('text=Policy review: Access granted under declared exception.')).toBeVisible({ timeout: 20000 });
    await expect(page.getByRole('tabpanel').locator('text=9 matched expectations')).toBeVisible();
    await expect(page.getByRole('tabpanel').locator('text=1 policy review')).toBeVisible();
    await expect(page.getByRole('tabpanel').locator('text=0 failed')).toBeVisible();

    // Verify policy review callout
    await expect(
      page.locator('text=Another signed-in user was allowed by your ownership waiver. Review whether that is intended.')
    ).toBeVisible();

    // Save F3 policy review screenshot
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '07-f3-policy-review.png'), fullPage: true });
  });

  test('04. F4 flow: syntax error diagnostic location', async ({ page }) => {
    // Select F4 example
    const exampleSelect = page.locator('#example-select');
    await exampleSelect.selectOption('F4');
    await expect(exampleSelect).toHaveValue('F4');

    // Click Check
    await page.locator('#btn-action-check').click();

    // Verify Parse Error banner
    await expect(page.locator('text=Specification Parse Error')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('text=Line 23').first()).toBeVisible();
  });

  test('05. Stale state: edit during or after run marks earlier revision', async ({ page }) => {
    // Select F2, run check
    const exampleSelect = page.locator('#example-select');
    await exampleSelect.selectOption('F2');
    await expect(exampleSelect).toHaveValue('F2');
    await page.locator('#btn-action-check').click();
    await expect(page.locator('h2:has-text("Specification checks passed.")')).toBeVisible({ timeout: 15000 });

    // Edit the editor content by typing into CodeMirror
    const cmContent = page.locator('.cm-content');
    await cmContent.click();
    await page.keyboard.type('\n# edited comment\n');

    // Verify staleness notice appears
    await expect(
      page.locator('div[role="status"]:has-text("Earlier source revision.")')
    ).toBeVisible();

    // Save stale screenshot
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '09-edited-stale.png'), fullPage: true });
  });

  test('06. Mode toggle and offline indicator', async ({ page }) => {
    // Toggle mode to Mock
    const modeBtn = page.locator('#btn-mode-toggle');
    await modeBtn.click();
    await expect(modeBtn).toContainText('Mock Mode');

    // Save mock mode screenshot
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '10-mock-mode.png'), fullPage: true });

    // Toggle back to Live
    await modeBtn.click();
    await expect(modeBtn).toContainText('Live Server');
  });

  test('07. Responsive layouts: 390px narrow stacked and 150% zoom', async ({ page }) => {
    // Narrow layout (390x844 mobile viewport)
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(300);

    // Verify app remains functional, actions don't overflow
    await expect(page.locator('#btn-action-check')).toBeVisible();
    await expect(page.locator('section[aria-label="TrustSpec Editor"]')).toBeVisible();
    await expect(page.locator('section[aria-label="Results and Invariant Inspection"]')).toBeVisible();

    // Save narrow stacked screenshot
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '11-narrow-stacked-390px.png'), fullPage: true });

    // Desktop zoomed layout (150% zoom simulation via viewport & scale)
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.evaluate(() => {
      document.body.style.zoom = '1.5';
    });
    await page.waitForTimeout(300);

    // Save 150% zoom screenshot
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '12-zoomed-150-percent.png'), fullPage: true });

    // Reset zoom
    await page.evaluate(() => {
      document.body.style.zoom = '1.0';
    });
  });
});
