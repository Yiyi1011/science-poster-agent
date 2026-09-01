import { FormEvent, useEffect, useRef, useState } from "react";
import "./studio.css";
import "./studio-updates.css";

type Source = { source_id: string; title: string; url: string; text: string };
type Input = { topic: string; audience: string; sources: Source[]; auto_sources?: boolean };
type Claim = { claim_id: string; text: string; source_id: string; quote: string; boundary: string };
type Scene = { scene_id: string; heading: string; narration: string; visual_action: string; claim_ids: string[]; role?: string };
type Draft = { title: string; takeaway: string; claims: Claim[]; diagram: { kind: string; labels: string[]; caption: string }; scenes: Scene[];
  explainer?: Array<{ heading: string; body: string; claim_ids: string[] }>; learning_check?: { question: string; answer: string } };
type Finding = { target: string; severity: string; message: string };
type Change = { field: string; before: unknown; after: unknown };
type Version = { version: number; draft: Draft; mode: string; model: string; review_status: string; changes: Change[];
  findings: Finding[]; detected_findings?: Finding[]; proposed_changes?: Change[]; mechanical_changes?: Array<Change & { reason: string }>;
  calls: Array<{ model: string; request_id: string; purpose: string }>; fallback?: boolean; fallback_reason?: string };
type CartoonPlan = { actors: Array<{ icon: string; label: string; explanation: string }>; relationship: string; caption: string };
const cartoonDiff = (before?: CartoonPlan, after?: CartoonPlan) => {
  if (!before || !after) return [];
  const entries = (p: CartoonPlan): Record<string,string> => ({ "关系类型": p.relationship, "说明句": p.caption,
    ...Object.fromEntries(p.actors.flatMap((a,i) => [[`对象${i+1}·图标`,a.icon],[`对象${i+1}·标签`,a.label],[`对象${i+1}·解释`,a.explanation]])) });
  const a=entries(before), b=entries(after);
  return [...new Set([...Object.keys(a),...Object.keys(b)])].filter(k=>a[k]!==b[k]).map(k=>({field:k,before:a[k]??"（无）",after:b[k]??"（移除）"}));
};
type Media = { id: string; version: number; state: string; stage: string; video?: string; poster?: string; duration_seconds?: number; kind: string; resumed_from?: string;
  events?: Array<{ at: string; stage: string }>;
  render_revisions?: Array<{reason:string;previous_video:string;video:string}>;
  structure_repairs?: Array<{stage:string;state:string;errors?:Array<{field:string;type:string}>;final_errors?:Array<{field:string;type:string}>}>;
  mechanical_repairs?: Array<{field:string;before:string;after:string;reason:string}>;
  failure_details?: Array<{field:string;type:string}>;
  human_reviews?: Array<{ reviewer: string; issues: string[]; status: string }>;
  scenes: Array<{ scene_id: string; accepted: string; candidates: Array<{ file: string; attempt: number; correction: string; plan?: CartoonPlan; review?: { status: string; issues: string[] } }> }> };
type Project = { id: string; input: Input; versions: Version[]; runs: Array<{ id: string; state: string; stage: string; error: string }>; media?: Media[] };
type Research = { sources: Source[]; selected: Array<{ source_id: string; reason: string }>; events: Array<{ url: string; state: string }>;
  gap: string; explanation?: { answer: string; domain: string }; calls: Array<{ model: string; purpose: string; request_id: string }> };
type Summary = { id: string; topic: string };
const blankSource = (): Source => ({ source_id: "S1", title: "", url: "", text: "" });
const blankInput = (): Input => ({ topic: "", audience: "普通公众", sources: [blankSource()], auto_sources: true });
const roleNames: Record<string, string> = { hook: "问题引入", example: "生活情境", mechanism: "机制解释", process: "逐步展开", misconception: "常见误会", boundary: "适用边界", takeaway: "记住要点" };
const api = "/api/studio";

