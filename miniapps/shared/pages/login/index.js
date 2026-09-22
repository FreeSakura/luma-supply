const app=()=>getApp()
Page({
 data:{mode:'login',role:'customer',lang:'zh',form:{username:'',password:'',phone:'',code:'',agreement:false},devCode:'',busy:false},
 onLoad(){this.setData({role:app().globalData.role,lang:app().globalData.lang})},
 input(e){this.setData({['form.'+e.currentTarget.dataset.key]:e.detail.value})},
 agree(e){this.setData({'form.agreement':e.detail.value})},
 mode(e){this.setData({mode:e.currentTarget.dataset.mode})},
 async send(){const r=await app().request('/auth/code',{phone:this.data.form.phone});this.setData({devCode:r.development_code||''})},
 async submit(){if(this.data.busy)return;this.setData({busy:true});try{const data={...this.data.form,role:this.data.role};const mode=this.data.mode;if(mode==='reset'){await app().request('/auth/reset',data);this.setData({mode:'login'});return}const r=await app().request(mode==='register'?'/auth/register':'/auth/login',data);if(r.user.role!==this.data.role){wx.showToast({title:'请使用对应端的账号',icon:'none'});return}app().setLogin(r);wx.switchTab({url:'/pages/home/index'})}finally{this.setData({busy:false})}},
 async wechat(){wx.login({success:async r=>{try{const result=await app().request('/auth/wechat',{code:r.code});if(result.user.role!==this.data.role){wx.showToast({title:'微信快捷登录仅客户使用',icon:'none'});return}app().setLogin(result);wx.switchTab({url:'/pages/home/index'})}catch{}}})}
})
