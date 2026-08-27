# 多设备并行开发 Git 工作流

本项目由多台设备（笔记本 / 台式机 / 服务器等）并行开发。为避免互相覆盖、减少冲突，
统一采用「分支隔离 + main 仅做集成」的策略。任何设备上的 agent（opencode）在开始写代码前，
请先阅读本文件并遵守下列规则。

## 核心原则
1. **不在 `main` 上直接开发**：每台设备使用自己的长期分支。
2. **`main` 只做集成**：由某一台设备（或被指派者）把各分支合并进 `main` 后推送。
3. **绝不 `git push --force`**：确需强推时用 `git push --force-with-lease`。
4. 推送前先 `git fetch` / `git pull --rebase`，保持线性历史。

> 本仓库已设置 `git config pull.rebase true`（仓库级），`git pull` 默认变基。

## 分支命名
- 设备分支：`dev-laptop` / `dev-desktop` / `dev-server`（按实际设备取名）
- 功能分支：`feat/<主题>` / `fix/<主题>`（如 `feat/refund-withdrawal`）

## 每台设备：一次性初始化
```bash
git fetch origin
git checkout main
git pull --rebase

# 保护本机未提交改动
git checkout -b dev-<设备名>
git add -A
git commit -m "wip: <设备名> 当前进度"
git rebase origin/main
git push -u origin dev-<设备名>

git config --global pull.rebase true
git config --global push.default current
```

## 日常开发（三台都一样）
```bash
git checkout dev-<设备名>   # 已在该分支可跳过
# 编辑代码…
git add -A && git commit -m "feat/fix: …"
git push                    # 只推自己的分支，绝不动别人
```

## 合并到 main（只在一台设备做）
方式 A — GitHub PR（推荐，冲突在网页解）：
从 `dev-xxx` 发起 PR 到 `main`，审核后点击合并。

方式 B — 本地合并：
```bash
git checkout main
git pull --rebase origin main
git merge dev-laptop dev-desktop dev-server   # 逐个或一起合
# 若有冲突：解冲突 → git add → git commit → git push origin main
```

## Agent（opencode）代执行授权
经用户**明确授权**后，agent 可代执行以下操作（默认不主动做，先询问）：
- 把 `dev-<设备>` 分支快进合并进 `main`：
  `git checkout main && git merge --ff-only origin/dev-<设备> && git push origin main`。
- 在 `main` 被意外强推/分叉、且诊断确认安全后，用 `git push --force-with-lease origin main` 恢复正确历史。

授权边界：agent **绝不**在用户未确认的情况下无差别 `git push --force` 到 `main` 或他人分支；
对**自己的** `dev` 分支 rebase 后同步可用 `git push --force-with-lease origin dev-<设备>`。
完整操作见 opencode skill `multidevice-git`（仓库内 `.opencode/skills/multidevice-git/SKILL.md`）。

## 红线
- 不要 `git push --force` 到 `main` 或他人分支。
- `main` 上不做直接功能开发。
- 每天开工前 `git fetch` 看一眼他人分支进度，避免大规模分叉。

## 说明：为什么不会“静默覆盖”
Git 不会静默丢代码：后推的非快进提交会被服务端拒绝（`! [rejected] (non-fast-forward)`），
逼你先拉再推；若改了同一文件，`rebase`/`merge` 会要求手动解冲突。真正的覆盖只来自 `--force`。
分支隔离后，各设备的 `push` 只影响自己的分支，不再可能互相覆盖。
