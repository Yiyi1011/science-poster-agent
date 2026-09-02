import { FormEvent, useEffect, useState } from "react";
import {
  createPosterPlan,
  createRevisionPlan,
  createVideoStoryboard,
  createVisualAssetSpecs,
  renderPoster,
} from "./api";
import type {
  PosterPlan,
  PosterRequest,
  ReviewCategory,
  RevisionPlan,
  VideoStoryboard,
  VisualAssetBundle,
} from "./types";
import { siteUrl } from "./runtime";

const initialRequest: PosterRequest = {
  topic: "",
  audience: "普通公众",
  source_text: "",
  visual_style: "现代、清晰、克制",
  aspect_ratio: "3:4",
};

const examplePresets: Array<{ label: string; note: string; request: PosterRequest }> = [
  {
    label: "太阳爆发",
    note: "知识库检索主案例",
    request: {
      ...initialRequest,
      topic: "太阳爆发如何在8分钟到几天内影响地球通信与导航？",
      visual_style: "现代科学信息图，深蓝宇宙底色，高对比时间轴，克制的编辑插图",
    },
  },
  {
    label: "AI可信错误",
    note: "人工智能科普",
    request: {
      ...initialRequest,
      topic: "为什么生成式AI会给出看似可信却错误的内容？",
      source_text: `[AI-001｜NIST AI 600-1] 生成式AI可能产生“confabulation”：以自信、连贯的形式呈现错误或虚假的内容。风险来自输出外观可信，而非内容已经经过事实核验。\n\n[AI-002｜NIST生成式AI风险管理资料] 降低风险需要结合来源核查、检索增强、人工复核和明确的不确定性表达；这些措施只能降低风险，不能保证所有输出正确。\n\n[AI-003｜UNESCO生成式AI教育与研究指南] 教育和研究场景中的使用者需要批判性评估模型输出，并保护人的判断与责任。不能把模型错误拟人化为“故意撒谎”。`,
      visual_style: "证据筛网与校验路径，深蓝底色，琥珀色风险提示，清晰信息卡",
    },
  },
  {
    label: "检索练习",
    note: "教育技术案例",
    request: {
      ...initialRequest,
      topic: "为什么主动回忆通常比反复重读更利于长期记忆？",
      source_text: `[EDU-001｜Karpicke & Roediger, Science, 2008] 在实验条件下，反复检索能显著改善一周后的长期保持；材料已经正确回忆后继续重复学习，并没有产生同等收益。\n\n[EDU-002｜Roediger & Karpicke, Journal of Memory and Language] 与只重复学习相比，学习后进行记忆测试可增强延迟测验中的保持，但即时表现和长期保持不能混为一谈。\n\n[EDU-003｜Dunlosky等, Psychological Science in the Public Interest, 2013] 练习测试和分散练习被评为高效学习策略；反复重读的总体效用较低。结论受材料、学习者、反馈和测验间隔影响，不能表达为对所有人、所有任务都必然更好。`,
      visual_style: "学习路径对比信息图，蓝绿色主色，间隔节点与反馈回路，避免神经结构拟人化",
    },
  },
];

