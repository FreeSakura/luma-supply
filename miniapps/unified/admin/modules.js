const modules = [
  {id:'dashboard', label:'工作总览', permission:'reports', group:'operations', icon:'chart', note:'查看经营与履约概况'},
  {id:'catalog', label:'商品与规格', permission:'catalog', group:'supply', icon:'layers', note:'维护商品、规格与定价'},
  {id:'quotes', label:'报价审核', permission:'quotes', group:'supply', icon:'tag', note:'核对价格与供货信息'},
  {id:'merchants', label:'商家认证', permission:'merchants', group:'supply', icon:'store', note:'审核资质，管理合作商家'},
  {id:'users', label:'客户与权限', permission:'users', group:'operations', icon:'users', note:'管理客户与员工权限'},
  {id:'inquiries', label:'客户询价', permission:'orders', group:'sales', icon:'message', note:'回复需求，跟进询价转单'},
  {id:'orders', label:'销售订单', permission:'orders', group:'sales', icon:'box', note:'确认订单，跟进交付进度'},
  {id:'procurements', label:'采购协同', permission:'procurement', group:'sales', icon:'truck', note:'规划采购，协调供货履约'},
  {id:'tickets', label:'售后工单', permission:'orders', group:'sales', icon:'shield', note:'跟进问题与处理记录'},
  {id:'reviews', label:'商品评价', permission:'operations', group:'operations', icon:'star', note:'查看体验，回应客户反馈'},
  {id:'settings', label:'运营设置', permission:'operations', group:'operations', icon:'sliders', note:'维护轮播与客服资料'},
  {id:'index', label:'检索索引', permission:'catalog', group:'supply', icon:'scan', note:'更新图库，跟进检索任务'},
  {id:'exceptions', label:'异常中心', permission:'reports', group:'operations', icon:'alert', note:'集中跟进待处理异常'},
  {id:'audits', label:'操作记录', permission:'reports', group:'operations', icon:'clock', note:'查阅业务操作与变更'}
]
const groups = [
  {id:'supply', label:'商品与供应', note:'好商品与可靠供货'},
  {id:'sales', label:'销售与履约', note:'从客户需求到如期交付'},
  {id:'operations', label:'运营与支持', note:'让日常协同有序运转'}
]
function visible(user) {
  if (!user || !['admin','staff'].includes(user.role)) return []
  return user.role==='admin' ? modules : modules.filter(x => (user.permissions||[]).includes(x.permission))
}
function grouped(user) {
  const available=visible(user)
  return groups.map(group=>({...group,items:available.filter(item=>item.group===group.id)})).filter(group=>group.items.length)
}
module.exports={modules,visible,grouped}
