#!/bin/sh
set -e

# succeed if $1 doesn't IFS-split funny (globs, spaces, ...)
good_split() {
  set -- "$1" $1
  test $# = 2 && test "$1" = "$2"
}

case "$0" in
  */*) source_path="${0%/*}" ;;
  *)   source_path="." ;;
esac
good_split "${source_path}" || { echo "Error: '${source_path}' has space" >&2; exit 1;}
[ -d "${source_path}/.repo" ] || { echo "Error: '${source_path}/.repo' not found." >&2; exit 1; }
[ -f "${source_path}/build/generate_ninja.py" ] || { echo "Error: '${source_path}/build/generate_ninja.py' not found." >&2; exit 1; }
[ -f "${source_path}/template/template.html" ] || { echo "Error: '${source_path}/template/template.html' not found." >&2; exit 1; }

# -- 避免脚本名最开始带-导致cd误以为这是参数
cd -- "${source_path}"
mkdir -p ./out/dist

# 生成out/build.ninja
./build/generate_ninja.py . ./out/
# 在out/dist中生成articles目录
command ninja -f out/build.ninja

# TODO: 这部分后续加到ninja中
rm -rf ./out/dist/template
ln -snf "../../template" ./out/dist/template
