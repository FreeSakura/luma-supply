const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto')
const ts=require('../web/node_modules/typescript')
const source=ts.transpileModule(fs.readFileSync(require('node:path').join(__dirname,'../web/src/pendingSubmission.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText
const store=new Map(),localStorage={getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)}
function reload(){const exports={};vm.runInNewContext(source,{exports,localStorage,crypto});return exports}
let api=reload();const a={items:[1],message:'A'},b={items:[2],message:'B'}
const first=api.pendingKey('customer-1-inquiry',a),second=api.pendingKey('customer-1-inquiry',b)
assert.notEqual(first,second);api=reload()
assert.equal(api.pendingKey('customer-1-inquiry',a),first);assert.equal(api.pendingKey('customer-1-inquiry',b),second)
api.completePending('customer-1-inquiry',a);assert.equal(api.pendingKey('customer-1-inquiry',b),second)
assert.notEqual(api.pendingKey('customer-1-inquiry',a),first);assert.notEqual(api.pendingKey('customer-2-inquiry',b),second)
console.log('Web pending submissions: reload, simultaneous intents, completion and account isolation passed')
