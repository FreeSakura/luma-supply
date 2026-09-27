<script setup lang="ts">
import { computed, ref } from 'vue'
import { Search, ArrowUpRight } from 'lucide-vue-next'
const props=defineProps<{items:any[],lang:string}>()
const emit=defineEmits(['navigate','close'])
const query=ref('')
const matches=computed(()=>props.items.filter(item=>(item.zh+' '+item.en).toLowerCase().includes(query.value.toLowerCase().trim())))
</script>
<template>
  <div class="overlay" @click.self="emit('close')"><section class="dialog quick-navigator" aria-label="快速跳转"><button class="close" @click="emit('close')" aria-label="关闭快速跳转">×</button><h2>{{lang==='zh'?'前往工作区':'Go to workspace'}}</h2><div class="navigator-search"><Search :size="20"/><input v-model="query" aria-label="搜索工作区" :placeholder="lang==='zh'?'输入页面名称，例如：报价、订单…':'Find quotes, orders, or another page…'" @keydown.enter="matches[0]&&emit('navigate',matches[0].id)"/></div><div class="navigator-results"><button v-for="item in matches" :key="item.id" @click="emit('navigate',item.id)"><component :is="item.icon" :size="19"/><span>{{lang==='zh'?item.zh:item.en}}</span><ArrowUpRight :size="16"/></button><p v-if="!matches.length">{{lang==='zh'?'没有匹配的工作区':'No matching workspace'}}</p></div><small>{{lang==='zh'?'Enter 打开首项 · Esc 关闭':'Enter opens the first match · Esc closes'}}</small></section></div>
</template>
