// Read-only integration check against normal local servers; never save test drafts.
import {pathToFileURL,fileURLToPath} from 'node:url';
import {dirname,resolve} from 'node:path';
import {writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=await import(pathToFileURL(resolve(process.argv[2])).href);
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const browser=await chromium.launch({channel:'msedge',headless:true});
const errors=[],external=[],apiRequests=[];
try{
  const page=await browser.newPage({viewport:{width:1440,height:1050}});
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{
    const url=new URL(request.url());
    if(!request.url().startsWith('http://127.0.0.1:5173/'))external.push(request.url());
    if(url.pathname.startsWith('/api/'))apiRequests.push({method:request.method(),path:url.pathname});
  });
  await page.goto('http://127.0.0.1:5173/?view=storyboard');
  await page.locator('.editor-impact').waitFor();
  assert.equal(await page.locator('.editor-scenes > button').count(),7);
  await page.locator('.editor-scenes > button').nth(2).click();
  await page.waitForFunction(()=>{const v=document.querySelector('video');return v.readyState>=2&&!v.seeking&&v.currentTime>19.3;});
  assert.match(await page.locator('.editor-card-heading').innerText(),/光先到/);
  await page.screenshot({path:resolve(root,'evidence/storyboard-editor-qa/live-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:resolve(root,'evidence/storyboard-editor-qa/live-mobile.png')});
  assert.equal(errors.length,0);assert.equal(external.length,0);
  assert.ok(apiRequests.every(r=>r.method==='GET'||(r.method==='POST'&&r.path==='/api/videos/editor/solar/analyze')));
  const report={status:'passed',errors,external_requests:external,api_requests:apiRequests,mutating_requests:0,cloud_calls:0};
  await writeFile(resolve(root,'evidence/storyboard-editor-qa/live-report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));
}finally{await browser.close();}
