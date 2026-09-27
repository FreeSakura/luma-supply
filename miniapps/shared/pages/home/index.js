const app = () => getApp()
Page({
 data: {products:[], categories:['全部 / All'], categoryIndex:0, text:'', image:null, budget:'', available:false, lang:'zh', role:'customer', notice:'', banners:[], cropping:false, crop:{x:0,y:0,w:1,h:1}, loading:false, total:0, nextOffset:0, hasMore:false, searchMode:false,cctIndex:0,cctOptions:['不限 / Any'],cctValues:[null],supplierStats:{total:0,pending:0,rejected:0,expired:0},signedIn:false},
 async onShow() {
  app().syncTabs();this.setData({lang:app().globalData.lang, role:app().globalData.role,signedIn:!!app().globalData.token});if(this.data.role==='merchant'&&this.data.signedIn)await this.refreshSupplier()
  if (this._initialized && this._token === app().globalData.token) return
  this._token = app().globalData.token
  try {
   const [cats, settings, lighting] = await Promise.all([app().request('/catalog/categories'), app().request('/settings'),app().request('/catalog/lighting-options')])
   this.setData({cctIndex:0,cctOptions:['不限 / Any',...lighting.cct_k.map(k=>k+' K')],cctValues:[null,...lighting.cct_k],categories:['全部 / All', ...cats], categoryIndex:0, banners:(settings[app().globalData.role+'_banners']||[]).map(x=>({...x,picture:app().picture(x.image)}))})
   await this.load(); this._initialized = true
  } catch (_) { /* request() displays the actual error. */ }
 },
 async refreshSupplier(){try{const rows=await app().request('/quotes');this.setData({supplierStats:{total:rows.filter(q=>!q.deleted).length,pending:rows.filter(q=>app().quoteState(q)==='pending').length,rejected:rows.filter(q=>app().quoteState(q)==='rejected').length,expired:rows.filter(q=>app().quoteState(q)==='expired').length}})}catch(_){}},
 shortcut(e){if(!app().requireLogin())return;app().globalData.nextWork={tab:e.currentTarget.dataset.tab,status:e.currentTarget.dataset.status||''};wx.switchTab({url:'/pages/work/index'})},
 offer(e){wx.navigateTo({url:'/pages/detail/index?id='+e.currentTarget.dataset.id+'&sku='+e.currentTarget.dataset.sku+'&quote=1'})},
 decorate(rows) {return rows.map(p=>{const s=p.skus.find(s=>s.id===p.selected_sku_id)||p.skus[0];return {...p,picture:s.images.length?app().picture(s.images[0]):'',priceText:app().money(p.min_price),skuCode:s.code}})},
 async load(append=false) {
  if (append && (this.data.loading || !this.data.hasMore || this.data.searchMode)) return
  const request = this._generation = (this._generation||0) + 1
  const category = this.data.categoryIndex ? this.data.categories[this.data.categoryIndex] : ''
  const offset = append ? this.data.nextOffset : 0
  this.setData({loading:true,searchMode:false,notice:'', ...(append?{}:{products:[],total:0,hasMore:false})})
  try {
   const result = await app().request('/catalog/page?limit=24&offset='+offset+'&category='+encodeURIComponent(category)+(this.data.cctIndex?'&cct_k='+this.data.cctValues[this.data.cctIndex]:''))
   if (request !== this._generation) return
   const items = append ? [...this.data.products, ...this.decorate(result.items)] : this.decorate(result.items)
   this.setData({products:[...new Map(items.map(p=>[p.id,p])).values()],total:result.total,nextOffset:result.next_offset,hasMore:result.has_more})
  } catch (_) { /* Keep the last successful page available for a retry. */ }
  finally {if(request===this._generation)this.setData({loading:false})}
 },
 loadMore() {this.load(true)},
 onReachBottom() {this.load(true)},
 async onPullDownRefresh() {try{await this.load()}finally{wx.stopPullDownRefresh()}},
 input(e) {this.setData({[e.currentTarget.dataset.key]:e.detail.value})},
 category(e) {this.setData({categoryIndex:Number(e.detail.value)}); if(this.data.searchMode)this.search();else this.load()},
 cct(e) {this.setData({cctIndex:Number(e.detail.value)});if(this.data.searchMode)this.search();else this.load()},
 available(e) {this.setData({available:e.detail.value})},
 cropping(e) {this.setData({cropping:e.detail.value})},
 async upload() {if(!app().requireLogin())return;try{this.setData({image:await app().upload('query')})}catch(_){}},
 async search() {
  if(!app().requireLogin())return
  const d=this.data
  if(!d.text&&!d.image){await this.load();return}
  const request=this._generation=(this._generation||0)+1
  this.setData({loading:true})
  try {
   const r=await app().request('/search',{image_id:d.image?.id||null,text:d.text,category:d.categoryIndex?d.categories[d.categoryIndex]:'',max_price:d.budget?Math.round(Number(d.budget)*100):null,available_only:d.available,attributes:d.cctIndex?{cct_k:d.cctValues[d.cctIndex]}:{},crop:d.cropping?[Number(d.crop.x),Number(d.crop.y),Number(d.crop.w),Number(d.crop.h)]:null})
   if(request!==this._generation)return
   this.setData({products:this.decorate(r.products),notice:r.notice,queryId:r.query_id,searchMode:true,hasMore:false,total:r.products.length})
  } catch (_) { /* request() displays the actual error. */ }
  finally {if(request===this._generation)this.setData({loading:false})}
 },
 clear() {this.setData({image:null,text:'',notice:'',categoryIndex:0,cctIndex:0,budget:''});this.load()},
 detail(e) {wx.navigateTo({url:'/pages/detail/index?id='+e.currentTarget.dataset.id+'&sku='+e.currentTarget.dataset.sku})},
 banner(e) {const link=e.currentTarget.dataset.link;if(link&&link.startsWith('/product/'))wx.navigateTo({url:'/pages/detail/index?id='+link.split('/').pop()})},
 async feedback() {await app().request('/search/'+this.data.queryId+'/feedback',{issue:'结果不符合需求'});wx.showToast({title:'已记录 / Saved'})}
})
