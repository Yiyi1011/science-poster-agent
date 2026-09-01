# 代码文件索引

先按[版本导航](versions/README.md)找到版本，再在该标签下查看本索引。一个Git标签就是一份完整代码快照，无须把每份代码重复复制进目录。

## 当前通用工作台

| 文件 | 简要说明 |
|---|---|
| [backend/app/services/studio_media.py](../backend/app/services/studio_media.py) | 按脚本版本生成插画、视觉检查与重画、配音和媒体任务留痕 |
| [backend/app/services/studio_video.py](../backend/app/services/studio_video.py) | 实际配音时序、停顿、字幕和卡通/插画MP4合成；卡通默认不做PNG |
| [backend/app/services/studio_cartoon.py](../backend/app/services/studio_cartoon.py) | 千问规划对象/动作、非法装饰图标兼容与结构修复留痕、通用卡通绘制、视觉检查及同版旁白复用 |
| [backend/tests/test_studio_extended.py](../backend/tests/test_studio_extended.py) | 基础问题检索、完整讲解、媒体幂等/路径/拒绝候选和本地视频回归 |
| [scripts/verify_studio_media.py](../scripts/verify_studio_media.py) | 显式收费的单项目媒体实测脚本；不要当免费单元测试运行 |
| [scripts/qa_studio_media.mjs](../scripts/qa_studio_media.mjs) | 只读浏览器验证视频优先、实际播放、MP4下载、修改记录和选做海报 |
| [scripts/record_media_review.py](../scripts/record_media_review.py) | 追加明确人工复核意见，不覆盖模型检查或原视频 |
| [scripts/recompose_cartoon.py](../scripts/recompose_cartoon.py) | 复用原方案和配音修正程序动效，不调用AI；旧MP4保留且记录程序修正 |
| [frontend/src/main.tsx](../frontend/src/main.tsx) | 前端入口，默认通用工作台；`view=legacy/storyboard`进入早期页面 |
| [frontend/src/Studio.tsx](../frontend/src/Studio.tsx) | 问题输入、自动找资料、海报预览、分镜播放及修改历史 |
| [frontend/src/studio.css](../frontend/src/studio.css) | 工作台主体布局、独立滚动、手机适配和弹窗 |
| [frontend/src/studio-updates.css](../frontend/src/studio-updates.css) | 自动来源入口和来源追溯折叠区样式 |
| [backend/app/main.py](../backend/app/main.py) | FastAPI入口、路由注册、健康检查和前端静态托管 |
| [backend/app/config.py](../backend/app/config.py) | 从本地环境读取模型、地域、预算配置；不要把真实密钥写进代码 |
| [backend/app/studio_routes.py](../backend/app/studio_routes.py) | 项目、生成任务、版本海报和ZIP导出接口 |
| [backend/app/studio_models.py](../backend/app/studio_models.py) | 来源、事实、公众文案、图解和分镜的数据结构与长度限制 |
| [backend/app/services/studio_pipeline.py](../backend/app/services/studio_pipeline.py) | 通用提示词、生成/审核/自动修订/复检、语文与证据结构检查 |
| [backend/app/services/studio_research.py](../backend/app/services/studio_research.py) | 百炼搜索、搜索异常时官方概念页后备、原文段落ID选择、合规长度裁剪和来源快照 |
| [backend/app/services/studio_store.py](../backend/app/services/studio_store.py) | SQLite项目、只追加的版本、检索快照、任务去重与恢复 |
| [backend/app/services/public_poster.py](../backend/app/services/public_poster.py) | 新版白话海报SVG排版、图标和按词换行 |
| [backend/app/services/studio_export.py](../backend/app/services/studio_export.py) | 兼容旧版海报，导出SVG、独立分镜、估算字幕和版本记录 |
| [backend/app/services/qwen_client.py](../backend/app/services/qwen_client.py) | 百炼千问文本调用、结构化输出、脱敏回执 |
| [backend/app/services/model_policy.py](../backend/app/services/model_policy.py) | 限制千问模型和百炼北京接口；执行本地预算暂停线 |
| [backend/app/services/usage_ledger.py](../backend/app/services/usage_ledger.py) | 文字、图片、视觉审核、旁白的用量与费用估算记录 |
| [backend/app/data/studio-presets.json](../backend/app/data/studio-presets.json) | AI和学习方法两个可选教学资料示例，不是问题检索器 |
| [backend/tests/test_studio.py](../backend/tests/test_studio.py) | 隔离、去重、证据、修订、失败保留与接口测试 |
| [backend/tests/test_public_studio.py](../backend/tests/test_public_studio.py) | 公众文案、新旧版兼容、原文检索安全和失败停止测试 |
| [scripts/verify_public_studio.py](../scripts/verify_public_studio.py) | 有预算保护的真实Qwen跨主题验证；执行会调用付费接口 |
| [scripts/verify_studio_live.py](../scripts/verify_studio_live.py) | v0.2最初两主题真实模型验证 |
| [scripts/refine_studio_live.py](../scripts/refine_studio_live.py) | v0.2两主题的开发者反馈修订记录 |
| [scripts/qa_studio.mjs](../scripts/qa_studio.mjs) | 隔离Mock浏览器测试：生成、预览、导出、手机布局 |
| [scripts/qa_public_layout.mjs](../scripts/qa_public_layout.mjs) | 只读回放真实保存项目，检查6—8镜、手机宽度和SVG文字边界，不触发模型调用 |

