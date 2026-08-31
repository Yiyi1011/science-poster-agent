# GitHub备份、版本恢复与制作交接

## 1. 用户现在只需创建私有空仓库

1. 在 https://github.com 登录自己的账号。没有账号先注册；密码、验证码只在官方页面输入。
2. 打开 https://github.com/new 。
3. Owner选择自己的账号，Repository name填 `science-poster-agent`。
4. Description可填“跨主题科普可视化智能体：海报、分镜及自动修订”。
5. Visibility选择 **Private**；不勾选README，.gitignore和License选None。已有本地代码，不需要在远端生成第二份初始化文件。
6. 点击Create repository，将浏览器地址栏的仓库URL提供给协作者即可，不要提供密码、Token、Cookie或API Key。
7. 后续推送如要求登录，在GitHub官方认证页面自己完成。仓库网址不是写入授权；没有授权不能声称代码已上传。

官方说明：[创建仓库](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)。若同名仓库已经存在，先核对里面是否有内容，禁止直接覆盖或强推。

## 2. 仓库里有什么、不包含什么

- 包含：React/FastAPI源码、锁定的前端依赖清单、测试、公开资料摘录与来源台账、部署配置、操作文档、已确认的约67秒演示视频及字幕。
- 排除：`.env`、个人密钥、私有数据库、运行日志、原始API响应、账单及未脱敏截图、原始模型产物、`node_modules`、本地虚拟环境。
- `artifacts/`、`evidence/`中的完整研究/生成档案仍在原电脑；数据库、逐镜原始WAV、原始海报及全部评审记录不在代码包中。重做原动画时可能需要单独移交原始资产。
- 根工作区的比赛DOCX、盖章报名表、完整制作日志也不在本代码仓库内。提交证据索引提及的这些文件需要另行提供，不能把缺失档案写成“仓库已有”。
- `.env.example`仅是安全配置样例。不同接手者应自行建立百炼Key，原制作者可以撤销不再使用的Key。

本地检查（项目根目录运行）：

```powershell
python scripts/audit_repository.py --staged
```

它检查暂存区里的真实内容，不打印匹配到的密钥。扫描只是防护措施，不保证识别所有敏感信息；提交前仍应人工查看文件列表，截图不能随意入库。

## 3. 接手者首次运行：先用不扣模型费的模式

本项目不是只有HTML的静态网页。需要Python（项目声明>=3.11）、Node.js和Git；前端依赖以`frontend/package-lock.json`为准。

在新克隆目录中准备Python环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "./backend[dev,video]"
```

打开第一个PowerShell窗口启动后端：

```powershell
cd backend
$env:MOCK_AI = "true"
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

在项目根目录打开第二个PowerShell窗口启动前端：

```powershell
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

打开 http://127.0.0.1:5173/ 。Mock只是流程演示，不会生成可直接参赛的真实科学内容。两个窗口要保持运行；退出可按Ctrl+C。

双击启动器目前存在Windows脚本兼容/等待问题，已按用户意向暂缓处理。交接时以以上明确命令为准，不承诺启动器已经修好。

需要真实模型时，在本机从`.env.example`新建`.env`，填写自己的百炼北京配置并重启服务；不提交`.env`，也不将其上传GitHub。项目专用知识库仍是原账号的外部资源，接手者需迁移资料和重新配置，不会随Git自动转移。

离线测试（后端目录）：

```powershell
..\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

前端构建与本地动画测试（分别在前端目录、项目根目录）：

```powershell
npm run build
node --test scripts/test_solar_animatic.mjs
```

## 4. 版本和离线备份怎么使用

- Git提交：保存一次经过验证的代码改动及说明。
- 版本标签：固定一个重要里程碑，如`v0.1.0-baseline`。
- `.bundle`：保存Git提交、分支和标签；不保存未提交文件、密钥或GitHub服务器设置。
- `.zip`：方便直接阅读某个版本的源码；没有完整Git历史，不能替代bundle。

恢复bundle到一个**尚不存在的新目录**，不要覆盖正在工作的项目：

```powershell
git clone -b main "备份文件的完整路径.bundle" "新的恢复目录"
```

然后进入恢复目录，执行`git log --oneline --decorate`和`git tag`检查版本。恢复仓库的origin会指向本地bundle，并不是GitHub；正式协作前再核对并设置正确远端地址。

以后创建新备份时，在仓库内运行`git bundle create "新的备份文件路径.bundle" --all`及`git bundle verify "该备份文件路径.bundle"`。每次使用新文件名，保留旧备份。备份只含已提交内容，创建前先核对`git status`。

WPS同步同一目录不是独立的灾难恢复备份。建议把bundle再复制到另一台设备或独立存储位置，并保留GitHub私有远端副本。

## 5. GitHub协作与项目转让

通常先邀请接手者为私有仓库协作者，保留自己账号下的仓库；确定交接关系后再考虑转移所有权。不要把个人GitHub账号密码交给对方。代码访问、百炼资源、费用账号、域名和参赛材料是不同的交接对象。

转移仓库需在GitHub执行正式转移流程，接收方确认；并不自动移交阿里云账号或密钥。转移前保留本地bundle。官方说明：[仓库转移](https://docs.github.com/en/repositories/creating-and-managing-repositories/transferring-a-repository)。

## 6. 公网部署是另一阶段

当前尚未创建云端服务。Dockerfile是准备文件，不代表已验证真实FC构建或已上线。`docs/deployment-fc.md`中的历史配置/价格只是旧参考，部署当天必须重新核对官方控制台。

在开放真实模型之前，必须完成：

1. 登录或访问码保护、调用频率限制、预算闸门；避免任何人通过匿名接口消耗额度或读取草稿。
2. 持久化项目/版本存储；不能依赖FC临时目录保存唯一副本。
3. 无资料时的证据阻断、密钥仅保留服务端、上传文档隔离。
4. 确认试用额度、付费配置和项目70元暂停/100元实付上限；不默认购买资源。
5. 验证部署失败可回到上一个标签，不覆盖源代码和本地证据档案。

目前优先推进跨主题资料入口和独立项目存储，它们也为后续部署提供基础。
