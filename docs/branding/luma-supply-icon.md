# luma supply 图标与显示名称

本次使用内置 `image_gen` 生图模型制作图标。原图为 `luma-supply-icon-source.png`；后台上传用图标为 `docs/branding/luma-supply-icon.png`（512 × 512），另备 `luma-supply-avatar.png`（144 × 144）。缩放只生成适配尺寸，未更改图案。

图标和名称用于微信入口的账号资料。按用户确认，已回退页面内新增的品牌图标和名称修改，恢复原有太阳图形、LumaSupply 品牌文字、导航标题及 luma-unified 项目名称；房间清单与报价按钮的布局修复继续保留。图标素材已移出小程序包，仅保留在 docs/branding/ 供后台上传。

微信搜索、最近使用列表及小程序资料中的名称和头像属于微信公众平台的账号信息，不由 `app.json` 或 `projectname` 设置。需管理员登录 https://mp.weixin.qq.com ，在小程序设置的基本信息处，将名称设为 `luma supply` 并上传上述图标（按后台当前要求选择尺寸）。本次仅完成本地项目和素材，未修改微信平台账号信息。

当前项目已在微信开发者工具的“详情 → 基本信息”中确认使用个人小程序测试号。微信后台的实际修改入口尚未核实：当前浏览器安全策略阻止读取和操作 mp.weixin.qq.com，因此本次没有修改微信入口资料。

## 最终生图提示词

```text
Use case: logo-brand
Asset type: WeChat mini-program app icon for luma supply, a lighting selection and supply collaboration app.
Primary request: Create one polished minimal square app icon that matches an understated sage, ivory and forest-green lighting catalog interface. A single bold, elegant ivory pendant-lamp silhouette with a small warm golden light beneath it, subtly suggesting a lowercase l through its stem. Strong legible geometric mark, premium home lighting brand, calm and welcoming.
Composition: centered symbol, generous safe margin around mark for circular platform cropping; full-bleed solid deep forest green #234d40 square background, no rounded outer corners baked into image. Flat graphic shapes, precise smooth edges, warm ivory #f5f5f0 with a restrained pale amber accent. 1024x1024 square.
Constraints: no text, no letters, no watermark, no mockup, no device frame, no border, no decorative objects, no photographic scene. Keep highly recognizable at 48px.
```
