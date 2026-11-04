const fs = require('node:fs');
const assert = require('node:assert/strict');
const { chromium } = require('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');

(async () => {
  const fragment = fs.readFileSync('design-preview.html', 'utf8');
  const scripts = [...fragment.matchAll(/<script>([\s\S]*?)<\/script>/g)];
  scripts.forEach(match => new Function(match[1]));
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1024, height: 900 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    // Verify a sandboxed frame, including a host where optional Tweak is unavailable.
    await page.setContent('<iframe sandbox="allow-scripts" style="width:100%;height:880px;border:0"></iframe>');
    await page.locator('iframe').evaluate((frame, html) => { frame.srcdoc = html; }, fragment);
    const ui = page.frameLocator('iframe');
    await ui.locator('[data-grid] .mv-tile').first().waitFor();
    assert.equal(await ui.locator('[data-grid] .mv-tile').count(), 12);
    assert.ok(await ui.locator('.mv-logo').evaluate(image => image.complete && image.naturalWidth > 0));
    await ui.locator('[data-view="Videos"]').click();
    assert.equal(await ui.locator('.mv-duration').count(), 4);
    await ui.locator('.mv-tile').first().click();
    assert.equal(await ui.locator('[data-preview-name]').innerText(), 'A little adventure');
    assert.ok(await ui.locator('[data-player]').isVisible());
    await ui.locator('[data-view="People"]').click();
    assert.equal(await ui.locator('.mv-tile').count(), 2);
    assert.equal(await ui.locator('.mv-preview').isVisible(), false);
    await ui.locator('[data-view="Library"]').click();
    await ui.locator('input').fill('sunset');
    assert.equal(await ui.locator('.mv-tile').count(), 3);
    await ui.locator('input').fill('');
    await ui.locator('[data-view="Folders"]').click();
    assert.match(await ui.locator('.mv-folder').innerText(), /G:\\TK RESTORE\\PHOTOS/);
    await ui.locator('[data-view="Library"]').click();
    await ui.locator('[data-density]').click();
    await ui.locator('.mv-tile').first().click();
    assert.match(await ui.locator('[data-note]').innerText(), /Photo preview concept/);
    assert.equal(await ui.locator('[data-preview-name]').innerText(), 'Golden evening');
    assert.equal(await ui.locator('[data-player]').isVisible(), false);
    for (const width of [1024, 700, 320]) {
      await page.setViewportSize({ width, height: 1100 });
      const dimensions = await ui.locator('#tmv-design').evaluate(el => ({ width: el.ownerDocument.documentElement.clientWidth, scroll: el.ownerDocument.documentElement.scrollWidth }));
      assert.ok(dimensions.scroll <= dimensions.width + 1, `Overflow at ${width}: ${JSON.stringify(dimensions)}`);
    }
    await page.setViewportSize({ width: 1024, height: 1000 });
    await ui.locator('[data-density]').click();
    await page.locator('iframe').evaluate(frame => { frame.style.height = '1400px'; });
    await ui.locator('#tmv-design').screenshot({ path: 'design-preview-check.png' });
    // A failed or disabled script still leaves a populated visual.
    const staticPage = await browser.newPage({ javaScriptEnabled: false });
    await staticPage.setContent(fragment);
    assert.equal(await staticPage.locator('.mv-tile').count(), 12);
    assert.deepEqual(errors, []);
    console.log('PASS: sandbox startup; photos/videos/people/folders; search; density; selection; 320/700/1024px layout; script-disabled fallback; no page errors.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
