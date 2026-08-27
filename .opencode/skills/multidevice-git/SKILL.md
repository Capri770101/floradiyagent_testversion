---
name: multidevice-git
description: 在多台设备/多个 agent 并行开发一个 git 仓库时，管理分支隔离、设备同步、安全合并到 main，以及从"main 被强推/分叉"事故中恢复。Use when: 多设备协作、分支隔离、同步各设备分支到最新 main、把 dev 分支合并进 main、main 被强制推送或分叉后的恢复（git push --force-with-lease / rebase / 分叉评估）。Triggered by "多设备协作", "同步分支", "main 被强推", "分支隔离", "合并 dev 到 main", "recover forced main", or any parallel multi-device git workflow request.
---

# Multi-Device Git Collaboration & Sync

## Overview

同一仓库被多台设备（或多人/多 agent）并行开发时，直接在 `main` 上开发或 `git push --force main` 会把他人的历史整条冲掉。本 skill 用「分支隔离 + 受控集成 + 受控恢复」三件套根治：

- 每台设备用长期分支 `dev-<设备名>`（如 `dev-caprispc` / `dev-caprisdesktop` / `dev-gongsi`），功能分支可用 `feat/*`。
- `main` 只做集成，禁止直推、禁止强推（除非按"恢复流程"受控执行）。
- 设备间通过 rebase 自己的 `dev` 分支保持与 `main` 同步；集成时由一台机器把 `dev` 合并进 `main`。

## When to Use This Skill

- 用户说"多设备协作 / 分支隔离 / 同步各设备"。
- 要把某个 `dev-<设备>` 分支合并进 `main`。
- `git fetch` 后发现 `origin/main` 被改写（forced update）或与本地分叉，需要恢复。
- 某设备分支落后/分叉，需要 rebase 同步。
- 合并前做分叉与冲突风险评估。

## Core Convention（红线）

1. `main` = 集成分支，**只进不出**（只有合并/恢复时动）。
2. 每台设备拥有唯一 `dev-<设备名>` 长期分支，互不重叠命名。命名用**设备名**（如 `caprisdesktop`），不要用角色名（如 `admin`）。
3. **禁止 `git push --force origin main`**，除非走下方"恢复流程"且已确认安全（用 `--force-with-lease`）。
4. 对**自己的** `dev` 分支可 `git push --force-with-lease origin dev-<设备>`（rebase 后同步），不影响他人。
5. Agent 只有在用户明确授权后，才可代执行 main 集成合并或 `--force-with-lease` 恢复。默认先问。

## Setup（首次）

```
git config pull.rebase true
```
- 若仓库还没有协作规范，创建 `GIT_WORKFLOW.md`（分支隔离 + 集成 + 红线，引用进 `AGENTS.md`）。
- 每台设备建并跟踪自己的分支：
  ```
  git checkout -b dev-<设备名> --track origin/dev-<设备名>   # 远端已有则直接 checkout
  ```
- 若不清楚本机设备名，问用户；不要臆造与现有 `dev-*` 重名的分支。

## Daily Device Flow

```
git fetch
git rebase origin/main          # 在当前 dev-<设备> 上，把本地提交叠到最新 main
# ... 开发、提交 ...
git push --force-with-lease origin dev-<设备>   # rebase 后同步（仅自己的分支）
```
- 本地 `main` 想刷新：`git branch -f main origin/main`（仅当本地 `main` 无独有提交）。
- 有未推改动时务必用 `rebase` 而非 `merge`，避免无意义 merge commit。

## Integration: merge dev -> main

前置：目标 `dev` 分支已基于最新 `origin/main` 且通过验证。

```
git checkout main
git pull --rebase origin main
git merge --ff-only origin/dev-<设备>     # 快进合并，无分叉
git push origin main
git checkout dev-<设备>
git rebase origin/main                     # 保持本机分支最新
```

- 若 `--ff-only` 失败，说明 `main` 已有人推了新提交：先 `git pull --rebase` 再合并，或停下报告分叉。
- 合并后 `dev-<设备>` 与 `main` 同指向，可保留也可后续清理。

