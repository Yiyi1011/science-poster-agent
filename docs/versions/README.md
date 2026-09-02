# 版本导航：制作过程与最终交付分开

**目前仍在制作阶段，没有最终交付版。** `main` 是当前制作代码，不代表最终验收通过。

## 制作过程版本

| 标签 | 一句话说明 | 适合什么时候查找 |
|---|---|---|
| [v0.1.0-baseline](https://github.com/Yiyi1011/science-poster-agent/tree/v0.1.0-baseline) | 首次导入海报原型、太阳有声样片及字幕自动修正 | 查看最初的可运行基线；不是此前每一天的历史代码 |
| [v0.1.1-handoff](https://github.com/Yiyi1011/science-poster-agent/tree/v0.1.1-handoff) | 添加私有仓库备份和接手教程 | 查如何克隆、配置密钥和交接 |
| [v0.1.2-handoff-check](https://github.com/Yiyi1011/science-poster-agent/tree/v0.1.2-handoff-check) | 根据新目录恢复测试修正安装顺序 | 查前端构建与后端测试的先后关系 |
| [v0.2.0-studio](https://github.com/Yiyi1011/science-poster-agent/tree/v0.2.0-studio) | 跨主题项目、证据隔离、Qwen自动修订、单端口启动 | 查看原先的3—5镜和事实卡式海报实现 |
| [process/v0.3.0-preview](https://github.com/Yiyi1011/science-poster-agent/tree/process/v0.3.0-preview) | 公众文案与证据分层、6—8镜、问题自动检索入口 | 查纯脚本阶段；[变更和局限](process/v0.3.0-preview.md) |
| [process/v0.4.0-preview](https://github.com/Yiyi1011/science-poster-agent/tree/process/v0.4.0-preview) | 基础问题检索、详细讲解；默认卡通MP4、AI旁白字幕，海报选做 | 查首个视频优先版；[变更和局限](process/v0.4.0-preview.md) |
| [process/v0.4.1-preview](https://github.com/Yiyi1011/science-poster-agent/tree/process/v0.4.1-preview) | 修复卡通规划结构中断、官方资料后备与摘录超长清空 | 查结构修复与首条AI主题成片；[变更和局限](process/v0.4.1-preview.md) |
| [process/v0.4.2-preview](https://github.com/Yiyi1011/science-poster-agent/tree/process/v0.4.2-preview) | 修复WAV异常头导致字幕首句重复；右侧显示真实制作进度并自动切换成片 | 查时间轴与制作台修复；[变更和局限](process/v0.4.2-preview.md) |
| [process/v0.4.3-preview](https://github.com/Yiyi1011/science-poster-agent/tree/process/v0.4.3-preview) | 完整句字幕与自适应换行；Claude＋DeepSeek提示词、私有数据备份和回退交接 | 查完整句字幕与交接设计；[变更和局限](process/v0.4.3-preview.md) |
| [process/v0.4.4-preview](https://github.com/Yiyi1011/science-poster-agent/tree/process/v0.4.4-preview) | 显式关闭SQLite连接，修复Windows私有数据备份临时文件占用 | 最新稳定交接点；[变更和局限](process/v0.4.4-preview.md) |
| [process/v0.5.0-preview](https://github.com/Yiyi1011/science-poster-agent/tree/process/v0.5.0-preview) | 通用闭环四题端到端：任意问题→检索→讲解→6—8镜→审核→AI旁白字幕→可播放MP4 | M1验收点；[变更和局限](process/v0.5.0-preview.md)；内容仍须人工试听与科学终审 |
| [process/v0.5.1-preview](https://github.com/Yiyi1011/science-poster-agent/tree/process/v0.5.1-preview) | 用户只提问题，千问自动补证据并默认生成视频；重复项目可恢复归档；Windows启动预检 | M1—M3制作候选；[变更、实测和局限](process/v0.5.1-preview.md)；仍非最终交付 |
| [process/v0.5.6-preview](https://github.com/Yiyi1011/science-poster-agent/tree/process/v0.5.6-preview) | 权威资料恢复、水色7镜68秒真实成片、页面统一滚动、跨设备数据/证书/字体/容器候选 | 明日封装前检查点；[变更、实测和局限](process/v0.5.6-preview.md)；未创建final |
| `process/v0.5.8-preview`（待推送标签） | 公网零配置候选：匿名会话隔离、透明额度、单实例队列、生产启动校验和NAS部署清单 | 云端部署前检查点；[变更、验证和局限](process/v0.5.8-preview.md)；未创建final |
| [process/v0.4.5-handoff](https://github.com/Yiyi1011/science-poster-agent/tree/process/v0.4.5-handoff) | 下一阶段唯一执行说明：任意问题到视频、UI优化、Windows封装 | Claude＋DeepSeek接手入口；[执行说明](../NEXT_STAGE_EXECUTION_BRIEF.md)，功能沿用v0.4.4 |

旧标签原样保留，不移动、不重写历史。以后制作里程碑统一用 `process/v版本号-preview`；每次标签对应一个明确的Git提交，而不是把所有历史文件复制到当前目录。

## 最终交付版本

[最终交付区](final/README.md)目前只有验收门槛，没有软件包。

完成验收后另建 `final/v1.0.0` 标签，GitHub Release 标题以“最终交付”开头，且不是 Pre-release；制作包只放在“过程版本”发布区并标记 Pre-release。**现在不预先创建最终标签，不把本地样片或AI复检通过等同于最终作品验收。**

最终交付说明需包含：对应commit、运行教程、完整功能/局限、测试证据、赛事材料位置、包SHA256、数据迁移与接手说明。敏感密钥和私人原始材料不得上传仓库。

## 怎样找、怎样恢复

1. 在本页选择对应标签，即可浏览那一版完整代码；先读该版README和变更说明。
2. 找具体功能实现时用[代码文件索引](../CODE_MAP.md)，每个代码文件都有简述。
3. 不懂Git时，可在标签页用 Code → Download ZIP，解压到新的目录；不要覆盖正在运行的工作目录。
4. Git用户可新目录克隆，再运行 `git switch --detach 标签名`。准备修改时使用 `git switch -c 自己的新分支名`。
5. `.env`、本地项目数据库和生成档案不在Git里。代码版本与作品版本是两条不同的历史：作品的v1/v2保存在应用中，导出草稿ZIP包含完整修改记录。

版本不会自动包含后来的修复。例如旧版海报可以复现当时的效果，但不应当作当前推荐结果。
