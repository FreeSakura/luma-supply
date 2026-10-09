export const mediaUrl = (id: string) => '/api/public-media/' + encodeURIComponent(id)
export const money = (v: number) => '¥' + ((v || 0) / 100).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
export async function api(path: string, data?: any, method?: string) {
  const token = localStorage.getItem('luma-token')
  const headers: any = token ? { Authorization: 'Bearer ' + token } : {}
  if (!(data instanceof FormData) && data !== undefined) headers['Content-Type'] = 'application/json'
  const controller = new AbortController(), timer = setTimeout(()=>controller.abort(),15000)
  let response:Response, result:any
  try {
    response = await fetch('/api' + path, { method: method || (data === undefined ? 'GET' : 'POST'), headers, body: data === undefined ? undefined : data instanceof FormData ? data : JSON.stringify(data),signal:controller.signal })
    const content=await response.text()
    try {result=JSON.parse(content)} catch {result={detail:'服务暂不可用，请稍后重试'}}
  } catch {throw new Error('连接中断或超时，请核对记录后重试原操作')} finally {clearTimeout(timer)}
  if (!response.ok) {
    if(response.status===401&&!path.startsWith('/auth/')){localStorage.removeItem('luma-token');window.dispatchEvent(new Event('luma-session-expired'))}
    if(result.code==='reauth_required')window.dispatchEvent(new Event('luma-reauth-needed'))
    const detail = Array.isArray(result.detail) ? result.detail.map((x: any) => x.loc.slice(1).join('.') + ': ' + x.msg).join('; ') : result.detail
    const error:any=new Error(typeof detail==='string'?detail:result.message||'请求失败');error.status=response.status;error.code=result.code;error.requestId=result.request_id;throw error
  }
  return result
}
export async function upload(file: File, purpose: string) {
  const form = new FormData(); form.append('file', file); form.append('purpose', purpose)
  return api('/media', form)
}
