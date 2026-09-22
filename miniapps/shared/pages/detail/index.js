const app=()=>getApp()
Page({
 data:{product:null,sku:null,index:0,role:'customer',lang:'zh',support:[],reviews:[],quote:false,form:{price:'',available_quantity:'',lead_days:3,freight:0,min_quantity:1},room:'客厅',comparison:[],compareOpen:false},
 async onLoad(options){this.id=Number(options.id);this.requestedSku=Number(options.sku)||null;this.setData({role:app().globalData.role,lang:app().globalData.lang});await this.load()},
 async load(){const p=await app().request('/catalog/products/'+this.id+(this.requestedSku?'?sku='+this.requestedSku:''));const index=p.skus.findIndex(s=>s.id===p.selected_sku_id);p.skus=p.skus.map(s=>({...s,label:s.code+' '+s.specification,priceText:app().money(s.price),picture:app().picture(s.images[0]),attributeList:Object.keys(s.attributes).map(k=>({key:k,value:s.attributes[k]}))}));const settings=await app().request('/settings');this.setData({product:p,index,sku:p.skus[index],support:(settings.support||[]).map(x=>({...x,picture:app().picture(x.image)}))});await this.reviews()},
 async reviews(){const rows=await app().request('/reviews?sku_id='+this.data.sku.id);this.setData({reviews:rows})},
 select(e){const index=Number(e.detail.value);this.setData({index,sku:this.data.product.skus[index]});this.reviews()},
 input(e){this.setData({[e.currentTarget.dataset.key]:e.detail.value})},
 preview(){wx.previewImage({current:this.data.sku.picture,urls:this.data.sku.images.map(app().picture.bind(app()))})},
 support(e){wx.previewImage({urls:[e.currentTarget.dataset.url]})},
 async wish(){if(!app().requireLogin())return;await app().request('/wishlist',{sku_id:this.data.sku.id,room:this.data.room,quantity:1,watch_price:true});wx.showToast({title:'已加入 / Added'})},
 quote(){if(app().requireLogin())this.setData({quote:true})},
 close(){this.setData({quote:false,compareOpen:false})},
 async submitQuote(){const f=this.data.form;await app().request('/quotes',{sku_id:this.data.sku.id,price:Math.round(Number(f.price)*100),available_quantity:f.available_quantity===''?null:Number(f.available_quantity),lead_days:Number(f.lead_days),freight:Math.round(Number(f.freight)*100),min_quantity:Number(f.min_quantity),valid_until:new Date(Date.now()+30*86400000).toISOString()});this.setData({quote:false});wx.showToast({title:'已提交审核'})},
 compare(){let items=wx.getStorageSync('luma-compare')||[];const sku={...this.data.sku,product_name:this.data.product.name};if(!items.some(x=>x.id===sku.id))items.push(sku);if(items.length>4){wx.showToast({title:'最多四款 / Max 4',icon:'none'});return}wx.setStorageSync('luma-compare',items);this.setData({comparison:items,compareOpen:true})},
 clearCompare(){wx.removeStorageSync('luma-compare');this.setData({comparison:[],compareOpen:false})},
 onShareAppMessage(){return {title:this.data.product.name+' '+this.data.sku.code,path:'/pages/detail/index?id='+this.id+'&sku='+this.data.sku.id}}
})
