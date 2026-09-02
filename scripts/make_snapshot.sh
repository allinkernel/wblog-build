#!/bin/bash
# make_snapshot.sh — 生成 .repo/manifests/snapshot/<时间戳>.xml（repo manifest -r 锁各仓库 SHA）。
# 依赖 check_pushed（可恢复性红线：HEAD 须已在远端，否则未来 repo sync 拉不到）。
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

bash build/scripts/check_pushed.sh
mkdir -p .repo/manifests/snapshot
STAMP="$(date +%Y%m%d-%H%M%S)"
repo manifest -r -o ".repo/manifests/snapshot/$STAMP.xml"
echo "make snapshot: .repo/manifests/snapshot/$STAMP.xml"
echo "  回退: repo sync -m snapshot/$STAMP.xml"
echo "  （agent 不做 .repo/manifests 的 git 操作——请用户自行 add/commit/push）"
