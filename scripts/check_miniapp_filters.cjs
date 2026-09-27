// Check request wiring without claiming WeChat rendering or device coverage.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

async function check(role) {
  let definition
  const requests = []
  const app = {
    globalData: { role, token: 'fixture', lang: 'zh' },
    requireLogin: () => true,
    request: async (url, body) => {
      requests.push({ url, body })
      return body ? { products: [], notice: '', query_id: 1 } : { items: [], total: 0, next_offset: 0, has_more: false }
    },
  }
  const filename = path.join(__dirname, '..', 'miniapps', role, 'pages/home/index.js')
  vm.runInNewContext(fs.readFileSync(filename, 'utf8'), { Page: value => definition = value, getApp: () => app, wx: { stopPullDownRefresh() {} } })
  const page = { ...definition, data: JSON.parse(JSON.stringify(definition.data)), setData(values) { Object.assign(this.data, values) } }
  page.setData({ budget: '0', available: true, sortIndex: 2, categoryIndex: 1, categories: ['全部', '台灯'], cctIndex: 1, cctValues: [null, 4000] })
  await page.load()
  const query = new URL(requests.at(-1).url, 'http://localhost').searchParams
  assert.equal(query.get('max_price'), '0')
  assert.equal(query.get('available_only'), 'true')
  assert.equal(query.get('sort'), 'price_desc')
  assert.equal(query.get('category'), '台灯')
  assert.equal(query.get('cct_k'), '4000')
  page.setData({ text: '黑色台灯', searchMode: true })
  await page.onPullDownRefresh()
  assert.equal(requests.at(-1).url, '/search')
  assert.equal(requests.at(-1).body.max_price, 0)
  assert.equal(page.data.searchMode, true)
  page.resetFilters()
  await page.search()
  const cleared = new URL(requests.at(-1).url, 'http://localhost').searchParams
  assert.equal(cleared.has('max_price'), false)
  assert.equal(cleared.has('available_only'), false)
  assert.equal(cleared.get('sort'), 'newest')
  assert.equal(page.data.cropping, false)
  assert.equal(page.data.searchMode, false)
  console.log(`${role}: filter request, ranked refresh and reset passed (source execution only)`)
}

(async () => { await check('customer'); await check('merchant') })().catch(error => { console.error(error); process.exitCode = 1 })
