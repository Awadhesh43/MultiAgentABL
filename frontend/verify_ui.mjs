import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';

mkdirSync('screenshots', { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 950 } });
const errors = [];
page.on('console', (msg) => {
  if (msg.type() === 'error') errors.push(msg.text());
});
page.on('pageerror', (err) => errors.push('pageerror: ' + err.message));

async function shot(name) {
  await page.screenshot({ path: `screenshots/${name}.png` });
  console.log('screenshot:', name);
}

console.log('--- dashboard ---');
await page.goto('http://localhost:4200/dashboard', { waitUntil: 'networkidle' });
await page.waitForSelector('text=Portfolio', { timeout: 15000 });
await page.waitForSelector('table.deal-table tbody tr', { timeout: 15000 });
await shot('01-dashboard');

console.log('--- deal detail (first row) ---');
await page.click('table.deal-table tbody tr:first-child');
await page.waitForSelector('.deal-header h1', { timeout: 15000 });
await shot('02-deal-detail-overview');

console.log('--- deal detail: approvals tab ---');
await page.click('div.mat-mdc-tab-labels >> text=Approvals');
await page.waitForTimeout(500);
await shot('03-deal-detail-approvals');

console.log('--- global approvals inbox ---');
await page.click('a:has-text("Approvals")');
await page.waitForSelector('text=Approvals', { timeout: 15000 });
await page.waitForTimeout(500);
await shot('04-approvals-inbox');

console.log('--- decision dialog ---');
const reviewButtons = await page.locator('button:has-text("Review")').all();
if (reviewButtons.length) {
  await reviewButtons[0].click();
  await page.waitForSelector('app-decision-dialog', { timeout: 8000 });
  await page.waitForTimeout(500);
  await shot('05-decision-dialog');
  await page.click('button:has-text("Cancel")');
}

console.log('--- documents page ---');
await page.click('a:has-text("Document Intake")');
await page.waitForSelector('text=Document types', { timeout: 15000 });
await page.waitForTimeout(500);
await shot('06-documents');

await page.click('mat-expansion-panel-header >> nth=0');
await page.waitForTimeout(400);
await shot('07-documents-keyterms-expanded');

console.log('--- audit trail ---');
await page.click('a:has-text("Audit Trail")');
await page.waitForSelector('text=Hash chain', { timeout: 15000 });
await shot('08-audit');

console.log('--- wiki chat ---');
await page.click('a:has-text("ABL Wiki")');
await page.waitForSelector('text=ABL Wiki agent', { timeout: 15000 });
await shot('09-wiki-initial');

await page.click('button:has-text("What is a borrowing base and how is it calculated?")');
await page.waitForSelector('.bubble .citations', { timeout: 30000 });
await shot('10-wiki-answer');

console.log('--- console errors ---');
console.log(JSON.stringify(errors, null, 2));

await browser.close();