## Recovery: main 被强推 / 分叉（事故恢复）

**检测**
```
git fetch origin
git log --oneline -5 origin/main
```
若 `origin/main` 顶端不是你期望的提交（比如出现陌生 baseline、且缺失近期文件），即为被强推。

**诊断（关键：确认能否安全恢复）**
```
git branch -r
git log --oneline -5 origin/main          # 被污染的顶端
git log --oneline -5 HEAD                  # 本地正确历史
# 看被污染基线是否含独有重要提交（相对本地正确提交）
git diff --stat <正确提交> <污染基线>
```
- 若被污染基线相对本地正确提交**没有**独有重要改动（仅多运行时日志/无关文件），则本地正确历史可安全恢复。
- 若被污染基线有他人独有重要提交，**不要**直接覆盖，先与对方协调。

**恢复（受控强推，仅当诊断安全）**
```
git checkout main
git reset --hard <本地正确提交SHA>        # 如 77a867e / 4980260
git push --force-with-lease origin main    # 仅在远端 tip == 期望时才生效
git fetch origin
git rev-parse origin/main                  # 确认 == 本地正确提交
```
- `--force-with-lease` 会在远端已被他人抢先更新时拒绝，避免二次覆盖。
- 本仓库曾遇沙箱 bash 无 GitHub 出口：若 push 报 `Recv failure / Connection reset`，改由用户本机能直连 github 的机器执行该命令。

**事后**
- 通知强推方：停推 `main`，改走 `dev-<设备>` 分支。
- 验证三台 `git pull --rebase` 能拿到正确 `main`。

## Sync a stale device branch（陈旧分支拉平）

某设备分支基于旧 `main` 分出、现 `main` 已前进，直接合并会"删掉"新进度（因为 diff 只看到它缺的提交）。正确做法：

```
git checkout dev-<设备>
git rebase origin/main
git push --force-with-lease origin dev-<设备>
```
- 执行前可先在**临时分支**试 rebase 确认无冲突、净改动符合预期：
  ```
  git checkout -b trial dev-<设备>
  git rebase origin/main
  git diff --stat origin/main HEAD      # 应只剩该设备真实改动
  git checkout dev-<设备>; git branch -D trial
  ```
- 若三台都是同一人操作，可直接 rebase + 强推同步；若多人，先告知该设备所有者。

## Divergence Assessment（合并前必做）

```
git fetch origin
git log --oneline origin/main..origin/dev-<设备>     # 该分支独有提交
git diff --stat origin/main origin/dev-<设备>        # 相对 main 的实际文件差异
```
- 若 `diff --stat` 出现大量"删除"行且这些行正是 `main` 已有内容 → 该分支基于旧 `main`，需先 rebase 再合并（否则会回滚 `main`）。
- 各 `dev` 分支都动核心文件（如 `db.py` / 订单页）时，合并易冲突：要求小步 rebase、早合早消。

## Quick Reference

| 动作 | 命令 |
|---|---|
| 本机同步到最新 main | `git fetch && git rebase origin/main` |
| 推自己的 dev 分支 | `git push --force-with-lease origin dev-<设备>` |
| 合并 dev 进 main | `git checkout main && git merge --ff-only origin/dev-<设备> && git push origin main` |
| 恢复被强推的 main | `git reset --hard <正确SHA> && git push --force-with-lease origin main` |
| 评估分叉 | `git log origin/main..origin/dev-<设备>` + `git diff --stat origin/main origin/dev-<设备>` |
| 试 rebase 查冲突 | `git checkout -b trial dev-<设备> && git rebase origin/main` |

## Guardrails

- 绝不 `git push --force origin main`，除"恢复流程"且 `--force-with-lease` + 诊断安全。
- 不臆造与他人重复的 `dev-<设备>` 名。
- 合并/恢复改 `main` 前先 `git fetch` 并核对 `origin/main`。
- 动他人 `dev` 分支的强推前，确认是本人在多设备操作或已获授权。
