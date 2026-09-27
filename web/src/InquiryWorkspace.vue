<script setup lang="ts">
import { computed, ref } from 'vue'
import { api, money } from './api'
const props=defineProps<{items:any[],user:any,lang:string}>()
const emit=defineEmits(['changed','create-order','open-order'])
const t=(zh:string,en:string)=>props.lang==='zh'?zh:en
const filter=ref(''), detail=ref<any>(null), message=ref(''), closing=ref(''), reason=ref(''), error=ref(''), busy=ref(false)
const staff=computed(()=>['admin','staff'].includes(props.user.role))
const names:Record<string,string>={open:'待处理',ordered:'已转订单',withdrawn:'已撤回',closed:'已关闭'}
const actions:Record<string,string>={submitted:'提交询价',customer_message:'客户补充',service_reply:'客服回复',withdrawn:'客户撤回',closed:'客服关闭',ordered:'转为订单'}
const rows=computed(()=>props.items.filter(item=>!filter.value||item.status===filter.value))
const status=(value:string)=>props.lang==='zh'?names[value]||value:value
async function run(fn:()=>Promise<any>){busy.value=true;error.value='';try{await fn()}catch(e:any){error.value=e.message}finally{busy.value=false}}
async function open(item:any){await run(async()=>{detail.value=await api('/inquiries/'+item.id);message.value='';reason.value='';closing.value=''})}
async function reply(){await run(async()=>{detail.value=await api('/inquiries/'+detail.value.id+'/messages',{message:message.value});message.value='';emit('changed')})}
async function finish(){await run(async()=>{detail.value=await api('/inquiries/'+detail.value.id+'/'+closing.value,{message:reason.value});closing.value='';reason.value='';emit('changed')})}
function convert(item:any){detail.value=null;emit('create-order',item)}
function viewOrder(){const id=detail.value.order_id;detail.value=null;emit('open-order',{id})}
</script>

<template>
  <section class="inquiry-workspace">
    <div class="inquiry-toolbar"><label>{{t('询价状态','Inquiry status')}}<select v-model="filter" aria-label="询价状态筛选"><option value="">{{t('全部状态','All statuses')}}</option><option v-for="s in ['open','ordered','withdrawn','closed']" :value="s">{{status(s)}}</option></select></label><span>{{rows.length}} {{t('条询价','inquiries')}}</span></div>
    <div v-if="error&&!detail" class="error">{{error}}</div>
    <section class="panel" v-if="rows.length"><article v-for="item in rows" :key="item.id" class="inquiry-row">
      <div class="inquiry-copy"><span class="eyebrow">INQUIRY #{{item.id}}</span><h3>{{item.requirements?.project_name||t('房间清单询价','Room list inquiry')}}</h3>
        <div v-if="item.estimate" class="inquiry-facts"><b>{{t('商品参考合计','Goods estimate')}} {{money(item.estimate.goods_amount)}}</b><span v-if="item.requirements.budget">{{t('客户预算','Buyer budget')}} {{money(item.requirements.budget)}}</span><span v-if="item.requirements.needed_by">{{t('期望到货','Requested arrival')}} {{item.requirements.needed_by}}</span><span>{{item.requirements.destination}}</span><span>{{item.requirements.allow_alternatives?t('可协商替代款','Alternatives welcome'):t('替代款须另行沟通','Discuss substitutions first')}}</span></div>
        <p>{{item.message||t('查看明细与处理记录，继续沟通这次选购需求。','View items and updates to continue the conversation.')}}</p>
        <small>{{item.items.map((i:any)=>(i.snapshot?.product_name||'SKU '+i.sku_id)+' · '+(i.snapshot?.code||i.sku_id)+' × '+i.quantity+' / '+(i.room||'')).join(' · ')}}</small>
      </div><span class="badge">{{status(item.status)}}</span><div class="inquiry-buttons"><button class="secondary" @click="open(item)" :disabled="busy">{{t('查看与沟通','View and discuss')}}</button><button v-if="staff&&item.status==='open'" class="primary" @click="convert(item)">{{t('转为销售订单','Create order')}}</button></div>
    </article></section>
    <div v-else class="empty"><p>{{t('没有符合此状态的询价','No inquiries match this status')}}</p></div>

    <div v-if="detail" class="overlay" @click.self="detail=null"><section class="dialog wide inquiry-dialog"><button class="close" @click="detail=null" :aria-label="t('关闭询价详情','Close inquiry details')">×</button><span class="eyebrow">INQUIRY #{{detail.id}}</span><h2>{{detail.requirements?.project_name||t('询价详情与处理记录','Inquiry details and updates')}}</h2><span class="badge">{{status(detail.status)}}</span><div v-if="error" class="error">{{error}}</div>
      <div class="inquiry-facts" v-if="detail.estimate"><b>{{t('提交时商品参考金额','Goods estimate at submission')}} {{money(detail.estimate.goods_amount)}}</b><span v-if="detail.requirements.budget">{{t('客户预算','Budget')}} {{money(detail.requirements.budget)}}</span><span v-if="detail.requirements.needed_by">{{t('期望到货','Requested arrival')}} {{detail.requirements.needed_by}}</span><span>{{detail.requirements.destination}}</span></div>
      <p v-if="detail.message" class="notice">{{detail.message}}</p>
      <div class="inquiry-items"><div v-for="(item,index) in detail.items" :key="index"><b>{{item.snapshot?.product_name||'SKU '+item.sku_id}}</b><small>{{item.snapshot?.code||item.sku_id}} · {{item.snapshot?.specification}} · {{item.room}} × {{item.quantity}}</small><span v-if="item.line_amount!==undefined">{{money(item.line_amount)}}</span><p v-if="item.note">{{item.note}}</p></div></div>
      <h3>{{t('沟通与处理记录','Conversation and activity')}}</h3>
      <ol class="inquiry-timeline" v-if="detail.history.length"><li v-for="event in detail.history" :key="event.id"><div><b>{{event.actor_name}}</b><span>{{lang==='zh'?actions[event.action]||event.action:event.action}}</span><time>{{event.created_at.replace('T',' ').slice(0,19)}} UTC</time></div><p>{{event.message||t('已提交需求快照','Requirement snapshot submitted')}}</p></li></ol><p v-else class="muted">{{t('旧询价尚无处理记录；原始需求仍保留。','No recorded activity for this legacy inquiry; its original request is retained.')}}</p>
      <template v-if="detail.status==='open'">
        <form @submit.prevent="reply"><label>{{staff?t('回复客户','Reply to customer'):t('补充需求或问题','Add requirements or a question')}}<textarea v-model="message" maxlength="2000" required></textarea></label><button class="primary" :disabled="busy||!message.trim()">{{t('发送信息','Send message')}}</button></form>
        <div class="inquiry-footer"><button v-if="staff" class="secondary" @click="convert(detail)" :disabled="busy">{{t('转为销售订单','Create order')}}</button><button @click="closing=staff?'close':'withdraw'" :disabled="busy">{{staff?t('关闭本次询价','Close this inquiry'):t('撤回本次询价','Withdraw this inquiry')}}</button></div>
        <form v-if="closing" class="inquiry-close-form" @submit.prevent="finish"><p>{{t('此操作结束本次询价，原始需求与沟通记录会保留。需要调整选品时，可回到清单重新发起。','This ends the inquiry while preserving its request and history. Start a new inquiry from your list if you change selections.')}}</p><label>{{t('处理原因','Reason')}}<textarea v-model="reason" maxlength="2000" required></textarea></label><div class="inquiry-footer"><button class="primary" :disabled="busy||!reason.trim()">{{closing==='withdraw'?t('确认撤回','Confirm withdrawal'):t('确认关闭','Confirm closure')}}</button><button type="button" @click="closing=''">{{t('继续沟通','Keep discussing')}}</button></div></form>
      </template>
      <div v-else class="notice">{{detail.status==='ordered'?t('已转为订单，请在订单中继续处理履约。','Converted to an order. Continue fulfillment from the order.'):t('本次询价已结束。可以调整清单后重新询价。','This inquiry has ended. Update your list to request a new quote.')}}<button v-if="detail.order_id" @click="viewOrder">{{t('查看关联订单','View linked order')}}</button></div>
    </section></div>
  </section>
