const app=()=>getApp()
Page({
 data:{products:[],categories:['全部 / All'],categoryIndex:0,text:'',image:null,budget:'',available:false,lang:'zh',role:'customer',notice:'',banners:[],cropping:false,crop:{x:0,y:0,w:1,h:1}},
 async onShow(){this.setData({lang:app().globalData.lang,role:app().globalData.role});await this.load()},
 decorate(rows){return rows.map(p=>{const s=p.skus.find(s=>s.id===p.selected_sku_id)||p.skus[0];return {...p,picture:app().picture(s.images[0]),priceText:app().money(p.min_price),skuCode:s.code}})},
 async load(){const [rows,cats,settings]=await Promise.all([app().request('/catalog/products'),app().request('/catalog/categories'),app().request('/settings')]);this.setData({products:this.decorate(rows),categories:['全部 / All',...cats],banners:(settings[app().globalData.role+'_banners']||[]).map(x=>({...x,picture:app().picture(x.image)}))})},
 input(e){const k=e.currentTarget.dataset.key;this.setData({[k]:e.detail.value})},
 category(e){this.setData({categoryIndex:Number(e.detail.value)})},
 available(e){this.setData({available:e.detail.value})},
 cropping(e){this.setData({cropping:e.detail.value})},
 async upload(){if(!app().requireLogin())return;const r=await app().upload('query');this.setData({image:r})},
 async search(){if(!app().requireLogin())return;const d=this.data;if(!d.text&&!d.image){await this.load();return}const r=await app().request('/search',{image_id:d.image?.id||null,text:d.text,category:d.categoryIndex?d.categories[d.categoryIndex]:'',max_price:d.budget?Math.round(Number(d.budget)*100):null,available_only:d.available,crop:d.cropping?[Number(d.crop.x),Number(d.crop.y),Number(d.crop.w),Number(d.crop.h)]:null});const products=await Promise.all(r.results.map(async hit=>{const p=await app().request('/catalog/products/'+hit.product_id+'?sku='+hit.sku_id);p.min_price=hit.price;return p}));this.setData({products:this.decorate(products),notice:r.notice,queryId:r.query_id})},
 clear(){this.setData({image:null,text:'',notice:'',categoryIndex:0,budget:''});this.load()},
 detail(e){wx.navigateTo({url:'/pages/detail/index?id='+e.currentTarget.dataset.id+'&sku='+e.currentTarget.dataset.sku})},
 banner(e){const link=e.currentTarget.dataset.link;if(link&&link.startsWith('/product/'))wx.navigateTo({url:'/pages/detail/index?id='+link.split('/').pop()})},
 async feedback(){await app().request('/search/'+this.data.queryId+'/feedback',{issue:'结果不符合需求'});wx.showToast({title:'已记录 / Saved'})}
})
