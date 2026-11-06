# 架构与维护

## 边界

工作台 workstation.ps1 加载进程级隔离环境，workstation-bootstrap.py 进入核心。workstation-core.py 管理配置、任务、哈希、锁、阶段与导出；pipeline-worker.py 执行离线 GPU 阶段；subtitle_formats.py 负责格式校验与导出；sentence_units.py、boundary_repair.py、quality_pipeline.py 负责断句与重复校验。webui-server.py 是本机 WebUI 服务，review-server.py 管理独立人工修订，两个 HTML 文件仅负责交互呈现。

播放器 Player.cs 管理 WPF 界面、音频、字幕、词轴及用户设置；LoadingScene.cs 是启动时限为三秒的独立呈现组件。两模块只通过文件交接，无 Python 或模型耦合。

## 修改原则

保留音频与配置快照、原子结果、哈希绑定、阶段缓存指纹、任务互斥、受控取消与独立修订版本。新任务的审核状态保持 pending；代码、文本或音频变化后不得静默沿用不匹配词轴。UI 外观更新不能移除按钮 ID、事件行为或字幕选词。

## 检查

工作台已安装后，在新的 PowerShell 进程中加载 scripts/environment.ps1，再用该模块 envs/subtitle/Scripts/python.exe -I -B -X utf8 scripts/test-stage4-unit.py。该契约测试不执行模型，但需要已安装 Python 包与本地 NLTK 资源；测试写入模块 temp 下独立目录，不依赖作者真实任务。当前 16 项通过。

播放器通过 build.ps1 重新构建。提供你有权使用的长音频及 JSON/SRT 时，可运行 EXE 的 --smoke <audio> <subtitle> <report>；此检查实际播放音频，要求长于 1000 秒、字幕超过 200 句，只适用于符合这些条件的回归素材。仅报告首行 PASS 才算通过。短素材可运行 --test-srt <srt> <report> 检查解析，但不等于真实媒体播放。

首次安装编排尚未完成全新电脑端到端验证；不要把作者原机的既有媒体与 GPU 成功记录泛化为所有平台通过。

## 提交与发布

不提交 jobs/ui/cache/envs/models/runtime/temp、日志、个人设置、真实课堂包、秘密或完整题库。提交前运行 tools/audit-release.py，并检查 docs/source-manifest.json 与 Git 最终文件清单。模型/运行时下载和开源代码发布是不同操作；更新固定版本需核对上游与重新验证。修改品牌或美术素材前先读 ASSETS-LICENSE.md。

## 固定模型发行附件

models-v1 是独立于代码 Git 历史的固定模型发行包。发布时必须检查原模型锁中的全部文件，排除 .cache/lock/下载元数据，只打包所需权重、模型配置、分词文件、英文断句资源和许可。修改模型内容或分卷字节后应使用新模型包版本和新 manifest，不覆盖旧版本附件。仓库 config/model-bundle-v1.json 是安装器信任的校验清单，必须与已发布的附件一致。
