# LumaSupply 2.1

灯具商城与供应协同平台，提供客户选型、商家供货、客服成交、采购履约及售后服务。支持网页管理端、客户微信小程序和商家微信小程序。

业务流程：商品与报价审核 → 图片及参数选型 → 房间清单与询价 → 客服建单 → 客户确认 → 采购规划与人工确认 → 分批发货 → 签收评价及售后。

## 2.1 更新

- 管理账户支持TOTP动态口令、闲置会话失效和敏感操作重新验证。
- 登录失败及来源请求采用原子计数；验证码和动态口令防重复使用。
- 询价草稿及提交标识按账户保存，刷新页面和重试时保持业务连续性。
- 订单支持分页、服务端查找和关系批量读取，目录按相关规格预取报价。
- 图片按EXIF转正，上传视频校验容器及视频轨，检索输入检查图片发布权限。
- 索引发布跨进程互斥，备份使用完成标记及SHA256校验，恢复后重建索引。
- 客户与商家小程序增加验证码登录、订单继续加载及上传错误反馈。

版本说明见 [2.1迭代记录](docs/ITERATION_2_1.md)，接口定义见 [OpenAPI](docs/v21/evidence/openapi.json)。

## 快速运行

Windows：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

Linux或macOS：

```sh
sh scripts/start.sh
```

默认访问 `http://127.0.0.1:8000`，API文档为 `/docs`。初始化只在空数据库创建数据，演示账户和随机密码保存在 `local-only/demo-accounts.json`。升级时先备份，执行 `python -m backend.migrations`，并更新网页及小程序构建。

## 微信小程序

客户项目为 `miniapps/customer`，商家项目为 `miniapps/merchant`。共享代码位于 `miniapps/shared`，执行以下命令生成目标配置：

```sh
python -m scripts.build_miniapps --base-url https://your-api.example --customer-appid CUSTOMER_APPID --merchant-appid MERCHANT_APPID
```

服务端分别配置客户和商家AppID及Secret，客户端只保存AppID和API地址。商家先以已有账号登录，再在资料页绑定微信。开发与渠道接入步骤见 [小程序说明](miniapps/README.md)。

## 管理身份认证

```sh
python -m scripts.configure_mfa --user admin --output local-only/security/mfa.json
```

在认证器中添加对应账户，并将 `MFA_SECRETS_FILE` 设置为该文件的绝对路径。生产管理员使用密码与动态码登录，密钥由管理员保管。管理会话闲置30分钟失效；定价、员工授权、商家停用和采购确认要求近期身份验证。

## 项目结构

| 目录 | 内容 |
|---|---|
| backend | FastAPI业务服务 数据模型 身份与事务 |
| algorithms | 图像图文检索 供应商组合优化 |
| web | Vue 3与TypeScript网页 |
| miniapps | 客户和商家原生微信项目 |
| scripts | 初始化 实验 检查 迁移辅助 备份恢复 |
| tests | 单元 接口 并发与权限测试 |
| docs | 设计 版本 需求对应及运行记录 |
| output | 本地报告与交付包 |

## 验证和复现

```sh
python -m pytest -q
python -m scripts.experiments
python -m scripts.performance_l0
python -m scripts.export_contracts
```

前端构建：在 `web` 目录运行 `npm ci` 和 `npm run build`。原生检查使用 `scripts/check_miniapp_*.cjs`，网页提交标识检查使用 `scripts/check_pending_submission.cjs`。L0资源采样依赖可选包psutil。

2.1执行60项自动化测试、前端构建及十个浏览器关键检查。L0基准采用100 SPU、300 SKU、1200张图库图片、10家商家及1000张订单，三轮共9000个测量请求。参数、结果及数据生成方法见 [验证记录](docs/v21/evidence)。

## 文档和团队

七份文档包括系统设计、数据库与接口、算法设计与实验、实施过程、软件测试、部署运维与用户操作、项目总结。Word与可编辑正文保存在本地 `output/reports-2.1/`。

| 成员 | 贡献比例 | 负责方向 |
|---|---|---|
| 池洪伟 | 40% | 算法 数据与实验 性能优化 版本集成 |
| 兰玉栋 | 30% | 业务后端 账户权限 数据库与恢复 |
| 章琬菁 | 30% | 三端交互 微信小程序 系统测试 |

## 数据与许可

项目采用 [MIT许可证](LICENSE)。密钥、运行数据库、用户上传及个人材料不进入Git；第三方依赖和模型权重遵循各自许可，见 [第三方说明](THIRD_PARTY_NOTICES.md)。金额使用整数分，订单保存成交快照，实验数据来源与参数在对应材料中记录。
