const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
async function check(role){
 let definition,last,removed=false,navigated=false
 const wx={getStorageSync:()=>'',removeStorageSync:()=>removed=true,showToast(){},navigateTo:x=>{navigated=true;x.complete?.()},login:x=>x.success({code:'temporary-code'}),request:x=>last=x}
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../miniapps',role,'app.js'),'utf8'),{App:x=>definition=x,wx,require:()=>({role,baseUrl:'http://127.0.0.1:8000'})})
 const app={...definition,globalData:{...definition.globalData,token:'expired'}}
 let pending=app.request('/wishlist');assert.equal(last.timeout,15000);last.success({statusCode:401,data:{detail:'登录已失效'}});await assert.rejects(pending,/登录已失效/);assert(removed&&navigated);assert.equal(app.globalData.token,'')
 app.globalData.token='existing';removed=false;pending=app.request('/auth/wechat/bind',{code:'bad',role});last.success({statusCode:401,data:{detail:'code过期'}});await assert.rejects(pending,/code过期/);assert.equal(removed,false);assert.equal(app.globalData.token,'existing')
 assert.equal(await app.wechatCode(),'temporary-code');assert.notEqual(app.submissionKey(),app.submissionKey())
 console.log(role+': 15s timeout, expired session cleanup, binding error isolation and wx.login code passed (wx stub)')
}
check('customer').then(()=>check('merchant')).catch(e=>{console.error(e);process.exitCode=1})
