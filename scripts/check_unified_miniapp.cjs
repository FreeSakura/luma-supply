const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const {createRequire} = require('node:module')

const root = path.resolve(__dirname, '../miniapps/unified')
const storage = new Map()
const tabs = []
let app, page, route = ''
const wx = {
  getStorageSync: key => storage.get(key),
  setStorageSync: (key, value) => storage.set(key, value),
  removeStorageSync: key => storage.delete(key),
  setTabBarItem: item => tabs.push(item.text),
  switchTab: value => {route = value.url},
  navigateBack: () => {route = 'back'},
  navigateTo: value => {route = value.url},
  setNavigationBarTitle: () => {},
  showToast: () => {},
  request: options => options.success({statusCode: 403, data: {code:'reauth_required', detail: {message:'请重新验证'}}})
}
function load(file) {
  const absolute = path.join(root, file)
  const context = {App: value => {app = value}, Page: value => {page = value}, getApp: () => app, wx,
    require: createRequire(absolute), console, setTimeout, clearTimeout, Date, Math, JSON}
  vm.runInNewContext(fs.readFileSync(absolute, 'utf8'), context, {filename:absolute})
  if (page) page.setData = update => {
    for (const [key,value] of Object.entries(update)) {
      if (!key.includes('.')) page.data[key] = value
      else {const parts=key.split('.');let target=page.data;for(const part of parts.slice(0,-1))target=target[part] ||= {};target[parts.at(-1)]=value}
    }
  }
  return page
}

async function main() {
  load('app.js')
  storage.set('luma-lang','en')
  app.onLaunch()
  assert.equal(app.globalData.lang,'zh')
  for (const folder of ['home','work','detail','profile','login','admin']) {
    const markup=fs.readFileSync(path.join(root,'pages',folder,'index.wxml'),'utf8')
    assert.doesNotMatch(markup,/ \/ [A-Za-z]/)
    assert.doesNotMatch(markup,/bindtap="language"|English|Sign in|Find your light/)
  }
  const networkRequest=app.request
  await assert.rejects(networkRequest.call(app,'/admin/catalog',{}), error=>error.code==='reauth_required'&&error.status===403)
  app.request = async path => path === '/auth/login' ? {token:'demo-token',user:{id:1,role:'admin',username:'admin',permissions:[]}} : []
  const login = load('pages/login/index.js')
  login.data.form.username='admin';login.data.form.password='example'
  await login.submit()
  assert.equal(app.globalData.role,'admin')
  assert.equal(route,'/pages/home/index')
  assert.deepEqual(tabs.slice(-3),['总览','管理工作台','我的'])
  assert.equal(storage.get('luma-token-unified'),'demo-token')

  for (const role of ['customer','merchant']) {
    app.request=async path => path==='/auth/login'?{token:role+'-token',user:{id:role==='customer'?2:3,role,username:role,permissions:[]}}:[]
    const roleLogin=load('pages/login/index.js')
    roleLogin.data.form.username=role;roleLogin.data.form.password='example'
    await roleLogin.submit()
    assert.equal(app.globalData.role,role)
    assert.equal(storage.get('luma-token-unified'),role+'-token')
    assert.equal(tabs.at(-3),role==='customer'?'选灯':'选品')
  }
  app.setLogin({token:'demo-token',user:{id:1,role:'admin',username:'admin',permissions:[]}})

  const modules = require(path.join(root,'admin/modules.js'))
  assert.equal(modules.visible({role:'customer'}).length,0)
  assert.deepEqual(modules.visible({role:'staff',permissions:['orders']}).map(x=>x.id),['inquiries','orders','tickets'])
  assert.equal(modules.visible({role:'admin'}).length,14)

  app.request=async path => path==='/me'?{id:6,role:'staff',permissions:['catalog']}:[]
  await app.ensureUser()
  assert.equal(app.globalData.role,'staff')
  assert.deepEqual(modules.visible(app.globalData.user).map(x=>x.id),['catalog','index'])
  app.setLogin({token:'demo-token',user:{id:1,role:'admin',username:'admin',permissions:[]}})

  app.request = async path => path === '/admin/catalog' ? [] : []
  let admin = load('pages/admin/index.js')
  await admin.onLoad({module:'catalog'})
  assert.equal(admin.data.module,'catalog')
  assert.equal(admin.data.error,'')
  app.globalData.user={id:6,role:'staff',permissions:['catalog']}
  admin = load('pages/admin/index.js')
  await admin.onLoad({module:'orders'})
  assert.equal(route,'back')

  app.globalData.user={id:1,role:'admin',permissions:[]}
  const calls=[]
  app.request = async (path,body) => {calls.push(path);if(path==='/admin/catalog/7/state'&&calls.filter(x=>x===path).length===1){const error=new Error('请重新验证');error.code='reauth_required';throw error}return {}}
  admin = load('pages/admin/index.js')
  admin.data.module='catalog'
  admin.load=async()=>{}
  await admin.runAction('deactivate',{id:7},{})
  assert.equal(admin.data.modal,'reauth')
  admin.data.form={password:'example',otp:''}
  await admin.reauth()
  assert.deepEqual(calls,['/admin/catalog/7/state','/auth/reauth','/admin/catalog/7/state'])
  assert.equal(admin.data.modal,'')

  app.request=async()=>[]
  admin=load('pages/admin/index.js')
  admin.data.module='orders'
  await admin.openAction({id:'new-order'},null)
  admin.input({currentTarget:{dataset:{key:'remark'}},detail:{value:'待恢复订单'}})
  assert.equal(app.getDraft('order-form').remark,'待恢复订单')
  admin=load('pages/admin/index.js')
  admin.data.module='orders'
  await admin.openAction({id:'new-order'},null)
  assert.equal(admin.data.form.remark,'待恢复订单')
  app.dropDraft('order-form')

  const writes=[]
  app.request=async (path,body)=>{writes.push({path,body});return {id:8}}
  admin=load('pages/admin/index.js')
  admin.data.module='orders';admin.load=async()=>{}
  await admin.runAction('new-order',null,{customer_id:'2',items:[{sku_id:'1',quantity:'2',unit_price:''}],remark:'演示订单',inquiry_id:null})
  assert.equal(writes[0].path,'/orders')
  assert.equal(writes[0].body.customer_id,2)
  assert.equal(writes[0].body.items[0].unit_price,null)
  assert.match(writes[0].body.idempotency_key,/^wx-/)
  assert.equal(app.getDraft('pending-order-create'),null)

  await admin.runAction('shipment',{id:8},{carrier:'',tracking:'',proof:'demo-proof',items:[{line_id:4,quantity:'1'}]})
  assert.equal(writes[1].path,'/orders/8/shipments')
  assert.deepEqual(JSON.parse(JSON.stringify(writes[1].body.items)),[{line_id:4,quantity:1}])
  assert.equal(app.getDraft('pending-shipment-8'),null)
  console.log('Unified miniapp role, permission, and reauthentication checks passed.')
}
main().catch(error => {console.error(error);process.exitCode=1})
