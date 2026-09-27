<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { api, money, mediaUrl } from './api'
const props = defineProps<{items:any[],lang:string}>()
const emit = defineEmits(['changed','submitted'])
const t=(zh:string,en:string)=>props.lang==='zh'?zh:en
const selected=ref<number[]>([]), open=ref(false), busy=ref(false), error=ref(''), preview=ref<any>(null)
const form=reactive({project_name:'',budget:'',needed_by:'',destination:'',allow_alternatives:false,message:''})
let initialized=false
watch(()=>props.items,items=>{if(!items.length)return;if(!initialized){selected.value=items.map(x=>x.id);initialized=true}else selected.value=selected.value.filter(id=>items.some(x=>x.id===id))},{immediate:true})
watch(form,()=>preview.value=null)
watch(selected,()=>preview.value=null,{deep:true})
watch(()=>props.items,()=>preview.value=null)
const rooms=computed(()=>[...new Set(props.items.map(x=>x.room))].map(room=>({room,items:props.items.filter(x=>x.room===room)})))
const chosen=computed(()=>props.items.filter(x=>selected.value.includes(x.id)))
const amount=computed(()=>chosen.value.reduce((sum,x)=>sum+x.sku.price*x.quantity,0))
const quantity=computed(()=>chosen.value.reduce((sum,x)=>sum+x.quantity,0))
function selectRoom(room:string){selected.value=props.items.filter(x=>x.room===room).map(x=>x.id)}
function payload(){return {wishlist_ids:chosen.value.map(x=>x.id),message:form.message,requirements:{project_name:form.project_name,budget:form.budget===''?null:Math.round(Number(form.budget)*100),needed_by:form.needed_by||null,destination:form.destination,allow_alternatives:form.allow_alternatives}}}
async function run(fn:()=>Promise<any>){busy.value=true;error.value='';try{await fn()}catch(e:any){error.value=e.message}finally{busy.value=false}}
async function save(item:any){await run(async()=>{await api('/wishlist',{...item});emit('changed')})}
async function remove(id:number){await run(async()=>{await api('/wishlist/'+id,undefined,'DELETE');emit('changed')})}
function begin(){preview.value=null;error.value='';open.value=true}
async function prepare(){await run(async()=>{preview.value=await api('/inquiries/preview',payload())})}
async function submit(){await run(async()=>{await api('/inquiries',payload());open.value=false;emit('submitted')})}
</script>

