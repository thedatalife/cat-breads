// Probe: how fast does each Playwright browser configuration render the lounge's WebGL scene?
// Run from the Demo Studio folder so Playwright resolves:  S=<out dir> node probe-webgl-fps.mjs
// Serve the lounge first:  python3 -m http.server 8766 --directory web
//
// Results on Miles's Mac (M5 Max, Blender-exported lounge, 2026-10-16):
//   headless shell, dpr 2 (the studio's default)   SwiftShader     0.7 fps   cats loaded after 15.5 s
//   headless shell, dpr 1                          SwiftShader     1.0 fps   cats loaded after 20.0 s
//   full Chromium, new headless, --use-angle=metal  Apple M5 Max  121.0 fps   cats loaded after  7.1 s
//   full Chromium, headed                           Apple M5 Max  120.3 fps   cats loaded after  1.6 s
// Conclusion: capture WebGL pages with channel "chromium" + --use-angle=metal --ignore-gpu-blocklist
// (the studio's `launch` option), never the default headless shell.
import { chromium } from '/Users/miles/Code/remotion/node_modules/playwright/index.mjs';

const URL = 'http://127.0.0.1:8766/';
const S = process.env.S || '.';
const configs = [
  { label: 'headless-shell dpr2 (studio default)', launch: {}, dpr: 2 },
  { label: 'headless-shell dpr1', launch: {}, dpr: 1 },
  { label: 'chromium new-headless angle-metal dpr1', launch: { channel: 'chromium', args: ['--use-angle=metal', '--ignore-gpu-blocklist', '--enable-gpu-rasterization'] }, dpr: 1 },
  { label: 'headed dpr1', launch: { headless: false }, dpr: 1 },
];
for (const c of configs) {
  const t0 = Date.now(); let browser;
  try {
    browser = await chromium.launch(c.launch);
    const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: c.dpr });
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', (e) => errors.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
    await page.goto(URL, { waitUntil: 'networkidle', timeout: 60000 });
    const loadMs = Date.now() - t0;
    await page.waitForFunction(() => window.lounge && window.lounge.cats && window.lounge.cats.length >= 23, null, { timeout: 60000 }).catch(() => {});
    const catsMs = Date.now() - t0;
    const info = await page.evaluate(async () => {
      const cv = document.getElementById('c');
      const gl = cv.getContext('webgl2') || cv.getContext('webgl');
      const dbg = gl && gl.getExtension('WEBGL_debug_renderer_info');
      const renderer = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : 'n/a';
      const cats = window.lounge?.cats?.length ?? -1;
      const frames = await new Promise((res) => { let n = 0; const start = performance.now(); const tick = () => { n++; if (performance.now() - start < 3000) requestAnimationFrame(tick); else res(n); }; requestAnimationFrame(tick); });
      return { renderer, cats, fps: +(frames / 3).toFixed(1), dpr: window.devicePixelRatio };
    });
    await page.screenshot({ path: `${S}/probe-${c.label.replace(/[^a-z0-9]+/gi, '_')}.png` });
    console.log(JSON.stringify({ label: c.label, loadMs, catsMs, ...info, errors: errors.slice(0, 3) }));
    await browser.close();
  } catch (e) { console.log(JSON.stringify({ label: c.label, error: String(e).slice(0, 300) })); try { await browser?.close(); } catch {} }
}