async function request<T>(url: string, data?: unknown): Promise<T> {
  const response = await fetch(url, data === undefined ? undefined : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
  const result = await response.json();
  if (!response.ok) {
    const detail = result?.detail;
    throw new Error(typeof detail === "string" ? detail : Array.isArray(detail)
      ? detail.map((v: { loc: string[]; msg: string }) => `${v.loc.slice(1).join(" / ")}：${v.msg}`).join("；") : `请求失败 ${response.status}`);
  }
  return result as T;
}

const display = (value: unknown) => typeof value === "string" ? value : JSON.stringify(value);
const fieldLabel = (path: string) => path.replaceAll("scenes", "分镜").replaceAll("claims", "事实")
  .replaceAll("narration", "旁白").replaceAll("visual_action", "画面动作").replaceAll("boundary", "适用边界")
  .replaceAll("takeaway", "核心结论").replaceAll("heading", "小标题").replaceAll("title", "标题")
  .replaceAll("diagram", "图解").replaceAll("text", "文字").replaceAll("public_poster", "公众海报")
  .replaceAll("cards", "知识点").replaceAll("example", "情境").replaceAll("caution", "提醒")
  .replaceAll("nodes", "节点").replaceAll("body", "解释").replaceAll("detail", "说明").replaceAll("role", "叙事环节")
  .replaceAll("explainer", "详细讲解").replaceAll("learning_check", "理解小问题");

function ProductionProgress({ stage, events = [] }: { stage: string; events?: Array<{ at: string; stage: string }> }) {
  const visible = events.slice(-6);
  return <section className="studio-progress" aria-live="polite" aria-label="视频生成进度">
    <div className="studio-progress-now"><span aria-hidden="true" /><div><small>自动制作正在进行</small><h3>{stage || "正在准备资料与创作任务"}</h3></div></div>
    {visible.length ? <ol>{visible.map((event, index) => <li className={index === visible.length - 1 ? "current" : "done"} key={`${event.at}-${index}`}>
      <span aria-hidden="true">{index === visible.length - 1 ? "●" : "✓"}</span><div><strong>{event.stage}</strong><small>{new Date(event.at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</small></div>
    </li>)}</ol> : <ol className="studio-progress-plan"><li className="current"><span>●</span><div><strong>{stage || "检索并核对资料"}</strong><small>完成后将自动进入讲解、审核、卡通规划、配音字幕与合成</small></div></li></ol>}
    <p>页面会自动读取真实执行进度，无需重复点击。自动修正会留下记录；视频完成后这里会直接切换为播放器。</p>
  </section>;
}

export default function Studio() {
  const [input, setInput] = useState<Input>(blankInput);
  const [presets, setPresets] = useState<Input[]>([]);
  const [projects, setProjects] = useState<Summary[]>([]);
  const [project, setProject] = useState<(Project & { research?: Research | null }) | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [rebuild, setRebuild] = useState(false);
  const [tab, setTab] = useState("scenes");
  const [textOnly, setTextOnly] = useState(false);
  const [history, setHistory] = useState(0);
  const [config, setConfig] = useState<{ mock_ai: boolean; text_model: string; studio_model?: string } | null>(null);
  const [preview, setPreview] = useState(false);
  const [sceneIndex, setSceneIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const retry = useRef<{ project: string; version: number; feedback: string; request_id: string; rebuild: boolean; make_video: boolean } | null>(null);
  const mediaRetry = useRef<{ project: string; version: number; request_id: string } | null>(null);
  const selectedId = useRef("");
  const running = Boolean(project?.runs.some(r => r.state === "running") || project?.media?.some(m => m.state === "running"));
  const latest = project?.versions.at(-1);
  const version = project?.versions.find(v => v.version === history) ?? latest;
  const draft = version?.draft;
  const run = project?.runs.at(-1);
  const locked = busy || running;
  const posterUrl = project && version ? `${api}/projects/${project.id}/poster.svg?revision=${version.version}` : "";
  const versionMedia = project?.media?.filter(m => m.version === version?.version) ?? [];
  const selectedMedia = [...versionMedia].reverse().find(m => m.state === "succeeded" && Boolean(m.video)) ?? versionMedia.at(-1);
  const activeMedia = [...versionMedia].reverse().find(m => m.state === "running");
  const activeStage = activeMedia?.stage || (run?.state === "running" ? run.stage : "");
  const failedMediaCount = versionMedia.filter(m => m.state === "failed").length;
  const mediaUrl = (name: string) => `${api}/projects/${project!.id}/media/${selectedMedia!.id}/${encodeURIComponent(name)}`;

  useEffect(() => { Promise.all([request<Input[]>(`${api}/presets`), request<Summary[]>(`${api}/projects`), request<{ mock_ai: boolean; text_model: string }>("/api/config/public")])
    .then(([p, list, c]) => { setPresets(p); setProjects(list); setConfig(c); }).catch(e => setError(e.message)); }, []);

  useEffect(() => {
    if (!project || !running) return;
    const id = project.id;
    let cancelled = false;
    let timer: number;
    const poll = async () => {
      try { const value = await request<Project>(`${api}/projects/${id}`);
        if (!cancelled && selectedId.current === id) { setProject(value); setError(""); }
      } catch { if (!cancelled) setError("连接暂时中断，正在重新读取进度；不会重复发送生成请求。"); }
      if (!cancelled) timer = window.setTimeout(poll, 1500);
    };
    timer = window.setTimeout(poll, 1000);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [project?.id, running]);

  useEffect(() => {
    if (!playing || !draft) return;
    const scene = draft.scenes[sceneIndex];
    const timer = window.setTimeout(() => {
      if (sceneIndex + 1 < draft.scenes.length) setSceneIndex(sceneIndex + 1);
      else setPlaying(false);
    }, Math.max(6, Math.ceil(scene.narration.length / 3.5)) * 1000);
    return () => clearTimeout(timer);
  }, [playing, sceneIndex, draft]);

  useEffect(() => {
    if (!preview) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setPreview(false); };
    window.addEventListener("keydown", close);
    return () => { document.body.style.overflow = previous; window.removeEventListener("keydown", close); };
  }, [preview]);

  function newInput(value: Input) {
    selectedId.current = ""; setProject(null); setInput(structuredClone(value)); setHistory(0); setPlaying(false);
    setSceneIndex(0); setFeedback(""); setError(""); retry.current = null;
    setRebuild(false); setTab("scenes"); setTextOnly(false);
  }

  async function openProject(id: string) {
    selectedId.current = id; setBusy(true); setError(""); setPlaying(false); setSceneIndex(0); setHistory(0); setRebuild(false); setTab("scenes");
    try { const value = await request<Project & { research?: Research }>(`${api}/projects/${id}`); if (selectedId.current === id) { setProject(value); setInput(value.input); } }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  async function runProject(value: Project, note = "") {
    const number = value.versions.at(-1)?.version ?? 0;
    const previous = retry.current;
    const operation = previous?.project === value.id && previous.version === number && previous.feedback === note && previous.rebuild === rebuild && previous.make_video === !textOnly ? previous
      : { project: value.id, version: number, feedback: note, request_id: crypto.randomUUID(), rebuild, make_video: !textOnly };
    retry.current = operation;
    const next = await request<Project>(`${api}/projects/${value.id}/run`, { request_id: operation.request_id, expected_version: number, feedback: note, rebuild: operation.rebuild, make_video: operation.make_video });
    setTab(operation.make_video ? "scenes" : "explain");
    setProject(next); retry.current = null; setHistory(0); setSceneIndex(0); setPlaying(false);
  }

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const value = project ?? await request<Project>(`${api}/projects`, { ...input, sources: input.sources.filter(s => s.text.trim()) });
      selectedId.current = value.id; setProject(value);
      setProjects(await request<Summary[]>(`${api}/projects`));
      await runProject(value);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  async function revise() {
    if (!project) return;
    setBusy(true); setError("");
    try { await runProject(project, feedback); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  async function generateMedia() {
    if (!project || !version) return;
    setBusy(true); setError("");
    const previous = mediaRetry.current;
    const operation = previous?.project === project.id && previous.version === version.version ? previous :
      { project: project.id, version: version.version, request_id: crypto.randomUUID() };
    mediaRetry.current = operation;
    try {
      setProject(await request<Project>(`${api}/projects/${project.id}/media`, { request_id: operation.request_id, expected_version: operation.version, renderer: "cartoon" }));
      mediaRetry.current = null;
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  async function upload(file: File | undefined, index: number) {
    if (!file) return;
    if (!/\.(txt|md)$/i.test(file.name) || file.size > 100000) { setError("当前支持100KB以内的UTF-8 TXT/Markdown摘录；PDF请先复制相关正文。"); return; }
    try {
      const text = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer());
      if (text.length > 15000) throw new Error("单份资料最多15000字，请精选摘录。");
      editSource(index, { title: file.name, text }); setError("");
    } catch (e) { setError(`文件读取失败：${(e as Error).message}`); }
  }

  function editSource(index: number, patch: Partial<Source>) {
    setInput(v => ({ ...v, sources: v.sources.map((s, i) => i === index ? { ...s, ...patch } : s) }));
  }

  return <main className="studio">
    <header className="studio-header"><a href="/?view=legacy">SCIVIS / 科学可视化</a><nav><a href="/solar-animation/voiced.html">太阳动画</a><a href="/?view=storyboard">太阳分镜</a></nav></header>
    <section className="studio-intro"><span>从一个问题，到一段看得懂的科普视频</span><h1>让知识，动起来。</h1><p>提出问题，自动找资料、讲清楚、做成卡通视频。海报是后续选项。</p>
      <small className="studio-model">{config ? config.mock_ai ? "Mock演示 · 不调用模型" : `阿里云百炼 · ${config.studio_model ?? config.text_model} · 北京` : "正在读取模型配置…"}</small></section>
    <div className="studio-grid">
      <aside className="studio-input">
        <div className="studio-section-title"><h2>01 定义这次创作</h2><button type="button" disabled={locked} onClick={() => newInput(blankInput())}>新建</button></div>
        <div className="studio-presets">{presets.map((p, i) => <button key={p.topic} disabled={locked} onClick={() => newInput(p)}>{i === 0 ? "AI为何会答错" : "间隔学习"} ↗</button>)}</div>
        <label>打开已保存项目<select aria-label="打开已保存项目" value={project?.id ?? ""} disabled={locked} onChange={e => e.target.value && void openProject(e.target.value)}><option value="">新项目</option>{projects.map(p => <option key={p.id} value={p.id}>{p.topic}</option>)}</select></label>
        <form onSubmit={submit}>
          <fieldset disabled={locked || Boolean(project)}><label>你想解释什么？<input required minLength={2} maxLength={160} value={input.topic} onChange={e => setInput({ ...input, topic: e.target.value })} placeholder="例如：为什么重复复习要隔一段时间？" /></label>
            <label>讲给谁听？<select value={input.audience} onChange={e => setInput({ ...input, audience: e.target.value })}><option>普通公众</option><option>初中生</option><option>大学新生</option></select></label>
            <label className="studio-auto-source"><input type="checkbox" checked={Boolean(input.auto_sources)} onChange={e => setInput({ ...input, auto_sources: e.target.checked })} />没有资料时，自动检索公开来源</label>
            <p className="studio-hint">千问先作初步解释，再按领域查官方文档或研究原文。初步回答不冒充核实结论；有手动资料时优先使用你的资料。</p>
            <details className="studio-source-options" open={input.sources.some(s => Boolean(s.text))}><summary>我有资料，手动补充（选填）</summary>
            {input.sources.map((s, i) => <details className="studio-source" key={s.source_id} open={!project && i === 0}><summary>{s.source_id} · {s.title || "添加一份科学资料"}</summary>
              <label>资料名称<input required={Boolean(s.text)} minLength={2} maxLength={160} value={s.title} onChange={e => editSource(i, { title: e.target.value })} /></label>
              <label>公开来源链接（选填，不自动抓取）<input type="url" value={s.url} onChange={e => editSource(i, { url: e.target.value })} placeholder="https://…" /></label>
              <label>与问题相关的资料摘录<textarea rows={6} value={s.text} minLength={20} maxLength={15000} onChange={e => editSource(i, { text: e.target.value })} placeholder="粘贴正文，不要只贴链接。无资料时会停止生成，不会编造证据。" /></label>
              <label className="studio-file">或导入 TXT / MD<input type="file" accept=".txt,.md" onChange={e => void upload(e.target.files?.[0], i)} /></label></details>)}
            <button type="button" disabled={input.sources.length >= 6} onClick={() => setInput({ ...input, sources: [...input.sources, { ...blankSource(), source_id: `S${input.sources.length + 1}` }] })}>＋ 添加来源</button>
            </details>
          </fieldset>
          {project && <p className="studio-hint">资料已随项目保存。更换资料请<button type="button" className="studio-link" disabled={locked} onClick={() => newInput(input)}>复制为新项目</button>，旧作品不会被覆盖。</p>}
          <label className="studio-auto-source"><input type="checkbox" checked={textOnly} disabled={locked} onChange={e => setTextOnly(e.target.checked)} />这次只准备讲解与脚本，暂不制片</label>
          <p className="studio-hint">默认自动制作AI旁白＋字幕的卡通视频，目标约60—90秒；会调用百炼并产生费用。资料或检查不通过会停止。</p>
          <button className="studio-primary" disabled={locked || Boolean(latest)}>{locked ? "处理中，请稍候…" : latest ? "已保存 · 在右侧查看或修订" : textOnly ? "生成讲解并自动审核 →" : "生成科普视频 →"}</button>
        </form>
        <p className="studio-hint">资料仅进入本项目，不混用太阳知识库。提交后会发送至百炼；请勿粘贴密钥或未获授权的私人资料。</p>
        {error && <p role="alert" className="studio-error">{error}</p>}
      </aside>
      <section className="studio-results" aria-label="创作结果">
        <div className="studio-result-header"><h2>02 作品与改进</h2>{(run || selectedMedia) && <span role="status" className={running ? "studio-working" : ""}>{activeStage || selectedMedia?.stage || run?.stage}</span>}</div>
        {run?.error && <p className="studio-error">{run.error}</p>}
        {project?.research?.explanation && <details className="studio-research" open={!draft}><summary>先听个明白 · 千问初步解释（未核实）</summary><p>{project.research.explanation.answer}</p><small>模型基础知识回答，尚未独立核实；下面的资料与最终作品可能纠正它。不是论文摘录或审核结论。</small></details>}
        {project?.research && !project.research.sources.length && !running && <div className="studio-research"><button onClick={() => newInput(input)}>复制问题，使用新版重新检索</button><small>旧失败记录保留；复制后点击生成会发起新的百炼调用。</small></div>}
        {project?.research && <details className="studio-research"><summary>自动查找的资料 · {project.research.sources.length}份原文摘录</summary>
          {project.research.sources.map(s => <article key={s.source_id}><a href={s.url} target="_blank" rel="noopener noreferrer">{s.source_id} · {s.title} ↗</a><p>{project.research!.selected.find(p => p.source_id === s.source_id)?.reason}</p><details><summary>查看原文摘录</summary><blockquote>{s.text}</blockquote></details></article>)}
          {project.research.gap && <p>{project.research.gap}</p>}<small>搜索命中和逐字匹配不等于科学认证。自动读取暂限公开HTML；不会绕过付费墙或登录。</small>
          <details><summary>检索与读取记录</summary>{project.research.events.map((event, i) => <p key={i}>{event.state}{event.url ? ` · ${new URL(event.url).hostname}` : ""}</p>)}{project.research.calls.map((call, i) => <p key={i}>{call.model} · {call.purpose}<br /><small>{call.request_id}</small></p>)}</details>
        </details>}
        {!draft ? running ? <div className="studio-progress-wrap"><ProductionProgress stage={activeStage || run?.stage || "正在查找并核对资料"} events={activeMedia?.events} /></div> : <div className="studio-empty"><div className="studio-orbit">✦</div><h3>一个问题，一段科普</h3><p>卡通视频会在这里呈现。讲解、证据与修改记录一并保留，海报按需查看。</p><small>所有进度来自实际执行阶段，不用倒计时假装完成。</small></div> : <>
          <div className="studio-toolbar"><div role="tablist" aria-label="作品视图">{[["scenes", "科普视频"], ["explain", "一步步讲清楚"], ["poster", "配套海报（选做）"], ["evidence", "证据与版本"]].map(([key, label]) => <button key={key} role="tab" aria-selected={tab === key} onClick={() => { setTab(key); setPlaying(false); }}>{label}</button>)}</div>
            {!running && <a href={`${api}/projects/${project!.id}/export`}>导出草稿包 ↓</a>}</div>
          <div className="studio-scroll">
            <p className="studio-hint">{version?.mode === "mock" ? "Mock流程占位，未执行模型审核。" : version?.review_status === "blocked" ? "本轮复检未通过，保留原稿；不能作为已审核作品提交。" : version?.fallback ? `模型规划多次未通过，本版为本地模板初稿，内容待人工核实：${version?.fallback_reason ?? ""}` : "AI生成草稿；引文定位和AI复检不代替科学终审。"}</p>
            {tab === "poster" && <><button className="studio-poster" aria-label="放大海报" onClick={() => setPreview(true)}><img src={posterUrl} alt={draft.title} /><span>点击查看大图 ↗</span></button><p className="studio-hint">当前显示 v{version?.version}；概念图为程序绘制的可编辑SVG，不是模型生成的照片。导出包始终包含最新版及完整历史。</p></>}
            {tab === "explain" && <>{draft.explainer?.length ? draft.explainer.map((p, i) => <article className="studio-scene" key={i}><h3>{i + 1} · {p.heading}</h3><p>{p.body}</p><small>依据：{p.claim_ids.join("、")}</small></article>) : <p>这是旧版本，尚未保存详细讲解。使用下方“从原始资料重新组织整篇表达”可生成新版，保留旧稿。</p>}
              {draft.learning_check && <section className="studio-scene"><h3>想一想，你会怎么解释？</h3><p>{draft.learning_check.question}</p><details><summary>看看解释</summary><p>{draft.learning_check.answer}</p></details></section>}</>}
            {tab === "scenes" && <>
              {running && <ProductionProgress stage={activeStage || "正在继续自动制作"} events={activeMedia?.events} />}
              <section className="studio-media"><h3>你的科普视频</h3><p>千问规划卡通对象与动作 → 核查并修正 → AI旁白与字幕 → 可播放下载的MP4。画风参考太阳动画，目标约60—90秒；程序动画不冒充视频大模型成片。</p>
                {!selectedMedia?.video && !running && <><button disabled={locked || version?.version !== latest?.version || !["ai_checked_human_pending", "needs_human_review"].includes(version?.review_status ?? "")} onClick={() => void generateMedia()}>为这一版制作卡通视频（调用百炼）</button>
                <small>使用现有预算；审核提醒不等于科学终审通过。通常需要数分钟，开始后上方会显示真实进度。</small></>}
                {selectedMedia?.video && <p><strong>已找到本版可播放成片（v{selectedMedia.version}）。</strong> 下方可直接播放或下载；刷新页面不会丢失。</p>}
                {failedMediaCount > 0 && <details><summary>另保留{failedMediaCount}次未完成制片记录</summary>{versionMedia.filter(m=>m.state==="failed").map(m=><p key={m.id}>{m.stage}</p>)}</details>}
                {selectedMedia?.resumed_from && <p>本次已接续上次未完成任务，保留旧记录并复用已有素材。</p>}
                {selectedMedia?.human_reviews?.map((r, i) => <p className="studio-error" key={i}>人工复核仍需修改：{r.issues.join("；")}</p>)}
                {selectedMedia && <><p role="status">{selectedMedia.stage}</p>{selectedMedia.video && <><video controls preload="metadata" src={mediaUrl(selectedMedia.video)} /><p>{selectedMedia.duration_seconds}秒 · {selectedMedia.kind}</p><a href={mediaUrl(selectedMedia.video)} download>下载MP4</a>{selectedMedia.poster && <>{" · "}<a href={mediaUrl(selectedMedia.poster)} target="_blank" rel="noreferrer">查看插画海报PNG</a></>}</>}
                  {selectedMedia.structure_repairs?.map((repair,i)=><p key={i}>{repair.state === "applied" ? "已自动修复卡通规划结构，原脚本未改动。" : repair.state === "failed" ? "卡通规划自动修复后仍不符合结构，已停止收费步骤。" : "正在修复卡通规划结构…"}</p>)}
                  {Boolean(selectedMedia.mechanical_repairs?.length) && <details><summary>程序兼容处理（{selectedMedia.mechanical_repairs!.length}处，未改科学文字）</summary>{selectedMedia.mechanical_repairs!.map((r,i)=><p key={i}>{r.field}：{r.before} → {r.after}；{r.reason}</p>)}</details>}
                  {selectedMedia.state === "failed" && Boolean(selectedMedia.failure_details?.length) && <details><summary>查看可处理的结构错误</summary>{selectedMedia.failure_details!.map((e,i)=><p key={i}>{e.field} · {e.type}</p>)}</details>}
                  <details><summary>查看画面检查与自动修改痕迹</summary>{selectedMedia.render_revisions?.map((r,i)=><p key={i}>程序画面修正（非AI改写）：{r.reason} <a href={mediaUrl(r.previous_video)} target="_blank" rel="noreferrer">修改前视频</a></p>)}{selectedMedia.scenes.map(s => <article key={s.scene_id}><strong>{s.scene_id}</strong>{s.candidates.map((c, i) => {
                    const changes = cartoonDiff(s.candidates[i-1]?.plan,c.plan);
                    return <div className="studio-media-candidate" key={c.file}><p>候选{c.attempt}：{s.accepted === c.file ? "采用" : "未采用"} · {c.review?.status === "pass" ? "AI检查未发现明显问题" : c.review ? "AI建议修改（可能误判）" : "待检查"} <a href={mediaUrl(c.file)} target="_blank" rel="noreferrer">查看候选</a></p>
                      {i>0 && c.plan && <details><summary>实际方案变更（{changes.length}处）</summary>{changes.map(d=><div className="studio-diff" key={d.field}><strong>{d.field}</strong><del>{d.before}</del><ins>{d.after}</ins></div>)}</details>}
                      {Boolean(c.review?.issues.length || c.correction) && <details><summary>检查意见与改图要求（不等于全部已落实）</summary>{c.review?.issues.map((issue,j)=><p key={j}>{issue}</p>)}{c.correction && <p>传入的修改要求：{c.correction}</p>}</details>}
                    </div>;
                  })}</article>)}</details></>}
              </section>
              <details className="studio-script-details"><summary>查看分镜与讲解脚本（{draft.scenes.length}镜，可选）</summary>
              <p className="studio-hint">共{draft.scenes.length}镜 · 估算约{draft.scenes.reduce((total, s) => total + Math.max(6, Math.ceil(s.narration.length / 3.5)), 0)}秒；时长按旁白估算，尚非实际配音时长。</p>
              <div className={`studio-animatic ${playing ? "playing" : ""}`}><small>动态分镜预演 · 无旁白 · 非最终卡通视频</small>
                <div className="studio-mascot" aria-hidden="true"><span>● ●</span><b>⌣</b></div>
                <h3>{draft.scenes[sceneIndex]?.heading}</h3><p>{draft.scenes[sceneIndex]?.narration}</p>
                <div className="studio-nodes">{draft.diagram.labels.map((label, i) => <span key={i}>{label}</span>)}</div>
                <p className="studio-hint">{draft.scenes[sceneIndex]?.visual_action}</p>
                <div className="studio-player"><button onClick={() => { if (!playing && sceneIndex === draft.scenes.length - 1) setSceneIndex(0); setPlaying(!playing); }}>{playing ? "暂停" : "预演分镜"}</button><span>{sceneIndex + 1} / {draft.scenes.length}</span></div>
              </div>
              {draft.scenes.map((s, i) => <article className="studio-scene" key={s.scene_id}><small>{roleNames[s.role ?? ""] ?? "历史分镜"}</small><button onClick={() => { setSceneIndex(i); setPlaying(false); }}>{String(i + 1).padStart(2, "0")} · {s.heading}</button><p>{s.narration}</p><small>画面：{s.visual_action}</small><small>依据：{s.claim_ids.join("、")}</small></article>)}
              </details>
            </>}
            {tab === "evidence" && <>
              <label>查看版本<select value={version?.version} onChange={e => { setHistory(Number(e.target.value)); setSceneIndex(0); setPlaying(false); }}>{project!.versions.map(v => <option value={v.version} key={v.version}>v{v.version} · {v.review_status === "pending" ? "初稿" : "审核记录"}{v.fallback ? " · 模板降级" : ""}</option>)}</select></label>
              {draft.claims.map(c => <article className="studio-evidence" key={c.claim_id}><h3>{c.claim_id} · {c.text}</h3><blockquote>{c.quote}</blockquote><p>适用边界：{c.boundary}</p><small>来源编号：{c.source_id} · 核对原文匹配不等于自动证实结论</small></article>)}
              {(project!.input.sources.length ? project!.input.sources : project!.research?.sources ?? []).map(s => <p key={s.source_id}>{s.source_id} · {s.url ? <a href={s.url} target="_blank" rel="noopener noreferrer">{s.title} ↗</a> : s.title}</p>)}
              <details><summary>本版模型调用记录</summary>{version!.calls.map((c, i) => <p key={i}>{c.model} · {c.purpose}<br /><small>{c.request_id}</small></p>)}</details>
            </>}
            {tab === "evidence" && <section className="studio-revisions"><h3>自动改进留下了什么？</h3>
              <p>{version!.changes.length ? `本版实际修改了 ${version!.changes.length} 处，展开查看前后对比。` : "本版没有已应用的内容修改；审核记录与内容改动分开保存。"}</p>
              {Boolean(version!.mechanical_changes?.length) && <details><summary>程序排版一致性处理（非AI科学修订）</summary>{version!.mechanical_changes!.map((c, i) => <p key={i}>{c.reason}：{display(c.before)} → {display(c.after)}{version!.review_status === "blocked" ? "（候选未应用）" : ""}</p>)}</details>}
              {(version!.findings ?? []).filter(f => f.severity !== "info").map((f, i) => <p key={i} className={f.severity === "blocker" ? "studio-error" : ""}>{f.target}：{f.message}</p>)}
              {Boolean(version!.findings?.some(f => f.severity === "info")) && <details><summary>复检说明（折叠）</summary>{version!.findings.filter(f => f.severity === "info").map((f, i) => <p key={i}>{f.target}：{f.message}</p>)}</details>}
              {Boolean(version?.detected_findings?.length) && <details><summary>系统发现的问题</summary>{version!.detected_findings!.map((f, i) => <p key={i}>{f.target}：{f.message}</p>)}</details>}
              <details><summary>修改前后对比（{version!.changes.length}处）</summary>{version!.changes.map((c, i) => <div className="studio-diff" key={i}><strong>{fieldLabel(c.field)}</strong><del>{display(c.before)}</del><ins>{display(c.after)}</ins></div>)}</details>
              {Boolean(version?.proposed_changes?.length) && <p className="studio-error">有{version!.proposed_changes!.length}处候选修改未通过检查，未覆盖原稿。</p>}
              <label>你的补充建议（选填）<textarea rows={2} value={feedback} maxLength={1000} disabled={locked} onChange={e => setFeedback(e.target.value)} placeholder="例如：第二镜太抽象，请换成日常生活中的解释，但不要改变科学含义。" /></label>
              <label className="studio-auto-source"><input type="checkbox" checked={rebuild} disabled={locked} onChange={e => setRebuild(e.target.checked)} />从原始资料重新组织整篇表达（仍保留旧版）</label>
              <button className="studio-primary" disabled={locked} onClick={() => void revise()}>{textOnly ? "再次自动审核与修订" : "自动修订并制作新版视频"}</button>
            </section>}
          </div>
        </>}
      </section>
    </div>
    {preview && <div className="studio-lightbox" role="dialog" aria-modal="true" aria-label="海报大图" onClick={() => setPreview(false)}><button autoFocus onClick={() => setPreview(false)}>关闭 ×</button><img src={posterUrl} alt={draft?.title} onClick={e => e.stopPropagation()} /></div>}
  </main>;
}