## 早期海报与模型组件（保留，不代表均已接入新版）

| 文件 | 简要说明 |
|---|---|
| [frontend/src/App.tsx](../frontend/src/App.tsx) | 早期海报表单与方案预览 |
| [frontend/src/api.ts](../frontend/src/api.ts) | 早期前端API封装 |
| [frontend/src/types.ts](../frontend/src/types.ts) | 早期海报接口类型 |
| [frontend/src/styles.css](../frontend/src/styles.css) | 早期页面和共享基础样式 |
| [backend/app/models.py](../backend/app/models.py) | 早期海报请求、事实卡及计划结构 |
| [backend/app/services/pipeline.py](../backend/app/services/pipeline.py) | 早期海报生成管线与知识库读取 |
| [backend/app/services/bailian_app_client.py](../backend/app/services/bailian_app_client.py) | 百炼知识检索/应用接口调用 |
| [backend/app/services/svg_renderer.py](../backend/app/services/svg_renderer.py) | 早期事实卡海报SVG渲染 |
| [backend/app/services/visual_workflow.py](../backend/app/services/visual_workflow.py) | 图像候选、审校和视觉工作流程记录 |
| [backend/app/services/qwen_image_client.py](../backend/app/services/qwen_image_client.py) | 千问图像生成接口及图像预算控制 |
| [backend/app/services/qwen_vision_reviewer.py](../backend/app/services/qwen_vision_reviewer.py) | 千问视觉模型对图片的审核 |
| [backend/app/services/qwen_tts_client.py](../backend/app/services/qwen_tts_client.py) | 千问旁白合成与音频记录 |
| [backend/tests/test_api.py](../backend/tests/test_api.py) | 早期API与模型组件回归测试 |
| [scripts/verify_poster_pipeline.py](../scripts/verify_poster_pipeline.py) | 验证早期海报管线 |
| [scripts/verify_knowledge_app.py](../scripts/verify_knowledge_app.py) | 验证百炼知识服务连接 |
| [scripts/run_retrieval_eval.py](../scripts/run_retrieval_eval.py) | 固定知识库检索题集评估 |
| [scripts/bootstrap_visual_workflow.py](../scripts/bootstrap_visual_workflow.py) | 建立早期视觉工作档案 |
| [scripts/generate_first_visual_asset.py](../scripts/generate_first_visual_asset.py) | 首轮真实模型视觉资产生成实验 |
| [scripts/generate_cross_topic_cases.py](../scripts/generate_cross_topic_cases.py) | 早期跨主题样例生成实验 |
| [scripts/apply_cross_topic_science_review.py](../scripts/apply_cross_topic_science_review.py) | 将开发者科学复核落实到早期跨主题作品 |
| [scripts/render_solar_weather_svg.py](../scripts/render_solar_weather_svg.py) | 太阳天气主题专用海报绘制 |
| [scripts/render_svg_png.mjs](../scripts/render_svg_png.mjs) | 浏览器将SVG渲染成PNG |
| [scripts/recover_latest_poster_plan.py](../scripts/recover_latest_poster_plan.py) | 从历史档案恢复最近海报计划 |
| [scripts/review_poster_with_qwen_vl.py](../scripts/review_poster_with_qwen_vl.py) | 真实视觉模型审核海报实验 |
| [scripts/review_and_regenerate_hero.py](../scripts/review_and_regenerate_hero.py) | 主视觉候选审核后再生成 |
| [scripts/adjudicate_vision_review.py](../scripts/adjudicate_vision_review.py) | 保存开发者对视觉审核结果的裁决 |
| [scripts/reject_hero_and_generate_background.py](../scripts/reject_hero_and_generate_background.py) | 淘汰主视觉候选并尝试背景候选 |
| [scripts/reject_background_candidate.py](../scripts/reject_background_candidate.py) | 记录背景候选未通过，不将其混入正式成品 |

