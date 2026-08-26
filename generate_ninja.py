#! /usr/bin/python3

import json
import os
import re
import shutil
import sys

EXCLUDE_DIRS = {
    ".git",
    ".repo",
    "out",
    "build",
    "template",
    ".cache",
    "node_modules",
    # AI 工具/代理的工作目录（Codewhale、Gemini CLI 等），不应参与文章扫描。
    ".codewhale",
    ".codewhale-worktrees",
    ".gemini",
    ".claude",
    ".codex",
    ".cursor",
    ".aider",
}


def is_excluded_dir(name):
    # 兜底规则：任何以 "." 开头的隐藏目录一律不扫描。
    # 博客主题目录名会成为 URL 路径（articles/<top_name>/...），不可能以 "." 开头，
    # 因此该规则可自动覆盖未来新增的 AI 工具目录，无需每次改动名单。
    return name.startswith(".") or name in EXCLUDE_DIRS


def ninja_escape(path):
    return path.replace(":", "$:").replace(" ", "$ ")


# 宿主工具（AOSP 风格：构建工具安装到 out/host/，ninja rule 通过它执行）
HOST_TOOL_REL = os.path.join("host", "html_2_html.py")


def doc_type_rule(doc_type):
    # index.html 直接由 html_2_html.py 裁剪；其余走 pandoc/typst
    return {
        "md": "md_to_html",
        "html": "html_to_html",
        "typst": "typst_to_pdf",
    }.get(doc_type, "rst_to_html")


def node_sort_key(name):
    """文章目录名排序键（manifest 各层统一按此排序）。

    规则：目录名开头的点分数字序号（如 2.10、2.10.3）先按自然序比较
    （2.9 < 2.10），剩余部分再按字母序（ai-guide < translation）；
    无序号目录排在带序号之后，整体按字母序。
    """
    m = re.match(r"^(\d+(?:\.\d+)*)", name)
    if m:
        nums = tuple(int(x) for x in m.group(1).split("."))
        rest = re.sub(r"^[^a-z0-9]+", "", name[m.end():].lower())
        return (0, nums, rest)
    return (1, (), name.lower())


def get_file_mtime(path):
    return os.path.getmtime(path)


