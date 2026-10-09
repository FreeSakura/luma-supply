<script setup lang="ts">
import {ref,onMounted,onUnmounted} from 'vue'
import {api} from './api'
const emit=defineEmits(['verified'])
const visible=ref(false),password=ref(''),otp=ref(''),busy=ref(false),error=ref('')
function show(){visible.value=true;password.value='';otp.value='';error.value=''}
async function submit(){busy.value=true;error.value='';try{await api('/auth/reauth',{password:password.value,otp:otp.value});visible.value=false;password.value='';otp.value='';emit('verified')}catch(e:any){error.value=e.message}finally{busy.value=false}}
onMounted(()=>window.addEventListener('luma-reauth-needed',show))
onUnmounted(()=>window.removeEventListener('luma-reauth-needed',show))
</script>
<template><div v-if="visible" class="overlay fresh-auth" role="dialog" aria-modal="true" aria-labelledby="fresh-title"><form class="dialog" @submit.prevent="submit"><button type="button" class="close" aria-label="关闭身份验证" :disabled="busy" @click="visible=false">×</button><h2 id="fresh-title">验证身份</h2><p>请输入当前密码。验证后可继续刚才的操作，原表单会保留。</p><p v-if="error" class="error" role="alert">{{error}}</p><label>当前密码<input v-model="password" type="password" autocomplete="current-password" required autofocus/></label><label>动态验证码<input v-model="otp" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="已配置验证器的管理账户填写"/></label><button class="primary" :disabled="busy">{{busy?'正在验证':'确认验证'}}</button><button type="button" :disabled="busy" @click="visible=false">取消</button></form></div></template>
<style scoped>.fresh-auth{z-index:3000}.fresh-auth p{line-height:1.7}</style>
