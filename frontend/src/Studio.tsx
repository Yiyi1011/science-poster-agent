import { FormEvent, useEffect, useRef, useState } from "react";
import "./studio.css";

type Source = { source_id: string; title: string; url: string; text: string };
type Input = { topic: string; audience: string; sources: Source[] };
type Claim = { claim_id: string; text: string; source_id: string; quote: string; boundary: string };
type Scene = { scene_id: string; heading: string; narration: string; visual_action: string; claim_ids: string[] };
type Draft = { title: string; takeaway: string; claims: Claim[]; diagram: { kind: string; labels: string[]; caption: string }; scenes: Scene[] };
type Finding = { target: string; severity: string; message: string };
type Change = { field: string; before: unknown; after: unknown };
type Version = { version: number; draft: Draft; mode: string; model: string; review_status: string; changes: Change[];
  findings: Finding[]; detected_findings?: Finding[]; proposed_changes?: Change[]; calls: Array<{ model: string; request_id: string; purpose: string }> };
type Project = { id: string; input: Input; versions: Version[]; runs: Array<{ id: string; state: string; stage: string; error: string }> };
type Summary = { id: string; topic: string };
const blankSource = (): Source => ({ source_id: "S1", title: "", url: "", text: "" });
const blankInput = (): Input => ({ topic: "", audience: "普通公众", sources: [blankSource()] });
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
  .replaceAll("diagram", "图解").replaceAll("text", "文字");