def generate_build_system(repo_root, out_dir):
    dist_dir = os.path.join(out_dir, "dist")
    cache_dir = os.path.join(out_dir, ".cache")
    os.makedirs(cache_dir, exist_ok=True)

    timestamp_file = os.path.join(cache_dir, "wsw_blogs_timestamps.json")
    old_timestamps = {}
    if os.path.exists(timestamp_file):
        try:
            with open(timestamp_file, "r") as f:
                old_timestamps = json.load(f)
        except Exception:
            old_timestamps = {}

    need_update = False
    new_timestamps = {}

    self_script = os.path.realpath(__file__)
    build_sh_path = os.path.realpath(os.path.join(repo_root, "build.sh"))
    src_tool = os.path.realpath(os.path.join(repo_root, "build", "scripts", "html_2_html.py"))
    host_tool = os.path.join(out_dir, HOST_TOOL_REL)
    # Pagefind 全文搜索：静态二进制以 xz 压缩入库（节省 git 体积），安装时解压；索引脚本同策略装到 out/host/
    src_pagefind_xz = os.path.realpath(os.path.join(repo_root, "build", "scripts", "pagefind.xz"))
    src_pagefind_idx = os.path.realpath(os.path.join(repo_root, "build", "scripts", "pagefind_index.py"))
    host_pagefind = os.path.join(out_dir, "host", "pagefind")
    host_pagefind_idx = os.path.join(out_dir, "host", "pagefind_index.py")
    # 安装宿主工具：html_2_html.py → out/host/（copy2 保留 mtime，避免无谓全量重建）
    os.makedirs(os.path.dirname(host_tool), exist_ok=True)
    shutil.copy2(src_tool, host_tool)
    if os.path.exists(src_pagefind_xz):
        # 解压 pagefind.xz → out/host/pagefind；产物 mtime 对齐源 xz，ninja 增量判断稳定
        if not (os.path.exists(host_pagefind)
                and os.path.getmtime(host_pagefind) >= os.path.getmtime(src_pagefind_xz)):
            import lzma
            print("Installing pagefind from pagefind.xz ...")
            xz_mtime = os.path.getmtime(src_pagefind_xz)
            with lzma.open(src_pagefind_xz, "rb") as fin, open(host_pagefind, "wb") as fout:
                shutil.copyfileobj(fin, fout)
            os.chmod(host_pagefind, 0o755)
            os.utime(host_pagefind, (xz_mtime, xz_mtime))
    if os.path.exists(src_pagefind_idx):
        shutil.copy2(src_pagefind_idx, host_pagefind_idx)

    for script_path in [self_script, build_sh_path, src_tool, src_pagefind_idx, src_pagefind_xz]:
        if os.path.exists(script_path):
            current_mtime = get_file_mtime(script_path)
            new_timestamps[script_path] = current_mtime
            if script_path not in old_timestamps or current_mtime > old_timestamps[script_path]:
                need_update = True

    discovered = []
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if not is_excluded_dir(d)]
        entry = None
        doc_type = None
        # index.html 优先：html 直接编译比 md 剥离快，同目录下存在 index.html 时忽略 index.md
        if "index.html" in files:
            entry = "index.html"
            doc_type = "html"
        elif "index.md" in files:
            entry = "index.md"
            doc_type = "md"
        elif "index.typ" in files:
            entry = "index.typ"
            doc_type = "typst"
        if entry:
            abs_src = os.path.abspath(os.path.join(root, entry))
            current_mtime = get_file_mtime(abs_src)
            new_timestamps[abs_src] = current_mtime
            if abs_src not in old_timestamps or current_mtime > old_timestamps[abs_src]:
                need_update = True
            rel_dir = os.path.relpath(root, repo_root)
            if rel_dir == ".":
                continue
            parts = rel_dir.split(os.sep)
            discovered.append((abs_src, parts, doc_type))

    if len(new_timestamps) != len(old_timestamps):
        need_update = True

    if (
        not need_update
        and os.path.exists(os.path.join(out_dir, "build.ninja"))
        and os.path.exists(os.path.join(dist_dir, "manifest.json"))
    ):
        print("No changes detected, skipping generation.")
        return

    print("Changes detected. Regenerating build.ninja and manifest.json...")

    ninja_rules = [
        "rule md_to_html\n  command = pandoc $in -o $out --embed-resources --resource-path=$resource_path\n",
        "rule html_to_html\n  command = python3 %s $in $out\n" % ninja_escape(host_tool),
        "rule typst_to_pdf\n  command = typst compile $in $out\n",
        "rule rst_to_html\n  command = pandoc $in -o $out\n",
        "rule pagefind_index\n  command = python3 %s --pagefind %s --site %s --output %s\n" % (
            ninja_escape(os.path.abspath(host_pagefind_idx)),
            ninja_escape(os.path.abspath(host_pagefind)),
            ninja_escape(os.path.abspath(dist_dir)),
            ninja_escape(os.path.abspath(os.path.join(dist_dir, "pagefind"))),
        ),
    ]
    ninja_builds = []
    generated_targets = set()

    # 构建路径信息字典
    path_info = {}
    for abs_src, parts, doc_type in discovered:
        path_info[tuple(parts)] = {"abs_src": abs_src, "doc_type": doc_type, "parts": parts}

    # 辅助：查找最近的包含 index.* 文章的祖先路径（不包括自身）
    def find_parent(parts):
        for i in range(len(parts)-1, 0, -1):
            candidate = parts[:i]
            if candidate in path_info:
                return candidate
        return None

    # 获取顶级主题（没有父主题的路径）
    top_paths = []
    for parts in path_info.keys():
        if find_parent(parts) is None:
            top_paths.append(parts)

    # 创建节点对象
    node_map = {}
    for parts in path_info.keys():
        info = path_info[parts]
        node = {"file": None, "type": info["doc_type"], "children": {}}
        node_map[parts] = node

    # 计算输出路径
    def get_top(parts):
        parent = find_parent(parts)
        if parent is None:
            return parts
        else:
            return get_top(parent)

    for parts, info in path_info.items():
        top_parts = get_top(parts)
        top_name = top_parts[-1]
        sub_parts = parts[len(top_parts):]
        ext = ".html" if info["doc_type"] != "typst" else ".pdf"
        if sub_parts:
            sub_path = "/".join(sub_parts)
            out_rel_path = f"articles/{top_name}/{sub_path}/index{ext}"
        else:
            out_rel_path = f"articles/{top_name}/index{ext}"
        node_map[parts]["file"] = out_rel_path
        # 存储输出路径便于构建 ninja
        info["out_rel_path"] = out_rel_path
        info["abs_out"] = os.path.abspath(os.path.join(dist_dir, out_rel_path))

    # 建立父子关系：将子节点添加到父节点的 children 中
    for parts in path_info.keys():
        parent_parts = find_parent(parts)
        if parent_parts is not None:
            parent_node = node_map[parent_parts]
            child_name = parts[-1]
            parent_node["children"][child_name] = node_map[parts]

    # 各层子节点统一排序：带序号目录先按序号自然序、再按字母序；无序号目录排后按字母序
    for node in node_map.values():
        node["children"] = dict(sorted(node["children"].items(), key=lambda kv: node_sort_key(kv[0])))

    # 构建 manifest（顶层主题同样按排序规则）
    manifest = {}
    for parts in sorted(top_paths, key=lambda p: node_sort_key(p[-1])):
        top_name = parts[-1]
        node = node_map[parts]
        manifest[top_name] = {
            "file": node["file"],
            "type": node["type"],
            "nodes": node["children"]  # 将直接子节点放入 nodes
        }

    # 生成 ninja 构建规则
    esc_host_tool = ninja_escape(os.path.abspath(host_tool))
    for parts, info in path_info.items():
        abs_out = info["abs_out"]
        if abs_out in generated_targets:
            print(f"Warning: Duplicate target {info['out_rel_path']} skipped.")
            continue
        generated_targets.add(abs_out)
        esc_src = ninja_escape(info["abs_src"])
        esc_out = ninja_escape(abs_out)
        src_dir = os.path.dirname(info["abs_src"])
        esc_resource_path = ninja_escape(src_dir)
        os.makedirs(os.path.dirname(abs_out), exist_ok=True)
        rule = doc_type_rule(info["doc_type"])
        if info["doc_type"] == "html":
            # html->html：图片在 html_2_html.py 内内联，无需 resource_path；
            # 把宿主工具作为隐式依赖（| 后），工具更新时 ninja 自动重建全部 html 产物
            ninja_builds.append(
                f"build {esc_out}: html_to_html {esc_src} | {esc_host_tool}\n"
            )
        else:
            ninja_builds.append(
                f"build {esc_out}: {rule} {esc_src}\n"
                f"  resource_path = {esc_resource_path}"
            )

    # Pagefind 全文索引聚合目标：隐式依赖所有 html/md/rst 产物 + pagefind 工具，
    # 任一文章或工具变化都触发重建（pagefind_index rule 内部全量重建，ninja 负责判断时机）
    if os.path.exists(host_pagefind) and os.path.exists(host_pagefind_idx):
        html_outputs = sorted(
            ninja_escape(info["abs_out"])
            for info in path_info.values()
            if info["doc_type"] in ("md", "html", "rst")
        )
        if html_outputs:
            pf_js = ninja_escape(os.path.abspath(os.path.join(dist_dir, "pagefind", "pagefind.js")))
            deps = " ".join(html_outputs + [
                ninja_escape(os.path.abspath(host_pagefind)),
                ninja_escape(os.path.abspath(host_pagefind_idx)),
            ])
            ninja_builds.append(f"build {pf_js}: pagefind_index | {deps}\n")

    with open(os.path.join(out_dir, "build.ninja"), "w") as f:
        f.write("\n".join(ninja_rules + ninja_builds))
        f.write("\n")

    with open(os.path.join(dist_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=4, ensure_ascii=False)

    with open(timestamp_file, "w") as f:
        json.dump(new_timestamps, f)


if __name__ == "__main__":
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    out = sys.argv[2] if len(sys.argv) > 2 else "./out"
    generate_build_system(repo, out)
