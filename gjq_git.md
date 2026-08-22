## 队友首次同步

先确认有没有未提交工作：

```
git status
```

如果是全新克隆：

```
git clone https://github.com/viky-hu/gjq1919816.git
cd gjq1919816
git switch main
git pull --ff-only origin main
```

如果是现在已有的旧仓库：

```
git fetch newfront
git switch main
git reset --hard newfront/main
```

如果有未提交工作，先保存：

```
git stash push -u -m "before-main-rewrite-2026-08-22"
git fetch newfront
git switch main
git reset --hard newfront/main
git switch -c feature/recover-my-work
git stash pop
```

如果队友有旧分支上的已提交代码，不要直接推送旧分支，应该从新 `main` 创建分支，再使用 `cherry-pick` 搬运需要的提交。

## 日常开发流程

```
git switch main
git pull --ff-only newfront main
git switch -c feature/<topic>

# 修改 final-main/ 或其他项目代码

git add <files>
git commit -m "feat: describe change"
git push -u newfront feature/<topic>
```

之后创建 PR：

```
base: main
compare: feature/<topic>
```

合并方式选择：

```
Create a merge commit
```

## PR 前更新分支

个人分支可以使用 rebase：

```
git fetch newfront
git switch feature/<topic>
git rebase newfront/main
git push --force-with-lease
```

只允许对自己的功能分支使用 `--force-with-lease`，绝对不要对 `main` 使用。

## 必须注意

不要做这些事：

```
git push newfront main
git push --force newfront main
git commit  # 不要在 main 上直接提交
```

修改前端时注意路径已经变成：

```
final-main/apps/main-platform/
```

不再是：

```
newfront/apps/main-platform/
```

提交前建议运行：

```
pnpm --dir final-main type-check
pnpm --dir final-main build
```

目前 `main-platform` 仍有已有 TypeScript/Prisma 类型错误，检查失败时要在 PR 描述中说明，不要把失败结果误认为是 Git 合并问题。