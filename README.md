# 项目交付归档与可恢复清理

**Project Delivery Archive · `project-delivery-archive`**

把项目收尾从“整理一下文件”变成可验证的交付：盘点版本、识别云盘占位与 Git 独有历史、逐文件校验、实际恢复，再在明确授权下进行可撤销清理。

## 使用

将 [`project-delivery-archive/`](project-delivery-archive/) 完整放入支持 Agent Skills 的工具的技能目录。例如 Codex 通常使用 `~/.codex/skills/`。

> 使用 $project-delivery-archive，盘点项目源稿和交付目录，建立独立归档与恢复方案。先给出差异和清理候选，不删除文件。

## 包含内容

- [技能入口](project-delivery-archive/SKILL.md)：范围、验证、恢复和清理边界。
- [云盘与 Git](project-delivery-archive/references/cloud-and-git.md)：占位下载、worktree、独有历史、LFS 与子模块。
- [恢复关卡](project-delivery-archive/references/recovery-gates.md) 与 [归档记录模板](project-delivery-archive/assets/archive-record.md)。
- [只读清单工具](project-delivery-archive/scripts/archive_inventory.py)：macOS/Linux 上的 Python 3.10+，标准库；默认仅元数据，显式 `--hash` 后读取内容。不会复制或删除项目文件；使用固定目录句柄避免遍历时被符号链接替换而越界，不支持安全句柄的平台会停止。
- [测试](project-delivery-archive/scripts/test_archive_inventory.py)：临时合成目录中的内容差异、链接、占位提示和防覆盖检查。

```bash
python3 project-delivery-archive/scripts/archive_inventory.py scan /path/to/source --hash --output /outside/source.json
python3 project-delivery-archive/scripts/archive_inventory.py scan /path/to/archive --hash --output /outside/archive.json
python3 project-delivery-archive/scripts/archive_inventory.py compare /outside/source.json /outside/archive.json
python3 -m unittest discover -s project-delivery-archive/scripts -p 'test_*.py'
```

比较通过只证明覆盖范围内的普通文件字节与目录/链接结构匹配。ACL、扩展属性、资源叉、硬链接关系和应用恢复仍需单独验证。公有仓库只含通用方法与合成测试，不应存放真实清单、客户文件或凭据。
