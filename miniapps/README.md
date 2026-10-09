# 原生微信小程序

`customer/` 和 `merchant/` 为两个可导入微信开发者工具的独立项目，代码由 `shared/` 和 `scripts/build_miniapps.py` 生成。修改共享代码后重新生成，避免两端请求实现漂移。

1. 启动后端：`python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`。
2. 在微信开发者工具导入 `miniapps/customer` 或 `miniapps/merchant`，填写自己的 AppID，或使用测试号。
3. 本地调试勾选“不校验合法域名”；真机和发布必须改 `config.js` 中的 API 地址为可信 HTTPS 域名并配置平台合法域名。
4. 使用 `local-only/demo-accounts.json` 中对应角色的账号，或通过已配置短信网关注册。
5. 微信授权登录需要服务端环境变量。开发验证码仅允许服务器本机请求，不向局域网客户端暴露。

功能入口：登录注册找回、商品/SKU 搜索、上传图搜图、商品详情与 SKU 分享、客户清单询价/订单确认/签收/评价/售后、商家认证/报价版本/上下架、新建商品、双语界面及通知。账户角色由服务端校验。

当前没有用户的微信 AppID、已备案域名和真机账号，因此原生源码交付与微信平台发布/真机验收是不同状态。浏览器三端演示使用同一组真实业务 API，可在本地验证主线。

## 2.0 配置与新增功能

微信快捷登录支持客户与已绑定商家。商家先用现有商家账号登录，再在我的资料点击绑定微信；客户首次快捷登录需同意服务说明。冲突不会自动合并账号。两端的AppID与Secret分别使用 WECHAT_APP_ID/SECRET 和 WECHAT_MERCHANT_APP_ID/SECRET，Secret只在后端。

生成目标环境：`python -m scripts.build_miniapps --base-url https://your-api.example --customer-appid APPID --merchant-appid APPID`。默认仍为本地touristappid，HTTPS目标启用合法域名检查。清单修改携带version，询价重试复用submission_key；网络请求15秒超时，401清理失效会话。通知可跳到对应业务列表。

本轮未安装或运行微信开发者工具，没有真实微信授权和真机渲染结果。`node scripts/check_miniapp_v2.cjs` 使用wx桩验证网络及会话逻辑，不能替代原生平台验收。

## 2.1 交互与存储

客户和商家均支持验证码登录。工作台的询价草稿、选择和待处理请求标识按角色及用户ID隔离保存，重新进入后可继续预览和提交；多个请求分别保存标识，成功后清理对应项。订单按50条加载，支持继续加载和服务端关键词查找。网络层处理过期会话、15秒超时及非JSON上传错误。

检查：`node scripts/check_miniapp_v21.cjs`。渠道配置沿用客户与商家各自的AppID、Secret和合法域名。
