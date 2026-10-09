const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
async function check(role){
 const storage=new Map();let definition,uploadRequest
 const wx={getStorageSync:k=>storage.get(k),setStorageSync:(k,v)=>storage.set(k,structuredClone(v)),removeStorageSync:k=>storage.delete(k),showToast(){},chooseMedia:x=>x.success({tempFiles:[{tempFilePath:'fixture.jpg'}]}),uploadFile:x=>uploadRequest=x}
 function launch(){vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../miniapps',role,'app.js'),'utf8'),{App:x=>definition=x,wx,require:()=>({role,baseUrl:'http://127.0.0.1:8000'})});const app={...definition,globalData:{...definition.globalData}};app.onLaunch();return app}
 let app=launch();app.setLogin({token:'fixture',user:{id:1,role}})
 const body={wishlist_ids:[1],message:'Keep across restarts'};const key=app.pendingKey('inquiry',body)
 const second=app.pendingKey('inquiry',{...body,message:'Another tab'});assert.notEqual(second,key);
 app.saveDraft('inquiry',{form:{message:body.message},selectedIds:[1]});app=launch()
 assert.equal(app.pendingKey('inquiry',body),key);assert.equal(app.getDraft('inquiry').form.message,body.message)
 app.setLogin({token:'another',user:{id:2,role}});assert.notEqual(app.pendingKey('inquiry',body),key);assert.equal(app.getDraft('inquiry'),null)
 const uploading=app.upload('query');uploadRequest.success({statusCode:502,data:'<html>unavailable</html>'});await assert.rejects(uploading,/上传响应异常/)
 console.log(role+': persisted draft and retry key, account isolation, non-JSON upload failure passed')
}
check('customer').then(()=>check('merchant')).catch(e=>{console.error(e);process.exitCode=1})
