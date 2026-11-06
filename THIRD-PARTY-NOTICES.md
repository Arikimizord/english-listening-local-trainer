# 第三方组件与资源

本仓库公开本项目代码、构建脚本与锁定文件，不打包第三方 Python/FFmpeg/CUDA 运行库、模型权重或真题媒体。安装时从锁定文件指向的上游下载，使用与后续分发仍应遵守各自许可。

| 组件 | 用途 | 上游/许可来源 |
|---|---|---|
| WhisperX | 词级对齐流程 | [上游 BSD-2-Clause](https://github.com/m-bain/whisperX/blob/main/LICENSE) |
| faster-whisper | 本地英文转写 | [上游 MIT](https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE) |
| CTranslate2 | GPU 推理 | [上游 MIT](https://github.com/OpenNMT/CTranslate2/blob/master/LICENSE) |
| faster-whisper-large-v3 | 固定转写模型 | [锁定模型卡](https://huggingface.co/Systran/faster-whisper-large-v3/blob/edaa852ec7e145841d8ffdb056a99866b5f0a478/README.md)，模型卡声明 MIT |
| wav2vec2-base-960h | 固定英语对齐模型 | [锁定模型卡](https://huggingface.co/facebook/wav2vec2-base-960h/blob/22aad52d435eb6dbaf354bdad9b0da84ce7d6156/README.md)，以模型卡条款为准 |
| FFmpeg 7.1.1 full shared | 音频读取 | [构建来源](https://github.com/GyanD/codexffmpeg/releases/tag/7.1.1)；此 full shared 构建按 GPL-3.0-or-later 管理，不随仓库再分发 |
| NLTK punkt_tab | 英文断句 | [固定资源描述](https://github.com/nltk/nltk_data/blob/550b6625bcef1f2abff2ff770a5a0d272c9c6b2a/packages/tokenizers/punkt_tab.xml)，保留资源 README 许可 |
| uv / Python / PyTorch / NVIDIA 库 | 安装与运行 | 分别适用其上游许可证，非本项目 MIT 再授权 |

完整 Python 版本与可接受包哈希在 modules/subtitle-workstation/config/requirements-win-py311.lock。模型 revision、大小、LFS SHA-256 或 Git blob SHA-1 在 models-stage3.lock.json。安装器保留上游模型 README。这里的组件概述不是完整传递依赖许可清单，不代表所有组件均使用 MIT；需要重新打包第三方运行库时须单独审查。

下载脚本保留原模型锁中的上游 JFK 验证资源链接；这些文件仅在用户运行安装流程时下载到本机，不作为本仓库示范媒体上传。
