# LumaSupply 灯具商城与供应协同平台

综合课程项目：三端灯具业务、多模态商品检索、多商家采购优化。

业务主线：商家认证 → 商品及 SKU 审核 → 多商家报价 → 客户检索与清单询价 → 客服创建销售订单 → 客户确认 → 采购优化与确认 → 分批履约 → 评价及售后。

## 项目结构

- `backend/`：FastAPI 模块化业务 API、SQLAlchemy 数据模型。
- `algorithms/`：图像及图文检索、供应商组合优化。
- `web/`：Vue 3 + TypeScript 管理端及可在浏览器运行的三端演示。
- `miniapps/`：客户和商家原生微信小程序源码。
- `scripts/`：初始化、实验、部署与交付工具。
- `tests/`：核心业务、算法和接口验证。
- `docs/`：架构、迭代、需求追踪及项目成员分工。
- `local-only/`：课程原件提取、完整报告、截图及验收证据（不提交）。

## 交付原则

项目按 [MIT 许可证](LICENSE) 开源，保留阶段开发历史。课程原件、学号及联系方式、密钥、用户上传、运行数据库、模型权重及完整课程报告不进入 Git。已有项目成员分工记录保留。第三方依赖和模型权重遵循各自许可，见 [第三方说明](THIRD_PARTY_NOTICES.md)。自主生成的演示数据与真实商家数据明确区分；外部服务未联调时不标记为验收通过。金额统一使用整数分，历史订单保存快照。

## 1.1 技术迭代

- 目录搜索先在数据库按标题、SKU、颜色和规格筛选，再分页；支持 `offset`，保留命中 SKU 和对应价格。
- 检索重排批量读取当前商品与规格，立即使用新标题和参数，并排除已经移除的图片。
- 修正增量运费贪心基线：同一供应商后续报价提高合并运费时，计入新增差额。

详细设计、复现场景与兼容性见 [1.1 迭代记录](docs/ITERATION_1_1.md)。参与开发见 [贡献指南](CONTRIBUTING.md)。

## 快速运行

Windows：`powershell -ExecutionPolicy Bypass -File scripts/start.ps1`。

Linux/macOS：`sh scripts/start.sh`。

打开 `http://127.0.0.1:8000`；API 文档为 `/docs`。首次初始化的随机演示密码写入 `local-only/demo-accounts.json`，账户为 `admin`、`customer`、`merchant`、`merchant2`、`merchant3`。已有数据不会被脚本清空。

微信开发者工具可分别导入 `miniapps/customer`、`miniapps/merchant`。实际发布需要自己的 AppID 与 HTTPS 域名。详细步骤见 [部署说明](docs/DEPLOYMENT.md) 与 [小程序说明](miniapps/README.md)。

## 核心实现

- 审核生效的报价版本、万分比定价规则、订单规格与金额快照。
- 客服成交、客户确认、采购建议及事务确认、凭证和分批发货、评价售后。
- 360 维传统视觉特征与字符 TF-IDF 联合检索，具体 SKU 命中、多视图聚合、裁剪和硬条件过滤。
- CP-SAT 求解供应商组合和合并运费，保留最优/可行状态，并提供两种贪心及枚举对照。
- 三端账户归属控制、员工模块权限、未读通知、审计、索引版本与失败重试。

验证：`python -m pytest -q`（15 项关键测试）。前端：`cd web && npm ci && npm run build`。实验：`python -m scripts.experiments --no-deep`；安装 PyTorch/torchvision 后不加该选项可运行 ResNet18 对照。

## 已验证范围

本地 SQLite 业务主线、Vue 生产构建和三角色浏览器串联已验证。受控检索实验使用 144 张原创程序图、96 条测试查询，不能作为真实场景泛化准确率。采购比较包含 40 组实例，10 个小实例与完整枚举一致。

外部阿里云/微信/短信未配置，接口明确返回未配置状态；Chinese-CLIP 为可选编码器，未计入已运行实验。MySQL、Docker 和微信真机仍需对应环境验收。用户确认当前先完成本地交付并列明这些联调项。

阶段记录见 [迭代记录](docs/ITERATIONS.md)，验收映射见 [验收清单](docs/ACCEPTANCE.md)。全部课程报告保存在本地 `output/reports/`，不随源码推送。
