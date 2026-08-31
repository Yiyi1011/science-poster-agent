import { pathToFileURL, fileURLToPath } from 'node:url';
import { resolve, dirname } from 'node:path';
import { mkdir, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

const { chromium } = await import(process.argv[2] ? pathToFileURL(resolve(process.argv[2])).href : 'playwright');
const root=resolve(dirname(fileURLToPath(import.meta.url)), '..');
const output=resolve(root,'artifacts/video/solar-weather-v002-animation/qa');
await mkdir(output,{recursive:true});
const url=pathToFileURL(resolve(root,'frontend/public/solar-animation/index.html')).href;
const browser=await chromium.launch({channel:'msedge',headless:true});
const errors=[],externalRequests=[];
const report={scene_screenshots:[],viewports:[],controls:{},errors,externalRequests};
try {
  for(const viewport of [{width:1280,height:1080},{width:390,height:844}]) {
    const page=await browser.newPage({viewport});
    page.on('pageerror',error=>errors.push(error.message));
    page.on('request',request=>{if(/^https?:/.test(request.url()))externalRequests.push(request.url());});
    for(const time of (viewport.width===1280?[4,15,29,41,57,69,80]:[29])) {
      await page.goto(`${url}?t=${time}`);
      await page.evaluate(()=>document.fonts.ready);
      const filename=viewport.width===1280?`scene-at-${time}s.png`:'mobile-390x844.png';
      await page.screenshot({path:resolve(output,filename)});
      report.scene_screenshots.push(filename);
    }
    const metrics=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,canvasRight:document.querySelector('canvas').getBoundingClientRect().right}));
    report.viewports.push(metrics);
    assert.ok(metrics.scroll<=metrics.width,`Horizontal overflow at ${metrics.width}: ${metrics.scroll}`);
    assert.ok(metrics.canvasRight<=metrics.width,'Canvas is clipped');
    await page.goto(url);
    await page.getByRole('button',{name:'播放',exact:true}).click();
    await page.waitForFunction(()=>position>0.3);
    await page.getByRole('button',{name:'暂停',exact:true}).click();
    assert.equal(await page.evaluate(()=>playing),false);
    const frameA=await page.locator('canvas').screenshot();
    await page.evaluate(()=>{position=7;sync();});
    const frameB=await page.locator('canvas').screenshot();
    assert.ok(!frameA.equals(frameB),'Animation frame did not change');
    await page.getByRole('button',{name:'3. 光先到',exact:true}).click();
    assert.equal(await page.evaluate(()=>position),21);
    await page.locator('#seek').fill('84');
    assert.equal(await page.locator('#next').isDisabled(),true);
    await page.getByRole('button',{name:'播放',exact:true}).click();
    assert.ok(await page.evaluate(()=>position)<2);
    report.controls[viewport.width]='play/pause/seek/chapter/restart/animated-pixels passed';
    await page.close();
  }
  assert.equal(errors.length,0);assert.equal(externalRequests.length,0);
  report.status='passed';
} finally {
  await browser.close();
  await writeFile(resolve(output,'browser-qa.json'),JSON.stringify(report,null,2),'utf8');
}
console.log(JSON.stringify(report,null,2));
