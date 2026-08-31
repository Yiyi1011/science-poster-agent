import {pathToFileURL,fileURLToPath} from 'node:url';
import {resolve,dirname} from 'node:path';
import {writeFile,readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=await import(pathToFileURL(resolve(process.argv[2])).href);
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const out=resolve(root,'artifacts/video/solar-weather-v002-animation/qa-narrated-v001');
const base=process.argv[3]||'http://127.0.0.1:5173';
const source=JSON.parse(await readFile(resolve(root,'artifacts/video/solar-weather-v002-animation/storyboard-v003.json'),'utf8'));
const timeline=JSON.parse(await readFile(resolve(root,'artifacts/video/solar-weather-v002-animation/narration-v001/timeline-v001.json'),'utf8'));
const errors=[],external=[],failures=[],viewports=[];
const browser=await chromium.launch({channel:'msedge',headless:true});
try{
  for(const viewport of [{width:1280,height:1080},{width:390,height:844}]){
    const page=await browser.newPage({viewport});
    page.on('pageerror',e=>errors.push(e.message));
    page.on('request',r=>{if(/^https?:/.test(r.url())&&!r.url().startsWith(base+'/'))external.push(r.url());});
    page.on('response',r=>{if(r.status()>=400)failures.push({url:r.url(),status:r.status()});});
    await page.goto(base+'/solar-animation/voiced.html');
    await page.waitForFunction(()=>document.querySelector('video').readyState>=1);
    const initial=await page.evaluate(()=>{const v=document.querySelector('video');return {duration:v.duration,paused:v.paused,muted:v.muted,width:v.videoWidth,height:v.videoHeight,scroll:document.documentElement.scrollWidth,viewport:innerWidth};});
    assert.ok(Math.abs(initial.duration-timeline.duration_seconds)<0.08);
    assert.equal(initial.paused,true,'No autoplay');assert.equal(initial.muted,false);
    assert.ok(initial.scroll<=initial.viewport,'Horizontal overflow');
    assert.deepEqual(await page.locator('.transcript p').allTextContents(),source.scenes.map(s=>s.narration_draft));
    // The actual native HTML video must load and advance, not merely show a poster.
    await page.locator('video').evaluate(v=>{v.muted=true;return v.play();});
    await page.waitForFunction(()=>document.querySelector('video').currentTime>0.35);
    await page.locator('video').evaluate(v=>{v.pause();v.currentTime=25;});
    await page.waitForFunction(()=>{const v=document.querySelector('video');return !v.seeking&&v.readyState>=2;});
    await page.screenshot({path:resolve(out,`browser-${viewport.width}.png`)});
    for(const href of await page.locator('a[download]').evaluateAll(links=>links.map(a=>a.href))){
      const response=await page.request.get(href);assert.equal(response.status(),200);assert.ok((await response.body()).length>0);
    }
    viewports.push({...initial,playback_seek_download_transcript:'passed'});
    await page.close();
  }
  assert.equal(errors.length,0);assert.equal(external.length,0);assert.equal(failures.length,0);
}finally{await browser.close();}
const report={status:'passed',base,viewports,page_errors:errors,external_requests:external,http_failures:failures,cloud_calls:0,listening_review:'not_claimed'};
await writeFile(resolve(out,'browser-report.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify(report,null,2));
