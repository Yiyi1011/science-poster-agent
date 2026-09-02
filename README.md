# Science Poster Agent / 跨主题科普视频智能体（暂名）

> 当前是**制作过程版**，不是最终交付版。先看[版本导航](docs/versions/README.md)、[代码文件索引](docs/CODE_MAP.md)和[当前变更说明](docs/versions/process/v0.5.8-preview.md)。制作历史与[最终交付区](docs/versions/final/README.md)分开保存，最终版尚未发布。

新版工作台**默认生成科普视频，海报选做**：问题→按领域找资料→通俗讲解和6—8镜→检查修订→千问规划卡通对象/动作→视觉检查→AI旁白与字幕→MP4。画风与约60—90秒节奏参考太阳动画，属于程序卡通动画，不是视频大模型原生角色电影。完整讲解、理解小问题、证据和修改对比在次级入口；仍可选择只准备脚本。初步回答不冒充已核实来源；资料不足或审核不过会停止。以下早期清单含太阳专用流程，不代表全部已泛化。

面向普通公众的跨主题科学视觉传播应用。输入科学主题和权威资料，系统生成可追溯的科学事实卡、海报叙事方案和可编辑视觉规格；已包含视觉资产规划、视频分镜、人工反馈与自动修订路径，图像候选必须审核通过后才能进入成品。

## 地域策略

- 百炼应用、知识库、Qwen/Wan：华北2（北京），`cn-beijing`；
- React前端与FastAPI后端：可部署在杭州或北京；
- 浏览器不接触长期API Key，所有模型请求由FastAPI后端发起。

## 当前状态

已完成可演示的端到端原型：

- React + TypeScript + Vite前端；
- FastAPI后端；
- Mock模式，无真实API Key也可跑通；
- 百炼知识检索服务与 Qwen 文本模型接入；
- 严格JSON海报规划数据结构；
- 检索分数阈值 0.50，证据不足时在模型生成前拒绝；
- 海报方案自动渲染为可编辑 SVG，前端可预览和下载；
- 视觉资产规格、AI旁白＋字幕视频分镜和反馈修订计划；
- 30条固定RAG评测：严格通过率96.7%，Top 5预期来源命中率100%；
- `qwen-image-3.0`真实接口、10元图像子预算闸门、脱敏用量台账与失败候选止损；
- `qwen-audio-3.0-tts-flash` AI旁白、SRT字幕和音频技术质检；
- 太阳主案例36.64秒本地预演视频（H.264/AAC、三段推拉、烧录字幕），未调用付费视频模型；
- `qwen3-vl-flash`两轮视觉审核、人工裁决和SVG v2局部修订；
- 人工智能与教育技术两套跨主题权威证据包、Qwen事实卡、人工科学审核及可编辑SVG成品；
- FastAPI同源托管React生产构建、FC 9000端口容器定义和NAS `/data`持久化策略；
- 公网零配置候选：自动匿名签名会话、项目隔离、默认不限体验次数、单实例生成队列和生产启动校验；
- 调用记录、费用估算、引用文档与人工科学审校留痕。

## 版本备份与接手制作

Git历史从2026-08-31首次导入开始，版本说明见`VERSION_NOTES.md`。GitHub私有仓库创建、接手运行、bundle恢复及公网部署门槛见`docs/github-and-handoff.md`；Claude＋DeepSeek继续开发的材料清单和可复制提示词见`docs/CLAUDE_DEEPSEEK_HANDOFF.md`。仓库不包含`.env`、本地数据库、账单或完整原始生成档案；这些资料需在脱敏后另行交接。

最终普通用户入口计划为同源公网Web应用：打开网址即可使用，API Key只在云端。Windows桌面包作为制作方备用；源码也可在macOS/Linux或Docker中运行。代码备份不等同已部署公网。

## 最终用户零配置入口（发布候选）

公网部署后，普通用户只需打开HTTPS网址、输入科普问题并等待视频完成，不需要API Key、`.env`、Python或本地安装。浏览器会自动获得不含个人信息的匿名会话，不同浏览器的项目互不可见。部署方需一次性在阿里云配置百炼Key、会话密钥、NAS、并发和费用告警，见[函数计算部署清单](docs/deployment-fc.md)。当前尚未创建公网资源，不能把本说明写成“已上线”。

## 本地运行

### Windows双击启动（推荐）

不要直接双击 `frontend/index.html`。这是 Vite 的入口模板，使用 `file://` 打开时浏览器无法加载 React 模块，因此会显示空白页。

1. 双击项目根目录的 `启动本地应用.cmd`；
2. 等待浏览器自动打开 `http://127.0.0.1:5173/`；
3. 使用结束后双击 `停止本地应用.cmd`；
4. 启动失败时查看 `.local-logs` 文件夹。

### 后端

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item ..\.env.example ..\.env
uvicorn app.main:app --reload --port 8000
```

### 前端

```powershell
cd frontend
npm install
npm run dev
```

访问 `http://localhost:5173`。默认 `MOCK_AI=true`，无需API Key。

## 接入真实百炼

