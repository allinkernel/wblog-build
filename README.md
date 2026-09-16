# wblog-build —— 构建系统仓

把各内容仓里的文章源编译成静态站点、生成搜索数据库、打成只读镜像。
**入口只有一个：在工作区根执行 `make`**（本仓的 `Makefile` 通过软链暴露成根的 `Makefile`）。

> 项目全貌、怎么构建、怎么部署 → 看人类文档仓 **[wblog-base](../wblog-base/README.md)**。
> 本文件只说明这个仓里有什么、改哪里。

## 目录

```
build/
├── Makefile            构建入口（根 Makefile 是它的软链）：make / snapshot / check_pushed；install/push 仍是空壳
├── generate_ninja.py   扫描文章源 → out/build.ninja + out/dist/manifest.json + out/private.json
├── build.sh            历史脚本（Makefile 已内联其命令，根目录不再有它的软链）
├── scripts/
│   ├── html_2_html.py  html→html 规范化引擎（剥壳/清洗/内联图片）
│   ├── db_gen.py       out/dist → out/sql/*.sql + out/index.db（pages / pages_fts / meta / private_*）
│   ├── gen_image.sh    staging（解软链 + 剔除 agent 资产 + 收 index.db）→ mkfs.erofs → out/wblog.erofs
│   ├── verify_image.sh 镜像内容一致性校验（解包逐文件 sha256 对比 staging）
│   ├── check_pushed.sh 可恢复性红线门禁（push/snapshot 前必过）
│   ├── make_snapshot.sh repo manifest -r 快照
│   ├── search_server.py 本地 /api/search 的 Python 替代实现（与 OpenResty 同一契约）
│   └── pagefind_index.py + pagefind.xz   Pagefind（**已退役**，前端不再引用，待从构建移除）
└── deepseek.md         历史背景文档（内容已并入 harness 规范，不要当规范读）
```

## 一条命令做了什么

```bash
cd ~/self/wblog && make
```

```
generate_ninja.py → out/build.ninja + out/dist/manifest.json + out/private.json
ninja             → out/dist/articles/**（加密文章 → out/private-articles/**）
建模板软链         → out/dist/template -> ../../template
db_gen.py         → out/sql/{schema,data}.sql + out/index.db
gen_image.sh      → out/wblog.erofs（含 index.db，约 20MB，一个文件 = 整个站点）
verify_image.sh   → 逐文件校验镜像内容与 out/dist 一致
```

成功标志：最后一行打印 `[verify_image] ✓ erofs 镜像内容与 staging(=out/dist 实体化) 一致（N 文件）`。

## 改这个仓之前

构建脚本是**全站产物一致性的地基**，顺手改一行就可能让所有文章产物变样。动手前请读：

- 人类侧：[wblog-base/guide.md 第 3 节](../wblog-base/guide.md#3-构建)（构建与产物）
- Agent 侧：`../harness/skills/build-system/SKILL.md`（实现细节、确定性约束、踩坑记录）
