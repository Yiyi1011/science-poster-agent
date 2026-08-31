import {readFile,writeFile,mkdir,access,stat} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {dirname,resolve,relative} from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';

// Local export only. CLI: node script.mjs <playwright/index.mjs> <ffmpeg.exe> [--narrated]
if(!process.argv[2]||!process.argv[3])throw new Error('Provide Playwright module path and local FFmpeg executable.');
const {chromium}=await import(pathToFileURL(resolve(process.argv[2])).href);
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const output=resolve(root,'artifacts/video/solar-weather-v002-animation');
const narrated=process.argv.includes('--narrated');
const videoPath=resolve(output,narrated?'solar-messengers-narrated-v001.mp4':'solar-messengers-silent-v001.mp4');
try{await access(videoPath);throw new Error('Export exists; retain it and choose a new version.');}catch(error){if(error.code!=='ENOENT')throw error;}
await mkdir(output,{recursive:true});
const sourcePath=resolve(root,'frontend/public/solar-animation/player.js');
const storyboard=JSON.parse(await readFile(resolve(output,'storyboard-v003.json'),'utf8'));
const timeline=narrated?JSON.parse(await readFile(resolve(output,'narration-v001/timeline-v001.json'),'utf8')):storyboard;
const sha=buffer=>createHash('sha256').update(buffer).digest('hex');
if(narrated){
  assert.equal(sha(await readFile(resolve(root,timeline.audio_path))),timeline.audio_sha256);
  assert.equal(sha(await readFile(resolve(output,'storyboard-v003.json'))),timeline.source_sha256);
}
const width=1280,height=720,fps=24,duration=timeline.duration_seconds,frames=Math.round(duration*fps);
const errors=[],externalRequests=[];
const browser=await chromium.launch({channel:'msedge',headless:true});
let encoder,completed=false,stderr='';
try {
  const page=await browser.newPage({viewport:{width:1280,height:1080}});
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{if(/^https?:/.test(request.url()))externalRequests.push(request.url());});
  await page.goto(pathToFileURL(resolve(root,'frontend/public/solar-animation/index.html')).href);
  await page.evaluate(()=>document.fonts.ready);
  const liveScenes=await page.evaluate(()=>scenes.map(s=>({duration:s.duration,voice:s.voice,sub:s.sub})));
  assert.deepEqual(liveScenes,storyboard.scenes.map(s=>({duration:s.duration_seconds,voice:s.narration_draft,sub:s.subtitle_cards})), 'Saved storyboard and player differ; review before export.');
  encoder=spawn(resolve(process.argv[3]),[
    '-hide_banner','-loglevel','error','-n','-f','image2pipe','-framerate',String(fps),'-vcodec','png','-i','pipe:0',
    ...(narrated?['-i',resolve(root,timeline.audio_path),'-map','0:v:0','-map','1:a:0','-c:a','aac','-b:a','128k']:['-an']),
    '-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',videoPath,
  ],{windowsHide:true,stdio:['pipe','ignore','pipe']});
  // Attach close/error listeners immediately so an early encoder failure is not lost.
  const completion=once(encoder,'close');
  completion.catch(()=>{});
  encoder.stderr.on('data',chunk=>{stderr=(stderr+chunk.toString()).slice(-8000);});
  let pipeError;
  encoder.stdin.on('error',error=>{pipeError=error;});
  await page.evaluate(()=>{
    window.exportCanvas=document.createElement('canvas');exportCanvas.width=1280;exportCanvas.height=720;
  });
  for(let frame=0;frame<frames;frame++) {
    if(pipeError)throw pipeError;
    const time=frame/fps;
    const sceneIndex=timeline.scenes.findIndex(s=>time<s.start_seconds+s.duration_seconds);
    const active=timeline.scenes[sceneIndex];
    const progress=(time-active.start_seconds)/active.duration_seconds;
    const sourceTime=storyboard.scenes[sceneIndex].start_seconds+progress*storyboard.scenes[sceneIndex].duration_seconds;
    const caption=active.subtitle_cards[Math.min(active.subtitle_cards.length-1,Math.floor(progress*active.subtitle_cards.length))];
    const png=await page.evaluate(({sourceTime,caption,narrated})=>{
      draw(sourceTime);
      const art=exportCanvas.getContext('2d');
      art.fillStyle='#0d2238';art.fillRect(0,0,1280,720);
      art.drawImage(canvas,64,0,1152,648);
      if(narrated){
        art.fillStyle='#0d2238';art.fillRect(64,592,1152,48);
        art.font="500 15px 'Microsoft YaHei',sans-serif";art.textAlign='right';art.fillStyle='#a4bbcc';
        art.fillText('示意不按比例 · AI旁白：千问 · 试听版',1170,620);
      }
      art.fillStyle='#081827';art.fillRect(0,643,1280,77);
      art.font="600 30px 'Microsoft YaHei',sans-serif";art.textAlign='center';art.fillStyle='#fff4ce';
      art.fillText(caption,640,688);
      return exportCanvas.toDataURL('image/png').split(',')[1];
    },{sourceTime,caption,narrated});
    const buffer=Buffer.from(png,'base64');
    if(!encoder.stdin.write(buffer))await once(encoder.stdin,'drain');
    if(frame===0||frame===29*fps||frame===57*fps)await writeFile(resolve(output,`export-frame-${Math.floor(time)}s-${narrated?'narrated-':''}v001.png`),buffer);
    if(frame%(fps*14)===0)console.log(`Rendering ${Math.round(frame/frames*100)}% (${frame}/${frames})`);
  }
  encoder.stdin.end();
  const [exitCode]=await completion;
  if(exitCode!==0)throw new Error(`FFmpeg failed: ${stderr}`);
  assert.equal(errors.length,0);assert.equal(externalRequests.length,0);
  completed=true;
} finally {
  if(!completed && encoder && encoder.exitCode===null)encoder.kill();
  await browser.close();
}
function timestamp(seconds){const ms=Math.round(seconds*1000);return `${String(Math.floor(ms/3600000)).padStart(2,'0')}:${String(Math.floor(ms/60000)%60).padStart(2,'0')}:${String(Math.floor(ms/1000)%60).padStart(2,'0')},${String(ms%1000).padStart(3,'0')}`;}
const subtitleBlocks=[],voiceLines=['# 太阳的三位信使｜已确认风格的配音稿','',
  '状态：待AI配音。305字，7场景；84秒是当前画面预排时间，不是已测量的语音时长。',
  '合成声音后按每段实际音频时长调整镜头与字幕，不能为了硬凑84秒加速到难以听懂。',
  '现有SRT是画面要点字幕，不是逐字语音转录；最终可另导出完整无障碍字幕。',''];