export default function App() {
  const [request, setRequest] = useState(initialRequest);
  const [plan, setPlan] = useState<PosterPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [posterUrl, setPosterUrl] = useState("");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [visualAssets, setVisualAssets] = useState<VisualAssetBundle | null>(null);
  const [storyboard, setStoryboard] = useState<VideoStoryboard | null>(null);
  const [feedback, setFeedback] = useState("");
  const [reviewCategory, setReviewCategory] = useState<ReviewCategory>("layout");
  const [revision, setRevision] = useState<RevisionPlan | null>(null);
  const [revisionLoading, setRevisionLoading] = useState(false);

  useEffect(() => {
    return () => {
      if (posterUrl) URL.revokeObjectURL(posterUrl);
    };
  }, [posterUrl]);

  useEffect(() => {
    if (!loading) {
      setElapsedSeconds(0);
      return;
    }
    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [loading]);

  useEffect(() => {
    if (!previewOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPreviewOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [previewOpen]);

  const progressLabel = elapsedSeconds < 12
    ? "正在检索权威知识库"
    : elapsedSeconds < 55
      ? "正在生成事实卡与视觉叙事"
      : "正在校验结构并渲染海报";

  function loadPreset(preset: PosterRequest) {
    setRequest(preset);
    setPlan(null);
    setVisualAssets(null);
    setStoryboard(null);
    setRevision(null);
    setFeedback("");
    setError("");
    setPreviewOpen(false);
    if (posterUrl) URL.revokeObjectURL(posterUrl);
    setPosterUrl("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const nextPlan = await createPosterPlan(request);
      setPlan(nextPlan);
      setRevision(null);
      const [poster, nextAssets, nextStoryboard] = await Promise.all([
        renderPoster(nextPlan),
        createVisualAssetSpecs(nextPlan),
        createVideoStoryboard(nextPlan),
      ]);
      setVisualAssets(nextAssets);
      setStoryboard(nextStoryboard);
      setPreviewOpen(false);
      setPosterUrl(URL.createObjectURL(poster));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "未知错误");
    } finally {
      setLoading(false);
    }
  }

  async function submitRevision(event: FormEvent) {
    event.preventDefault();
    if (!plan || feedback.trim().length < 2) return;
    setRevisionLoading(true);
    setError("");
    try {
      setRevision(await createRevisionPlan({
        taskId: plan.task_id,
        version: revision?.to_version || 1,
        category: reviewCategory,
        feedback: feedback.trim(),
      }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "修订规划失败");
    } finally {
      setRevisionLoading(false);
    }
  }

  return (
    <main>
      <header className="hero">
        <div className="eyebrow">EVIDENCE → STORY → VISUAL</div>
        <h1>把专业科学知识<br />变成公众看得懂的海报</h1>
        <p>跨主题输入、证据追溯、视觉规划与迭代修订。</p>
        <a className="animation-entry" href={siteUrl("solar-animation/voiced.html")} target="_blank" rel="noopener noreferrer">观看卡通科普视频 → <small>约67秒 · 千问AI旁白 + 要点字幕 · 试听版</small></a>
        <a className="animation-entry" href={`${siteUrl()}?view=storyboard`}>自动修正太阳案例分镜 → <small>自动检查与留档 · 手动微调可选</small></a>
      </header>

      <section className="workspace">
        <form onSubmit={submit} className="panel input-panel">
          <div className="panel-title"><span>01</span><h2>定义传播任务</h2></div>
          <div className="example-group" aria-label="示范案例">
            <div className="example-heading"><strong>载入示范案例</strong><small>只预填，不会立即调用模型</small></div>
            <div className="example-grid">
              {examplePresets.map((preset) => (
                <button
                  className="example-button"
                  type="button"
                  key={preset.label}
                  onClick={() => loadPreset(preset.request)}
                >
                  <strong>{preset.label}</strong>
                  <small>{preset.note}</small>
                </button>
              ))}
            </div>
          </div>
          <label>
            科学主题
            <input
              required
              minLength={2}
              value={request.topic}
              onChange={(event) => setRequest({ ...request, topic: event.target.value })}
              placeholder="例如：日冕为什么比太阳表面更热？"
            />
          </label>
          <div className="split">
            <label>
              受众
              <select
                value={request.audience}
                onChange={(event) => setRequest({ ...request, audience: event.target.value })}
              >
                <option>普通公众</option>
                <option>中小学生</option>
                <option>大学生</option>
              </select>
            </label>
            <label>
              画幅
              <select
                value={request.aspect_ratio}
                onChange={(event) => setRequest({ ...request, aspect_ratio: event.target.value as PosterRequest["aspect_ratio"] })}
              >
                <option value="3:4">3:4 竖版</option>
                <option value="1:1">1:1 方形</option>
                <option value="16:9">16:9 横版</option>
                <option value="4:3">4:3 横版</option>
              </select>
            </label>
          </div>
          <label>
            权威资料摘录
            <textarea
              rows={8}
              value={request.source_text}
              onChange={(event) => setRequest({ ...request, source_text: event.target.value })}
              placeholder="可粘贴论文、教材或权威机构资料；留空时将自动查询百炼知识库。"
            />
          </label>
          <label>
            视觉方向
            <input
              value={request.visual_style}
              onChange={(event) => setRequest({ ...request, visual_style: event.target.value })}
            />
          </label>
          <button disabled={loading}>{loading ? "正在规划…" : "生成海报叙事方案"}</button>
          {loading && (
            <div className="progress-note" role="status">
              <span className="progress-dot" />
              <div><strong>{progressLabel}</strong><small>已等待 {elapsedSeconds} 秒，真实调用通常需要 30–90 秒。</small></div>
            </div>
          )}
          {error && <p className="error">{error}</p>}
        </form>

        <section className="panel output-panel">
          <div className="panel-title"><span>02</span><h2>证据与视觉方案</h2></div>
          {!plan ? (
            <div className="empty">
              <div className="orbit" />
              <p>提交一个科学主题后，这里将显示事实卡、证据缺口和海报结构。</p>
            </div>
          ) : (
            <article className="plan">
              <div className="status-row">
                <span className={`status ${plan.status}`}>{plan.status}</span>
                <span>{plan.mode === "mock" ? "Mock模式" : "百炼千问"}</span>
              </div>
              <div className="retrieval-row">
                <span>检索状态：{plan.retrieval_status || "用户资料"}</span>
                {plan.retrieval_max_score !== null && (
                  <strong>最高相关度 {plan.retrieval_max_score.toFixed(3)}</strong>
                )}
              </div>
              <h3>{plan.title}</h3>
              <p className="subtitle">{plan.subtitle}</p>
              {posterUrl && (
                <div className="poster-stage">
                  <button
                    className="poster-preview-button"
                    type="button"
                    onClick={() => setPreviewOpen(true)}
                    aria-label="打开海报大图预览"
                  >
                    <img src={posterUrl} alt={`${plan.title}科普海报`} />
                    <span>点击预览大图</span>
                  </button>
                  <a href={posterUrl} download={`${plan.task_id || "science-poster"}.svg`}>
                    下载可编辑 SVG
                  </a>
                </div>
              )}
              {(visualAssets || storyboard) && (
                <div className="workflow-summary">
                  <div className="workflow-heading">
                    <strong>多模态制作清单</strong>
                    <small>先规划、再生成、后审核；付费生图不会在网页中自动触发。</small>
                  </div>
                  <div className="workflow-metrics">
                    <div><b>{visualAssets?.assets.length || 0}</b><span>视觉资产规格</span></div>
                    <div><b>{storyboard?.scenes.length || 0}</b><span>视频分镜</span></div>
                    <div><b>{storyboard?.total_duration_seconds || 0}s</b><span>AI旁白＋字幕</span></div>
                  </div>
                  {visualAssets?.assets.map((asset) => (
                    <div className="asset-row" key={asset.asset_id}>
                      <span>{asset.asset_type}</span>
                      <small>关联事实卡：{asset.source_claim_ids.join("、") || "待补证据"}</small>
                      <b>{asset.status}</b>
                    </div>
                  ))}
                </div>
              )}
              <div className="section-list">
                {plan.sections.map((section, index) => (
                  <div className="story-section" key={section.heading}>
                    <b>{String(index + 1).padStart(2, "0")}</b>
                    <div><h4>{section.heading}</h4><p>{section.content_summary}</p><small>{section.visual_form}</small></div>
                  </div>
                ))}
              </div>
              <div className="fact-grid">
                {plan.fact_cards.map((fact) => (
                  <div className="fact-card" key={fact.claim_id}>
                    <strong>{fact.evidence_status} · {fact.claim_id}</strong>
                    <p>{fact.claim}</p>
                    <small>{fact.caveat}</small>
                  </div>
                ))}
              </div>
              {plan.source_documents.length > 0 && (
                <p className="sources">引用文档：{plan.source_documents.join("、")}</p>
              )}
              <p className="safety">{plan.safety_note}</p>
              <form className="revision-box" onSubmit={submitRevision}>
                <div className="workflow-heading">
                  <strong>反馈—修订闭环</strong>
                  <small>事实、因果和数值问题会强制回到证据审核；版式问题只做局部修改。</small>
                </div>
                <div className="revision-inputs">
                  <select
                    aria-label="反馈类型"
                    value={reviewCategory}
                    onChange={(event) => setReviewCategory(event.target.value as ReviewCategory)}
                  >
                    <option value="layout">版式</option>
                    <option value="readability">可读性</option>
                    <option value="color">色彩</option>
                    <option value="cropping">裁切</option>
                    <option value="fact">事实</option>
                    <option value="causality">因果</option>
                    <option value="number">数值</option>
                  </select>
                  <input
                    value={feedback}
                    minLength={2}
                    required
                    onChange={(event) => setFeedback(event.target.value)}
                    placeholder="例如：来源区字号太小，需要提高可读性"
                  />
                </div>
                <button disabled={revisionLoading}>{revisionLoading ? "正在判断修订路径…" : "生成修订方案"}</button>
                {revision && (
                  <div className={`revision-result ${revision.status}`}>
                    <strong>{revision.status === "blocked_by_evidence" ? "已阻断自动修改：先核验证据" : `修订 v${revision.from_version} → v${revision.to_version}`}</strong>
                    {revision.actions.map((action) => <p key={`${action.target_id}-${action.action}`}>{action.instruction}</p>)}
                  </div>
                )}
              </form>
            </article>
          )}
        </section>
      </section>
      {previewOpen && posterUrl && plan && (
        <div
          className="preview-modal"
          role="dialog"
          aria-modal="true"
          aria-label="海报大图预览"
          onClick={() => setPreviewOpen(false)}
        >
          <div className="preview-modal-content" onClick={(event) => event.stopPropagation()}>
            <div className="preview-modal-bar">
              <div><strong>{plan.title}</strong><small>可使用鼠标滚轮查看细节</small></div>
              <button type="button" onClick={() => setPreviewOpen(false)} aria-label="关闭大图">×</button>
            </div>
            <div className="preview-canvas">
              <img src={posterUrl} alt={`${plan.title}大图预览`} />
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
