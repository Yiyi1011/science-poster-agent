import {readFile,writeFile,access} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {dirname,resolve} from 'node:path';
import vm from 'node:vm';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const source=await readFile(resolve(root,'frontend/public/solar-animation/player.js'),'utf8');
const end=source.indexOf('let cumulative=0;');
if(end<0)throw new Error('Cannot locate local scene data boundary');
const scenes=vm.runInNewContext(source.slice(0,end)+'\nscenes;');
const target=resolve(root,'artifacts/video/solar-weather-v002-animation/storyboard-v003.json');
try{await access(target);throw new Error('v003 already exists; preserve it and choose a new version.');}catch(error){if(error.code!=='ENOENT')throw error;}
let start=0;
const data={version:3,generated_at:new Date().toISOString(),status:'local_animatic_pending_audience_review',artifact_kind:'scripted_canvas_animatic',automatic_ai_generation:false,narration_synthesized:false,cloud_calls:0,scene_source:'frontend/public/solar-animation/player.js',duration_seconds:scenes.reduce((t,s)=>t+s.duration,0),scenes:scenes.map((s,i)=>{const out={id:`SW-A03-${i+1}`,start_seconds:start,duration_seconds:s.duration,title:s.name,narration_draft:s.voice,subtitle_cards:s.sub,source_ids:s.sources,boundary:s.note};start+=s.duration;return out;})};
await writeFile(target,JSON.stringify(data,null,2),'utf8');
console.log(JSON.stringify({version:data.version,duration_seconds:data.duration_seconds,scenes:data.scenes.length,narration_chars:scenes.reduce((n,s)=>n+s.voice.length,0),cloud_calls:0}));
