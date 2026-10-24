// Génère les icônes PNG de la PWA à partir de static/icons/icon.svg.
// Usage : node scripts/render-icons.cjs   (nécessite playwright)
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
	const dir = path.join(__dirname, '..', 'frontend', 'static', 'icons');
	const svg = fs.readFileSync(path.join(dir, 'icon.svg'), 'utf8');
	const browser = await chromium.launch();
	for (const size of [192, 512]) {
		const page = await browser.newPage({ viewport: { width: size, height: size } });
		await page.setContent(
			`<html><body style="margin:0">${svg.replace('<svg ', `<svg width="${size}" height="${size}" `)}</body></html>`
		);
		await page.screenshot({ path: path.join(dir, `icon-${size}.png`), omitBackground: true });
		await page.close();
	}
	await browser.close();
})();