</template>

<style scoped>
.inquiry-toolbar{display:flex;align-items:center;gap:22px;margin-bottom:20px}.inquiry-toolbar label{display:flex;align-items:center;gap:12px;margin:0;white-space:nowrap}.inquiry-toolbar select{width:160px;margin:0}.inquiry-toolbar>span{font-size:12px;color:#839078}.inquiry-row{display:flex;align-items:center;gap:20px;padding:24px 0;border-bottom:1px solid #e7ecdf}.inquiry-row:last-child{border:0}.inquiry-copy{flex:1;min-width:0}.inquiry-copy p{margin:10px 0 6px}.inquiry-buttons{display:flex;gap:10px;flex-wrap:wrap}.inquiry-items{display:grid;gap:12px;margin:24px 0}.inquiry-items>div{padding:12px 0;border-bottom:1px solid #e5ebdd;font-size:12px}.inquiry-items small{display:block;margin-top:5px}.inquiry-items p{font-size:12px;margin:6px 0}.inquiry-timeline{padding:0;list-style:none;margin:20px 0 26px}.inquiry-timeline li{padding:14px 18px;margin-bottom:12px;background:#f5f7f0;border-left:3px solid #afbf9f;border-radius:0 7px 7px 0}.inquiry-timeline li>div{display:flex;gap:14px;align-items:center;flex-wrap:wrap;font-size:11px}.inquiry-timeline time{color:#8b9780;margin-left:auto;font-size:10px}.inquiry-timeline p{font-size:13px;color:#4e6144;white-space:pre-wrap;overflow-wrap:anywhere;margin:10px 0 0}.inquiry-footer{display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin:20px 0}.inquiry-close-form{border-top:1px solid #dce5d1;padding-top:16px}.inquiry-close-form p{font-size:12px}
@media(max-width:750px){.inquiry-row{flex-wrap:wrap;gap:14px}.inquiry-copy{flex-basis:100%}.inquiry-buttons{flex:1}.inquiry-toolbar{flex-wrap:wrap;gap:10px}.inquiry-toolbar select{width:145px}.inquiry-timeline li{padding:12px}.inquiry-timeline time{margin-left:0}}
</style>
