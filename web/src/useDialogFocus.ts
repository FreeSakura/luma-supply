import { onMounted, onUnmounted } from 'vue'

/** Keyboard behavior for the existing shared dialog markup. */
export function useDialogFocus() {
  let observer: MutationObserver
  let current: HTMLElement | null = null
  const returnTo = new WeakMap<HTMLElement, HTMLElement>()
  const focusable = (root: HTMLElement) => Array.from(root.querySelectorAll<HTMLElement>(
    'button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex="0"]'
  )).filter(el => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden')
  function sync() {
    const dialogs = Array.from(document.querySelectorAll<HTMLElement>('.overlay .dialog, .sidebar.is-open'))
    const next = dialogs.at(-1) || null
    if (next === current) return
    const old = current
    current = next
    if (old?.classList.contains('sidebar')) {
      old.removeAttribute('role'); old.removeAttribute('aria-modal'); old.removeAttribute('tabindex')
    }
    if (next) {
      next.setAttribute('role', 'dialog')
      next.setAttribute('aria-modal', 'true')
      next.tabIndex = -1
      if (!returnTo.has(next) && document.activeElement instanceof HTMLElement) returnTo.set(next, document.activeElement)
      const field = focusable(next).find(el => ['INPUT','SELECT','TEXTAREA'].includes(el.tagName))
      ;(field || focusable(next)[0] || next).focus()
    } else if (old) {
      const target = returnTo.get(old)
      if (target?.isConnected) target.focus()
      returnTo.delete(old)
    }
  }
  function keydown(event: KeyboardEvent) {
    if (!current) return
    if (event.key === 'Escape') {
      const close = current.querySelector<HTMLButtonElement>('button.close')
      if (close && !close.disabled) { event.preventDefault(); event.stopPropagation(); close.click() }
    }
    if (event.key === 'Tab') {
      const items = focusable(current)
      if (!items.length) { event.preventDefault(); current.focus(); return }
      const first = items[0], last = items[items.length - 1]
      if (event.shiftKey && (document.activeElement === first || !current.contains(document.activeElement))) {
        event.preventDefault(); last.focus()
      } else if (!event.shiftKey && (document.activeElement === last || !current.contains(document.activeElement))) {
        event.preventDefault(); first.focus()
      }
    }
  }
  onMounted(() => {
    observer = new MutationObserver(sync)
    observer.observe(document.body, {childList:true,subtree:true,attributes:true,attributeFilter:['class']})
    document.addEventListener('keydown', keydown)
    sync()
  })
  onUnmounted(() => { observer?.disconnect(); document.removeEventListener('keydown', keydown) })
}
