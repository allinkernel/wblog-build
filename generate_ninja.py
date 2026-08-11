#! /usr/bin/python3

import json
import os
import sys

EXCLUDE_DIRS = {
    ".git",
    ".repo",
    "out",
    "build",
    "template",
    ".cache",
    "node_modules",
}


def ninja_escape(path):
    return path.replace(":", "$:").replace(" ", "$ ")


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
    for script_path in [self_script, build_sh_path]:
        if os.path.exists(script_path):
            current_mtime = get_file_mtime(script_path)
            new_timestamps[script_path] = current_mtime
            if script_path not in old_timestamps or current_mtime > old_timestamps[script_path]:
                need_update = True

    discovered = []
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        entry = None
        doc_type = "md"
        if "index.md" in files:
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
        "rule typst_to_pdf\n  command = typst compile $in $out\n",
        "rule rst_to_html\n  command = pandoc $in -o $out\n",
    ]
    ninja_builds = []
    generated_targets = set()

    # 构建路径信息字典
    path_info = {}
    for abs_src, parts, doc_type in discovered:
        path_info[tuple(parts)] = {"abs_src": abs_src, "doc_type": doc_type, "parts": parts}

    # 辅助：查找最近的包含 index.md 的祖先路径（不包括自身）
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

    # 构建 manifest
    manifest = {}
    for parts in top_paths:
        top_name = parts[-1]
        node = node_map[parts]
        manifest[top_name] = {
            "file": node["file"],
            "type": node["type"],
            "nodes": node["children"]  # 将直接子节点放入 nodes
        }

    # 生成 ninja 构建规则
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
        rule = "md_to_html" if info["doc_type"] == "md" else ("typst_to_pdf" if info["doc_type"] == "typst" else "rst_to_html")
        ninja_builds.append(
            f"build {esc_out}: {rule} {esc_src}\n"
            f"  resource_path = {esc_resource_path}"
        )

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
