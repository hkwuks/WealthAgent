import { PanelBase } from '../layout'
import { fundQuantApi } from '../api'
import { state } from '../state'

const DIR_LABEL: Record<string, string> = { buy: '↑买入', sell: '↓卖出', hold: '→持有' }
const DIR_CLASS: Record<string, string> = { buy: 'tag-buy', sell: 'tag-sell', hold: 'tag-hold' }

export class SignalList extends PanelBase {
  private sseSource: EventSource | null = null
  private refreshTimer: ReturnType<typeof setInterval> | null = null

  constructor() {
    // 信号列表的 5 列在 1/3 宽（约 413px）里会被挤成竖排/省略号。
    // 满宽独占一行，名称才有可读空间。
    super({ id: 'signal_list', title: '信号列表', defaultGridPos: { x: 0, y: 2, w: 3, h: 1 } })
  }

  render(): HTMLElement {
    const el = document.createElement('div')
    el.className = 'panel-signallist'
    el.innerHTML = `
      <div class="panel-header">
        <h3>信号列表</h3>
        <div class="panel-toolbar">
          <select class="sig-filter">
            <option value="all">全部</option>
            <option value="buy">买入</option>
            <option value="sell">卖出</option>
          </select>
          <span class="sig-sse-dot"></span>
        </div>
      </div>
      <div class="sig-table-wrapper">
        <table class="sig-table">
          <thead>
            <tr>
              <th>基金</th>
              <th>方向</th>
              <th class="text-right">置信度</th>
              <th>策略</th>
              <th style="width:34px;"></th>
            </tr>
          </thead>
          <tbody class="sig-tbody"></tbody>
        </table>
      </div>
      <div class="sig-footer">
        <span>实时推送 SSE</span>
      </div>`
    return el
  }

  protected afterMount(): void {
    // 过滤切换 → 客户端过滤（调用 refresh 重新获取后由 render 过滤）
    this.el?.querySelector('.sig-filter')?.addEventListener('change', () => this.refresh())

    // 行点击 → 选中基金
    this.el?.querySelector('.sig-tbody')?.addEventListener('click', (e) => {
      const studyBtn = (e.target as HTMLElement).closest('.sig-study-btn')
      if (studyBtn) {
        // 研究按钮 → 打开研究区
        const btn = studyBtn as HTMLElement
        const code = btn.dataset.code || ''
        const signal = {
          direction: btn.dataset.direction || 'hold',
          confidence: parseFloat(btn.dataset.confidence || '0'),
          strategy_name: btn.dataset.strategy || '',
          timestamp: btn.dataset.timestamp || '',
          fund_code: code,
          fund_name: '',
        } as any
        const fundName = state.get('fundPool').find(f => f.fund_code === code)?.fund_name || ''
        signal.fund_name = fundName
        // 研究区现在是「策略暴露 / 因子评价」两个 tab，点信号看因子暴露
        state.set('researchPanel', { visible: true, activeTab: 'exposure', fundCode: code, signal })
        return
      }
      const row = (e.target as HTMLElement).closest<HTMLElement>('[data-code]')
      if (row) state.set('selectedFund', row.dataset.code || null)
    })

    // SSE
    this.startSSE()

    // 定时刷新
    this.refreshTimer = setInterval(() => this.refresh(), 30000)
  }

  private setDotColor(color: string): void {
    const dot = this.el?.querySelector('.sig-sse-dot') as HTMLElement
    if (dot) dot.style.background = color
  }

