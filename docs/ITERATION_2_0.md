# 2.0 本地交付迭代

日期：2026-10-08。基线：1.7.0 / d3e90de。用户确认保留仓库名称，以 2.0 为 Release 标题，并将原定 Your dot 云电脑验证调整为本地验证。

## 业务变化

- 清单 PATCH 必填 `version`，条件更新成功递增版本；同房间同 SKU 的重复 POST 返回 409，避免绕过版本保护。
- 询价创建必填 `submission_key`，按客户及键唯一。载荷指纹相同返回首个询价，不同载荷返回 409；并发重试只有一份快照、事件和提交映射。
- 客户和商家微信配置分开。商家先登录既有账号再绑定，首次微信客户需同意，冲突禁止自动合并或角色提升。
- 未发布商品图不再对任意登录者开放；采购和发货凭证分别按关联与权限访问。
- 售后按订单行累计数量，不超过购买量；已关闭工单仍计入，本地演示政策不代表已建立退款核销机制。
- 采购基线使用相同预算及供应商约束，违规明确标记；晚到规划使用采购版本和状态条件写回。
- 管理会话绝对期限缩为 8 小时，账户失败限速为 15 分钟 10 次。管理员 MFA、闲置失效、来源联合限速尚未实现。

## 跨端与升级

网页和原生小程序同步清单版本与询价提交键。网页订单和发货在同一表单载荷下保留重试键。小程序增加微信绑定、通知入口、15 秒请求超时和 401 会话清理。

`python -m scripts.build_miniapps --base-url https://your-api.example --customer-appid APPID --merchant-appid APPID` 可生成两个目标环境项目。AppSecret 只在服务端。默认生成本地地址和 touristappid；不代表真机可发布。

新增三张表：`inquiry_submissions`、`wechat_identities`、`login_attempts`；`wishlist` 增加 `version`，历史行默认 1。启动自动执行增量升级，也可运行 `python -m backend.migrations`。旧写客户端缺少两个必填字段会返回 422，需同步升级。

## 实际验证

- 最终 pytest 42 项通过，Vue 类型检查及生产构建通过。
- Edge 三角色旅程九项检查通过，包含真实服务器提交后丢弃响应、重试不重复询价，以及第二设备写入后的冲突草稿。
- 三个原生逻辑脚本分别验证筛选、清单和网络会话；属于 wx 桩及源逻辑测试，没有原生渲染或真机结论。
- 九种受控检索方法：融合 Hit@1 为 81/96，MRR 为 0.9132；同过滤裁剪图像基线为 74/96。数据是程序生成图，非实拍图库。
- 40 组采购实例均 OPTIMAL，10 小实例与枚举一致；40 行组平均节约 0.414%，不作商业收益外推。
- 目录 80 请求并发 8，P95 286.95ms；检索 30 请求并发 4，P95 155.36ms；均无错误。不是正式 L0/L1 负载。
- 独立恢复目录和 8001 服务核对 73 媒体、订单总額 107992 分、客户登录、图片访问和审计禁止访问。

脱敏原始证据在 [evidence](v2/evidence)，逐需求状态在 [需求追踪](v2/REQUIREMENT_TRACE.md)。报告正文、截图和 Word 文档在本地 `output/reports-2.0/`，不进入公开仓库。

## 可复现检查

```sh
python -m pytest -q
python -m scripts.experiments
python -m scripts.build_miniapps
node scripts/check_miniapp_filters.cjs
node scripts/check_miniapp_wishlist.cjs
node scripts/check_miniapp_v2.cjs
```

浏览器：先启动全新隔离演示实例，然后在可用 Playwright/Edge 环境运行 `node scripts/browser_v2_check.cjs`。该脚本会创建业务，不要在真实数据上执行。恢复：`python -m scripts.restore BACKUP NEW_DIRECTORY`，目标必须不存在。

## 文档与交付

团队职责和工作量见TEAM_PLAN，阶段成果对应版本提交。算法设计与实验合并，补入部署运维手册，形成七份新版报告。微信、短信和云检索未配置；真实数据效果、L1、跨数据库部署及完整生产安全仍有待办，不声明生产全面验收。
