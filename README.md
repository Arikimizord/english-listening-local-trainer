# 英语听力训练专用播放器

## 让你的本地 Agent 帮你部署

将下面这一句话发送给你电脑上**能读取文件、运行终端的本地编程 Agent**（例如 Codex、Claude Code 或 Cline）：

> 请将 https://github.com/Arikimizord/english-listening-local-trainer 克隆到我选择的本地目录，先阅读根目录 AGENTS.md 和两个模块的 README；检查 Windows x64、NVIDIA GPU、驱动与磁盘条件，符合条件后按 docs/INSTALL.md 运行 setup.ps1，下载并校验本仓库 models-v1 Release 的固定模型分卷，完成 doctor 检查并打开字幕工作站，同时告诉我离线播放器 EXE 在哪里；只在项目目录安装，不升级固定依赖、不上传我的音频，遇到条件不符或校验失败请停止并说明。

这是一条**发给 Agent 的自然语言指令，不是 PowerShell 命令**。模型和依赖的联网下载已在该指令中明确授权；Agent 仍会遵守你本机的权限与确认机制。你需要先安装并登录所用 Agent；本项目不提供 Agent 服务或 API 额度。首次部署可能下载多 GB 文件，GPU/驱动不符合条件时不能靠一句话绕过。

只想听音频、已有字幕？直接使用 [离线播放器模块](modules/offline-player/README.md)，无需部署字幕工作台、Python 或模型。需要自己生成字幕？查看 [字幕工作台模块](modules/subtitle-workstation/README.md)。

**AGENTS.md 是给 Agent 的部署与维护说明，不是程序运行依赖。** 普通用户不使用 Agent 也能按 README 操作。当前提供可执行安装脚本和固定模型校验，但尚未在全新电脑完成整套安装验证，不能承诺所有 Agent 或电脑均能无人值守成功。

面向英语教师、四六级备考者和需要逐句精听的自主学习者的本地听力备课与训练工作流。

**代码许可证：MIT · 原创猫角色与 Learn with Adam 品牌保留权利**

[工作台安装](docs/INSTALL.md) · [使用指南](docs/USAGE.md) · [维护与验证](docs/MAINTENANCE.md) · [本地示范导入](examples/README.md) · [原创素材条款](ASSETS-LICENSE.md)

## 为什么分成两个模块

**备课电脑负责制作，教室电脑负责播放。** 转写和词级对齐需要模型、大量存储及 NVIDIA GPU；上课播放只需要音频、字幕和一个轻量 Windows 程序。二者通过同名音频、JSON、SRT 文件交接，不要求教室电脑安装 Python、模型或联网。

推荐场景：教师提前在有 GPU 的电脑上生成字幕并试听修订，再将课堂包复制到离线教室电脑；学生使用已准备好的课堂包逐句精听、循环与变速训练。也适合强调音频留在本机的个人备课工作流。

当前主要支持英文音频、Windows 10 x64。转写端采用固定版本 faster-whisper-large-v3 与英文 wav2vec2 对齐；播放器使用 Windows 自带 WPF/MediaElement，软件渲染，不新增运行包。课堂播放器并非转写软件：没有字幕也能播放音频，但词级高亮需要对应 JSON 词轴。

## 仓库结构

```
modules/
  subtitle-workstation/  # 本地转写、词级对齐、WebUI、修订、导出与固定依赖
    scripts/            # 生产代码、安装/下载工具及契约测试
    config/             # 锁定依赖与模型 revision/哈希
    planning/           # 仅保留 doctor 需要的包版本基线，不包含主机记录
  offline-player/       # 离线 WPF 播放器
    src/                # 播放器与三秒猫鼠加载动画
    assets/             # 原创加载动画素材，权利保留
    dist/               # 当前验收版本的 EXE
    build.ps1           # 使用系统 .NET Framework 编译器构建
examples/               # 当前一套真题示范的本地导入说明，不含媒体
docs/                  # 架构、使用、重建与发布审查
```

## 两个模块怎么用

播放器：进入 `modules/offline-player/dist/` 打开 `听力课堂.exe`，拖入音频；同名 JSON 优先加载，找不到时加载 SRT。支持词轴高亮、选词、字幕显隐、倍速、音量、单句循环、句末暂停、切句与全屏。源代码构建入口：在 Windows PowerShell 中运行 `modules/offline-player/build.ps1`。

字幕工作台：需先按重建文档准备私有运行环境与固定模型，再双击 `modules/subtitle-workstation/字幕工作站.cmd`。网页只绑定本机随机会话地址；导入音频或填写本地路径，生成后试听修订，下载课堂包并复制到播放器。启动时不自动下载模型。

## 准确性与适用边界

识别结果需要人工试听，词轴存在不代表字幕已通过审核。原实现针对本机 NVIDIA GPU 配置做过验证，不承诺任意电脑即装即用。模型首次安装需要网络，生产处理离线；播放器不调用识别模型。当前不是手机应用、在线服务、完整题库管理平台或无 GPU 的通用转写工具。

## 维护与数据

修改播放器呈现层时不要改变字幕解析和播放状态机；修改工作台时保留独立修订版本、音频哈希校验、取消/恢复与结构化 CLI 协议。用户任务、缓存、运行环境和模型权重不进 Git；固定依赖与模型下载来源进 Git。审核过的成品状态不因新版本自动迁移。

代码和原创文档采用 [MIT](LICENSE)；猫动画与 Learn with Adam 名称/Logo 适用 [独立权利声明](ASSETS-LICENSE.md)，不授予商标许可。第三方组件适用 [上游许可证](THIRD-PARTY-NOTICES.md)。因此工作流代码开放不等于所有图像和品牌均采用开放许可证。

按作者确认，本仓库不上传真题音频及字幕；仅提供这一套示范的本地导入方法。模型通过 [固定模型 Release](https://github.com/Arikimizord/english-listening-local-trainer/releases/tag/models-v1) 分发，默认安装器会校验并安装；模型大文件不进入 Git 历史，环境与缓存也不进入 Git。已有验收针对作者本机；新电脑的首次安装与 GPU 兼容性仍需验证。