  private startSSE(): void {
    this.sseSource = new EventSource('/api/fund-quant/signal/stream')
    this.sseSource.onopen = () => this.setDotColor('#10b981')
    this.sseSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'heartbeat') return
        if (data.fund?.code) {
          this.refresh()
          // 闪烁琥珀色提示新信号
          this.setDotColor('#fbbf24')
          setTimeout(() => this.setDotColor('#10b981'), 2000)
        }
      } catch { /* ignore parse errors */ }
    }
    this.sseSource.onerror = () => {
      // 标记断开 + 10s 重连
      this.setDotColor('#94a3b8')
      this.sseSource?.close()
      setTimeout(() => this.startSSE(), 10000)
    }
  }

  async refresh(): Promise<void> {
    if (!this.el) return
    const filter = (this.el.querySelector('.sig-filter') as HTMLSelectElement)?.value || 'all'
    try {
      // 只显示 fundPool 中存在的基金信号。白名单传给后端，
      // 由后端先过滤再截断——库里 148 条 000001 历史测试残留会挤掉真实信号。
      const poolCodes = state.get('fundPool').map(f => f.fund_code)
      if (!poolCodes.length) {
        // 基金池还没加载完。此时不传白名单会拿到测试残留数据，宁可不显示。
        const tb = this.el.querySelector('.sig-tbody')
        if (tb) tb.innerHTML = `<tr><td colspan="5" style="padding:24px;text-align:center;color:var(--text-tertiary);font-size:13px;">等待基金池加载…</td></tr>`
        return
      }
      const res = await fundQuantApi.getLatestSignals(poolCodes, 30)
      let signals = res.data || []

      // 去重 (code + direction + confidence 相同视为重复)
      const seen = new Set<string>()
      signals = signals.filter(s => {
        const key = `${s.fund_code}|${s.direction}|${s.confidence}|${s.strategy_name}`
        if (seen.has(key)) return false
        seen.add(key)
        return true
      })

      if (filter !== 'all') signals = signals.filter(s => s.direction === filter)

      const tbody = this.el.querySelector('.sig-tbody')
      if (!tbody) return

      if (!signals.length) {
        tbody.innerHTML = `<tr><td colspan="5" style="padding:24px;text-align:center;color:var(--text-tertiary);font-size:13px;">暂无信号数据</td></tr>`
        state.set('signals', [])
        return
      }

      // 生成行html，如果是新数据则标记 glow class
      const existingRows = tbody.querySelectorAll('tr[data-code]')
      const existingKeys = new Set<string>()
      existingRows.forEach(r => existingKeys.add(r.getAttribute('data-key') || ''))

      tbody.innerHTML = signals.slice(0, 30).map(s => {
        const key = `${s.fund_code}|${s.direction}|${s.confidence}`
        const isNew = existingRows.length > 0 && !existingKeys.has(key)
        const name = s.fund_name || s.fund_code
        const when = (s.created_at || '').slice(5, 16)
        return `<tr data-code="${s.fund_code}" data-key="${key}" class="${isNew ? 'sig-row-new' : ''}">
          <td class="sig-name" title="${name} (${s.fund_code}) · ${when}">
            <div class="sig-name-cell">
              <span class="sig-name-text">${name}</span>
              <span class="sig-code">${s.fund_code}</span>
            </div>
          </td>
          <td class="sig-dir">
            <span class="${DIR_CLASS[s.direction] || ''}">${DIR_LABEL[s.direction] || s.direction}</span>
          </td>
          <td class="sig-conf">
            <span class="sig-conf-num">${(s.confidence * 100).toFixed(0)}%</span>
            <span class="sig-conf-bar"><i style="width:${s.confidence * 100}%;background:${
              s.confidence > 0.7 ? '#10b981' : s.confidence > 0.5 ? '#f59e0b' : '#94a3b8'}"></i></span>
          </td>
          <td class="sig-strat" title="${s.strategy_name || '-'}">${s.strategy_name || '-'}</td>
          <td class="sig-act">
            <button class="btn btn-sm btn-ghost sig-study-btn" data-code="${s.fund_code}" data-direction="${s.direction}" data-confidence="${s.confidence}" data-strategy="${s.strategy_name || ''}" data-timestamp="${s.created_at || ''}" title="研究此信号">🔍</button>
          </td>
        </tr>`
      }).join('')

      state.set('signals', signals.map(s => ({
        direction: s.direction as any,
        confidence: s.confidence,
        strategy_name: s.strategy_name,
        timestamp: s.created_at,
        fund_code: s.fund_code,
        fund_name: s.fund_name || '',
      })))
    } catch { /* 静默保留旧数据 */ }
  }

  destroy(): void {
    this.sseSource?.close()
    if (this.refreshTimer) clearInterval(this.refreshTimer)
    super.destroy()
  }

  onActivated(): void {
    this.refresh()
  }
}
