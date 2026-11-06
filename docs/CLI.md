# 工作台 CLI 协议

所有命令默认离线并返回单个 UTF-8 JSON；`--json`、`--offline` 是可选的显式标记；`--help` 是人读文本，作为 JSON 协议的例外。不会自动下载或换模型，不会自动批准成品。

## 入口

推荐 agent 通过参数数组调用 `pwsh -NoProfile -File <工作台>/workstation.ps1 ...`；也可使用 `workstation.cmd`，但需遵守 Windows CMD 引号规则。输入音频等复杂路径放在配置 JSON 中，避免拼接 shell 命令。入口不依赖调用者当前目录，结束后恢复调用进程的环境和目录。

```powershell
$r = (Resolve-Path './modules/subtitle-workstation').Path
& "$r\workstation.cmd" doctor --json
& "$r\workstation.cmd" plan --config "$r\config\examples\local-audio.json" --json
& "$r\workstation.cmd" run --config "$r\config\examples\local-audio.json" --json
& "$r\workstation.cmd" status --job <job_id> --json
& "$r\workstation.cmd" cancel --job <job_id> --json
& "$r\workstation.cmd" run --job <job_id> --resume --json
& "$r\workstation.cmd" review --job <job_id> --json
& "$r\workstation.cmd" review --job <job_id> --apply <text-patch.json> --json
& "$r\workstation.cmd" export --job <job_id> --json
```

`run` 默认同步执行，stdout 仅在结束时输出结果；agent 可用进程会话保持运行，另一个调用查询 status 或请求 cancel，无后台服务。`--stage asr|align|export|all` 可设停点；asr 停点成功不代表已经生成全部字幕。

## 配置

```json
{"schema_version":1,"audio":"E:\\某目录\\音频.mp3","language":"en","timeout_seconds":1800}
```

只接受本地音频，拒绝 URL/UNC、无音轨媒体及未知配置字段；相对音频路径相对于配置文件。先 probe 再执行，plan 不创建任务。模型缺失或改变会报错，不自动补下载。

可选 `reference_text` 是参考英文字符串，仅允许音频≤60秒；长音频应提供 `reference_segments`，如 `[{"start":0,"end":10,"text":"English transcript"}]`，每段≤60秒且严格位于原始媒体时间轴内。两个参考字段不能同时使用；没有参考则先转写，再提供文本修订补丁。不自动 OCR PDF，不让 agent 以猜测补全文案。

## 状态、恢复与哈希

- 返回 schema_version、ok、command、stage、review_status、outputs、warnings、errors，任务命令另含 job_id；错误未知任务时 job_id 可为空。
- job_id 为32位小写十六进制。`created/running/completed/failed/canceled/needs_realign` 是技术状态；owner_review/review_status 保持 pending。
- `run --config` 始终创建新任务并复制输入快照；旧任务恢复始终使用该快照，不吸收原始文件后来的变化。音频或配置要改变，请建新任务，不编辑 job.json/config-snapshot.json。
- 每阶段写原子结果与 SHA-256 收据；只有指纹、状态与文件哈希同时匹配才复用。代码、依赖锁或模型锁变化会使缓存失效；缺失/损坏产物重算；旧补丁基线不符会显式报冲突。
- 任务锁与工作台 GPU 锁保证正常调用中同一任务/同一 GPU 重任务互斥；取消由持有真实 Popen 句柄的管理器终止自己创建的进程，不按任意 PID 杀进程。
- 受控取消和阶段边界可恢复；不要直接强杀管理器。强杀可留下孤儿 worker，检测到仍存活则拒绝修改；父进程创建子进程到登记 child_pid 的极窄崩溃窗口尚无绝对保证。PID 被系统复用时保守拒绝，不自动杀其他进程；需要人工核对日志与进程身份。
- `status` 对父进程已死的运行记录提供 observed_status；不是后台监控服务，进度粒度为当前阶段，日志见任务 asr.log/align.log。

## 人工文本补丁

review 每次创建新的 reviews/<修订号>/text-patch.json，不覆盖已有手改文件；保留 base_transcript_sha256，只编辑 segment_text 的段号对应文本。apply 保存独立 patches/<修订号>.json，多份补丁按顺序覆盖指定段的文字；每份都绑定同一 ASR 基线。配置了参考原文时不再混用 ASR 补丁，需新建参考任务。

apply 会清除当前成品指针并使 align/export 失效，随后必须 resume 重对齐；ASR 可命中原缓存。旧导出修订保留，export 重新核对快照、ASR、有效补丁文本、管线和词轴；禁止拿旧轴配新文字。更换 ASR 基线后旧补丁须人工重做，不能静默迁移。

第 4 步提供文件协议，没有波形编辑器/GUI/播放器按钮；词轴直接修订和试听界面留待第 5 步。

## 导出

每次新修订存 exports/<修订号>/，含 JSON、SRT、基础 ASS 和哈希 manifest。导出后统一为 pending；句级 SRT 不自带词级放大，ASS 只做基础卡拉 OK 变色。缺词轴、重叠、文字不符或厘秒冲突会明示降级句级；不均分句子时间伪造词轴。warnings 可为字符串或结构化对象。实际播放器视觉验收、当前词放大样式属于后续阶段。

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 技术成功，仍待用户审核 |
| 2 | 参数、配置、路径或输入文件错误 |
| 3 | 环境/模型未就绪 |
| 4 | 任务/GPU 被占用或锁异常 |
| 5 | 工作进程失败、超时或内部错误 |
| 6 | 用户取消或受控中断 |
| 7 | 输入/补丁/缓存基线冲突，需要重跑或人工处理 |

核心不调用云端、LLM 或新依赖安装；原生解码库并非系统级网络沙箱，需更强网络约束时使用用户管理的防火墙。不要把短样本通过写成全库字幕精度通过。
