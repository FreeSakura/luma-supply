const app=()=>getApp()
Page({
 data:{role:'customer',lang:'zh',profile:{},addresses:[],notifications:[],form:{},modal:'',unread:0},
 async onShow(){this.setData({role:app().globalData.role,lang:app().globalData.lang});if(app().requireLogin())await this.load()},
 async load(){const profile=await app().request(this.data.role==='merchant'?'/merchant/profile':'/me');const notifications=await app().request('/notifications');this.setData({profile,notifications,unread:notifications.filter(n=>!n.read).length,addresses:this.data.role==='customer'?await app().request('/addresses'):[]})},
 input(e){this.setData({[e.currentTarget.dataset.key]:e.detail.value})},
 async license(){const r=await app().upload('license');this.setData({'profile.license_media_id':r.id})},
 async save(){const p=this.data.profile;if(this.data.role==='merchant'){await app().request('/merchant/profile',{shop_name:p.shop_name,legal_name:p.legal_name,phone:p.phone,address:p.address,license_media_id:p.license_media_id},'PUT')}else{await app().request('/me',{username:p.username,name:p.name},'PATCH')}wx.showToast({title:'已保存 / Saved'});await this.load()},
 newAddress(){this.setData({modal:'address',form:{}})},
 async saveAddress(){await app().request('/addresses',this.data.form);this.setData({modal:''});await this.load()},
 async deleteAddress(e){await app().request('/addresses/'+e.currentTarget.dataset.id,undefined,'DELETE');await this.load()},
 async markRead(e){await app().request('/notifications/'+e.currentTarget.dataset.id+'/read',{});await this.load()},
 language(){const lang=this.data.lang==='zh'?'en':'zh';app().globalData.lang=lang;wx.setStorageSync('luma-lang',lang);this.setData({lang})},
 password(){this.setData({modal:'password',form:{}})},
 async changePassword(){await app().request('/auth/password',this.data.form);this.setData({modal:''});await this.logout()},
 async logout(){try{await app().request('/auth/logout',{})}finally{app().globalData.token='';wx.removeStorageSync('luma-token-'+this.data.role);wx.navigateTo({url:'/pages/login/index'})}},
 close(){this.setData({modal:''})}
})
