import { useEffect, useRef, useState } from "react";
import "./storyboard-editor.css";

type Scene = {
  scene_id: string; title: string; duration_seconds: number; narration: string;
  subtitle_cards: string[]; visual_direction: string;
};
type BaselineScene = Scene & { source_ids: string[]; boundary: string; audio_duration_seconds: number; media_start_seconds: number };
type SceneAnalysis = {
  scene_id: string; changed_fields: string[]; requires_tts: boolean; requires_render: boolean;
  requires_science_review: boolean; start_seconds: number; duration_seconds: number;
  issues: Array<{code: string; severity: string; message: string}>;
};
type Analysis = {
  scenes: SceneAnalysis[]; duration_seconds: number; tts_scene_count: number; tts_characters: number;
  estimated_tts_cost_cny: number; requires_recomposition: boolean; has_validation_errors: boolean;
  requires_science_review: boolean; status: string; cloud_calls: number; media_updated: boolean;
};
type Correction = {
  method: string; input_sha256: string; boundary: string;
  changes: Array<{scene_id:string;field:string;before:unknown;after:unknown;reason:string}>;
  skipped: Array<{scene_id:string;message:string}>;
};
type AutomaticRun = Correction & {
  run_id:string; result_version:number; base_version:number; completed_at:string;
  new_version_created:boolean; outcome:string; before_error_count:number; after_error_count:number;
  input_edits_before_automation:Array<{scene_id:string;fields:string[]}>;
  steps:Array<{label:string;status:string;at:string}>;
};
type Snapshot = {
  project_id: string; title: string; version: number; saved_at: string | null; note: string; scenes: Scene[];
  baseline_scenes: BaselineScene[]; media_url: string; media_version: string; acceptance: string;
  history: Array<{version: number; saved_at: string | null; note: string}>; analysis: Analysis;
  changes_from_previous: Array<{scene_id: string; fields: Record<string, {before: unknown; after: unknown}>}>;
  auto_correction?: Correction | null;
  automation_runs: AutomaticRun[];
};
const endpoint = "/api/videos/editor/solar";
const fieldNames: Record<string, string> = {title:"镜头标题", duration_seconds:"时长", narration:"旁白", subtitle_cards:"字幕", visual_direction:"画面说明"};

async function jsonRequest<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof data?.detail === "string" ? data.detail :
      response.status === 422 ? "内容不符合要求：每镜需填写标题、旁白、画面说明和1–6条非空字幕，时长为3–30秒。" : `请求失败（${response.status}），请检查本地后端是否启动。`;
    throw new Error(detail);
  }
  return data as T;
}
const clone = (scenes: Scene[]) => scenes.map(s => ({...s, subtitle_cards:[...s.subtitle_cards]}));
const displayDuration = (seconds: number) => Number(seconds.toFixed(3));

