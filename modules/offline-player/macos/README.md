# 听力课堂 · macOS Apple Silicon

Apple Silicon 预览版沿用 Windows 版的课堂配色、三秒猫鼠开场和播放控件。播放器通过系统 WebKit / AVFoundation 或 Safari 读取本地音频和字幕，运行时无需联网、模型、Python、Electron 或 Rosetta。

## 直接使用

从 [播放器预览 Release](https://github.com/Arikimizord/english-listening-local-trainer/releases/tag/player-v0.4.0) 下载 Safari 离线包，完整解压后，用 Safari 打开 `听力课堂.html`。使用“打开课堂包”选择包含音频和同名字幕的目录，或把这些文件一起拖入。也可单独打开音频，再点“选择字幕”。一个文件夹若含多份音频，建议直接选择所需音频和对应字幕。

桌面 App 单独提供 arm64 压缩包，采用临时签名。需要直接使用免安装入口时可选择 Safari 离线包。

## 构建桌面 App

在装有 Xcode Command Line Tools 的 Apple Silicon Mac 上打开终端，进入本目录并执行 `bash ./build.command`。成功后双击生成的 `听力课堂.app`。构建产物为 arm64，采用本机临时签名。可以把目标路径作为第一个参数传入，其上级目录需已存在。

桌面版可直接选取或拖入 MP3、M4A、WAV、AAC 或音频 MP4，按音频所在目录自动查找同名字幕。优先使用通过音频哈希校验的 JSON，有同名 SRT 时可在 JSON 校验失败后退回 SRT。一并拖入不同名字幕可手动配对。已有部分题库音频使用 `.mp3` 扩展名、内部为 MP4/AAC，播放器按真实容器打开原件。

## 课堂操作

- 空格播放或暂停，左右方向键切句并播放，H 隐藏或显示字幕。隐藏状态在切句后保留。
- 单句循环与句末暂停互斥。句末暂停后再次播放会从下一句开始。断句策略标记为 `unresolved` 的 JSON 会提示先审核字幕。
- 拖动进度条或按 ±15 秒定位。支持 0.75×、1×、1.25×、1.5×、音量、字幕字号、全屏。桌面版支持 F11 与 Esc，必要时配合 Mac 键盘的 Fn。
- 暂停后拖选字幕或双击选词，按 ⌘C 复制。音量、倍速、字号和近期播放位置保存在当前用户本机。

可按 [本地示范导入](../../../examples/README.md) 准备音频和字幕。猫角色与 Learn with Adam 品牌权利保留，见 [素材声明](../../../ASSETS-LICENSE.md)。

Windows Chrome 已用本地样本验证播放、定位、切句、词轴高亮、选词、盲听、倍速、音量、循环、句末暂停与续播。macOS Golden Gate 27.0.1、M5 实机上的 Safari 播放和资源占用仍待验证。
