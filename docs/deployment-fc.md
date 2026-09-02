# 阿里云函数计算低成本部署方案

状态：公网零配置发布候选已准备，尚未创建任何计费云资源。

2026-09-02更新：最终用户入口改为同源公网Web应用。匿名浏览器会自动获得签名会话，项目彼此隔离；创建、审核和制片有透明额度，全局生成队列受控；旧版付费接口在公网模式关闭。最终用户无需账号、API Key、`.env`或本地安装。百炼Key和会话签名密钥只配置在FC环境变量中。

这仍是发布候选清单：价格和试用资格须以部署当天控制台为准。创建云资源前先由负责人确认。不要把真实Key写入镜像、GitHub、源码ZIP或截图。

## 推荐架构

使用一个阿里云函数计算（FC）Web函数承载整个应用：FastAPI同时提供`/api/*`和构建后的React静态文件。这样前后端同源，不需要单独购买服务器、OSS或域名，也不会把百炼API Key暴露到浏览器。

推荐区域：华北2（北京），与当前百炼业务空间一致。

## 推荐配置

| 项目 | 建议值 | 原因 |
|---|---:|---|
| 类型 | Web函数，自定义容器或Funciton AI Web项目 | 适合FastAPI常驻HTTP服务 |
| 监听 | `0.0.0.0:9000` | FC自定义容器默认CAPort为9000 |
| vCPU / 内存 | 1 vCPU / 2 GB起步 | 本服务本地绘制1280×720帧并用FFmpeg合成视频，512 MB不是本版验收配置 |
| 最小实例数 | 验收/答辩期间1，结束后0 | 当前任务在单进程后台持续执行；答辩期保活，非展示期降为0节省费用 |
| 最大实例数 | 1 | SQLite、任务集合与生成队列按单实例设计，禁止横向扩容 |
| 单实例并发 | 至少5 | 一个生成任务运行时仍需接受前端进度轮询和媒体读取 |
| 执行超时 | 900秒或更长 | 官方允许更长超时；需覆盖检索、两轮审核、逐镜检查、TTS与合成 |
| 临时磁盘 | 10 GB | FFmpeg中间帧和音频需要空间；仅作为工作空间，不作为唯一成品存储 |
| 持久目录 | NAS挂载到`/data` | SQLite、项目、音频、字幕和MP4必须跨实例回收保存 |
| HTTP触发器 | HTTPS公网地址 | 代码内匿名会话、额度和队列已启用；Key不下发浏览器 |

## 必须配置的环境变量

从本地`.env`逐项复制到FC环境变量界面，但不要上传`.env`文件或截图：

- `APP_ENV=production`
- `MOCK_AI=false`
- `ALIBABA_REGION=cn-beijing`
- `DASHSCOPE_API_KEY`（项目专用Key）
- `DASHSCOPE_BASE_URL`（与Key同一北京业务空间）
- `BAILIAN_WORKSPACE_ID`
- `BAILIAN_APP_ID`
- `RETRIEVAL_MIN_SCORE=0.50`
- `QWEN_TEXT_MODEL=qwen-plus`
- `SCIENCE_POSTER_DATA_DIR=/data`
- 现有预算相关环境变量
- `PUBLIC_ACCESS_ENABLED=true`
- `PUBLIC_SESSION_SECRET`（至少32位随机值，只在FC环境变量中保存）
- `PUBLIC_PROJECTS_PER_DAY=12`
- `PUBLIC_RUNS_PER_HOUR=6`
- `PUBLIC_MEDIA_PER_HOUR=3`
- `PUBLIC_MAX_ACTIVE_JOBS=1`
- `PUBLIC_MAX_QUEUED_JOBS=4`

同源部署时`ALLOWED_ORIGINS`填写最终函数URL；后端不需要也不会把Key返回给前端。生产启动会校验真实千问模型、北京HTTPS端点、Key、绝对持久目录、签名密钥和队列参数，缺一项即停止启动。

## 费用控制

1. 正式答辩和公开验收期间最小实例数设为1，避免后台视频任务因实例回收中断；展示结束后改为0。
2. 不购买CU资源包，先使用试用额度或按量付费；低流量演示不需要预付费计划。
3. FC官方计费说明指出：某函数在一个小时内有调用或持续资源使用时，若该小时折算费用低于0.01元，会按0.01元最低计费。因此“偶尔访问”的理论下限约为每个发生调用的小时0.01元，实际还要加模型、知识库、日志和外网流量费用。
4. 部署后立即设置10元费用预警；沿用全项目70元暂停、100元上限。
5. 不开启最小实例、预留实例、GPU、NAS或长期日志存储。

## 当前代码已完成的部署准备

- React生产构建由Docker多阶段构建生成。
- FastAPI同源托管`frontend/dist`，未知`/api/*`不会错误回退到HTML。
- 容器监听`0.0.0.0:9000`。
- `.dockerignore`明确排除`.env`、日志、原始模型产物和本地评测资料。
- 云端持久数据统一写入NAS挂载目录`/data`；临时磁盘只承载可丢弃的中间文件。
- 健康检查地址：`/api/health`。
- 容器保持单worker，监听`0.0.0.0:9000`，HTTP keep-alive设为900秒。
- 公开模式自动签发HttpOnly/SameSite匿名会话；不同浏览器看不到彼此项目。
- 公开模式关闭旧海报规划和本地太阳分镜接口，避免绕过工作台额度。

## 部署前仍需用户完成

1. 在FC控制台确认是否可领取新用户CU试用额度。
2. 选择“Funciton AI连接代码仓库自动构建”或“ACR镜像＋自定义容器”。当前电脑没有Docker，优先前者。
3. 如果采用代码仓库，需要提供一个私有GitHub、Gitee、GitLab或Codeup仓库并在FC控制台授权连接；密钥只放FC环境变量。
4. 创建函数前截图计费配置、答辩期最小实例数1/最大实例数1、NAS挂载和费用预警，作为预算与合规证据。

## 官方依据

- FC Web函数兼容Web框架、可按需扩缩，默认无流量时释放实例。
- 自定义容器HTTP服务必须监听`0.0.0.0:CAPort`，默认端口9000。
- 自定义容器HTTP服务需支持至少15分钟请求超时/Keep-Alive，容器需在120秒内启动。
- FC临时磁盘会随实例回收而清除；需长期保存的视频和项目应使用NAS或OSS，本项目首版采用NAS以保持现有SQLite/文件接口。
- FC支持从GitHub等代码仓库持续部署；本项目使用私有GitHub仓库并由负责人在控制台授权。

官方文档（部署日再次核对）：

- https://help.aliyun.com/en/functioncompute/custom-container/
- https://help.aliyun.com/en/functioncompute/web-function-quick-start
- https://help.aliyun.com/en/nas/user-guide/use-function-compute-to-upload-or-download-files-over-the-internet
- https://help.aliyun.com/en/functioncompute/selection-of-function-storage
- https://help.aliyun.com/en/functioncompute/migrate-existing-web-projects-to-funciton-ai-to-realize-service-serverless-and-continuous-deployment
