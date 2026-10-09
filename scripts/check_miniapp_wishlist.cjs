// Native page logic checks, without simulating WeChat rendering.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

async function check(role) {
  let definition, fail = true, pendingPreview, lastRequest
  const app = {
    request: async (url, body, method) => {
      lastRequest = { url, body, method }
      if (url === '/inquiries/preview') return new Promise(resolve => pendingPreview = resolve)
      if (fail) throw new Error('Save failed')
      return { id: 7 }
    },
    money: value => String(value),
    saveDraft() {},
  }
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', 'miniapps', role, 'pages/work/index.js'), 'utf8'), {
    Page: value => definition = value, getApp: () => app, wx: { showToast() {} },
  })
  const page = { ...definition, data: JSON.parse(JSON.stringify(definition.data)), async load() {}, setData(values) {
    for (const [key, value] of Object.entries(values)) {
      const parts = key.split('.'); let object = this.data
      for (const part of parts.slice(0, -1)) object = object[part]
      object[parts.at(-1)] = value
    }
  } }
  page.data.rows = [{ id: 7, version: 1, room: '客厅', quantity: 2, note: '', watch_price: true, watch_stock: false }]
  page.editWish({ currentTarget: { dataset: { id: 7 } } })
  page.data.form.quantity = 4
  await assert.rejects(page.saveWish(), /Save failed/)
  assert.equal(page.data.rows[0].quantity, 2)
  assert.equal(page.data.form.quantity, 4)
  assert.equal(page.data.modal, 'wish')
  assert.equal(page.data.submitting, false)
  fail = false; await page.saveWish()
  assert.equal(lastRequest.method, 'PATCH')
  assert.equal(lastRequest.url, '/wishlist/7')
  assert.equal(lastRequest.body.quantity, 4)
  assert.equal(lastRequest.body.version, 1)
  assert.equal(page.data.modal, '')
  page.setData({ modal: 'inquiry', selectedIds: [7], form: { budget: '100' } })
  const preview = page.previewInquiry()
  page.input({ currentTarget: { dataset: { key: 'budget' } }, detail: { value: '500' } })
  pendingPreview({ estimate: { goods_amount: 20000, budget_gap: 10000, rooms: [] }, can_submit: true })
  await preview
  assert.equal(page.data.inquiryPreview, null)
  assert.equal(page.data.submitting, false)
  console.log(`${role}: failed edit retains draft; PATCH save and stale preview checks passed (source only)`)
}

(async () => { await check('customer'); await check('merchant') })().catch(error => { console.error(error); process.exitCode = 1 })
