#! /usr/bin/python3
"""pagefind_index.py — 为 out/dist 站点生成 Pagefind 全文搜索索引。

用法: pagefind_index.py --pagefind <pagefind二进制> --site <out/dist> --output <out/dist/pagefind>

流程（为什么需要包壳，见 template/spec.md 第 10 节）:
1. 扫描 --site/articles/ 下所有 index.html（html_2_html 产物，纯 body 片段）；
2. 每个片段包成完整 HTML（<html><head><title>…</head><body>…），保持 articles/ 相对路径，
   写入临时镜像目录 —— Pagefind 只索引完整 HTML 文档，且索引路径 = 站点 URL 路径；
3. 调用 pagefind（静态二进制，AOSP 风格安装于 out/host/）对镜像生成索引；
4. 把输出（pagefind.js、fragment/、index/ 等）整体拷入 --output 目录。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

HEADING_RE = re.compile(r"<h([1-6])[^>]*>(.*?)</h\1>", re.S)
TAG_RE = re.compile(r"<[^>]+>")


def extract_title(html):
    """从片段首标题提取文档标题（与 html_2_html 的规范一致：body 首个元素是标题）。"""
    m = HEADING_RE.search(html)
    if m:
        title = re.sub(r"\s+", " ", TAG_RE.sub("", m.group(2))).strip()
        if title:
            return title
    return "未命名文章"


def wrap_document(html):
    title = extract_title(html)
    return (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n"
        "<meta charset=\"UTF-8\">\n<title>%s</title>\n</head>\n<body>\n%s\n</body>\n</html>\n"
        % (title, html)
    )


def build_mirror(articles, mirror):
    """把 articles 下所有 index.html 包壳写入镜像（保持相对路径）。返回 html 文件数。"""
    count = 0
    for root, dirs, files in os.walk(articles):
        for name in files:
            if name != "index.html":
                continue
            src = os.path.join(root, name)
            rel = os.path.relpath(src, os.path.dirname(articles))  # articles/...
            dst = os.path.join(mirror, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(src, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            with open(dst, "w", encoding="utf-8") as f:
                f.write(wrap_document(content))
            count += 1
    return count


def main():
    ap = argparse.ArgumentParser(description="Pagefind 全文搜索索引生成器")
    ap.add_argument("--pagefind", required=True, help="pagefind 静态二进制路径")
    ap.add_argument("--site", required=True, help="站点根目录（out/dist）")
    ap.add_argument("--output", required=True, help="索引输出目录（out/dist/pagefind）")
    args = ap.parse_args()

    site = os.path.abspath(args.site)
    articles = os.path.join(site, "articles")
    if not os.path.isdir(articles):
        print("pagefind_index: 无 %s 目录，跳过索引" % articles, file=sys.stderr)
        return 0

    tmp = tempfile.mkdtemp(prefix="pagefind-mirror-")
    try:
        mirror = os.path.join(tmp, "site")
        n = build_mirror(articles, mirror)
        if n == 0:
            print("pagefind_index: articles 下无 index.html，跳过", file=sys.stderr)
            return 0
        print("pagefind_index: 包壳 %d 篇文章，开始索引..." % n)

        pf_out = os.path.join(tmp, "pfout")
        cmd = [args.pagefind, "--source", mirror, "--output-path", pf_out]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        if proc.returncode != 0:
            print("pagefind_index: pagefind 索引失败", file=sys.stderr)
            return proc.returncode

        # 整体拷入输出目录（先清空旧产物，避免分片 hash 改名后残留）
        output = os.path.abspath(args.output)
        if os.path.isdir(output):
            shutil.rmtree(output)
        os.makedirs(output, exist_ok=True)
        for name in os.listdir(pf_out):
            s = os.path.join(pf_out, name)
            d = os.path.join(output, name)
            if os.path.isdir(s):
                shutil.copytree(s, d)
            else:
                shutil.copy2(s, d)
        print("pagefind_index: 索引已写入 %s" % output)
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
