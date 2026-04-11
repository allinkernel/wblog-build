#! /usr/bin/python3

import json
import os
import sys
import xml.etree.ElementTree as ET


def ninja_escape(path):
    # ninja的目标命中不能包含空格和:，所以需要用$转义
    return path.replace(":", "$:").replace(" ", "$ ")


def get_file_mtime(path):
    return os.path.getmtime(path)


def generate_build_system(repo_root, out_dir):
    dist_dir = os.path.join(out_dir, "dist")
    cache_dir = os.path.join(out_dir, ".cache")
    os.makedirs(cache_dir, exist_ok=True)

    timestamp_file = os.path.join(cache_dir, "wsw_blogs_timestamps.json")
    # 加载旧的时间戳
    old_timestamps = {}
    if os.path.exists(timestamp_file):
        with open(timestamp_file, "r") as f:
            old_timestamps = json.load(f)

    all_xml_files = []
    need_update = False
    new_timestamps = {}

    for root, _, files in os.walk(repo_root):
        if "wsw_blog.xml" in files:
            xml_path = os.path.abspath(os.path.join(root, "wsw_blog.xml"))
            print("find ", xml_path)
            current_mtime = get_file_mtime(xml_path)
            new_timestamps[xml_path] = current_mtime
            all_xml_files.append((xml_path, root))

            if (
                xml_path not in old_timestamps
                or current_mtime > old_timestamps[xml_path]
            ):
                need_update = True

    if (
        not need_update
        and os.path.exists(os.path.join(out_dir, "build.ninja"))
        and os.path.exists(os.path.join(dist_dir, "manifest.json"))
    ):
        print("No changes detected in all wsw_blog.xml file, skipping generating ninja")
        return

    print("Changes detected. Regenerating build.ninja...")

    ninja_rules = [
        "rule md_to_html\n  command = pandoc $in -o $out --self-contained\n",
        "rule typst_to_pdf\n  command = typst compile $in $out\n",
        "rule rst_to_html\n  command = pandoc $in -o $out\n",
    ]
    ninja_builds = []
    manifest = {}

    # 使用set实现目标去重
    generated_targets = set()

    for xml_path, root in all_xml_files:
        topic_el = ET.parse(xml_path).getroot()
        topic_name = topic_el.get("name", "Unknown_Topic")

        if topic_name not in manifest:
            manifest[topic_name] = {"nodes": {}}

        for blog in topic_el.findall("blog"):
            # 1. 使用 get 并提供默认值，消除 None 报错
            struct_path = blog.get("target", "")
            src_rel = blog.get("file", "")
            doc_type = blog.get("type", "md")

            # 如果关键属性缺失，跳过
            if not struct_path or not src_rel:
                continue

            # 2. 路径计算 (显式转为绝对路径)
            abs_src = os.path.abspath(os.path.join(root, src_rel))
            esc_src = ninja_escape(abs_src)
            ext = ".html" if doc_type != "typst" else ".pdf"

            # 这里的 out_rel_path 是前端 manifest 用的相对路径
            out_rel_path = f"articles/{topic_name}/{struct_path}{ext}"
            # 这里的 abs_out 是 Ninja 编译用的物理路径
            abs_out = os.path.abspath(os.path.join(dist_dir, out_rel_path))
            if abs_out in generated_targets:
                print(f"Warning: Duplicate target skipped: {out_rel_path}")
                continue
            generated_targets.add(abs_out)
            esc_out = ninja_escape(abs_out)

            os.makedirs(os.path.dirname(abs_out), exist_ok=True)

            # 3. Ninja 指令
            rule = (
                "md_to_html"
                if doc_type == "md"
                else ("typst_to_pdf" if doc_type == "typst" else "rst_to_html")
            )
            ninja_builds.append(f"build {esc_out}: {rule} {esc_src}")

            # 4. 递归构建 Manifest (已经确保 struct_path 不为 None)
            current = manifest[topic_name]["nodes"]
            parts = struct_path.split("/")
            for i, part in enumerate(parts):
                if part not in current:
                    current[part] = {"children": {}, "file": None, "type": None}
                if i == len(parts) - 1:  # 叶子节点
                    current[part]["file"] = out_rel_path
                    current[part]["type"] = doc_type
                current = current[part]["children"]

    # 写入 build.ninja 和 manifest.json
    with open(os.path.join(out_dir, "build.ninja"), "w") as f:
        f.write("\n".join(ninja_rules + ninja_builds))
        f.write("\n")

    with open(os.path.join(dist_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=4)

    # 保存新的时间戳
    with open(timestamp_file, "w") as f:
        json.dump(new_timestamps, f)


if __name__ == "__main__":
    repo = sys.argv[1] if len(sys.argv) > 1 else "./.repo"
    out = sys.argv[2] if len(sys.argv) > 2 else "./out"
    generate_build_system(repo, out)