export default function Studio() {
  const [input, setInput] = useState<Input>(blankInput);
  const [presets, setPresets] = useState<Input[]>([]);
  const [projects, setProjects] = useState<Summary[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [tab, setTab] = useState("poster");
  const [history, setHistory] = useState(0);
  const [config, setConfig] = useState<{ mock_ai: boolean; text_model: string } | null>(null);
  const [preview, setPreview] = useState(false);
  const [sceneIndex, setSceneIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const retry = useRef<{ project: string; version: number; feedback: string; request_id: string } | null>(null);
  const selectedId = useRef("");
  const running = project?.runs.some(r => r.state === "running") ?? false;
  const latest = project?.versions.at(-1);
  const version = project?.versions.find(v => v.version === history) ?? latest;
  const draft = version?.draft;
  const run = project?.runs.at(-1);
  const locked = busy || running;
  const posterUrl = project && version ? `${api}/projects/${project.id}/poster.svg?revision=${version.version}` : "";

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
  }

  async function openProject(id: string) {
    selectedId.current = id; setBusy(true); setError(""); setPlaying(false); setSceneIndex(0); setHistory(0);
    try { const value = await request<Project>(`${api}/projects/${id}`); if (selectedId.current === id) { setProject(value); setInput(value.input); } }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  async function runProject(value: Project, note = "") {
    const number = value.versions.at(-1)?.version ?? 0;
    const previous = retry.current;
    const operation = previous?.project === value.id && previous.version === number && previous.feedback === note ? previous
      : { project: value.id, version: number, feedback: note, request_id: crypto.randomUUID() };
    retry.current = operation;
    const next = await request<Project>(`${api}/projects/${value.id}/run`, { request_id: operation.request_id, expected_version: number, feedback: note });
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
    <section className="studio-intro"><span>从一个问题，到一份看得懂的科学作品</span><h1>让知识，有画面。</h1><p>带上资料，千问帮你组织证据、设计海报与分镜，并留下修改痕迹。</p>
      <small className="studio-model">{config ? config.mock_ai ? "Mock演示 · 不调用模型" : `阿里云百炼 · ${config.text_model} · 北京` : "正在读取模型配置…"}</small></section>
    <div className="studio-grid">
      <aside className="studio-input">
        <div className="studio-section-title"><h2>01 定义这次创作</h2><button type="button" disabled={locked} onClick={() => newInput(blankInput())}>新建</button></div>
        <div className="studio-presets">{presets.map((p, i) => <button key={p.topic} disabled={locked} onClick={() => newInput(p)}>{i === 0 ? "AI为何会答错" : "间隔学习"} ↗</button>)}</div>
        <label>打开已保存项目<select aria-label="打开已保存项目" value={project?.id ?? ""} disabled={locked} onChange={e => e.target.value && void openProject(e.target.value)}><option value="">新项目</option>{projects.map(p => <option key={p.id} value={p.id}>{p.topic}</option>)}</select></label>
        <form onSubmit={submit}>
          <fieldset disabled={locked || Boolean(project)}><label>你想解释什么？<input required minLength={2} maxLength={160} value={input.topic} onChange={e => setInput({ ...input, topic: e.target.value })} placeholder="例如：为什么重复复习要隔一段时间？" /></label>
            <label>讲给谁听？<select value={input.audience} onChange={e => setInput({ ...input, audience: e.target.value })}><option>普通公众</option><option>初中生</option><option>大学新生</option></select></label>
            {input.sources.map((s, i) => <details className="studio-source" key={s.source_id} open={!project && i === 0}><summary>{s.source_id} · {s.title || "添加一份科学资料"}</summary>
              <label>资料名称<input required={Boolean(s.text)} minLength={2} maxLength={160} value={s.title} onChange={e => editSource(i, { title: e.target.value })} /></label>
              <label>公开来源链接（选填，不自动抓取）<input type="url" value={s.url} onChange={e => editSource(i, { url: e.target.value })} placeholder="https://…" /></label>
              <label>与问题相关的资料摘录<textarea rows={6} value={s.text} minLength={20} maxLength={15000} onChange={e => editSource(i, { text: e.target.value })} placeholder="粘贴正文，不要只贴链接。无资料时会停止生成，不会编造证据。" /></label>
              <label className="studio-file">或导入 TXT / MD<input type="file" accept=".txt,.md" onChange={e => void upload(e.target.files?.[0], i)} /></label></details>)}
            <button type="button" disabled={input.sources.length >= 6} onClick={() => setInput({ ...input, sources: [...input.sources, { ...blankSource(), source_id: `S${input.sources.length + 1}` }] })}>＋ 添加来源</button>
          </fieldset>
          {project && <p className="studio-hint">资料已随项目保存。更换资料请<button type="button" className="studio-link" disabled={locked} onClick={() => newInput(input)}>复制为新项目</button>，旧作品不会被覆盖。</p>}
          <button className="studio-primary" disabled={locked || Boolean(latest)}>{locked ? "处理中，请稍候…" : latest ? "已保存 · 在右侧查看或修订" : "生成作品并自动审核 →"}</button>
        </form>
        <p className="studio-hint">资料仅进入本项目，不混用太阳知识库。提交后会发送至百炼；请勿粘贴密钥或未获授权的私人资料。</p>
        {error && <p role="alert" className="studio-error">{error}</p>}
      </aside>
      <section className="studio-results" aria-label="创作结果">
        <div className="studio-result-header"><h2>02 作品与改进</h2>{run && <span role="status" className={running ? "studio-working" : ""}>{run.stage}</span>}</div>
        {run?.error && <p className="studio-error">{run.error}</p>}
        {!draft ? <div className="studio-empty"><div className="studio-orbit">✦</div><h3>先有证据，再有表达</h3><p>海报、独立视频分镜和修改记录，会在这里逐步出现。</p><small>所有进度来自实际执行阶段，不用倒计时假装完成。</small></div> : <>
          <div className="studio-toolbar"><div role="tablist" aria-label="作品视图">{[["poster", "图解海报"], ["scenes", "独立分镜"], ["evidence", "证据与版本"]].map(([key, label]) => <button key={key} role="tab" aria-selected={tab === key} onClick={() => { setTab(key); setPlaying(false); }}>{label}</button>)}</div>
            {!running && <a href={`${api}/projects/${project!.id}/export`}>导出草稿包 ↓</a>}</div>
          <div className="studio-scroll">
            <p className="studio-hint">{version?.mode === "mock" ? "Mock流程占位，未执行模型审核。" : version?.review_status === "blocked" ? "本轮复检未通过，保留原稿；不能作为已审核作品提交。" : "AI生成草稿；引文定位和AI复检不代替科学终审。"}</p>
            {tab === "poster" && <><button className="studio-poster" aria-label="放大海报" onClick={() => setPreview(true)}><img src={posterUrl} alt={draft.title} /><span>点击查看大图 ↗</span></button><p className="studio-hint">当前显示 v{version?.version}；概念图为程序绘制的可编辑SVG，不是模型生成的照片。导出包始终包含最新版及完整历史。</p></>}
            {tab === "scenes" && <>
              <div className={`studio-animatic ${playing ? "playing" : ""}`}><small>动态分镜预演 · 无旁白 · 非最终卡通视频</small>
                <div className="studio-mascot" aria-hidden="true"><span>● ●</span><b>⌣</b></div>
                <h3>{draft.scenes[sceneIndex]?.heading}</h3><p>{draft.scenes[sceneIndex]?.narration}</p>
                <div className="studio-nodes">{draft.diagram.labels.map((label, i) => <span key={i}>{label}</span>)}</div>
                <p className="studio-hint">{draft.scenes[sceneIndex]?.visual_action}</p>
                <div className="studio-player"><button onClick={() => { if (!playing && sceneIndex === draft.scenes.length - 1) setSceneIndex(0); setPlaying(!playing); }}>{playing ? "暂停" : "预演分镜"}</button><span>{sceneIndex + 1} / {draft.scenes.length}</span></div>
              </div>
              {draft.scenes.map((s, i) => <article className="studio-scene" key={s.scene_id}><button onClick={() => { setSceneIndex(i); setPlaying(false); }}>{String(i + 1).padStart(2, "0")} · {s.heading}</button><p>{s.narration}</p><small>画面：{s.visual_action}</small><small>依据：{s.claim_ids.join("、")}</small></article>)}
            </>}
            {tab === "evidence" && <>
              <label>查看版本<select value={version?.version} onChange={e => { setHistory(Number(e.target.value)); setSceneIndex(0); setPlaying(false); }}>{project!.versions.map(v => <option value={v.version} key={v.version}>v{v.version} · {v.review_status === "pending" ? "初稿" : "审核记录"}</option>)}</select></label>
              {draft.claims.map(c => <article className="studio-evidence" key={c.claim_id}><h3>{c.claim_id} · {c.text}</h3><blockquote>{c.quote}</blockquote><p>适用边界：{c.boundary}</p><small>来源编号：{c.source_id} · 核对原文匹配不等于自动证实结论</small></article>)}
              {project!.input.sources.map(s => <p key={s.source_id}>{s.source_id} · {s.url ? <a href={s.url} target="_blank" rel="noopener noreferrer">{s.title} ↗</a> : s.title}</p>)}
              <details><summary>本版模型调用记录</summary>{version!.calls.map((c, i) => <p key={i}>{c.model} · {c.purpose}<br /><small>{c.request_id}</small></p>)}</details>
            </>}
            <section className="studio-revisions"><h3>自动改进留下了什么？</h3>
              <p>{version!.changes.length ? `本版实际修改了 ${version!.changes.length} 处，展开查看前后对比。` : "本版没有已应用的内容修改；审核记录与内容改动分开保存。"}</p>
              {(version!.findings ?? []).filter(f => f.severity !== "info").map((f, i) => <p key={i} className={f.severity === "blocker" ? "studio-error" : ""}>{f.target}：{f.message}</p>)}
              {Boolean(version!.findings?.some(f => f.severity === "info")) && <details><summary>复检说明（折叠）</summary>{version!.findings.filter(f => f.severity === "info").map((f, i) => <p key={i}>{f.target}：{f.message}</p>)}</details>}
              {Boolean(version?.detected_findings?.length) && <details><summary>系统发现的问题</summary>{version!.detected_findings!.map((f, i) => <p key={i}>{f.target}：{f.message}</p>)}</details>}
              <details><summary>修改前后对比（{version!.changes.length}处）</summary>{version!.changes.map((c, i) => <div className="studio-diff" key={i}><strong>{fieldLabel(c.field)}</strong><del>{display(c.before)}</del><ins>{display(c.after)}</ins></div>)}</details>
              {Boolean(version?.proposed_changes?.length) && <p className="studio-error">有{version!.proposed_changes!.length}处候选修改未通过检查，未覆盖原稿。</p>}
              <label>你的补充建议（选填）<textarea rows={2} value={feedback} maxLength={1000} disabled={locked} onChange={e => setFeedback(e.target.value)} placeholder="例如：第二镜太抽象，请换成日常生活中的解释，但不要改变科学含义。" /></label>
              <button className="studio-primary" disabled={locked} onClick={() => void revise()}>再次自动审核与修订</button>
            </section>
          </div>
        </>}
      </section>
    </div>
    {preview && <div className="studio-lightbox" role="dialog" aria-modal="true" aria-label="海报大图" onClick={() => setPreview(false)}><button autoFocus onClick={() => setPreview(false)}>关闭 ×</button><img src={posterUrl} alt={draft?.title} onClick={e => e.stopPropagation()} /></div>}
  </main>;
}
