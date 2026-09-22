# 运行与部署

## 本地运行

Windows PowerShell：`powershell -ExecutionPolicy Bypass -File scripts/start.ps1`。

Linux/macOS：`sh scripts/start.sh`。

服务启动后访问 `http://127.0.0.1:8000`。接口交互文档：`/docs`。种子数据只在空数据库写入，不清空已有数据；演示账户和随机密码写入 `local-only/demo-accounts.json`。

手工步骤：

```sh
python -m venv .venv
# Windows: .venv\Scripts\python.exe ; Unix: .venv/bin/python
python -m pip install -r requirements.txt
python -m scripts.seed
cd web
npm ci
npm run build
cd ..
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

请在激活虚拟环境后使用手工步骤中的 python。默认运行单个 worker；索引任务的进程内锁不支持多进程并行消费者。

## 验证与实验

```sh
python -m pytest -q
python -m scripts.experiments --no-deep
python -m scripts.build_miniapps
```

深度视觉基线需安装 `torch`、`torchvision`，执行 `python -m scripts.experiments`。首次 ResNet18 下载约 45 MB 官方预训练权重，不提交到 Git。Chinese-CLIP 可选：安装 cn-clip，配置 `IMAGE_ENCODER=chinese-clip` 并下载对应权重后重建索引；未运行时不计入实验结果。

实验结果及原始预测在 `local-only/experiments`。默认数据为原创程序绘制的受控数据，不能解释为真实场景检索准确率。真实授权图片可按 `scripts/import_catalog.py` 的清单格式导入。

## 配置与生产边界

复制 `.env.example` 为 `.env`，填写自己的服务配置。`.env` 被 Git 排除。阿里云实例入库约定：ProductId 为本地 SKU ID，PicName 为图片 ID。当前 SDK 适配器提供调用路径，实际实例入库和云端联调仍需账户。

正式运行设置 `APP_ENV=production`，短信开发验证码将关闭。短信网关契约：POST JSON `{phone, code, expires_seconds}`，Bearer Token 认证；需接入自己的短信服务网关。微信需 AppID/Secret 及 HTTPS 合法域名。没有配置时接口返回 503，不会伪造成功。

`DATABASE_URL=mysql+pymysql://user:password@host/database?charset=utf8mb4` 可选择 MySQL。默认 SQLite 已实测；MySQL/Docker 路径提供源码但须在目标环境补充实测。初始化使用 SQLAlchemy 元数据，后续表结构升级需要显式迁移，不能把 create_all 当作历史结构迁移。

容器运行：`docker compose up --build`，空数据初始化可在容器中执行 `python -m scripts.seed`，请保存输出的演示凭证并修改密码。容器不默认导入数据或开放公网。

## 备份与恢复

停止服务后备份 `data/runtime/`，其中数据库、附件、索引版本必须一起备份。运行 `python -m scripts.backup` 可通过 SQLite 在线备份 API 生成一致数据库副本，并复制媒体及索引到本地备份目录。恢复需停服，将选定备份复制到新的数据目录后设置 DATA_DIR/DATABASE_URL；先验证再切换，不覆盖未备份原库。

## 数据与开源控制

仓库按用户最新要求公开，项目原始代码使用 MIT 许可证。原始课程资料、报告、用户名单、业务数据库、上传附件、账号与密钥不提交。后续提交继续检查数据授权、配置和依赖许可证，MIT 不覆盖外部模型权重与第三方数据。演示图来源和真实商家图来源必须区分。
