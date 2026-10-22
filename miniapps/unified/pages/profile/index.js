const app=()=>getApp()
const profileStates={pending:'待审核',approved:'已通过',rejected:'已驳回',disabled:'已停用'}
const permissionNames={users:'客户与权限',merchants:'商家认证',catalog:'商品与规格',quotes:'报价审核',orders:'销售订单',procurement:'采购协同',operations:'运营设置',reports:'工作报表'}
Page({
 data:{role:'customer',admin:false,demo:true,lang:'zh',profile:{},permissionText:'',permissionList:[],addresses:[],notifications:[],form:{},modal:'',unread:0},
 async onShow(){if(app().globalData.token){try{await app().ensureUser()}catch(_){return}}app().syncTabs();const role=app().globalData.role;this.setData({role,admin:role==='admin'||role==='staff',demo:app().globalData.demo,lang:app().globalData.lang});if(app().requireLogin())await this.load()},
 async load(){const profile=await app().request(this.data.role==='merchant'?'/merchant/profile':'/me');const notifications=await app().request('/notifications');this.setData({profile:{...profile,statusText:profileStates[profile.status]||profile.status},permissionText:(profile.permissions||[]).map(x=>permissionNames[x]||x).join(' · '),permissionList:profile.role==='admin'?Object.values(permissionNames):(profile.permissions||[]).map(x=>permissionNames[x]||x),notifications,unread:notifications.filter(n=>!n.read).length,addresses:this.data.role==='customer'?await app().request('/addresses'):[]})},
 shortcut(e){app().globalData.nextWork={tab:e.currentTarget.dataset.tab};wx.switchTab({url:'/pages/work/index'})},
 input(e){this.setData({[e.currentTarget.dataset.key]:e.detail.value})},
 async license(){const r=await app().upload('license');this.setData({'profile.license_media_id':r.id})},
 async save(){const p=this.data.profile;if(this.data.role==='merchant'){await app().request('/merchant/profile',{shop_name:p.shop_name,legal_name:p.legal_name,phone:p.phone,address:p.address,license_media_id:p.license_media_id},'PUT')}else{await app().request('/me',{username:p.username,name:p.name},'PATCH')}wx.showToast({title:'已保存'});await this.load()},
 newAddress(){this.setData({modal:'address',form:{}})},
 async saveAddress(){await app().request('/addresses',this.data.form);this.setData({modal:''});await this.load()},
 async deleteAddress(e){await app().request('/addresses/'+e.currentTarget.dataset.id,undefined,'DELETE');await this.load()},
 async markRead(e){await app().request('/notifications/'+e.currentTarget.dataset.id+'/read',{});await this.load()},
 password(){this.setData({modal:'password',form:{}})},
 async bindWechat(){if(this._binding)return;this._binding=true;try{const code=await app().wechatCode();await app().request('/auth/wechat/bind',{code,role:this.data.role});wx.showToast({title:'微信绑定成功',icon:'success'})}catch{}finally{this._binding=false}},
 openNotification(e){const link=e.currentTarget.dataset.link;if(['orders','inquiries','tickets','quotes','catalog'].includes(link)){if(this.data.admin)wx.navigateTo({url:'/pages/admin/index?module='+link});else{app().globalData.nextWork={tab:link};wx.switchTab({url:'/pages/work/index'})}}},
 async changePassword(){await app().request('/auth/password',this.data.form);this.setData({modal:''});await this.logout()},
 async logout(){try{await app().request('/auth/logout',{})}finally{app().clearLogin();wx.navigateTo({url:'/pages/login/index'})}},
 close(){this.setData({modal:''})}
})
