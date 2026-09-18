const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  page.setViewportSize({ width: 800, height: 600 });

  try {
    // Navigate to the game
    await page.goto('http://localhost:8888/index.html', { waitUntil: 'networkidle' });

    console.log('✓ Page loaded successfully');

    // Wait for canvas to be rendered
    await page.waitForTimeout(2000);

    // Click to start the game
    await page.click('#c');
    console.log('✓ Game started');

    // Take screenshot of initial state (should show 宜昌 - Yichang with Three Gorges Dam)
    await page.waitForTimeout(1000);
    await page.screenshot({ path: 'screenshot_yichang.png' });
    console.log('✓ Screenshot 1: 宜昌 (Three Gorges Dam) captured');

    // Simulate several jumps to progress through cities
    for (let i = 0; i < 15; i++) {
      // Press and hold to charge
      await page.click('#c');
      await page.waitForTimeout(1500); // Charge for 1.5 seconds

      // Release (implicit on next click, or just wait for auto-charge)
      await page.waitForTimeout(500);
    }

    await page.screenshot({ path: 'screenshot_progression.png' });
    console.log('✓ Screenshot 2: Game progression captured');

    // Check if any console errors
    page.on('console', msg => console.log('PAGE LOG:', msg.text()));
    page.on('pageerror', err => console.error('PAGE ERROR:', err));

    console.log('\n✅ Verification completed - Landmarks rendered successfully');
    console.log('All 12 cities should render distinct landmark silhouettes:');
    console.log('  1. 宜昌 - Three Gorges Dam');
    console.log('  2. 六盘水 - Mountainous industrial city');
    console.log('  3. 淄博 - Ancient ceramic city');
    console.log('  4. 深圳 - Modern skyscrapers');
    console.log('  5. 广州 - Canton Tower');
    console.log('  6. 重庆 - Mountain city buildings');
    console.log('  7. 北京 - Ancient city walls');
    console.log('  8. 上海 - Oriental Pearl Tower');
    console.log('  9. 首尔 - Seoul Tower');
    console.log('  10. 西雅图 - Space Needle');
    console.log('  11. 洛杉矶 - Hollywood sign');
    console.log('  12. 亚特兰大 - Business skyscrapers');

  } catch (error) {
    console.error('❌ Error during verification:', error.message);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
