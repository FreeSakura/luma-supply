# 需求到实现与证据

本地业务完成与外部平台验收分别记录。测试数量为 11 个关键测试函数和 8 个浏览器检查，不等于全部页面逐像素验证。

| ID | 页面及接口 | 数据/算法 | 证据与状态 |
|---|---|---|---|
| R01 | 三端登录与个人资料；auth、me、addresses、admin/staff | User、Session、Address、权限依赖 | 本地账户及归属测试通过；真实短信/微信待联调 |
| R02 | 商家认证与平台商家列表；merchant/profile、admin/merchants | Merchant、私有 license Media | 本地审批、禁用与报价剔除实现；证件为用户自备 |
| R03 | 商品列表、新建商品、新增规格；catalog、admin/skus | Product、SKU、Media | SPU/SKU、参数、图片与状态实现；演示数据明确标记 |
| R04 | 报价页、CSV 导入、审批及重报 | Quote 版本、审核状态、预留量继承 | T04 与所有权测试；CSV 先预检再提交 |
| R05 | 商品调价、全局定价预览 | PricingRule、SKU manual_price、OrderLine snapshot | T03 历史快照保持；人工价优先 |
| R06 | 选灯首页、上传与目标框；search | retrieval.py、IndexTask、SearchLog | 六方法实验；真实照片及阿里云实例待联调 |
| R07 | 详情、SKU 分享、对比、清单询价 | Wishlist、Inquiry | 浏览器选中 SKU 到询价通过 |
| R08 | 客服从询价建单、客户确认地址/自提 | Order、OrderLine、地址快照 | T01、T02、T03、T08 及浏览器流程 |
| R09 | 采购建议、确认、凭证和分批发货 | CP-SAT、Procurement、Shipment | T01、T05、T06、T09；枚举与采购实验 |
| R10 | 评价、回复删除、售后处理 | Review、Ticket、通知 | 文字图片视频附件路径、签收前置、状态迁移 |
| R11 | 语言切换、两端轮播、客服配置 | Setting，1—6 项约束 | 数量约束已测；原生页面提供双语文字；真实客服二维码待用户配置 |
| R12 | 消息、审计、异常、检索反馈 | Notification、Audit、SearchLog | 本地实现，不承诺外部推送渠道 |
| R13 | 索引状态、重建与失败重试 | current 原子指针、NPZ 元数据 | 本地 72 图片索引已建；单 worker 部署 |
| R14 | 本地实验脚本与报告 | 144 图库图、48 验证查询、96 测试查询 | 可重复受控数据，绝不称为真实照片准确率 |
| R15 | 采购基线、优化状态和实验 | 40 合成实例，10 个枚举对照 | 全部 40 例 OPTIMAL，10/10 枚举一致 |
| R16 | 本地 output/reports 和答辩 PPT | 8 份报告 + Markdown + PPTX | 内容与真实实现/验证对应，成员实际贡献待各人补录 |
| R17 | Git、启动脚本、依赖锁与备份 | 私有仓库，原件/数据/报告排除 | 阶段提交推送；SQLite 实测，MySQL/Docker 待目标环境验证 |

## 明确的后续联调项

1. 阿里云图片入库、实例搜索与配额验证。SDK 已提供，用户暂无线下配置。
2. 微信开发者工具编译、真机与正式域名、微信 OAuth 和短信服务。交付原生源码不等同已上架。
3. 授权真实灯具图库、独立拍摄查询、人工相关性标注和非灯具输入评价。当前仅受控图形实验。
4. MySQL 事务语义与 Docker 部署的实机验证。默认已验证环境是 Windows + SQLite。
5. 团队成员独立阅读、复现实验、现场改动练习与真实 Git 贡献记录。不能用 AI 辅助生成替代个人学习证明。
