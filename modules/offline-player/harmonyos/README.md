# 听力课堂 · 鸿蒙电脑浏览器版

面向 HarmonyOS 5 及以上的华为鸿蒙电脑。播放、界面和猫鼠开场都在一个 HTML 文件里。学生用华为浏览器打开即可，音频和字幕在本机读取。

## 学生怎么用

1. 从 [鸿蒙电脑版 Release](https://github.com/Arikimizord/english-listening-local-trainer/releases/tag/player-harmonyos-v0.1.0) 下载并解压。把 `听力课堂-鸿蒙电脑.html` 放到文件管理的 **个人 → 下载 → 浏览器**，用华为浏览器打开。项目里的本机成品也可直接发送该 HTML。
2. 点击 **打开音频和字幕**，同时选中同一节课的音频和同名 `.json` 或 `.srt`。也可以一起拖入页面，或先打开音频，再点 **选择字幕**。浏览器只读你选中的文件，所以单独选择音频时还需要选字幕。
3. 空格播放或暂停，左右方向键切句，H 显示或隐藏字幕。还可以调速度、音量和字号，开启单句循环或句末暂停，拖选字幕后按 Ctrl+C 复制。

以 `lesson.mp3`、`lesson.json`、`lesson.srt` 为例，JSON 用于逐词高亮，SRT 用于逐句字幕。同名 JSON 必须与原音频的哈希一致。若某台电脑的浏览器无法解码录音，可向老师索取同一录音的标准 MP3 或 WAV 及对应 SRT。

华为建议从上述目录打开本地 HTML。播放器已内嵌样式、脚本和动画，下载后可离线使用。[华为官方说明](https://consumer.huawei.com/cn/support/content/zh-cn16057326/)

## 构建与验证

开发者从播放器目录运行 `python harmonyos/build.py`，输出 `harmonyos/dist/听力课堂-鸿蒙电脑.html`。Python 仅用于打包。鸿蒙版和 Mac 版共用播放界面及字幕内核。

Windows Chrome 已在阻断页面联网、禁用 Web Crypto 的条件下用本地样本验证了播放、同名字幕、词级高亮、切句、循环、句末暂停与 SRT 回退。华为浏览器的文件选择和音频解码仍需在学生的鸿蒙电脑上确认。
