// Read-only QA for the finished-work layout. Never clicks generation or paid actions.
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
import {mkdir, writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';

const {chromium} = await import(pathToFileURL(resolve(process.argv[2])).href);
const projectId = process.argv[3];
const out = resolve(process.argv[4] || 'evidence/studio-v056/browser-layout');
await mkdir(out, {recursive:true});
const browser = await chromium.launch({channel:'msedge', headless:true});
const errors = [];
try {
  const detail = await fetch(`http://127.0.0.1:8000/api/studio/projects/${projectId}`).then(response => response.json());
  const page = await browser.newPage({viewport:{width:1440,height:1000}});
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://127.0.0.1:8000/');
  await page.locator('.studio-saved > summary').click();
  const target = page.locator('.studio-saved-open').filter({hasText:detail.topic}).first();
  await target.click();
  await page.getByRole('tab',{name:'科普视频',exact:true}).waitFor();
  const video = page.locator('.studio-media video');
  await video.waitFor();
  await video.evaluate(element => new Promise((done, fail) => {
    if (element.readyState >= 1) return done();
    element.onloadedmetadata = done;
    element.onerror = () => fail(new Error('video metadata failed'));
  }));
  const metadata = await video.evaluate(element => ({duration:element.duration,width:element.videoWidth,height:element.videoHeight}));
  assert(metadata.duration >= 60 && metadata.duration <= 95, JSON.stringify(metadata));
  assert.equal(metadata.width,1280); assert.equal(metadata.height,720);
  await video.evaluate(async element => {element.muted=true; await element.play();});
  await page.waitForTimeout(500);
  assert(await video.evaluate(element => element.currentTime > 0));
  await video.evaluate(element => element.pause());
  const downloadHref = await page.getByRole('link',{name:'下载MP4',exact:true}).getAttribute('href');
  const download = await page.request.get(new URL(downloadHref,page.url()).href,{headers:{Range:'bytes=0-1023'}});
  assert([200,206].includes(download.status()));
  await page.getByRole('tab',{name:'证据与版本',exact:true}).click();
  await page.getByText(/2份原文摘录/).waitFor();
  await page.getByRole('tab',{name:'科普视频',exact:true}).click();
  const geometry = await page.evaluate(() => {
    const scroll = document.querySelector('.studio-scroll');
    const input = document.querySelector('.studio-input');
    const scrollStyle = getComputedStyle(scroll);
    const inputStyle = getComputedStyle(input);
    return {overflow:scrollStyle.overflowY,maxHeight:scrollStyle.maxHeight,inputPosition:inputStyle.position,
      pageWidth:document.documentElement.scrollWidth,viewportWidth:innerWidth};
  });
  assert.equal(geometry.overflow,'visible');
  assert.equal(geometry.maxHeight,'none');
  assert.equal(geometry.inputPosition,'sticky');
  assert(geometry.pageWidth<=geometry.viewportWidth);
  assert.equal(await page.getByRole('link',{name:/太阳动画|太阳分镜/}).count(),0);
  const colors = await page.evaluate(() => {
    const media=document.querySelector('.studio-media');
    const warning=document.createElement('div'); warning.className='studio-error'; warning.textContent='对比度测试'; media.append(warning);
    const result={foreground:getComputedStyle(warning).color,background:getComputedStyle(warning).backgroundColor}; warning.remove(); return result;
  });
  assert.notEqual(colors.foreground,'rgb(240, 248, 247)');
  assert.notEqual(colors.foreground,colors.background);
  await page.screenshot({path:resolve(out,'desktop-top.png'),fullPage:true});
  await page.evaluate(() => scrollTo(0, Math.max(0, document.body.scrollHeight * .45)));
  await page.waitForTimeout(150);
  await page.screenshot({path:resolve(out,'desktop-scrolled.png')});
  await page.setViewportSize({width:390,height:844});
  await page.evaluate(() => scrollTo(0,0));
  const mobileWidth = await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,viewport:innerWidth,
    offenders:[...document.querySelectorAll('body *')].map(el=>({tag:el.tagName,cls:el.className?.toString?.()||'',right:el.getBoundingClientRect().right,width:el.getBoundingClientRect().width})).filter(x=>x.right>innerWidth+1).slice(0,12)}));
  assert(mobileWidth.scroll<=mobileWidth.viewport,JSON.stringify(mobileWidth));
  await page.screenshot({path:resolve(out,'mobile.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  const report={projectId,geometry,metadata,warningColors:colors,errors,paid_actions:0};
  await writeFile(resolve(out,'report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
}
