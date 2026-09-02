#!/bin/bash
# verify_image.sh — 校验 erofs 镜像内容 = staging（= out/dist 实体化），作为 make 一部分（用户 2026-09-03）
# 背景：mkfs.erofs 同一输入多次生成的镜像【字节 hash 不一致】（工具本身非确定，已实测），故校验内容：
#   extract.erofs 解包镜像 → python 逐文件 sha256 对比 staging。沙箱/无 fuse 环境均可跑。
# extract.erofs 取自用户编译的 erofs 工具集（/home/mindul/source/erofs/usr/bin/），可部署到服务器。
set -e
cd "$(dirname "$0")/../.."
IMG="out/wblog.erofs"
STAGE="out/dist-erofs-pre"
[ -f "$IMG" ] || { echo "[verify_image] ✗ $IMG 不存在"; exit 1; }
[ -d "$STAGE" ] || { echo "[verify_image] ✗ $STAGE 不存在"; exit 1; }

X="$(command -v extract.erofs 2>/dev/null || true)"
[ -n "$X" ] || X="/home/mindul/source/erofs/usr/bin/extract.erofs"
if [ ! -x "$X" ]; then echo "[verify_image] ✗ 找不到 extract.erofs，无法做内容校验"; exit 1; fi

TMP="$(mktemp -d)"
"$X" -i "$IMG" -x -f -o "$TMP" -s >/dev/null 2>&1
rc=$?
if [ $rc -ne 0 ]; then echo "[verify_image] ✗ extract.erofs 解包失败($rc)"; rm -rf "$TMP"; exit 1; fi

python3 - "$STAGE" "$TMP" <<'PY'
import sys, os, hashlib, glob
stage, tmp = sys.argv[1], sys.argv[2]
# extract.erofs 默认解到 <镜像basename>/ 子目录，探测真正的镜像根（含 manifest.json 的层）
cands = [tmp] + [d for d in glob.glob(os.path.join(tmp, "*")) if os.path.isdir(d)]
base = next((c for c in cands if os.path.isfile(os.path.join(c, "manifest.json"))), None)
if base is None:
    print(f"[verify_image] ✗ 解包结果中找不到镜像根（含 manifest.json）: {tmp}")
    sys.exit(1)
def walk(d):
    m = {}
    for r, _, fs in os.walk(d):
        for f in fs:
            p = os.path.join(r, f)
            if os.path.islink(p):
                continue
            rel = os.path.relpath(p, d)
            try:
                m[rel] = hashlib.sha256(open(p, "rb").read()).hexdigest()
            except OSError:
                m[rel] = "?"
    return m
a, b = walk(stage), walk(base)
missing = [k for k in a if k not in b]
extra = [k for k in b if k not in a]
diff = [k for k in a if k in b and a[k] != b[k]]
if missing or extra or diff:
    print("[verify_image] ✗ 不一致")
    if missing: print("  镜像缺失:", missing[:10])
    if extra:   print("  镜像多余:", extra[:10])
    if diff:    print("  内容不同:", diff[:10])
    sys.exit(1)
print(f"[verify_image] ✓ erofs 镜像内容与 staging(=out/dist 实体化) 一致（{len(a)} 文件）")
PY
rc=$?
rm -rf "$TMP"
exit $rc