<template>
  <section class="room-planner">
    <div v-if="error&&!open" class="error">{{error}}</div>
    <div class="planner-summary panel">
      <div><span class="eyebrow">{{t('按房间规划采购','PLAN BY ROOM')}}</span><h2>{{t('先选好这一批，再交给客服报价','Choose a batch for your quote')}}</h2><p>{{t('勾选需要询价的规格。参考金额不含运费和安装，最终价格由客服确认。','Select variants to request. Estimates exclude delivery and installation; service confirms the final price.')}}</p></div>
      <div class="planner-total"><strong>{{money(amount)}}</strong><span>{{chosen.length}} {{t('项','lines')}} · {{quantity}} {{t('件','units')}}</span></div>
      <button class="primary" :disabled="!chosen.length||busy" @click="begin">{{t('清单一键询价','Request a quote')}}</button>
    </div>
    <div class="planner-selection"><button @click="selected=items.map(x=>x.id)">{{t('全选','Select all')}}</button><button @click="selected=[]">{{t('取消全选','Clear selection')}}</button></div>
    <section class="panel" v-for="group in rooms" :key="group.room">
      <div class="section-heading"><div><h2>{{group.room}}</h2><small>{{t('已选参考金额','Selected estimate')}} {{money(group.items.filter(x=>selected.includes(x.id)).reduce((sum,x)=>sum+x.sku.price*x.quantity,0))}}</small></div><button class="secondary" @click="selectRoom(group.room)">{{t('只选这个房间','Select only this room')}}</button></div>
      <div class="planner-line" v-for="item in group.items" :key="item.id">
        <input type="checkbox" v-model="selected" :value="item.id" :aria-label="t('选择 ','Select ')+item.sku.code"/>
        <img v-if="item.sku.images[0]" :src="mediaUrl(item.sku.images[0])" :alt="item.product_name"/>
        <div class="planner-product"><b>{{item.product_name}}</b><small>{{item.sku.code}} · {{item.sku.specification}}</small><small>{{item.sku.size_mm||t('尺寸待补充','Size not provided')}} · {{item.sku.attributes.cct_k?item.sku.attributes.cct_k+' K':t('色温待补充','CCT not provided')}}</small><input v-model="item.note" @change="save(item)" :aria-label="t('备注 ','Notes ')+item.sku.code" :placeholder="t('安装位置、偏好或特殊要求','Position, preferences or special requirements')" maxlength="300"/></div>
        <label class="compact">{{t('数量','Qty')}}<input v-model="item.quantity" @change="save(item)" type="number" min="1" max="100000" :aria-label="t('数量 ','Quantity ')+item.sku.code"/></label>
        <strong>{{money(item.sku.price*item.quantity)}}</strong><button @click="remove(item.id)" :aria-label="t('移除 ','Remove ')+item.sku.code">×</button>
      </div>
    </section>
    <div v-if="open" class="overlay" @click.self="open=false"><section class="dialog wide inquiry-composer"><button class="close" @click="open=false" :aria-label="t('关闭询价','Close inquiry')">×</button><h2>{{t('把采购需求说清楚','Prepare your quote request')}}</h2><p>{{t('只提交当前勾选项。预算和到货日期是您的期望，供货与运费由客服另行确认。','Only selected items are sent. Budget and date are requests; supply and freight need confirmation.')}}</p><div v-if="error" class="error">{{error}}</div>
      <form @submit.prevent="prepare"><div class="form-grid"><label>{{t('项目名称','Project name')}}<input v-model="form.project_name" maxlength="100"/></label><label>{{t('商品预算 元（可选）','Goods budget CNY (optional)')}}<input v-model="form.budget" type="number" min="0.01" step="0.01"/></label><label>{{t('期望到货日期','Requested arrival date')}}<input v-model="form.needed_by" type="date"/></label><label>{{t('配送城市或区域','Delivery city or area')}}<input v-model="form.destination" maxlength="150"/></label></div><label class="check"><input type="checkbox" v-model="form.allow_alternatives"/>{{t('可以向我推荐替代款，须经我确认','Suggest alternatives, subject to my approval')}}</label><label>{{t('补充说明','Additional requirements')}}<textarea v-model="form.message" maxlength="3000"></textarea></label><button class="secondary" :disabled="busy||!chosen.length">{{t('预览询价清单','Preview quote request')}}</button></form>
      <div v-if="preview" class="inquiry-preview"><div class="plan-summary"><span>{{t('商品参考合计','Estimated goods total')}}<b>{{money(preview.estimate.goods_amount)}}</b></span><span>{{t('数量','Quantity')}}<b>{{preview.estimate.quantity}}</b></span><span v-if="preview.estimate.budget!==null">{{t('商品预算','Goods budget')}}<b>{{money(preview.estimate.budget)}}</b></span></div><p v-if="preview.estimate.over_budget" class="notice">{{t('参考金额超出预算 ','Estimate exceeds budget by ')}}{{money(preview.estimate.budget_gap)}}{{t('，仍可发送给客服协商。','; you may still request a quote.')}}</p><div v-for="room in preview.estimate.rooms" class="list-item"><b>{{room.room}}</b><span>{{room.quantity}} {{t('件','units')}} · {{money(room.amount)}}</span></div><p v-for="issue in preview.estimate.issues" :class="issue.blocking?'error':'muted'">{{issue.message}}</p><p class="muted">{{t('提交时重新读取参考价格并保存快照；此询价不是订单。','Current prices are captured on submission. This request is not an order.')}}</p><button class="primary full" :disabled="busy||!preview.can_submit" @click="submit">{{t('确认发送询价','Send quote request')}}</button></div>
    </section></div>
  </section>
</template>

<style scoped>
.planner-summary{display:flex;gap:28px;align-items:center}.planner-summary>div:first-child{flex:1}.planner-summary h2{font-size:20px}.planner-summary p{font-size:12px;margin:10px 0 0}.planner-total{display:flex;flex-direction:column;gap:8px;white-space:nowrap}.planner-total strong{font-size:27px;font-weight:500}.planner-total span{font-size:11px;color:#849477}.planner-selection{display:flex;gap:20px;margin:18px 0;font-size:12px}.planner-line{display:flex;align-items:center;gap:18px;border-top:1px solid #e5eadf;padding:22px 0}.planner-line>img{width:78px;height:78px;object-fit:cover;border-radius:7px}.planner-product{flex:1;min-width:130px}.planner-product b,.planner-product small{display:block}.planner-product input{font-size:11px;margin-top:8px;padding:8px}.planner-line>strong{font-size:14px;white-space:nowrap}.planner-line label{font-size:11px}.planner-line label input{width:75px}.inquiry-preview{border-top:1px solid #dfe7d5;margin-top:22px}.inquiry-preview .list-item{justify-content:space-between;font-size:12px;padding:12px 0}
@media(max-width:850px){.planner-summary{flex-wrap:wrap;gap:20px}.planner-summary>div:first-child{flex-basis:100%}.planner-total{flex:1}.planner-line{flex-wrap:wrap;gap:12px}.planner-product{flex:1}.planner-line>strong{margin-left:auto}}
</style>