1. 在百炼华北2（北京）创建本项目专用API Key；
2. 项目已经创建 `.env`，不需要再次复制；
3. 在 `.env` 填写 `DASHSCOPE_API_KEY`；
4. 将 API Key 页面上的 `OpenAI compatible` 专属 Base URL 完整复制到 `DASHSCOPE_BASE_URL`；Key 和 Base URL 必须属于同一业务空间；
5. 将 `MOCK_AI=false`；
6. 确认 `QWEN_TEXT_MODEL` 是当前北京业务空间可用的模型ID；
7. 重启后端并调用 `/api/posters/plan`；
8. 任何时候都不要把 `.env`、完整Key或控制台密钥截图提交到Git。

## API

以下包含历史开发接口。`PUBLIC_ACCESS_ENABLED=true`的最终公网模式只开放`/api/studio/*`、健康检查和公开配置，旧接口返回404，避免绕过公开额度；本地开发模式仍可使用完整列表。

- `GET /api/health`：健康状态与Mock模式；
- `GET /api/config/public`：前端可公开配置，不返回密钥；
- `POST /api/knowledge/query`：调用已发布的百炼知识库应用，执行引用/阈值证据门槛；
- `POST /api/posters/plan`：生成事实卡、证据缺口和海报叙事规格。
- `POST /api/posters/render-svg`：把结构化方案渲染为可编辑 SVG 海报。
- `POST /api/visual-assets/specs`：从事实卡建立视觉资产规格和候选上限；
- `POST /api/videos/storyboard`：从同一事实链建立AI旁白＋字幕视频分镜；
- `POST /api/revisions/plan`：将人工反馈分流为证据阻断或局部修订。
- `GET /api/videos/editor/solar`：读取太阳案例最新草稿及修订影响，无模型调用；
- `POST /api/videos/editor/solar/analyze`：检查字幕长度、阅读时长、配音复用和内容复核需求；
- `POST /api/videos/editor/solar/auto-fix`：生成无损字幕拆分/时长延长建议，不自动应用；
- `PUT /api/videos/editor/solar`：保存不可覆盖的新草稿版本，旧版本冲突返回409；
- `GET /api/videos/editor/solar/versions/{version}`：读取历史版本，v0是已认可成片基线。

## 下一阶段

有声卡通片：启动本地应用后，点击首页“观看卡通科普视频”，或访问`http://127.0.0.1:5173/solar-animation/voiced.html`。约67秒，代码动画+千问旁白+短字幕；用户已认可试听版，尚非最终科学审核通过的参赛成品。旧84秒无声动态分镜保留在`/solar-animation/index.html`。

自动修正工作台：访问`http://127.0.0.1:5173/?view=storyboard`，点击一次“自动检查并修正”，系统检查7镜、修正字幕/时长、复检并自动留档，无需手动应用或保存。默认只展示摘要，展开查看修改前后；手动微调默认折叠。检查记录中可载入明确标记的练习输入。当前不调用模型、不覆盖视频；旁白含义改写与视频重生成尚未接入。操作及边界见`docs/storyboard-editor-guide.md`。

1. [已更新] 原36.64秒海报朗读只保留为过程证据；约67秒有声卡通版已获用户认可，进入逐镜修订流程；
2. [已完成] 教育技术、人工智能两个跨主题代表案例、人工审核和首页预填入口；
3. [进行中] 公网零配置保护与本机生产预检已通过；待阿里云连接GitHub实构建、NAS挂载、HTTPS地址和一条真实公网视频验收；
4. [已完成草稿] 官方DOCX提交模板和90秒演示脚本；待团队资料、WPS逐页目检和正式录屏。

详细设计见[`docs/visual-generation-roadmap.md`](docs/visual-generation-roadmap.md)。

低成本部署方案见[`docs/deployment-fc.md`](docs/deployment-fc.md)。

提交证据映射见[`docs/submission-evidence-index.md`](docs/submission-evidence-index.md)，录制顺序见[`docs/demo-video-script-v001.md`](docs/demo-video-script-v001.md)。
# v0.2.0：跨主题工作台

新增独立项目、资料快照、海报/独立分镜、最多两轮千问自动审核修订、前后对比与草稿包导出。使用说明及实际边界见[跨主题工作台](docs/studio-guide.md)。旧太阳动画和分镜仍保留。

封装版有预构建前端时，可运行`python scripts/run_packaged.py`或Windows双击`启动封装版.cmd`，访问`http://127.0.0.1:8000/`。它只需要一个后端服务，不需Vite；不是免安装EXE。请继续遵守下方的环境配置与密钥保护要求。

### 换电脑或换系统

- 通用源码包：安装 Python 3.11+，创建虚拟环境后执行 `pip install -e "./backend[video]"`，再运行 `python scripts/run_packaged.py`。macOS/Linux 建议安装 Noto CJK；也可通过 `SCIVIS_FONT_PATH` 指定中文字体。
- 容器：`docker build -t scivis .`，然后 `docker run --env-file .env -p 9000:9000 -v scivis-data:/data scivis`；作品数据在命名卷中，重启容器不会丢失。
- 程序会使用当前操作系统的原生 HTTPS 证书库，并在启动前检查视频依赖、FFmpeg、中文字体、数据目录可写性和百炼配置。不要通过关闭 TLS 校验“修复”网络错误。
- 每台设备需配置自己的 `.env`，不要复制或上传他人的 Key。如程序目录只读，将 `SCIENCE_POSTER_DATA_DIR` 设为用户可写目录。
