# 赛事提交证据索引

> 目的：把提交模板中的陈述映射到可复核文件。所有路径均相对`science-poster-agent/`；任何截图在提交前都必须再次检查是否泄露Key或个人信息。

| 模板/评审关注点 | 可提交证据 | 当前状态 |
|---|---|---|
| v0.4.1失败恢复与跨主题可靠性 | `docs/versions/process/v0.4.1-preview.md`、`evidence/studio-v041/`、本机项目媒体记录 | AI主题旧脚本在3次结构失败后由新版成功生成6镜68秒MP4；4处装饰图标机械兼容可见且未改科学文字。API基础问题在百炼搜索短暂异常时仍读取MDN/AWS两份原文，生成8镜并通过自动审核；本轮未重复生成API视频 |
| v0.4视频默认、海报选做与基础问题 | `docs/versions/process/v0.4.0-preview.md`、`evidence/studio-v040/`、`artifacts/studio-media/` | API自动审核后生成6镜68秒卡通MP4；千问规划＋程序动作＋AI旁白字幕，不是原生视频模型。插画实验和卡通首轮箭头误导分别保留人工问题记录，不冒充自动科学认证 |
| v0.3.0通俗表达、6—8镜与只提问题检索 | `docs/versions/process/v0.3.0-preview.md`、`evidence/studio-v030/`及`browser-real/report.json` | 真实三案最新6/7/7镜；学习案有时间范围提醒。AI与学习案含明确开发者复核反馈，不冒充无人干预成功率；月球检索失败记录保留 |
| 过程代码与最终代码分隔 | `docs/versions/README.md`、`docs/CODE_MAP.md`、`VERSION_NOTES.md` | 标签及每版简述可查，旧标签不改；当前只有制作预览版，没有最终交付标签 |
| 跨主题独立项目与Qwen语义修订 | `evidence/studio-v020/report.json`、`refined-*.json`、项目完整JSON/草稿ZIP、`docs/studio-guide.md` | 两个真实qwen-plus项目；生成、审核改写与复检10次文本调用，首轮各4处修改，开发者提出边界问题后分别再改7处/11处。留存原稿，不冒充专家或公众评测；通用视频仍为分镜 |
| 新工作台交互验证 | `evidence/studio-v020/browser/report.json`、桌面/手机截图 | 独立滚动、放大预览、项目恢复、无声分镜预演、ZIP下载等通过；Mock浏览器测试与真实模型内容测试分开 |
| v0.2.0源码与本地封装 | `docs/studio-guide.md`、`scripts/package_release.py`、`scripts/run_packaged.py` | 94项后端测试、3项动画测试与前端构建通过；单端口启动，不等于免安装EXE或已公网部署 |
| 主案例成品 | `artifacts/solar-weather-poster-v2.svg`、`artifacts/solar-weather-poster-v2.png` | 已完成，SVG可编辑 |
| 主案例科学审核 | `artifacts/solar-weather-science-review-v1.md`、知识库7份上传文档 | 已完成；最终仍建议领域人员签字/署名 |
| 跨主题复用A：AI可信错觉 | `artifacts/cross-topic/ai-confabulation/poster-v004-final.*`、`science-review-v001.md`、`final-manifest-v001.json` | 已完成 |
| 跨主题复用B：检索练习 | `artifacts/cross-topic/retrieval-practice/poster-v004-final.*`、`science-review-v001.md`、`final-manifest-v001.json` | 已完成 |
| 权威资料与版权来源 | `cross-topic-cases/*/source-ledger.md`、太阳知识库资料的来源字段 | 已完成台账；最终图注待统一 |
| RAG可靠性 | `retrieval-evaluation/retrieval-report-v1.md`、`retrieval-results-v1.json` | 严格29/30，Top 5来源30/30，3条拒答正确 |
| Qwen-VL自动检查与修正 | `artifacts/workflow/e227ed71-e128-4ae7-9da4-a0db070e56b3/vision-review-v001.json`、`vision-review-v002.json`、`vision-review-adjudication-v001.json` | 已完成两轮并保留人工裁决 |
| 图像模型失败与止损 | 同工作流目录的`visual-review-v001..v003.json`、`visual-assets-v005.json` | 已完成；3张候选均拒绝，未污染成品 |
| 旧AI旁白与海报预演 | `artifacts/video/solar-weather-v001/solar-weather-preview-v001.mp4`、`audience-review-v002.md` | 仅过程证据；用户指出术语过深，不作为正式科普成品 |
| 新卡通动画与反馈 | `artifacts/video/solar-weather-v002-animation/solar-messengers-narrated-v001.mp4`、`user-acceptance-v002.md`、`mp4-narrated-technical-review-v001.json`、`narration-v001/` | 约67秒有声卡通版获用户认可；原84秒无声版保留，22项技术检查通过。多人受众和专家终审待完成；非通用自动动画生成 |
| 自动优先修正与可选手动微调 | `evidence/storyboard-editor-qa/automatic-first/report.json`、前后对照截图、`docs/storyboard-editor-guide.md` | 一次点击完成本地检查、无损字幕拆分、时长延长、复检和自动保存；记录输入/系统改动区别、原值/新值/原因。无修改也留档，网络重试不重复保存；手动微调折叠。截图来自明确练习输入，不冒充模型错误或视频重生成 |
| 调用与费用 | `evidence/model-usage.jsonl`、`evidence/budget-authorization.md`、`evidence/billing-snapshot-2026-08-31.json` | v0.3结束时原价估算累计3.235630元；后续新增费用看最新台账/制作日志，不是实付。用户此前截图优惠后0.2799122559元无账期/付款状态，不等同历史实付；两项不能相加。搜索插件等费用须核对账单 |
| 百炼应用调用证明 | `evidence/console/`与`evidence/knowledge-*.json` | 已有脱敏证据；正式提交截图待挑选 |
| 应用可复现 | `README.md`、`backend/pyproject.toml`、`frontend/package.json`、`Dockerfile` | 本地可复现，67项后端测试和前端构建通过；云端持久化与访问控制仍需部署前确认 |
| 公网部署 | `docs/deployment-fc.md`、`evidence/production-unified-server-check-2026-08-29.json` | 生产形态已验证；公网资源尚未创建 |
| 完整过程与报错 | 工作区根目录`制作日志.md` | 已记录LOG-001起的操作、错误与解决办法 |
| 提交模板草稿 | 工作区`提交材料/赛道三方向2-提交材料草稿-v001.docx`与`work/submission-draft/structural-qa-v001.md` | 结构审计通过；待WPS逐页视觉检查和团队资料 |

## 最终打包时的红线

- `.env`、完整API Key、AccessKey、Cookie和未脱敏控制台截图不得进入提交包。
- 被人工拒绝的图像候选只能放在“失败与纠错记录”，不得作为正式成品。
- 尚未做受众测试、公网部署或领域专家签字的项目不得写成“已完成”。
- DOCX导出PDF后必须再次核对20页上限、链接可访问性和二维码。
