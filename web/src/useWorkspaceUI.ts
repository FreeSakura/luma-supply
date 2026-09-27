import { computed, ref, watch, type Ref } from 'vue'

/** Presentation-only filters over records the current role is already allowed to read. */
export function useWorkspaceUI(page: Ref<string>, rows: Ref<any[]>) {
  const query = ref('')
  const status = ref('')
  const compact = ref(localStorage.getItem('luma-density') === 'compact')
  const supported = ['catalog','quotes','orders','procurements','merchants','users','tickets','reviews','audits','exceptions']
  const enabled = computed(() => supported.includes(page.value))
  function rowStatus(row: any) {
    if (page.value === 'users') return row.active ? 'active' : 'disabled'
    if (page.value === 'quotes') {
      if (row.deleted) return 'deleted'
      if (!row.active) return 'inactive'
      if (Date.parse(row.valid_until + (row.valid_until.endsWith('Z') ? '' : 'Z')) <= Date.now()) return 'expired'
    }
    return row.status || ''
  }
  const statuses = computed(() => [...new Set([...rows.value.map(rowStatus).filter(Boolean), ...(status.value ? [status.value] : [])])])
  const visible = computed(() => {
    if (!enabled.value) return rows.value
    const needle = query.value.trim().toLocaleLowerCase()
    return rows.value.filter(row => {
      if (status.value && rowStatus(row) !== status.value) return false
      if (!needle) return true
      const values = [row.id,row.number,row.order_number,row.sku_code,row.shop_name,row.name,row.username,
        row.customer_name,row.service_name,row.legal_name,row.phone,row.category,row.title,row.description,
        row.reason,row.text,row.message,row.action,row.target,
        ...(row.skus || []).map((s:any) => s.code),
        ...(row.lines || []).flatMap((l:any) => [l.snapshot?.code,l.snapshot?.product_name])]
      return values.some(v => String(v ?? '').toLocaleLowerCase().includes(needle))
    })
  })
  watch(page, () => { query.value = ''; status.value = '' }, { flush:'sync' })
  watch(compact, value => localStorage.setItem('luma-density', value ? 'compact' : 'comfortable'))
  return { query, status, compact, enabled, statuses, visible, rowStatus }
}
