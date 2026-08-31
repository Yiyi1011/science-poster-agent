// Read-only browser QA of real saved projects. Never clicks generation / paid actions.
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
import {mkdir, writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium} = await import(pathToFileURL(resolve(process.argv[2])).href);
const ids = process.argv.slice(3);
const out = resolve('evidence/studio-v030/browser-real');
await mkdir(out,{recursive:true});
const browser = await chromium.launch({channel:'msedge',headless:true});
const errors=[], report=[];
try {
  const page = await browser.newPage({viewport:{width:1440,height:1050}});
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8000/');
  await page.getByLabel('打开已保存项目').waitFor();
  assert(await page.getByText('没有资料时，自动检索公开来源').isVisible());
  await page.screenshot({path:out+'/question-only-entry.png',fullPage:true});
  for(const id of ids) {
    const p=await (await page.request.get(`http://127.0.0.1:8000/api/studio/projects/${id}`)).json();
    const v=p.versions.at(-1);
    assert(v.draft.public_poster);
    assert(v.draft.scenes.length>=6 && v.draft.scenes.length<=8);
    await page.getByLabel('打开已保存项目').selectOption(id);
    await page.getByRole('button',{name:'放大海报'}).waitFor();
    await page.locator('.studio-poster img').evaluate(img=>img.decode());
    await page.screenshot({path:out+`/${id}-desktop.png`,fullPage:true});
    await page.getByRole('tab',{name:'独立分镜'}).click();
    assert.equal(await page.locator('.studio-scene').count(),v.draft.scenes.length);
    await page.screenshot({path:out+`/${id}-scenes.png`,fullPage:true});
    await page.getByRole('tab',{name:'图解海报'}).click();
    await page.getByRole('button',{name:'放大海报'}).click();
    await page.getByRole('dialog').waitFor();
    await page.keyboard.press('Escape');
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.screenshot({path:out+`/${id}-mobile.png`,fullPage:true});
    await page.setViewportSize({width:1440,height:1050});
    const svgPage=await browser.newPage({viewport:{width:1200,height:1800}});
    const response=await page.request.get(`http://127.0.0.1:8000/api/studio/projects/${id}/poster.svg`);
    assert.equal(response.status(),200);
    // Chromium's standalone SVG viewer can hang full-page capture. Inspect identical SVG in a plain document.
    const svgMarkup=await response.text();
    await svgPage.setContent('<!doctype html><html><meta charset="utf-8"><style>body{margin:0}svg{display:block}</style><body>'+svgMarkup+'</body></html>');
    await svgPage.evaluate(()=>document.fonts.ready);
    const bounds=await svgPage.evaluate(()=>{
      const svg=document.querySelector('svg');
      const {width,height}=svg.viewBox.baseVal;
      const texts=[...svg.querySelectorAll('text')];
      return {width,height,outside:texts.filter(t=>{const b=t.getBBox();return b.x<0||b.y<0||b.x+b.width>width||b.y+b.height>height;}).map(t=>t.textContent)};
    });
    assert.deepEqual(bounds.outside,[]);
    await svgPage.screenshot({path:out+`/${id}-poster.png`,fullPage:true});
    await svgPage.close();
    report.push({id,version:v.version,scenes:v.draft.scenes.length,review_status:v.review_status,bounds});
  }
  assert.deepEqual(errors,[]);
  await writeFile(out+'/report.json',JSON.stringify({report,errors},null,2));
  console.log(JSON.stringify({report,errors}));
} finally {await browser.close();}