## 太阳动画与字幕编辑（案例专用）

| 文件 | 简要说明 |
|---|---|
| [frontend/src/StoryboardEditor.tsx](../frontend/src/StoryboardEditor.tsx) | 太阳分镜、自动修正痕迹和可选人工修改界面 |
| [frontend/src/storyboard-editor.css](../frontend/src/storyboard-editor.css) | 太阳分镜编辑页面样式 |
| [backend/app/storyboard_routes.py](../backend/app/storyboard_routes.py) | 太阳分镜加载、修订与导出API |
| [backend/app/services/storyboard_editor.py](../backend/app/services/storyboard_editor.py) | 太阳分镜版本、字幕和时长自动修正 |
| [frontend/public/solar-animation/index.html](../frontend/public/solar-animation/index.html) | 太阳无声卡通动画预演 |
| [frontend/public/solar-animation/voiced.html](../frontend/public/solar-animation/voiced.html) | 太阳有声样片播放入口 |
| [frontend/public/solar-animation/player.js](../frontend/public/solar-animation/player.js) | 太阳有声播放器控制 |
| [frontend/public/solar-animation/player.css](../frontend/public/solar-animation/player.css) | 播放器样式 |
| [backend/tests/test_storyboard_editor.py](../backend/tests/test_storyboard_editor.py) | 分镜编辑与版本验证 |
| [backend/tests/test_storyboard_automatic_run.py](../backend/tests/test_storyboard_automatic_run.py) | 太阳分镜自动处理任务回归 |
| [scripts/test_solar_animatic.mjs](../scripts/test_solar_animatic.mjs) | 太阳动画时序/结构断言 |
| [scripts/export_solar_animatic_script.mjs](../scripts/export_solar_animatic_script.mjs) | 导出太阳动画文案脚本 |
| [scripts/export_solar_animatic_video.mjs](../scripts/export_solar_animatic_video.mjs) | 捕获并导出太阳卡通动画视频 |
| [scripts/export_video_package.py](../scripts/export_video_package.py) | 汇集早期视频素材、字幕和元数据 |
| [scripts/compose_local_preview_video.py](../scripts/compose_local_preview_video.py) | 合成早期海报朗读式预演视频 |
| [scripts/synthesize_video_narration.py](../scripts/synthesize_video_narration.py) | 早期视频旁白合成 |
| [scripts/synthesize_solar_animatic.py](../scripts/synthesize_solar_animatic.py) | 太阳卡通分镜旁白合成 |
| [scripts/repair_audio_metadata.py](../scripts/repair_audio_metadata.py) | 修正音频时长等元数据 |
| [scripts/check_audio_package.py](../scripts/check_audio_package.py) | 检查音频文件和交付元数据 |
| [scripts/check_solar_animatic_export.py](../scripts/check_solar_animatic_export.py) | 检查太阳动画导出结果 |
| [scripts/check_solar_narrated_export.py](../scripts/check_solar_narrated_export.py) | 检查有声太阳动画导出结果 |
| [scripts/qa_solar_animatic.mjs](../scripts/qa_solar_animatic.mjs) | 无声太阳动画浏览器测试 |
| [scripts/qa_solar_narrated.mjs](../scripts/qa_solar_narrated.mjs) | 有声太阳样片浏览器测试 |
| [scripts/qa_storyboard_editor.mjs](../scripts/qa_storyboard_editor.mjs) | 太阳编辑器浏览器基础测试 |
| [scripts/qa_storyboard_editor_live.mjs](../scripts/qa_storyboard_editor_live.mjs) | 太阳编辑器实际服务测试 |
| [scripts/qa_storyboard_automatic_flow.mjs](../scripts/qa_storyboard_automatic_flow.mjs) | 检查太阳自动处理流程 |
| [scripts/qa_storyboard_autocorrection.mjs](../scripts/qa_storyboard_autocorrection.mjs) | 检查太阳自动修正及前后对比 |

