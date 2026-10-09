const config = require('./config')
App({
  globalData: { baseUrl: config.baseUrl, role: config.role, token: '', user: null, lang: 'zh' },
  onLaunch() { this.globalData.token = wx.getStorageSync('luma-token-' + config.role) || ''; this.globalData.lang = wx.getStorageSync('luma-lang') || 'zh'; this.globalData.user=wx.getStorageSync('luma-user-'+config.role)||null },
  draftName(scope){return 'luma-'+config.role+'-'+this.globalData.user.id+'-'+scope},
  getDraft(scope){return wx.getStorageSync(this.draftName(scope))||null},
  saveDraft(scope,data){wx.setStorageSync(this.draftName(scope),data)},
  dropDraft(scope){wx.removeStorageSync(this.draftName(scope))},
  pendingKey(scope,payload){const signature=JSON.stringify(payload),stored=this.getDraft('pending-'+scope),entries=Array.isArray(stored)?stored:stored?[stored]:[];const old=entries.find(x=>x.signature===signature);if(old)return old.key;const key=this.submissionKey();entries.push({signature,key});this.saveDraft('pending-'+scope,entries);return key},
  completePending(scope,payload){const stored=this.getDraft('pending-'+scope),entries=(Array.isArray(stored)?stored:stored?[stored]:[]).filter(x=>x.signature!==JSON.stringify(payload));if(entries.length)this.saveDraft('pending-'+scope,entries);else this.dropDraft('pending-'+scope)},
  async ensureUser(){if(!this.globalData.user)this.globalData.user=await this.request('/me');return this.globalData.user},
  submissionKey(){return 'wx-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2)+'-'+Math.random().toString(36).slice(2)},
  clearLogin(){this.globalData.token='';this.globalData.user=null;wx.removeStorageSync('luma-token-'+config.role);wx.removeStorageSync('luma-user-'+config.role)},
  wechatCode(){return new Promise((resolve,reject)=>wx.login({success:r=>r.code?resolve(r.code):reject(new Error('微信未返回授权码')),fail:e=>{wx.showToast({title:'微信授权失败，请重试',icon:'none'});reject(e)}}))},
  request(path, data, method) {
    return new Promise((resolve, reject) => wx.request({url: this.globalData.baseUrl + '/api' + path, data, timeout:15000, method: method || (data === undefined ? 'GET' : 'POST'), header: {Authorization: 'Bearer ' + this.globalData.token}, success: r => {
      if (r.statusCode >= 200 && r.statusCode < 300) resolve(r.data)
      else {if(r.statusCode===401&&!path.startsWith('/auth/')){this.clearLogin();if(!this._loginRedirect){this._loginRedirect=true;wx.navigateTo({url:'/pages/login/index',fail:()=>{this._loginRedirect=false}})}}const message= r.data&&typeof r.data.detail === 'string' ? r.data.detail : '请检查填写内容 / Check input'; wx.showToast({title:message, icon:'none'}); const error=new Error(message);error.status=r.statusCode;reject(error)}
    },fail: e => {wx.showToast({title:'连接失败 / Connection failed',icon:'none'}); reject(e)}}))
  },
  upload(purpose) { return new Promise((resolve,reject)=>wx.chooseMedia({count:1,mediaType:purpose==='review'||purpose==='ticket'?['image','video']:['image'],success:chosen=>{
    wx.uploadFile({url:this.globalData.baseUrl+'/api/media',filePath:chosen.tempFiles[0].tempFilePath,name:'file',formData:{purpose},header:{Authorization:'Bearer '+this.globalData.token},success:r=>{let data;try{data=JSON.parse(r.data)}catch{data={detail:'上传响应异常，请重试'}}if(r.statusCode===201&&data.id)resolve(data);else{const error=new Error(data.detail||'上传失败');wx.showToast({title:error.message,icon:'none'});reject(error)}},fail:reject})
  },fail:reject})) },
  picture(id) { return this.globalData.baseUrl + '/api/public-media/' + encodeURIComponent(id) },
  money(v) { return '¥' + ((v||0)/100).toFixed(2) },
  setLogin(r) {this._loginRedirect=false;this.globalData.token=r.token;this.globalData.user=r.user;wx.setStorageSync('luma-token-'+config.role,r.token);wx.setStorageSync('luma-user-'+config.role,r.user)},
  syncTabs(){const merchant=this.globalData.role==='merchant',english=this.globalData.lang==='en';const labels=english?(merchant?['Sourcing','Offers','Profile']:['Discover','Workspace','Profile']):(merchant?['选品','供货工作台','商家资料']:['选灯','选购与订单','我的']);labels.forEach((text,index)=>wx.setTabBarItem({index,text}))},
  quoteState(q){if(q.deleted)return 'deleted';if(!q.active)return 'inactive';if(Date.parse(q.valid_until+(q.valid_until.endsWith('Z')?'':'Z'))<=Date.now())return 'expired';return q.status},
  requireLogin(){if(!this.globalData.token){wx.navigateTo({url:'/pages/login/index'});return false}return true}
})
