# 云盘与 Git 的归档陷阱

## 按需下载文件

先检查当前操作系统和云盘客户端。iCloud Finder 的 Download Now / Keep Downloaded 可用于使内容保留在本机；具体入口随系统版本核实。先估算下载与归档同时占用的空间，保持网络和同步状态稳定。移动文件出 iCloud Drive 可能同时从其他设备的 iCloud 中移除它，不能把“移动出云盘”当成无副作用的备份。

哈希会读取内容，可能触发下载。元数据盘点不等于内容已落地；成功读取全部普通文件也不能证明云端没有其他尚未列出的内容。核对云盘同步状态、原始目录范围和读取异常。无法下载的项单列阻塞，不用空文件替代。

官方说明：[Apple：iCloud Drive 文件](https://support.apple.com/guide/mac-help/work-with-folders-and-files-in-icloud-drive-mchl1a02d711/mac)。

## Git 调查清单

在源仓库只读检查；所有结果都留在私有归档记录中，remote URL 可能含认证信息，展示前脱敏。

- `git status --porcelain=v1 --untracked-files=all`：工作区改动与未跟踪文件，另行检查被忽略但有价值的文件。
- `git worktree list --porcelain`：所有 worktree 与分支状态。对每个 worktree 重复检查，不擅自 prune 或 remove。
- `git rev-parse --git-dir --git-common-dir`：确认对象库和公共元数据位置，路径可能位于本目录之外。
- `git show-ref`、`git stash list`、`git reflog --all`：分别检查持久引用、暂存工作与历史线索；不要只看当前分支。
- 经授权同步远端后，对具体本地/远端引用比较提交。无 upstream、远端不可达或未实时核对时，不标记“全部推送”。

`git bundle create PATH --all` 可保存引用可达对象，但不是完整工作区快照。未提交改动、索引、配置、hooks、reflog-only 对象以及 LFS 实体内容等需另行处理。stash 与 linked-worktree 的特殊引用也须逐项验证，不假定一个 bundle 覆盖全部本地状态。若选择额外创建保留引用，先说明对源仓库的修改并取得相应授权。

对子模块逐个保存实际 commit 与独有改动，对 Git LFS 另查实际内容是否可恢复。归档 worktree 时要包含其指向的共享仓库，或制作可独立还原的包并记录对应关系。

验证 bundle 完整性、在隔离位置 clone/还原对应引用并恢复工作区改动；不要以一次 `bundle verify` 的成功代替整个项目的恢复测试。

官方依据：[Git bundle](https://git-scm.com/docs/git-bundle)、[Git worktree](https://git-scm.com/docs/git-worktree)、[Git reflog](https://git-scm.com/docs/git-reflog)。
