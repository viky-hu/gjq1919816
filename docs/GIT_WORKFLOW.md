# Git 协作手册

本文档约定团队如何从 `main` 创建工作分支、推送代码，并由维护者合并回主线。

## 一、分支规则

- `main` 是稳定主线，不直接开发。
- 队友只能把自己的工作推送到个人分支，不能直接推送 `main`。
- 分支名使用以下格式：
  - `feature/<topic>`：新功能
  - `fix/<topic>`：问题修复
  - `chore/<topic>`：依赖、配置或工程维护
  - `docs/<topic>`：文档
- 每个分支只处理一个主题，避免把多个不相关功能混在同一个 PR 中。

示例：

```text
feature/login-window
fix/retrieve-timeout
chore/update-dependencies
docs/git-workflow
```

## 二、第一次获取项目

```powershell
git clone https://github.com/viky-hu/gjq1919816.git
cd gjq
git switch main
git pull --ff-only newfront main
```

如果仓库已经克隆过，先确认没有未保存的修改：

```powershell
git status
```

## 三、队友开始工作

每次开始新任务，都从最新的 `main` 创建新分支：

```powershell
git switch main
git pull --ff-only newfront main
git switch -c feature/<topic>
```

不要在 `main` 上直接开发，也不要把别人的分支作为自己的长期工作分支。

## 四、提交和推送

完成一个逻辑完整的小步骤后提交：

```powershell
git status
git add <修改过的文件>
git commit -m "feat: describe the change"
```

提交消息建议使用以下前缀：

```text
feat: 新功能
fix: 问题修复
chore: 工程维护
docs: 文档变更
refactor: 重构
test: 测试
```

第一次推送该分支：

```powershell
git push -u newfront feature/<topic>
```

后续提交直接推送：

```powershell
git push
```

## 五、提交 PR 前同步主线

在 PR 发起前，先把最新 `main` 的变化带到自己的分支。个人分支可以使用 rebase，让 PR 更容易阅读：

```powershell
git fetch newfront
git rebase newfront/main
git push --force-with-lease
```

只对自己的个人分支使用 `--force-with-lease`。不要对 `main` 使用 force push。

如果 rebase 出现冲突：

```powershell
git status
# 手动解决冲突后
git add <已解决的文件>
git rebase --continue
```

如果需要放弃本次 rebase：

```powershell
git rebase --abort
```

## 六、发起和合并 PR

队友完成工作后：

1. 将分支推送到 GitHub。
2. 创建 Pull Request，目标分支选择 `main`。
3. 在 PR 描述中说明修改内容、验证命令和已知限制。
4. 请求维护者审核。
5. 根据审核意见继续在同一分支提交并推送。

维护者合并时：

- 选择 GitHub 的 **Create a merge commit**。
- 不选择 **Squash and merge**。
- 不选择 **Rebase and merge**。
- 合并前确认 PR 已经基于最新 `main`，并完成必要检查。
- 合并后删除已经完成的远端 feature 分支。

这样 Git 图会保持清晰的形状：

```text
main:    A────B────────────M
                    \      /
feature:             C──D─
```

其中 `M` 是 merge commit，第一父提交来自 `main`，第二父提交来自 feature 分支。

## 七、维护者的本地备用合并方式

如果无法使用 GitHub PR，维护者可以在本地执行：

```powershell
git switch main
git pull --ff-only newfront main
git fetch newfront feature/<topic>
git merge --no-ff --no-edit newfront/feature/<topic>
git push newfront main
```

本地合并也必须使用 `--no-ff`，这样分支关系会保留在提交图中。

## 八、本次历史重写后的恢复

本仓库在 **2026 年 8 月 21 日** 整理过一次历史。旧历史保存在远端分支：

```text
archive/main-before-history-rewrite-2026-08-21
```

如果本地没有未提交修改，直接同步新主线：

```powershell
git fetch newfront
git switch main
git reset --hard newfront/main
```

如果本地有未提交修改，先保存：

```powershell
git status
git stash push -u -m "before main history rewrite sync"
git fetch newfront
git switch main
git reset --hard newfront/main
git stash pop
```

如果本地有尚未推送的提交，先创建备份分支：

```powershell
git switch -c backup/<your-name>-before-history-rewrite
git push -u newfront backup/<your-name>-before-history-rewrite
git fetch newfront
git switch main
git reset --hard newfront/main
```

之后再从新 `main` 创建新的工作分支，并通过 PR 合入。不要把旧的独立历史重新 merge 回新主线。

## 九、常用检查

查看当前分支和工作区：

```powershell
git status --short --branch
```

查看分支图：

```powershell
git log --graph --oneline --decorate --all
```

确认自己的分支是否基于最新主线：

```powershell
git merge-base --is-ancestor newfront/main HEAD
```

确认没有待提交内容：

```powershell
git diff --check
git status
```

## 十、禁止事项

- 不要直接 push `main`。
- 不要使用 `git push --force`。
- 不要把两个独立仓库的根提交用 `--allow-unrelated-histories` 拼进项目主线。
- 不要用同一个长期分支承载多个无关任务。
- 不要未经审核把未验证的代码合入 `main`。
