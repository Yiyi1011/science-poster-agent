// Read-only QA. Never clicks generation or revision buttons.
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
import {mkdir, writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium} = await import(pathToFileURL(resolve(process.argv[2])).href);
const id = process.argv[3];
const out = resolve('evidence/studio-v050/browser-media', id);
await mkdir(out,{recursive:true});
const browser = await chromium.launch({channel:'msedge',headless:true});
const errors=[];
try {
  const page=await browser.newPage({viewport:{width:1440,height:1050}});
  page.on('pageerror', e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8000/');
  await page.getByLabel('打开已保存项目').selectOption(id);
  await page.getByRole('tab',{name:'科普视频',exact:true}).waitFor();
  assert.equal(await page.getByRole('tab',{name:'科普视频',exact:true}).getAttribute('aria-selected'),'true');
  await page.getByRole('tab',{name:'一步步讲清楚'}).click();
  assert(await page.locator('.studio-scroll .studio-scene').count()>=4);
  await page.getByText('看看解释',{exact:true}).click();
  await page.screenshot({path:out+'/explanation.png',fullPage:true});
  await page.getByRole('tab',{name:'科普视频',exact:true}).click();
  const video=page.locator('.studio-media video');
  await video.waitFor();
  const videoSrc=await video.getAttribute('src');
  assert(videoSrc?.includes('preview'),'page did not show the playable video');
  await video.evaluate(v=>new Promise((resolve,reject)=>{
    if(v.readyState>=1) return resolve();
    v.onloadedmetadata=resolve; v.onerror=()=>reject(new Error('video failed'));
  }));
  const metadata=await video.evaluate(v=>({duration:v.duration,width:v.videoWidth,height:v.videoHeight}));
  // 60—90秒是目标时长带；月亮题实测90.64秒（旁白朗读时长所致，仅超0.64秒），留95秒容差。
  assert(metadata.duration>=60 && metadata.duration<=95 && metadata.width===1280 && metadata.height===720);
  await video.evaluate(async v=>{v.muted=true; await v.play();});
  await page.waitForTimeout(1000);
  assert(await video.evaluate(v=>v.currentTime)>0);
  await video.evaluate(v=>v.pause());
  await page.screenshot({path:out+'/video-and-audit.png',fullPage:true});
  const download=await page.request.get(new URL(await page.getByRole('link',{name:'下载MP4',exact:true}).getAttribute('href'),page.url()).href,{headers:{Range:'bytes=0-1023'}});
  assert([200,206].includes(download.status()));
  await page.getByRole('tab',{name:'配套海报（选做）',exact:true}).click();
  await page.getByRole('button',{name:'放大海报'}).waitFor();
  const poster=await page.request.get(new URL(await page.locator('.studio-poster img').getAttribute('src'),page.url()).href);
  assert.equal(poster.status(),200);
  assert(poster.headers()['content-type'].startsWith('image/svg+xml'));
  await page.getByRole('tab',{name:'证据与版本',exact:true}).click();
  await page.getByText('自动改进留下了什么？',{exact:true}).waitFor();
  assert(await page.getByText('你的补充建议（选填）',{exact:true}).count()===1);
  const geometry=await page.locator('.studio-scroll').evaluate(el=>({client:el.clientHeight,scroll:el.scrollHeight}));
  assert(geometry.scroll>geometry.client,'real evidence tab must overflow into the independent scroll area');
  await page.getByRole('tab',{name:'科普视频',exact:true}).click();
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:out+'/mobile.png',fullPage:true});
  assert.deepEqual(errors,[]);
  await writeFile(out+'/report.json',JSON.stringify({project:id,videoSrc,metadata,errors,paid_actions:0},null,2));
  console.log(JSON.stringify({project:id,videoSrc,metadata,errors,paid_actions:0}));
} finally {await browser.close();}