## 启动、配置、打包

| 文件 | 简要说明 |
|---|---|
| [启动封装版.cmd](../启动封装版.cmd) | 调用封装版PowerShell启动器 |
| [scripts/launch-packaged.ps1](../scripts/launch-packaged.ps1) | 寻找Python环境并启动单端口应用 |
| [scripts/run_packaged.py](../scripts/run_packaged.py) | 验证端口与项目身份，隐藏启动服务，成功后开浏览器 |
| [启动本地应用.cmd](../启动本地应用.cmd) / [停止本地应用.cmd](../停止本地应用.cmd) | 早期双端口开发启动/停止入口 |
| [scripts/start-local.ps1](../scripts/start-local.ps1) / [scripts/stop-local.ps1](../scripts/stop-local.ps1) | 早期开发服务管理；接手者优先使用新版封装启动器 |
| [scripts/package_release.py](../scripts/package_release.py) | 从已提交代码与前端构建制作本地ZIP和Git bundle |
| [scripts/audit_repository.py](../scripts/audit_repository.py) | 上传前检查敏感文件和疑似密钥，不输出密钥原文 |
| [Dockerfile](../Dockerfile) | 容器构建定义，不代表已公网部署 |
| [.env.example](../.env.example) | 配置示例；真实密钥只能放本机`.env` |
| [backend/pyproject.toml](../backend/pyproject.toml) | Python版本、依赖和测试配置 |
| [frontend/package.json](../frontend/package.json) / [package-lock.json](../frontend/package-lock.json) | 前端脚本和锁定依赖 |
| [frontend/vite.config.ts](../frontend/vite.config.ts) | Vite开发端口、代理和构建配置 |
| [frontend/index.html](../frontend/index.html) | React入口模板，不能用文件协议双击当成完整应用 |
| [frontend/src/vite-env.d.ts](../frontend/src/vite-env.d.ts) | TypeScript的Vite环境声明 |
| [backend/app/__init__.py](../backend/app/__init__.py) / [services/__init__.py](../backend/app/services/__init__.py) | Python包标记，无业务逻辑 |

`cross-topic-cases/`是资料整理与审校说明；`docs/`是教程和交接文档；`frontend/public/solar-animation/media/`是允许随仓库保存的太阳样片素材，不是生成器代码。其他配置JSON提供画面和流程参数，改动后也应随版本提交。

任何带`generate`、`synthesize`、`review`或`verify_*live`的实验脚本都应先读文件说明；部分会调用真实模型。接手者不要逐个双击运行全部脚本。
