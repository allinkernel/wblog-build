#! /usr/bin/python3

import json
import os
import sys
import xml.etree.ElementTree as ET


def ninja_escape(path):
    return path.replace(":", "$:").replace(" ", "$ ")


def generate_build_system(repo_root, out_dir):
    dist_dir = os.path.join(out_dir, "dist")
    ninja_rules = [
        "rule md_to_html\n  command = pandoc $in -o $out --self-contained\n",
        "rule typst_to_pdf\n  command = typst compile $in $out\n",
        "rule rst_to_html\n  command = pandoc $in -o $out\n",
    ]
    ninja_builds = []
    manifest = {}

    # ... 前面的 rules 定义保持不变 ...

    for root, dirs, files in os.walk(repo_root):
        if "wsw_blog.xml" in files:
            xml_path = os.path.join(root, "wsw_blog.xml")
            try:
                tree = ET.parse(xml_path)
                topic_el = tree.getroot()
            except Exception as e:
                print(f"Error parsing {xml_path}: {e}")
                continue

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
    with open(os.path.join(dist_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=4)


generate_build_system(sys.argv[1], sys.argv[2])
