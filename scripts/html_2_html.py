#! /usr/bin/python3
"""html_2_html.py — 任意 HTML 输入 → 适配 template/template.html 的规范文章片段。

用法: html_2_html.py <in.html> <out.html>

本工具是 html->html 构建规则（与 md->html 同等级）的规范化引擎：
无论输入是「完整 HTML 文档」（POSIX 官方下载、typora 导出、tinymce 等所见即所得
编辑器产物）还是「纯 body 片段」（pandoc 或 AI agent 生成），输出一律为符合
template/spec.md 的规范文章片段（<body> 内部内容）。

处理规则:
1. 剥壳: 兼容两种输入形态
   - 完整文档: 丢弃 <!DOCTYPE>/<html>/<head> 全部内容/<body> 标签本身，只留 body 内容；
   - 纯片段: 无壳标签时，整个文档视为 body 内容直接收集。
2. 丢弃 <script>/<style>/<link>/<base>/<basefont>/<meta>（正文内嵌脚本/样式会污染模板）。
3. 移除文档级导航壳: 所有 <div class="NAVHEADER">…</div>。
4. 头部壳裁剪: 第一个 <h1>~<h6> 之前的内容（导航/页眉/装饰锚点）全部丢弃。
5. 表现标签归一: <tt> → <code>（术语获得模板行内代码样式）；
   <center>/<font> 剥离标签、保留内容。
6. 内联样式清洗（spec: 颜色/字体一律交给模板主题）: 移除非 <table>/<td>/<th>
   元素上的 style 属性（tinymce 等编辑器高频产出 <span style="…">），
   表格列宽等必要场景保留。
7. 安全清理: <a href="javascript:…"> 去掉 href（防止正文内执行脚本报错）。
8. 图片内联: <img src="相对路径"> → base64 data URI（与 md->html 的
   --embed-resources 产物一致，out/dist 自包含）；文件缺失时保留原 src 并警告。
9. 输出纯 HTML 片段，供模板 #article-container 直接 innerHTML 渲染。
"""

import base64
import mimetypes
import os
import sys
from html.parser import HTMLParser

# 含内容、整段丢弃的容器标签
SKIP_CONTAINER_TAGS = {"script", "style", "title"}
# 空元素（无闭合标签），标签本身丢弃即可
VOID_DROP_TAGS = {"link", "base", "basefont", "meta"}
# 只剥离标签本身、保留内容
STRIP_TAGS = {"center", "font"}
# 标签语义映射（内容保留，标签替换为模板认识的语义标签）
RENAME_TAGS = {"tt": "code"}
# 文档外壳标签：标签本身丢弃，head 内容整段跳过
SHELL_TAGS = {"html", "head", "body"}
# 内联样式保留白名单（spec: 仅允许表格列宽等必要场景）
STYLE_KEEP_TAGS = {"table", "td", "th"}

HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")