export default function StoryboardEditor() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [selected, setSelected] = useState(0);
  const [note, setNote] = useState("");
  const [historicalVersion, setHistoricalVersion] = useState("0");
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [autoRunning,setAutoRunning] = useState(false);
  const [selectedRunId,setSelectedRunId] = useState("");
  const retryRun = useRef<{fingerprint:string;run_id:string}|null>(null);
  const video = useRef<HTMLVideoElement>(null);
  const dirty = Boolean(snapshot && JSON.stringify(scenes) !== JSON.stringify(snapshot.scenes));

  function accept(data: Snapshot) {
    setSnapshot(data); setScenes(clone(data.scenes)); setAnalysis(data.analysis); setNote(""); setError("");
    setSelectedRunId("");
  }
  useEffect(() => {
    const controller = new AbortController();
    jsonRequest<Snapshot>(endpoint, {signal:controller.signal}).then(accept).catch(reason => {
      if (!controller.signal.aborted) setError(reason.message);
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!snapshot) return;
    // A saved response already includes server analysis. Avoid flashing stale
    // "baseline" badges while needlessly requesting the same analysis again.
    if(JSON.stringify(scenes)===JSON.stringify(snapshot.scenes)){
      setAnalysis(snapshot.analysis);setChecking(false);return;
    }
    const controller = new AbortController();
    setChecking(true); setAnalysis(null);
    const timer = window.setTimeout(() => {
      jsonRequest<Analysis>(endpoint+"/analyze", {
        method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({scenes}), signal:controller.signal,
      }).then(data => { if(!controller.signal.aborted){setAnalysis(data); setChecking(false); setError("");} })
        .catch(reason => { if(!controller.signal.aborted){setError(reason.message); setChecking(false);} });
    }, 300);
    return () => {window.clearTimeout(timer);controller.abort();};
  }, [scenes, snapshot]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {event.preventDefault(); event.returnValue="";};
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  function update(changes: Partial<Scene>) {
    setScenes(current => current.map((scene, i) => i === selected ? {...scene,...changes} : scene));
    setMessage("");
  }
  function selectScene(index: number) {
    setSelected(index);
    const player = video.current;
    if(player && snapshot && player.readyState >= 1){player.pause();player.currentTime=snapshot.baseline_scenes[index].media_start_seconds+0.125;}
  }
  async function save() {
    if (!snapshot || !dirty) return;
    setBusy(true);setError("");setMessage("");
    try {
      const data = await jsonRequest<Snapshot>(endpoint, {method:"PUT", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({expected_version:snapshot.version, scenes, note})});
      accept(data);setMessage(`已保存草稿 v${data.version}；原视频未改变，未调用付费模型。`);
    } catch(reason){setError(reason instanceof Error?reason.message:"保存失败");}
    finally{setBusy(false);}
  }
  async function reload() {
    if(dirty && !window.confirm("加载最新版本会放弃尚未保存的编辑。需要保留时，请先导出草稿。继续吗？"))return;
    setBusy(true);
    try{accept(await jsonRequest<Snapshot>(endpoint));setMessage("已加载最新保存的草稿。");}
    catch(reason){setError(reason instanceof Error?reason.message:"加载失败");}
    finally{setBusy(false);}
  }
  async function loadHistory() {
    if(dirty && !window.confirm("载入历史内容会替换当前未保存的编辑；不会删除已保存版本。继续吗？"))return;
    setBusy(true);
    try{
      const data=await jsonRequest<Snapshot>(`${endpoint}/versions/${historicalVersion}`);
      // Keep the latest expected_version: restoring creates a new immutable version.
      setScenes(clone(data.scenes));setNote(`参考历史 v${data.version} 恢复内容`);
      setMessage(`已把历史 v${data.version} 载入编辑区，点击保存才会创建新版本。`);setError("");
    }catch(reason){setError(reason instanceof Error?reason.message:"载入失败");}
    finally{setBusy(false);}
  }
  function exportDraft() {
    if(!snapshot)return;
    const payload={schema:"scivis.storyboard-draft.v1",project_id:snapshot.project_id,base_version:snapshot.version,
      unsaved_changes:dirty,note,scenes,analysis,baseline_scenes:snapshot.baseline_scenes,
      media_version:snapshot.media_version,media_updated:false,cloud_calls:0,exported_at:new Date().toISOString(),
      auto_correction:!dirty?snapshot.auto_correction:null,automation_runs:snapshot.automation_runs};
    const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:"application/json"}));
    const anchor=document.createElement("a");anchor.href=url;anchor.download=`solar-storyboard-v${snapshot.version}${dirty?"-unsaved":""}.json`;anchor.click();
    window.setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  async function runAutomatic() {
    if(!snapshot)return;
    setBusy(true);setAutoRunning(true);setError("");setMessage("");
    const input={scenes,expected_version:snapshot.version};
    const fingerprint=JSON.stringify(input);
    if(retryRun.current?.fingerprint!==fingerprint)retryRun.current={fingerprint,run_id:crypto.randomUUID()};
    try{
      const data=await jsonRequest<{snapshot:Snapshot;run:AutomaticRun;replayed:boolean}>(endpoint+"/auto-run",{
        method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({...input,run_id:retryRun.current.run_id})});
      accept(data.snapshot);retryRun.current=null;
      const result=data.run;
      setSelectedRunId(result.run_id);
      setMessage(`${result.changes.length?`系统已自动修正${result.changes.length}项`:'检查完成，没有可安全自动修改的项目'}；${result.new_version_created?`草稿 v${result.result_version} 已自动保存`:'已留存检查记录，未创建重复版本'}。${result.outcome==='needs_review'?'仍有待审核项。':''}原成片未改变。`);
      const first=data.snapshot.scenes.findIndex(s=>s.scene_id===result.changes[0]?.scene_id);
      if(first>=0)selectScene(first);
    }catch(reason){setError(reason instanceof TypeError?'连接中断，保存结果暂不确定。可再次点击自动修正，系统会复用运行编号，避免重复保存；也可加载最新查看记录。':reason instanceof Error?reason.message:"自动检查失败");}
    finally{setBusy(false);setAutoRunning(false);}
  }
  function loadCorrectionExample() {
    if(dirty&&!window.confirm("练习会替换第3镜第一条字幕，其他编辑保留。需要保留原字幕时请先导出草稿。继续吗？"))return;
    setScenes(current=>current.map((scene,i)=>i===2?{...scene,subtitle_cards:["耀斑发出的辐射约八分钟后到达地球，可能影响向阳一侧的部分短波通信。",...scene.subtitle_cards.slice(1)]}:scene));
    selectScene(2);
    setNote("练习输入：验证长字幕自动拆分与阅读时长调整");
    setMessage("已载入一条练习用长字幕，尚未保存；这不是模型错误证据，原成片不变。可点击自动修正按钮验证真实规则。");
  }
  const correction = snapshot?.automation_runs.find(run=>run.run_id===selectedRunId) || snapshot?.automation_runs[0];
  const currentRun = correction?.result_version===snapshot?.version&&!dirty;
  const corrected = (field:string) => currentRun&&correction?.changes.some(change=>change.scene_id===scenes[selected]?.scene_id&&change.field===field);
  const prettyValue = (value:unknown) => Array.isArray(value)?value.join("\n"):typeof value==="number"?`${displayDuration(value)}秒`:String(value);

  const active=scenes[selected];
  const baseline=snapshot?.baseline_scenes[selected];
  const review=analysis?.scenes[selected];
  return <main className="storyboard-editor">
    <header className="editor-header">
      <div><div className="eyebrow">SCIVIS / VIDEO WORKSHOP</div><h1>系统来修正，你来把关</h1><p>太阳的三位信使 · 自动检查、修正与留痕</p></div>
      <div className="editor-header-actions"><span className="editor-zero">本轮操作不调用模型</span><a href="/">返回海报创作</a></div>
    </header>
    <div className="editor-notice">点击一次，系统自动检查7个镜头、修正可处理的问题并保存记录。当前自动处理字幕与时长；旁白和科学含义改写、重新配音与视频重生成尚未接入，不会覆盖原成片。</div>
    {error && <p className="editor-error" role="alert">{error}</p>}
    {message && <p className="editor-message" role="status">{message}</p>}
    {!snapshot ? <section className="editor-loading"><p>{error?"暂时无法加载编辑器。请确认后端已启动后重试。":"正在加载已认可的7个镜头…"}</p>{error&&<button onClick={reload}>重试加载</button>}</section> : <>
      <div className="editor-toolbar">
        <span>草稿 <b>v{snapshot.version}</b> · <strong>{dirty?"有未保存修改":"已保存 / 基线"}</strong></span>
        <span>预计时长 <b>{analysis?displayDuration(analysis.duration_seconds):"—"}s</b></span>
        <div><button type="button" className="secondary" disabled={busy} onClick={reload}>加载最新</button><button type="button" className="secondary" disabled={busy} onClick={exportDraft}>导出当前草稿 JSON</button></div>
      </div>
      <section className="automation-workflow" aria-label="自动修正工作流" aria-busy={autoRunning}>
        <div className="automation-head"><div><span className="editor-small-heading">AUTOMATIC FIRST / 无需逐镜手改</span><h2>检查 → 自动修正 → 复检 → 留档</h2><p>只改检测到的问题。前后差异由系统记录，没有问题也会留下检查记录。</p></div>
          <button type="button" disabled={busy||checking||!analysis} onClick={runAutomatic}>{autoRunning?'正在自动检查、修正并保存…':'自动检查并修正'}</button>
        </div>
        {dirty&&<p className="automation-input-note">当前有未保存输入。本次运行会保留这些输入、自动修正后另存草稿；输入中的手动改动不会计作系统修正。</p>}
        {autoRunning&&<p role="status">系统正在执行本地检查与保存，请稍候。无需逐项确认。</p>}
        {correction&&<section className="correction-summary" aria-label="自动修正摘要">
          <div className="correction-stage">{currentRun?'自动流程已完成':'历史运行记录 · 当前内容已不同'} · v{correction.base_version} → v{correction.result_version} · {new Date(correction.completed_at).toLocaleString()}</div>
          <strong>{correction.changes.length?`${correction.changes.length}项自动修正 · 涉及${new Set(correction.changes.map(c=>c.scene_id)).size}个镜头`:'未发现可安全自动修正的项目'}{correction.outcome==='needs_review'?' · 仍需审核':''}</strong>
          <ol className="automation-steps">{correction.steps.map((step,i)=><li key={i} data-state={step.status}><span>{step.status==='needs_review'?'!':'✓'}</span>{step.label}{step.status==='no_change'?'（无需修改）':''}</li>)}</ol>
          <div className="automation-facts">格式阻断项 {correction.before_error_count} → {correction.after_error_count} · {correction.new_version_created?'已自动保存草稿':'已保存检查记录，不新增重复版本'}</div>
          {correction.changes.length>0&&<details><summary>查看修改前后</summary>{correction.changes.map(change=><div className="correction-diff" key={change.scene_id+change.field}><b>第{change.scene_id.slice(-1)}镜 · {fieldNames[change.field]||change.field}</b><div><span>修改前</span><del>{prettyValue(change.before)}</del></div><div><span>修改后</span><ins>{prettyValue(change.after)}</ins></div><p>{change.reason}</p></div>)}</details>}
          {correction.skipped.map((item,i)=><p key={i}>{item.scene_id}：{item.message}</p>)}
          {correction.input_edits_before_automation.length>0&&<small>运行前输入另有{correction.input_edits_before_automation.length}个镜头的改动，单独留档，不计入以上自动修正数量。</small>}
          <small>实际执行：本地规则修正，不是千问视觉审核。新成片未生成；科学表述仍需复核。</small>
        </section>}
        <details className="automation-history"><summary>检查记录与测试入口（可选）</summary>
          {snapshot.automation_runs.length>0&&<label>查看运行记录<select aria-label="查看运行记录" value={correction?.run_id||''} onChange={event=>setSelectedRunId(event.target.value)}>{snapshot.automation_runs.map(run=><option key={run.run_id} value={run.run_id}>{new Date(run.completed_at).toLocaleString()} · {run.changes.length}项修正 · v{run.result_version}</option>)}</select></label>}
          <p>如需验证效果，可载入一条明确标记的长字幕练习，再运行自动修正。这不是模型曾出错的证据，也不改变原成片。</p><button type="button" className="secondary" disabled={busy} onClick={loadCorrectionExample}>载入长字幕练习</button><small>最近10次运行可在此查看；完整记录保存在本地数据库。</small>
        </details>
      </section>
      <div className="editor-grid">
        <nav className="editor-scenes" aria-label="分镜列表">
          <div className="editor-small-heading">七个镜头 / 查看修正位置</div>
          {scenes.map((scene,index)=><button type="button" key={scene.scene_id} aria-pressed={index===selected} onClick={()=>selectScene(index)}>
            <span className="scene-index">{String(index+1).padStart(2,"0")}</span><span><strong>{scene.title||"未命名镜头"}</strong><small>{displayDuration(scene.duration_seconds)} 秒 · {analysis?(analysis.scenes[index]?.changed_fields.length?"有改动":"基线"):"待检查"}</small></span>
          </button>)}
          <div className="editor-history"><label>参考历史版本<select aria-label="参考历史版本" value={historicalVersion} onChange={event=>setHistoricalVersion(event.target.value)} disabled={busy}>{snapshot.history.map(item=><option key={item.version} value={String(item.version)}>v{item.version} · {item.note}</option>)}</select></label><button type="button" className="secondary" onClick={loadHistory} disabled={busy}>载入历史内容</button><small>保存后成为新版本，旧版本不会被覆盖。列表显示最近50版及基线。</small></div>
        </nav>
        <section className="editor-form" aria-label="镜头编辑">
          <div className="editor-card-heading"><span>SCENE {String(selected+1).padStart(2,"0")}</span><h2>{active.title}</h2><small>{active.scene_id}</small></div>
          <section className="scene-readonly" aria-label="当前分镜内容"><div><strong>旁白</strong><p>{active.narration}</p></div><div className={corrected('subtitle_cards')?'editor-auto-mark':undefined}><strong>画面要点字幕 {corrected('subtitle_cards')&&<em>系统已修正</em>}</strong><ul>{active.subtitle_cards.map((text,i)=><li key={i}>{text}</li>)}</ul></div><p className={corrected('duration_seconds')?'editor-auto-mark':undefined}>镜头时长 {displayDuration(active.duration_seconds)} 秒 {corrected('duration_seconds')&&<em>系统已修正</em>}</p><details><summary>画面与动作说明</summary><p>{active.visual_direction}</p></details></section>
          <details className="manual-editor"><summary>手动微调（可选）</summary><p>只有想亲自改内容时才展开。手动保存与系统自动修正分开记录。</p>
          <fieldset disabled={busy}>
            <div className="editor-split"><label>镜头标题<input maxLength={40} value={active.title} onChange={event=>update({title:event.target.value})}/></label><label className={corrected('duration_seconds')?'editor-auto-mark':undefined}>预排时长（秒）<input aria-label="预排时长（秒）" type="number" min={3} max={30} step="any" value={Number.isNaN(active.duration_seconds)?"":displayDuration(active.duration_seconds)} onChange={event=>update({duration_seconds:event.target.valueAsNumber})}/>{corrected('duration_seconds')&&<small>本次自动修正</small>}</label></div>
            <label>AI旁白稿 <small>{active.narration.length} 字符 · 修改后需重新配本镜头</small><textarea rows={4} maxLength={1500} value={active.narration} onChange={event=>update({narration:event.target.value})}/></label>
            <label className={corrected('subtitle_cards')?'editor-auto-mark':undefined}>画面要点字幕 <small>每行一条，1–6条；每条建议不超过18字</small><textarea rows={4} value={active.subtitle_cards.join("\n")} onChange={event=>update({subtitle_cards:event.target.value.split("\n")})}/>{corrected('subtitle_cards')&&<small>本次自动修正：只拆分，不改原文</small>}</label>
            <div className="editor-caption-counts">{active.subtitle_cards.map((caption,i)=><span key={i} className={[...caption].length>18?"too-long":""}>第{i+1}条：{[...caption].length}字</span>)}</div>
            <label>画面与动作说明 <small>记录待修改内容，不会在输入时自动生成动画</small><textarea rows={4} maxLength={1500} value={active.visual_direction} onChange={event=>update({visual_direction:event.target.value})}/></label>
          </fieldset>
          <div className="editor-evidence"><strong>保留科学边界</strong><p>{baseline?.boundary}</p><small>来源编号（锁定）：{baseline?.source_ids.join(" · ")}</small></div>
          <div className="editor-save"><label>本次修改说明<input placeholder="例如：第3镜字幕缩短，保留条件限定" value={note} maxLength={300} onChange={event=>setNote(event.target.value)} disabled={busy}/></label><button type="button" disabled={busy||checking||!analysis||!dirty||note.trim().length<2} onClick={save}>{busy?"正在保存…":"保存草稿（不生成）"}</button><small>质检问题可以随草稿保存，但必须处理后才能进入生成环节。</small></div>
          </details>
        </section>
        <aside className="editor-inspector">
          <section className="editor-media"><div className="editor-small-heading">对照：已认可的67秒成片 / 不随草稿改变</div><video ref={video} controls playsInline preload="metadata" src={snapshot.media_url} aria-label="已认可的成片对照" onLoadedMetadata={()=>{if(video.current)video.current.currentTime=snapshot.baseline_scenes[selected].media_start_seconds+0.125;}}/><a href="/solar-animation/voiced.html" target="_blank" rel="noopener noreferrer">打开大图播放与完整旁白 →</a><small>点击左侧镜头，可定位原片对应位置。</small></section>
          <section className="editor-analysis" aria-live="polite"><div className="editor-small-heading">本地检查 / 当前镜头</div>
            {checking?<p>正在检查修改影响…</p>:review?<>
              <div className="editor-impact"><span>配音</span><b>{review.requires_tts?"本镜头待重配":"复用原配音"}</b><span>画面</span><b>{review.requires_render?"待重新渲染":"保留原镜头"}</b></div>
              <p className="editor-changes">{review.changed_fields.length?`相对成片已改：${review.changed_fields.map(f=>fieldNames[f]||f).join("、")}`:"内容与已认可的成片基线一致。"}</p>
              {review.issues.map(issue=><p key={issue.code} className={`editor-issue ${issue.severity}`}>{issue.message}</p>)}
              {analysis&&<div className="editor-cost"><strong>整片修订清单</strong><p>{analysis.tts_scene_count} / 7 镜待重配音 · {7-analysis.tts_scene_count} 镜可复用录音</p><p>待配音原价估算：¥{analysis.estimated_tts_cost_cny.toFixed(4)}</p><small>这不是扣费。本页没有生成按钮；估算不含其他服务，实际费用以账单为准。</small><p>{analysis.has_validation_errors?"存在阻断项，需先修正。":analysis.requires_science_review?"存在内容改动，待科学复核。":analysis.requires_recomposition?"只涉及本地时序修改，仍需重新合成与验收。":"尚无需要重生成的内容。"}</p></div>}
            </>:<p>请先修正输入格式，再检查修改影响。</p>}
          </section>
          {snapshot.changes_from_previous.length>0&&<details className="editor-diff"><summary>最近一次保存改了什么？</summary>{snapshot.changes_from_previous.map(change=><div key={change.scene_id}><strong>{change.scene_id}</strong>{Object.entries(change.fields).map(([key,value])=><div key={key}><b>{fieldNames[key]||key}</b><p>之前：{Array.isArray(value.before)?value.before.join(" / "):String(value.before)}</p><p>之后：{Array.isArray(value.after)?value.after.join(" / "):String(value.after)}</p></div>)}</div>)}</details>}
        </aside>
      </div>
    </>}
  </main>;
}
