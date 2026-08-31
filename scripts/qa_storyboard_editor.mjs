// Browser integration against a separately launched local backend with TEMP data.
// Never run mutation tests against the user's normal port 8000 store.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {resolve,dirname} from 'node:path';
import assert from 'node:assert/strict';
const {chromium}=await import(pathToFileURL(resolve(process.argv[2])).href);
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const output=resolve(root,'evidence/storyboard-editor-qa');
await mkdir(output,{recursive:true});
const frontend='http://127.0.0.1:5173', testBackend='http://127.0.0.1:8123';
const endpoint='/api/videos/editor/solar';
const browser=await chromium.launch({channel:'msedge',headless:true});
const errors=[],external=[],requests=[],checks={};
async function waitAnalysis(page){await page.waitForFunction(()=>!document.querySelector('.editor-analysis')?.textContent.includes('正在检查')&&Boolean(document.querySelector('.editor-impact')));}
try{
  const page=await browser.newPage({viewport:{width:1440,height:1050},acceptDownloads:true});
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{requests.push({method:r.method(),path:new URL(r.url()).pathname});if(!r.url().startsWith(frontend+'/'))external.push(r.url());});
  await page.route('**/api/videos/editor/solar**',async route=>{
    const request=route.request();
    const response=await route.fetch({url:testBackend+new URL(request.url()).pathname});
    await route.fulfill({response});
  });
  await page.goto(frontend+'/?view=storyboard');
  await page.locator('.editor-card-heading h2').waitFor();await waitAnalysis(page);
  const get=async()=>{const r=await page.request.get(testBackend+endpoint);assert.equal(r.status(),200);return r.json();};
  const put=async data=>page.request.put(testBackend+endpoint,{data});
  let current=await get();
  // A repeat QA run restores the test database only, retaining test history.
  if(current.analysis.requires_recomposition){
    const zero=await (await page.request.get(testBackend+endpoint+'/versions/0')).json();
    assert.equal((await put({scenes:zero.scenes,expected_version:current.version,note:'QA isolated reset'})).status(),200);
    await page.reload();await waitAnalysis(page);current=await get();
  }
  const initial=current.version;
  await page.locator('.manual-editor > summary').click();
  await page.locator('.editor-scenes > button').nth(2).click();
  const subtitles=page.getByLabel('画面要点字幕',{exact:false});
  const previous=await subtitles.inputValue();
  await subtitles.fill(previous.replace('约8分钟：从太阳出发算起','从太阳出发，约8分钟到地球'));
  await waitAnalysis(page);
  assert.match(await page.locator('.editor-cost').innerText(),/0 \/ 7 镜待重配音/);
  assert.match(await page.locator('.editor-impact').innerText(),/复用原配音/);
  await page.getByLabel('本次修改说明',{exact:true}).fill('QA：仅修改第3镜字幕');
  await page.getByRole('button',{name:'保存草稿（不生成）',exact:true}).click();
  await page.waitForFunction(v=>document.querySelector('.editor-message')?.textContent.includes(`已保存草稿 v${v}`),initial+1);
  await page.reload();await waitAnalysis(page);await page.locator('.editor-scenes > button').nth(2).click();
  assert.match(await subtitles.inputValue(),/从太阳出发，约8分钟到地球/);
  await page.locator('.manual-editor > summary').click();
  checks.subtitle_only_reuses_all_audio_and_survives_reload=true;
  await page.locator('.editor-scenes > button').nth(0).click();
  const narration=page.getByLabel('AI旁白稿',{exact:false});
  await narration.fill((await narration.inputValue())+'先分清不同的信使。');await waitAnalysis(page);
  assert.match(await page.locator('.editor-cost').innerText(),/1 \/ 7 镜待重配音/);
  await page.getByLabel('本次修改说明',{exact:true}).fill('QA：第1镜旁白变更');
  await page.getByRole('button',{name:'保存草稿（不生成）',exact:true}).click();
  await page.waitForFunction(v=>document.querySelector('.editor-message')?.textContent.includes(`已保存草稿 v${v}`),initial+2);
  await page.locator('.editor-scenes > button').nth(3).click();
  await subtitles.fill((await subtitles.inputValue()).replace('卫星、航天员需要留意','留意卫星与航天员的风险'));await waitAnalysis(page);
  await page.getByLabel('本次修改说明',{exact:true}).fill('QA：后续字幕修改不得漏掉待重配旁白');
  await page.getByRole('button',{name:'保存草稿（不生成）',exact:true}).click();
  await page.waitForFunction(v=>document.querySelector('.editor-message')?.textContent.includes(`已保存草稿 v${v}`),initial+3);
  await waitAnalysis(page);assert.match(await page.locator('.editor-cost').innerText(),/1 \/ 7 镜待重配音/);
  checks.previous_pending_narration_is_retained=true;
  await page.getByLabel('参考历史版本',{exact:true}).selectOption('0');
  await page.getByRole('button',{name:'载入历史内容',exact:true}).click();await waitAnalysis(page);
  await page.getByRole('button',{name:'保存草稿（不生成）',exact:true}).click();
  await page.waitForFunction(v=>document.querySelector('.editor-message')?.textContent.includes(`已保存草稿 v${v}`),initial+4);
  current=await get();assert.equal(current.analysis.status,'matches_accepted_media');
  const old=await page.request.get(testBackend+endpoint+`/versions/${initial+2}`);assert.equal(old.status(),200);
  assert.match((await old.json()).scenes[0].narration,/先分清不同的信使/);
  checks.restore_is_append_only=true;
  // Simulate another tab saving while this page has an unsaved change.
  await page.locator('.editor-scenes > button').nth(0).click();
  await page.getByLabel('镜头标题',{exact:true}).fill('当前窗口尚未保存');await waitAnalysis(page);
  current.scenes[0].title='另一个窗口已保存';
  assert.equal((await put({scenes:current.scenes,expected_version:current.version,note:'QA competing window'})).status(),200);
  await page.getByLabel('本次修改说明',{exact:true}).fill('QA conflicting save');
  await page.getByRole('button',{name:'保存草稿（不生成）',exact:true}).click();
  await page.locator('[role=alert]').filter({hasText:'已有新版本'}).waitFor();
  assert.equal(await page.getByLabel('镜头标题',{exact:true}).inputValue(),'当前窗口尚未保存');
  const downloadPromise=page.waitForEvent('download');
  await page.getByRole('button',{name:'导出当前草稿 JSON',exact:true}).click();
  const download=await downloadPromise;
  const downloadPath=await download.path();
  const exported=JSON.parse(await readFile(downloadPath,'utf8'));
  assert.equal(exported.unsaved_changes,true);assert.equal(exported.scenes[0].title,'当前窗口尚未保存');
  checks.conflict_keeps_local_edits_exportable=true;
  page.once('dialog',dialog=>dialog.accept());await page.getByRole('button',{name:'加载最新',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.editor-message')?.textContent.includes('已加载最新保存的草稿'));
  await waitAnalysis(page);
  assert.equal(await page.getByLabel('镜头标题',{exact:true}).inputValue(),'另一个窗口已保存');
  await page.getByLabel('参考历史版本',{exact:true}).selectOption('0');await page.getByRole('button',{name:'载入历史内容',exact:true}).click();await waitAnalysis(page);
  await page.getByRole('button',{name:'保存草稿（不生成）',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.editor-message')?.textContent.includes('已保存草稿'));
  await waitAnalysis(page);
  await page.locator('.editor-scenes > button').nth(2).click();
  await page.waitForFunction(()=>{const v=document.querySelector('video');return v.readyState>=2&&!v.seeking&&v.currentTime>19.3&&v.currentTime<19.5;});
  checks.scene_picker_seeks_into_correct_baseline_scene=true;
  await page.screenshot({path:resolve(output,'desktop-1440.png'),fullPage:true});
  const desktop=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,editor:document.querySelector('.editor-form').getBoundingClientRect().height,viewport:innerHeight}));
  assert.ok(desktop.scroll<=desktop.width);assert.ok(desktop.editor<desktop.viewport);
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:resolve(output,'mobile-390.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.getByLabel('预排时长（秒）',{exact:true}).fill('3');await waitAnalysis(page);
  assert.match(await page.locator('.editor-analysis').innerText(),/不能截断/);
  checks.short_scene_blocks_render_without_calling_tts=true;
  checks.desktop_and_mobile_layout_passed=true;
  assert.equal(errors.length,0);assert.equal(external.length,0);
  assert.ok(requests.filter(r=>r.path.startsWith('/api/')).every(r=>r.path.startsWith(endpoint)));
  const report={status:'passed',checks,errors,external_requests:external,cloud_calls:0,desktop,
    data_scope:'isolated TEMP SQLite test database, not user drafts',version_start:initial,version_end:(await get()).version};
  await writeFile(resolve(output,'browser-report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));
}finally{await browser.close();}
