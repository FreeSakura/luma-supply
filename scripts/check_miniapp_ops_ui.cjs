// Exercise navigation and payloads behind the management / supplier mobile UI.
// This runs page source with wx mocks; it does not claim native-device coverage.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const {createRequire} = require('node:module')
const root = path.resolve(__dirname, '../miniapps/unified')
const modules = require(path.join(root, 'admin/modules'))
const plain = value => JSON.parse(JSON.stringify(value))
const event = dataset => ({currentTarget:{dataset}})
const requests = []
let response = [], route = ''
const app = {
  globalData:{role:'admin', user:{id:1,role:'admin',permissions:[]}, token:'fixture', lang:'zh'},
  request:async (url, body, method) => {requests.push({url,body,method});return response},
  money:value => '¥'+((value||0)/100).toFixed(2),
  picture:id => '/pictures/'+id,
  quoteState:row => row.deleted?'deleted':!row.active?'inactive':row.status,
  saveDraft(){},getDraft:()=>null,
  requireLogin:()=>true,syncTabs(){},ensureUser:async()=>app.globalData.user
}
function load(folder) {
  let page
  const file=path.join(root,`pages/${folder}/index.js`)
  vm.runInNewContext(fs.readFileSync(file,'utf8'), {
    Page:value=>{page=value},getApp:()=>app,require:createRequire(file),setTimeout,clearTimeout,
    wx:{setNavigationBarTitle(){},showToast(){},navigateBack(){route='back'},switchTab:value=>{route=value.url}},console
  },{filename:file})
  page.data=plain(page.data)
  page.setData=update=>{
    for(const [key,value] of Object.entries(update)) {
      const parts=key.split('.');let target=page.data
      for(const part of parts.slice(0,-1))target=target[part] ||= {}
      target[parts.at(-1)]=value
    }
  }
  return page
}
async function main() {
  for(const user of [{role:'admin'}, {role:'staff',permissions:['orders']}, {role:'staff',permissions:[]}, {role:'customer'}, {role:'merchant'}]) {
    const groups=modules.grouped(user), ids=groups.flatMap(group=>group.items.map(item=>item.id))
    assert.deepEqual([...ids].sort(),modules.visible(user).map(item=>item.id).sort())
    assert.equal(new Set(ids).size,ids.length)
    assert(groups.every(group=>group.items.length))
  }
  app.globalData.user={id:6,role:'staff',permissions:['orders']};app.globalData.role='staff'
  const staffHome=load('home');requests.length=0
  await staffHome.loadAdmin()
  assert.equal(staffHome.data.adminHasDashboard,false)
  assert.equal(requests.length,0,'Staff without reports must not fetch the dashboard')
  assert.deepEqual(plain(staffHome.data.adminGroups.flatMap(group=>group.items.map(item=>item.id))),['inquiries','orders','tickets'])
  app.globalData.user={id:1,role:'admin',permissions:[]};app.globalData.role='admin'

  response=[{id:7,name:'灯具',status:'active',skus:[{id:71,code:'A',manual_price:null},{id:72,code:'B',manual_price:9000}]}]
  const catalog=load('admin');await catalog.onLoad({module:'catalog'})
  assert.equal(new Set(catalog.data.rows[0].actions.map(action=>action.key)).size,5)
  catalog.toggleRowActions(event({id:'7'}));assert.equal(catalog.data.rows[0].expanded,true)
  let selected
  catalog.openAction=async (action,row)=>{selected={action,row}}
  await catalog.menuAction(event({id:'7',action:'sku-price',sku:'72'}))
  assert.equal(selected.action.skuId,72);assert.equal(selected.row.id,7)
  assert.equal(selected.action.price,90)
  catalog.toggleRowActions(event({id:7}));assert.equal(catalog.data.rows[0].expanded,false)

  response=[{id:1,status:'pending',sku_code:'A',price:0,available_quantity:0,lead_days:3},{id:2,status:'approved',sku_code:'B',price:12000,available_quantity:null,lead_days:5}]
  const quotes=load('admin');await quotes.onLoad({module:'quotes'})
  assert.deepEqual(plain(quotes.data.statusOptions),['全部状态','待审核','已通过'])
  assert.match(quotes.data.rows[0].subtitle,/可供 0 件/)
  quotes.statusPick({detail:{value:'2'}})
  assert.equal(quotes.data.statusFilter,'approved');assert.equal(quotes.data.statusLabel,'已通过')
  assert.deepEqual(plain(quotes.data.rows.map(row=>row.id)),[2])

  const permissions=load('admin')
  await permissions.openAction({id:'staff-edit',label:'编辑权限'},{id:6,name:'员工',permissions:['catalog'],active:true})
  assert.equal(permissions.data.permissionOptions.find(item=>item.name==='catalog').label,'商品与规格')
  permissions.permissionChange({detail:{value:['catalog','orders']}})
  response={};requests.length=0;permissions.load=async()=>{}
  await permissions.submit()
  assert.equal(requests[0].url,'/admin/staff/6')
  assert.deepEqual(plain(requests[0].body.permissions),['catalog','orders'])

  response={customer_banners:[{image:'demo-image',title:'原始标题',link:'/product/7'}]}
  const settings=load('admin');await settings.onLoad({module:'settings'})
  assert.equal(settings.data.settingRows[0].picture,'/pictures/demo-image')
  settings.settingInput({currentTarget:{dataset:{index:0,field:'title'}},detail:{value:'新标题'}})
  response={};requests.length=0;await settings.saveSettings()
  assert.equal(requests[0].body.customer_banners[0].title,'新标题')
  assert.equal('picture' in requests[0].body.customer_banners[0],false,'Image previews must not leak into the settings payload')

  app.globalData.role='merchant';app.globalData.user={id:3,role:'merchant',permissions:[]}
  const work=load('work');work.openImport();assert.equal(work.data.modal,'import')
  work.close();assert.equal(work.data.modal,'')
  for(const folder of ['home','work','profile','detail','admin']) {
    const page=load(folder), markup=fs.readFileSync(path.join(root,`pages/${folder}/index.wxml`),'utf8')
    for(const [,name] of markup.matchAll(/(?:bind|catch)(?:tap|change|input|confirm|blur)="(\w+)"/g)) {
      assert.equal(typeof page[name],'function',`${folder}: missing ${name}`)
    }
  }
  console.log('Management / supplier mobile UI checks passed: permission-scoped groups, secondary SKU actions, translated filters, permission payloads, setting previews, import state and event bindings.')
}
main().catch(error=>{console.error(error);process.exitCode=1})
