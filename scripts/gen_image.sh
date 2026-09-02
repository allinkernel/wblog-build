#!/bin/bash
# gen_image.sh — 从 out/dist 生成 erofs 镜像（部署产物）
# staging 到 out/dist-erofs-pre（cp -rL 把 out/dist/template 软链解成真实内容；out/dist 本体保持软链，
#   便于改 wblog_new/template 后 8888 即时生效）；mkfs.erofs 固定时间戳（-T --all-time）。
# 压缩：实测 lz4hc/zstd/lzma 对当前 staging 结果都 ~11M（pagefind/template 已不可再压，抹平算法差异），
#   故默认 lz4hc（生成快 + 服务器读解压快）；如需调整设 EROFS_Z 覆盖（如 -zzstd,19 / -zlzma,9）。
# 注意：mkfs.erofs 对同一输入多次生成【字节 hash 不一致】（工具本身非确定），内容一致性由
#   verify_image.sh（make 一部分）保证——详见该脚本头注。
set -e
cd "$(dirname "$0")/../.."
STAGE="out/dist-erofs-pre"
IMG="out/wblog.erofs"
T_STAMP="1700000000"            # 固定时间戳（确定性相关，勿改）
EROFS_Z="${EROFS_Z:--zlz4hc,12}"

MKFS="$(command -v mkfs.erofs 2>/dev/null)"
[ -x "$MKFS" ] || { echo "缺 mkfs.erofs"; exit 1; }

rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -rL out/dist/. "$STAGE/"
find "$STAGE" -exec touch -h -d "@$T_STAMP" {} + 2>/dev/null || true

rm -f "$IMG"
"$MKFS" "$EROFS_Z" -C65536 -T"$T_STAMP" --all-time "$IMG" "$STAGE" >/dev/null
echo "gen_image: $IMG ($(du -h "$IMG" | cut -f1), $EROFS_Z) from $STAGE"