class ArticleHTMLParser(HTMLParser):
    def __init__(self, src_file):
        super().__init__(convert_charrefs=False)  # 保留实体原样，防止 innerHTML 解析错位
        self.src_dir = os.path.dirname(os.path.abspath(src_file))
        self.out = []
        self.first_tag_seen = False   # 是否已见首个标签（文档前缀注释/声明不收集）
        self.seen_shell = False       # 是否出现过 html/head/body 壳（区分完整文档与片段）
        self.collecting = False       # 是否处于收集状态（body 内，或片段模式的整个文档）
        self.in_head = False          # head 内一切丢弃
        self.heading_seen = False     # 是否已遇到首个标题（此前为头部壳，丢弃）
        self.skip_depth = 0           # SKIP_CONTAINER_TAGS 嵌套深度
        self.nav_div_depth = 0        # NAVHEADER 容器内 div 嵌套深度

    # ---------- 输出 ----------
    def _emit(self, s):
        if (self.first_tag_seen and self.collecting and not self.in_head
                and not self.skip_depth and not self.nav_div_depth and self.heading_seen):
            self.out.append(s)

    def _begin_collect(self):
        # 片段模式：未见壳标签时，第一个实际内容标签到来 → 整个文档视为 body 内容
        if not self.seen_shell:
            self.collecting = True

    @staticmethod
    def _serialize(tag, attrs, self_closing=False):
        parts = [tag]
        for k, v in attrs:
            if v is None:
                parts.append(k)
            else:
                # attr 值来自 convert_charrefs=False 的原始文本，原样写回即正确
                parts.append(f'{k}="{v}"')
        s = "<" + " ".join(parts)
        return s + " />" if self_closing else s + ">"

    @staticmethod
    def _clean_attrs(tag, attrs):
        # spec: 内联样式仅允许表格列宽等必要场景；其余一律移除（颜色/字体交给模板主题）
        if tag in STYLE_KEEP_TAGS:
            return attrs
        return [(k, v) for k, v in attrs if k != "style"]

    # ---------- HTMLParser 回调 ----------
    def handle_starttag(self, tag, attrs):
        self.first_tag_seen = True
        if tag in SHELL_TAGS:
            self.seen_shell = True
            if tag == "head":
                self.in_head = True
            elif tag == "body":
                self.collecting = True
            return
        if self.in_head:
            return  # head 内一切丢弃（title/style/link/meta/script…）
        if tag in SKIP_CONTAINER_TAGS:
            self.skip_depth += 1
            return
        if tag in VOID_DROP_TAGS:
            return  # 空元素，直接丢弃
        self._begin_collect()
        if tag == "div":
            if self.nav_div_depth > 0:
                self.nav_div_depth += 1
                return
            if any(k == "class" and "NAVHEADER" in v for k, v in attrs):
                self.nav_div_depth = 1
                return
            # 普通 div
            self._emit(self._serialize(tag, self._clean_attrs(tag, attrs)))
            return
        if tag in HEADING_TAGS:
            self.heading_seen = True
            self._emit(self._serialize(tag, self._clean_attrs(tag, attrs)))
            return
        if tag == "a" and any(k == "href" and str(v).startswith("javascript:") for k, v in attrs):
            # javascript: 链接在模板内会执行脚本报错，去掉 href 保留文本
            self._emit(self._serialize(tag, [(k, v) for k, v in attrs if k != "href"]))
            return
        if tag == "img":
            new_attrs = []
            for k, v in attrs:
                if k == "src" and v and not v.startswith(
                        ("data:", "http://", "https://", "//", "#", "mailto:")):
                    p = os.path.normpath(os.path.join(self.src_dir, v))
                    if os.path.isfile(p):
                        mime = mimetypes.guess_type(p)[0] or "application/octet-stream"
                        with open(p, "rb") as f:
                            v = "data:%s;base64,%s" % (mime, base64.b64encode(f.read()).decode("ascii"))
                    else:
                        print("Warning: html_2_html: 图片文件缺失，保留原 src: %s (%s)" % (v, os.path.relpath(p, self.src_dir)), file=sys.stderr)
                new_attrs.append((k, v))
            self._emit(self._serialize(tag, new_attrs))
            return
        if tag in STRIP_TAGS:
            return  # 剥离标签，保留内容
        tag = RENAME_TAGS.get(tag, tag)
        self._emit(self._serialize(tag, self._clean_attrs(tag, attrs)))

    def handle_startendtag(self, tag, attrs):
        # <img … /> 等自闭合写法
        self.first_tag_seen = True
        if tag == "img":
            self.handle_starttag(tag, attrs)
            return
        if tag in SHELL_TAGS or self.in_head:
            return
        if tag in SKIP_CONTAINER_TAGS or tag in VOID_DROP_TAGS:
            return
        self._begin_collect()
        if self.nav_div_depth or self.skip_depth or not self.heading_seen:
            return
        tag = RENAME_TAGS.get(tag, tag)
        if tag in STRIP_TAGS:
            return
        self._emit(self._serialize(tag, self._clean_attrs(tag, attrs), self_closing=True))

    def handle_endtag(self, tag):
        if tag == "head":
            self.in_head = False
            return
        if tag == "body":
            self.collecting = False
            return
        if tag == "html":
            return
        if tag in SKIP_CONTAINER_TAGS:
            if self.skip_depth > 0:
                self.skip_depth -= 1
            return
        if tag == "div" and self.nav_div_depth > 0:
            self.nav_div_depth -= 1
            return
        if tag in VOID_DROP_TAGS:
            return  # 理论上不会出现（void 元素无 endtag），防御性处理
        if tag in STRIP_TAGS:
            return
        self._emit("</%s>" % RENAME_TAGS.get(tag, tag))

    def handle_data(self, data):
        self._emit(data)

    def handle_entityref(self, name):
        # convert_charrefs=False 时实体单独回调，必须原样保留（否则 &lt; 等会丢失）
        self._emit("&%s;" % name)

    def handle_charref(self, name):
        # 数字字符引用（&#39; 等）
        self._emit("&#%s;" % name)

    def handle_comment(self, data):
        self._emit("<!--%s-->" % data)

    def handle_decl(self, decl):
        pass  # <!DOCTYPE> 等声明丢弃


def convert(in_file, out_file):
    with open(in_file, "r", encoding="utf-8", errors="replace") as f:
        html = f.read()
    p = ArticleHTMLParser(in_file)
    try:
        p.feed(html)
        p.close()
    except Exception as e:
        print("Warning: html_2_html: parse issue in %s: %s" % (in_file, e), file=sys.stderr)
    content = "".join(p.out).strip()
    if not content:
        print("Warning: html_2_html: 输出为空（输入 %s）" % in_file, file=sys.stderr)
    out_dir = os.path.dirname(os.path.abspath(out_file))
    os.makedirs(out_dir, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: html_2_html.py <in.html> <out.html>", file=sys.stderr)
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
