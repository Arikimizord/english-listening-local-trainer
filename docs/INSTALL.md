# 安装与重建

## 只使用离线播放器

Windows 10/11 x64，具备 .NET Framework 4.x/WPF 和 Windows 媒体解码组件。打开 modules/offline-player/dist/听力课堂.exe 即可。精简系统或 Windows N 版的媒体组件需单独检查；目前没有承诺全平台兼容。

从源码构建：在仓库根目录打开 Windows PowerShell，运行：

```powershell
powershell -NoProfile -File ./modules/offline-player/build.ps1
```

输出为 modules/offline-player/dist/听力课堂.exe。资源已预生成，无需 npm、NuGet 或 Python。编译可能提示兼容旧 .NET Framework 的 FormattedText 构造器弃用警告；它不影响构建。

## 配置本地字幕工作台

当前固定方案为 Windows x64 + NVIDIA CUDA GPU，建议 8 GB 显存起步、16 GB 以上内存、40 GB 以上可用磁盘作为安装余量（建议值，不是经过穷举测试的最低配置）。原作者本机为约 8 GB 显存。转写与对齐依次运行；关闭其他占显存程序。CPU/AMD/Apple GPU 暂无已验证流程。

首次安装需网络：访问官方 GitHub/uv/Python、PyPI、PyTorch 与 Hugging Face，下载固定版本依赖和模型。生产音频不上传。下载量为多 GB，模型约 3.5 GB，解包、轮子和缓存另占空间；请放在空间充足的本地磁盘，不使用需要管理员权限的系统目录或网络盘。

在仓库根目录新开子 PowerShell 执行：

```powershell
powershell -NoProfile -File ./modules/subtitle-workstation/setup.ps1
```

安装器创建模块本地目录，校验 uv 压缩包，安装私有 Python 3.11.18，下载并校验 Torch 2.8.0+cu128，按带哈希锁文件同步依赖，下载并校验私有 FFmpeg 7.1.1，再从本仓库 models-v1 Release 下载四个分卷、验证分卷及模型原文件哈希并安装模型和 NLTK 资源，最后执行 doctor。不修改持久 PATH、系统注册表或全局 Python，不自动更换模型或回退 CPU。

setup.ps1 是对当前已验收安装工具的开源编排入口；已完成语法及依赖入口检查，尚未在全新电脑重新下载全套环境。安装失败请保留输出并检查上游可访问性、磁盘、驱动和固定包版本；不要为“通过”而跳过哈希校验。断点下载文件保留在 cache；再次运行会按下载器逻辑校验和复用。

仅准备运行时可传 -SkipModels，但此时无法进行生产或通过完整 doctor；再次不带该参数运行以准备模型。安装阶段联网，后续工作台生产入口显式离线；缺模型时报告错误，不会在转写中临时下载。

打开 modules/subtitle-workstation/字幕工作站.cmd。保持启动终端运行，使用它打开的随机本机网址。若旧网址失效，重启并使用新网址，不向局域网开放端口。

## 版本锁

- config/requirements.in：直接依赖；requirements-win-py311.lock：完整版本/哈希。
- config/models-stage3.lock.json：固定模型 revision 和文件完整性信息。
- planning/environment-validation.json：仅保留 doctor 必需的包名与版本基线。
- 私有 FFmpeg/uv 下载工具内有固定 URL 与校验和。

运行时、模型和第三方二进制不随 Git 分发；不复制作者的虚拟环境作为安装方法。

## 固定模型附件与备用下载

默认模型来源为本仓库 models-v1 Release，config/model-bundle-v1.json 固定四个分卷的大小与 SHA-256，以及合并整包和文件的 SHA-256。原有 models-stage3.lock.json 还校验上游 revision、大小及 SHA-256/Git blob SHA-1。模型不需要用户自行选择版本。

已有分卷时运行 setup.ps1 -ModelBundleDirectory <绝对目录>。模型包包含权重、配置、分词文件、英文 NLTK 资源与上游许可证；不包含 Python/CUDA/FFmpeg 环境、音频或生产任务。四个卷必须齐全，安装时还需要临时合并与解包空间。

可用 `setup.ps1 -UseUpstreamModels` 显式改用原锁定上游下载；仍固定 revision 并核对哈希，不下载 latest 权重。若仅安装模型至已有运行环境，可用该环境的 Python 运行 scripts/install-model-bundle.py --directory <绝对目录>。--verify-only 会检查完整模型包而不安装。网络中断可重跑下载工具续传；校验失败应保留错误并检查文件，不绕过。
