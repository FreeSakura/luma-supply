import { ref, type Ref } from 'vue'
import { api } from './api'

/** Catalog pages and ranked search cards have different lifetimes. */
export function useDiscovery(catalog: Ref<any[]>, category: Ref<string>, cct: Ref<string>, filters: () => {maxPrice:string, availableOnly:boolean, sort:string}) {
  const browseItems = ref<any[]>([])
  const searchResult = ref<any>(null)
  const loading = ref(false)
  const total = ref(0)
  const hasMore = ref(false)
  let nextOffset = 0
  let generation = 0

  function remember(products: any[]) {
    const byId = new Map(catalog.value.map(product => [product.id, product]))
    products.forEach(product => byId.set(product.id, product))
    catalog.value = [...byId.values()]
  }

  async function loadCatalog(append = false) {
    if (append && (loading.value || !hasMore.value || searchResult.value)) return
    const request = ++generation
    loading.value = true
    searchResult.value = null
    if (!append) { browseItems.value = []; total.value = 0; hasMore.value = false }
    try {
      const query = new URLSearchParams({ category: category.value, limit: '24', offset: String(append ? nextOffset : 0) })
      if(cct.value)query.set('cct_k',cct.value)
      const options = filters()
      if(options.maxPrice !== '')query.set('max_price',String(Math.round(Number(options.maxPrice)*100)))
      if(options.availableOnly)query.set('available_only','true')
      query.set('sort',options.sort)
      const result = await api('/catalog/page?' + query)
      if (request !== generation) return
      const items = append ? [...browseItems.value, ...result.items] : result.items
      browseItems.value = [...new Map(items.map((p: any) => [p.id, p])).values()] as any[]
      total.value = result.total
      nextOffset = result.next_offset
      hasMore.value = result.has_more
      remember(result.items)
    } catch (error) {
      if (request === generation) throw error
    } finally {
      if (request === generation) loading.value = false
    }
  }

  async function search(parameters: Record<string, any>) {
    const request = ++generation
    loading.value = true
    try {
      const result = await api('/search', parameters)
      if (request !== generation) return
      searchResult.value = result
      remember(result.products)
    } catch (error) {
      if (request === generation) throw error
    } finally {
      if (request === generation) loading.value = false
    }
  }

  function reset() {
    generation++
    catalog.value = []
    searchResult.value = null
    browseItems.value = []
    hasMore.value = false
    loading.value = false
    total.value = 0
    nextOffset = 0
  }

  return { browseItems, searchResult, loading, total, hasMore, loadCatalog, search, reset }
}