let index=1;
for(const scene of timeline.scenes){
  scene.subtitle_cards.forEach((caption,i)=>{const start=scene.start_seconds+i*scene.duration_seconds/scene.subtitle_cards.length;const end=scene.start_seconds+(i+1)*scene.duration_seconds/scene.subtitle_cards.length;subtitleBlocks.push(`${index++}\n${timestamp(start)} --> ${timestamp(end)}\n${caption}\n`);});
  voiceLines.push(`## ${scene.id}｜${scene.title}（画面预排${scene.duration_seconds}秒）`,'',scene.narration_draft,'',`边界：${scene.boundary}`,`来源：${scene.source_ids.join('、')}`,'');
}
await writeFile(resolve(output,narrated?'subtitles-summary-narrated-v001.srt':'subtitles-summary-timed-v001.srt'),subtitleBlocks.join('\n'),'utf8');
if(!narrated)await writeFile(resolve(output,'narration-ready-v001.md'),voiceLines.join('\n'),'utf8');
const manifest={generated_at:new Date().toISOString(),artifact_kind:narrated?'local_cartoon_with_qwen_narration':'local_silent_animatic_mp4',version:1,status:narrated?'awaiting_listening_review':'awaiting_ai_narration',
  video:relative(root,videoPath).replaceAll('\\','/'),width,height,fps,frames,duration_seconds:duration,audio_stream:narrated,
  subtitle_mode:'burned_in_summary_cards',subtitle_count:subtitleBlocks.length,source_script_sha256:sha(await readFile(sourcePath)),
  video_sha256:sha(await readFile(videoPath)),bytes:(await stat(videoPath)).size,cloud_calls:0,estimated_incremental_cloud_cost_cny:0,
  user_style_accepted:true,formal_audience_study_completed:false,final_submission_ready:false,page_errors:errors,automatic_external_requests:externalRequests};
if(narrated)Object.assign(manifest,{narration_model:timeline.model,narration_voice:timeline.voice,narration_estimated_cost_cny:timeline.estimated_cost_cny,narration_calls:7,narration_audio_sha256:timeline.audio_sha256,animation_generation:'manual_canvas_code',general_automatic_animation:false});
await writeFile(resolve(output,narrated?'mp4-narrated-manifest-v001.json':'mp4-export-manifest-v001.json'),JSON.stringify(manifest,null,2),'utf8');
console.log(JSON.stringify(manifest,null,2));
