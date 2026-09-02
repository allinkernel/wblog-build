# wblog 构建 Makefile（在 wblog_new 根目录执行 make）
# 本文件物理在 build/ 仓库；仓库根经 manifest linkfile 到 wblog_new/Makefile（用户上库时补 linkfile）。
# 命令在仓库根 cwd 语义下运行（./build.sh 为根 linkfile）。
#
#   make            = 完整构建：build.sh(html+manifest) + db_gen(sql+本地.db) + erofs 镜像
#   make install    = 本地部署形态就位（fuse 挂载镜像验收）——待 push/install 细节用户定后实现
#   make push       = 部署服务器（先过 check_pushed 红线）——push 细节用户定后实现
#   make snapshot   = 产 .repo/manifests/snapshot/<时间戳>.xml（先过 check_pushed）
# 产物确定性（用户 2026-09-02）：同一 repo manifest 状态多次 make，sql/.db/erofs hash 必须一致。

.PHONY: all build install push snapshot check_pushed
all: build

build:
	./build.sh
	python3 build/scripts/db_gen.py --dist out/dist --manifest out/dist/manifest.json \
		--out-sql out/sql --out-db out/index.db
	bash build/scripts/gen_image.sh
	bash build/scripts/verify_image.sh

install: build
	@echo "make install: 本地部署就位（fuse 挂载 out/wblog.erofs 验收）——待 push/install 细节定后实现"

push: check_pushed
	@echo "make push: 待用户定 push 细节（服务器目标/ssh/建库方式）后实现"

snapshot: check_pushed
	bash build/scripts/make_snapshot.sh

check_pushed:
	bash build/scripts/check_pushed.sh
