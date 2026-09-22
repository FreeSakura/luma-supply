export const mediaUrl = (id: string) => '/api/public-media/' + encodeURIComponent(id)
export const money = (v: number) => '¥' + ((v || 0) / 100).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
export async function api(path: string, data?: any, method?: string) {
  const token = localStorage.getItem('luma-token')
  const headers: any = token ? { Authorization: 'Bearer ' + token } : {}
  if (!(data instanceof FormData) && data !== undefined) headers['Content-Type'] = 'application/json'
  const response = await fetch('/api' + path, { method: method || (data === undefined ? 'GET' : 'POST'), headers, body: data === undefined ? undefined : data instanceof FormData ? data : JSON.stringify(data) })
  const result = await response.json()
  if (!response.ok) {
    const detail = Array.isArray(result.detail) ? result.detail.map((x: any) => x.loc.slice(1).join('.') + ': ' + x.msg).join('; ') : result.detail
    throw new Error(detail || '请求失败')
  }
  return result
}
export async function upload(file: File, purpose: string) {
  const form = new FormData(); form.append('file', file); form.append('purpose', purpose)
  return api('/media', form)
}
