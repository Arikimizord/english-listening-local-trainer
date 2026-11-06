# Local Agent deployment and maintenance instructions

## User-invoked deployment

When the user asks you to deploy this project (including the one-sentence prompt in README.md), that request authorizes project-local downloads and installation of the pinned dependencies and model bundle. First read both module READMEs, docs/INSTALL.md and ASSETS-LICENSE.md. Ask for the target folder only if the user has not selected one and no suitable current checkout exists.

Check Windows x64, NVIDIA GPU/driver, disk space (recommend 40 GB for first installation including temporary model assembly), and existing installation before doing work. Explain missing prerequisites; do not install/change GPU drivers, weaken protections, silently switch models, or use CPU fallback. Reuse a suitable checkout. Never delete or replace a user's environment, models, media or jobs merely to get a clean run.

Run setup.ps1 in a fresh PowerShell child process; default downloads the models-v1 GitHub Release bundle whose expected hashes and revisions are committed in config/model-bundle-v1.json and config/models-stage3.lock.json. A local bundle folder may be supplied with -ModelBundleDirectory; fixed upstream download is an explicit fallback via -UseUpstreamModels. Verify doctor JSON and exit code. Do not report inference/quality success from doctor alone. Open the local WebUI and give the offline EXE location after installation checks. Do not process personal recordings unless explicitly requested. Report compatibility and fresh-machine validation limitations honestly.

Use existing environment/account approval mechanisms. Never ask the user to paste passwords or tokens. A natural-language request does not bypass OS permissions, network policies, or required confirmations.

## Maintenance

Read docs/MAINTENANCE.md. Keep the two modules independent. Preserve hash-bound snapshots, independent revisions, pending human review, and fixed dependency/model versions. Do not publish private data or upload personal recordings. Exclude local caches, environments, model files, jobs, UI state, logs and media from Git. Models are distributed as separately licensed Release assets. Code is MIT; characters and branding are excluded. Run tools/audit-release.py before publication.
