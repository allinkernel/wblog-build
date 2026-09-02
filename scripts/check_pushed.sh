#!/bin/bash
# check_pushed.sh — 可恢复性红线 gate：所有 manifest 项目的本地 HEAD 必须在远端分支历史中。
# 任一未上库 → exit 非 0（阻止 make push / make snapshot）。用户定 2026-09-02。
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"      # wblog_new 根
cd "$ROOT"

python3 - "$ROOT" <<'PY' || exit 1
import os, sys, xml.etree.ElementTree as ET
root = sys.argv[1]
mf = os.path.join(root, ".repo", "manifests", "default.xml")
tree = ET.parse(mf)
unpushed = []
missing_origin = []
for p in tree.getroot().iter("project"):
    path = p.get("path"); rev = p.get("revision")
    if not path or not os.path.isdir(os.path.join(root, path, ".git")):
        continue
    branch = rev.replace("refs/heads/", "") if rev and "/" not in rev else (rev or "main")
    if not branch or branch.startswith("refs/"):
        branch = "main"
    # origin/<branch> 是否存在
    if os.system(f"git -C {os.path.join(root,path)} show-ref --verify --quiet refs/remotes/origin/{branch}") != 0:
        missing_origin.append(f"{path} (无远端 origin/{branch})"); continue
    if os.system(f"git -C {os.path.join(root,path)} merge-base --is-ancestor HEAD origin/{branch}") != 0:
        unpushed.append(path)
if unpushed or missing_origin:
    print("⚠ 可恢复性红线检查失败 —— 以下仓库有未上库提交或缺失远端分支：")
    for x in unpushed:        print("  未上库: ", x)
    for x in missing_origin:  print("  缺失:   ", x)
    print("先 push 这些仓库再执行 make push / make snapshot。")
    sys.exit(1)
print("check_pushed ✓ 所有仓库 HEAD 已在远端分支历史中")
PY
