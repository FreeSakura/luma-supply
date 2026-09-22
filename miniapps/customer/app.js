const config = require('./config')
App({
  globalData: { baseUrl: config.baseUrl, role: config.role, token: '', user: null, lang: 'zh' },
  onLaunch() { this.globalData.token = wx.getStorageSync('luma-token-' + config.role) || ''; this.globalData.lang = wx.getStorageSync('luma-lang') || 'zh' },
  request(path, data, method) {
    return new Promise((resolve, reject) => wx.request({url: this.globalData.baseUrl + '/api' + path, data, method: method || (data === undefined ? 'GET' : 'POST'), header: {Authorization: 'Bearer ' + this.globalData.token}, success: r => {
      if (r.statusCode >= 200 && r.statusCode < 300) resolve(r.data)
      else {const message= typeof r.data.detail === 'string' ? r.data.detail : '请检查填写内容 / Check input'; wx.showToast({title:message, icon:'none'}); reject(new Error(message))}
    },fail: e => {wx.showToast({title:'连接失败 / Connection failed',icon:'none'}); reject(e)}}))
  },
  upload(purpose) { return new Promise((resolve,reject)=>wx.chooseMedia({count:1,mediaType:purpose==='review'||purpose==='ticket'?['image','video']:['image'],success:chosen=>{
    wx.uploadFile({url:this.globalData.baseUrl+'/api/media',filePath:chosen.tempFiles[0].tempFilePath,name:'file',formData:{purpose},header:{Authorization:'Bearer '+this.globalData.token},success:r=>{let data=JSON.parse(r.data);if(r.statusCode===201)resolve(data);else{wx.showToast({title:data.detail||'上传失败',icon:'none'});reject(data)}},fail:reject})
  },fail:reject})) },
  picture(id) { return this.globalData.baseUrl + '/api/public-media/' + encodeURIComponent(id) },
  money(v) { return '¥' + ((v||0)/100).toFixed(2) },
  setLogin(r) {this.globalData.token=r.token;this.globalData.user=r.user;wx.setStorageSync('luma-token-'+config.role,r.token)},
  requireLogin(){if(!this.globalData.token){wx.navigateTo({url:'/pages/login/index'});return false}return true}
})
