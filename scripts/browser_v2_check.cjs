// Actual local browser journey. WeChat-specific wx APIs are verified separately.
const {chromium}=require('playwright')
const assert=require('node:assert/strict')
const fs=require('node:fs')
const path=require('node:path')
const root=path.resolve(__dirname,'..'),out=path.join(root,'local-only/browser-v2')
fs.mkdirSync(out,{recursive:true})
const password=JSON.parse(fs.readFileSync(path.join(root,'local-only/demo-accounts.json'),'utf8')).password
const base=process.env.LUMA_BASE_URL||'http://127.0.0.1:8000'
async function run(){
 const browser=await chromium.launch({headless:true,channel:'msedge'})
 const context=await browser.newContext({viewport:{width:1440,height:1000}})
 const page=await context.newPage(),errors=[],checks=[]
 page.on('pageerror',e=>errors.push(e.message))
 const button=name=>page.getByRole('button',{name,exact:true})
 async function shot(name){await page.screenshot({path:path.join(out,name+'.png'),fullPage:true})}
 async function login(username){await page.goto(base);await page.waitForLoadState('networkidle');await page.getByLabel('用户名',{exact:true}).fill(username);await page.getByLabel('密码',{exact:true}).fill(password);await button('继续').click();await page.locator('.sidebar').waitFor();await page.waitForLoadState('networkidle')}
 async function logout(){await button('退出登录').click();await page.getByLabel('用户名',{exact:true}).waitFor()}
 try{
  await login('customer');await page.locator('.product-card').nth(17).waitFor();assert.equal(await page.locator('.product-card').count(),18);await shot('01-customer-catalog');checks.push('Customer login and exact catalog count')
  await page.locator('.product-card').first().click();await page.locator('.product-dialog').waitFor();const sku=await page.locator('.detail-copy select').inputValue();await button('加入选购清单').click();await page.locator('.product-dialog').waitFor({state:'hidden'})
  await button('房间清单').click();await page.locator('.planner-line').first().waitFor();await page.locator('.planner-line').first().getByRole('button',{name:/编辑/}).click();await page.getByLabel('采购数量',{exact:true}).fill('2');await button('保存清单修改').click();await page.locator('.wish-editor').waitFor({state:'hidden'});await shot('02-room-list');checks.push('SKU '+sku+' carries through detail and versioned wishlist editing')
  // A second device changes the server after this browser has captured version 2.
  await page.locator('.planner-line').first().getByRole('button',{name:/编辑/}).click()
  const conflict=await page.evaluate(async()=>{const h={Authorization:'Bearer '+localStorage.getItem('luma-token'),'Content-Type':'application/json'};const rows=await (await fetch('/api/wishlist',{headers:h})).json();const r=rows[0];return (await fetch('/api/wishlist/'+r.id,{method:'PATCH',headers:h,body:JSON.stringify({version:r.version,note:'第二设备已修改'})})).status})
  assert.equal(conflict,200);await page.getByLabel('采购数量',{exact:true}).fill('9');await button('保存清单修改').click();await page.getByText(/清单已在其他设备修改/).first().waitFor();assert.equal(await page.getByLabel('采购数量',{exact:true}).inputValue(),'9');await shot('03-version-conflict');checks.push('Second-device conflict is visible and preserves the unsaved draft')
  await page.keyboard.press('Escape');await page.reload();await page.waitForLoadState('networkidle');await button('房间清单').click();await page.locator('.planner-line').first().waitFor()
  await button('清单一键询价').click();await page.getByLabel('项目名称',{exact:true}).fill('2.0 本地验收');await button('预览询价清单').click();await page.locator('.inquiry-preview').waitFor()
  // Server commits the first submission; the browser loses that response.
  let dropped=false
  await page.route('**/api/inquiries',async route=>{if(route.request().method()==='POST'&&!dropped){dropped=true;await route.fetch();await route.abort('failed')}else await route.continue()})
  await button('确认发送询价').click();await page.locator('.inquiry-composer .error').waitFor();await button('确认发送询价').click();await page.locator('.inquiry-row').first().waitFor();await page.unroute('**/api/inquiries')
  const count=await page.evaluate(async()=>{const a=await (await fetch('/api/inquiries',{headers:{Authorization:'Bearer '+localStorage.getItem('luma-token')}})).json();return a.filter(x=>x.requirements.project_name==='2.0 本地验收').length})
  assert.equal(count,1);await shot('04-inquiry');checks.push('Lost success response retried with same key creates one inquiry')
  await logout();await login('merchant');await button('我的报价').click();await page.locator('tbody tr').first().waitFor();assert.equal(await page.locator('tbody tr').count(),36);await shot('05-merchant');checks.push('Merchant own-quote workbench renders 36 approved offers')
  await logout();await login('admin');await shot('06-dashboard');await button('客户询价').click();await page.getByRole('button',{name:'转为销售订单',exact:true}).first().click();await button('创建订单并通知客户').click();await page.locator('.dialog').waitFor({state:'hidden'});await shot('07-order');checks.push('Service converts immutable inquiry into sales order')
  await logout();await login('customer');await button('我的订单').click();await page.getByRole('button',{name:/查看详情/}).first().click();await button('确认订单').click();await page.locator('.dialog').waitFor({state:'hidden'});checks.push('Customer confirms own order for pickup')
  await logout();await login('admin');await button('采购协同').click();await button('生成采购方案').first().click();await button('计算方案').click();await page.getByText('采购方案建议',{exact:true}).waitFor();await shot('08-procurement');await button('确认采购并预留数量').click();await page.locator('.dialog').waitFor({state:'hidden'});checks.push('CP-SAT plan and human reservation completed through browser')
  await logout();await login('customer');await page.setViewportSize({width:390,height:844});await shot('09-mobile');assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));checks.push('390px customer viewport has no horizontal overflow')
  assert.equal(errors.length,0)
  fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({scope:'Actual local Edge browser; not WeChat runtime',checks,javascript_errors:errors,passed:true},null,2))
  console.log(JSON.stringify({checks,passed:true}))
 }catch(error){await shot('failure');fs.writeFileSync(path.join(out,'failure.json'),JSON.stringify({checks,errors,error:String(error)},null,2));throw error}finally{await browser.close()}
}
run().catch(e=>{console.error(e);process.exitCode=1})
