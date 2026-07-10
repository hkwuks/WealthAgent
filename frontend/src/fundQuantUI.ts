import { api } from './api'
import { toast } from './toast'
import {
  renderTimingChart, renderRadarChart, renderPieChart,
  renderBacktestChart, renderSignalTimeline,
} from './fundQuantCharts'
import * as echarts from 'echarts'

const BASE = '/api/fund-quant'

export class FundQuantUI {
  private container: HTMLDivElement | null = null
  private currentTab = 'strategy'
  private charts: echarts.ECharts[] = []
  private sseSource: EventSource | null = null

  init(container: HTMLDivElement) {
    this.container = container
    this.render()
    this.bindSubTabs()
    this.loadStrategies()
  }

  private render() {
    if (!this.container) return
    this.container.innerHTML = `
      <div class="fund-quant-page">
        <div class="section-card">
          <div class="section-header">
            <h2>📊 基金量化</h2>
            <span class="section-badge">V2</span>
          </div>
          <nav class="sub-tabs" id="fq-sub-tabs">
            <button class="sub-tab active" data-view="strategy">📋 策略</button>
            <button class="sub-tab" data-view="timing">📈 择时</button>
            <button class="sub-tab" data-view="selection">🔍 选基</button>
            <button class="sub-tab" data-view="allocation">⚖️ 配置</button>
            <button class="sub-tab" data-view="backtest">🔄 回测</button>
            <button class="sub-tab" data-view="signal">🔔 信号</button>
            <button class="sub-tab" data-view="portfolio">💼 组合</button>
          </nav>
          <div id="fq-content"><div class="fq-loading">加载中...</div></div>
        </div>
      </div>`
  }

  private bindSubTabs() {
    const tabs = this.container?.querySelectorAll<HTMLButtonElement>('.sub-tab')
    tabs?.forEach(tab => {
      tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'))
        tab.classList.add('active')
        this.currentTab = tab.dataset.view || 'strategy'
        this.disposeCharts()
        this.loadView(this.currentTab)
      })
    })
  }

  private disposeCharts() {
    this.charts.forEach(c => c.dispose())
    this.charts = []
  }

  private loadView(view: string) {
    switch (view) {
      case 'strategy': this.loadStrategies(); break
      case 'timing': this.showTimingView(); break
      case 'selection': this.showSelectionView(); break
      case 'allocation': this.showAllocationView(); break
      case 'backtest': this.showBacktestView(); break
      case 'signal': this.showSignalView(); break
      case 'portfolio': this.showPortfolioView(); break
    }
  }

  // ═════════════════════════════════════════
  // 策略列表
  // ═════════════════════════════════════════

  private async loadStrategies() {
    const content = this.container?.querySelector('#fq-content')
    if (!content) return
    try {
      const res = await api.get(`${BASE}/strategy/list`)
      const strategies = res.data || []
      const byType: Record<string, any[]> = { timing: [], selection: [], allocation: [] }
      strategies.forEach((s: any) => { (byType[s.type] = byType[s.type] || []).push(s) })

      content.innerHTML = `
        <div class="fq-section-title">可用策略 (${strategies.length})</div>
        ${Object.entries(byType).filter(([_, v]) => v.length).map(([type, list]) => `
          <div class="fq-type-group">
            <div class="fq-type-label tag-${type}">${type} (${list.length})</div>
            <div class="strategy-grid">
              ${list.map((s: any) => `
                <div class="strategy-card">
                  <div class="strategy-name">${s.name}</div>
                  <div class="strategy-type tag-${s.type}">${s.type}</div>
                  <div class="strategy-desc">${s.description || '-'}</div>
                  <button class="btn btn-sm btn-outline mt-1" data-strategy='${JSON.stringify(s)}'>查看参数</button>
                </div>
              `).join('')}
            </div>
          </div>
        `).join('')}`

      content.querySelectorAll('[data-strategy]').forEach(el => {
        el.addEventListener('click', () => {
          const s = JSON.parse((el as HTMLElement).dataset.strategy || '{}')
          toast.info(`${s.name} 参数: ${JSON.stringify(s.default_params, null, 2)}`)
        })
      })
    } catch (e) {
      content.innerHTML = '<div class="fq-error">获取策略列表失败</div>'
    }
  }

  // ═════════════════════════════════════════
  // 择时视图
  // ═════════════════════════════════════════

  private showTimingView() {
    const content = this.container?.querySelector('#fq-content')
    if (!content) return
    content.innerHTML = `
      <div class="fq-view">
        <div class="fq-section-title">择时评估 — 净值走势</div>
        <div class="fq-form-row">
          <input type="text" id="fq-timing-code" value="000001" placeholder="基金代码" class="input" />
          <button class="btn btn-primary" id="fq-timing-btn">评估</button>
        </div>
        <div id="fq-timing-chart" class="fq-chart"></div>
        <div id="fq-timing-detail" class="fq-result-area"></div>
      </div>`
    content.querySelector('#fq-timing-btn')?.addEventListener('click', () => this.doEvaluate())
    this.doEvaluate()  // load default
  }

  private async doEvaluate() {
    const content = this.container?.querySelector('#fq-content')
    const code = (content?.querySelector('#fq-timing-code') as HTMLInputElement)?.value.trim()
    if (!code) return toast.warning('请输入基金代码')
    const chartEl = content?.querySelector('#fq-timing-chart') as HTMLElement
    const detailEl = content?.querySelector('#fq-timing-detail') as HTMLElement
    if (chartEl) chartEl.innerHTML = '<div class="fq-loading">加载中...</div>'

    try {
      // 先取净值用于画图
      const navRes = await api.get(`/api/funds/${code}/nav-history`)
      const navData = navRes.data?.nav_history || []
      // 再取择时评估
      const evalRes = await api.post(`${BASE}/timing/evaluate`, { fund_code: code })
      const evalData = evalRes.data || {}

      if (chartEl && navData.length > 1) {
        const points = navData.map((d: any) => ({ date: d.date.slice(0, 10), nav: d.nav || d.adjusted_nav }))
        const buySignals = (evalData.signals || [])
          .filter((s: any) => s.direction === 'buy')
          .map((s: any) => ({ date: s.timestamp?.slice(0, 10) || '', nav: 0 }))
        const sellSignals = (evalData.signals || [])
          .filter((s: any) => s.direction === 'sell')
          .map((s: any) => ({ date: s.timestamp?.slice(0, 10) || '', nav: 0 }))
        // 找到信号对应净值
        for (const sig of [...buySignals, ...sellSignals]) {
          const match = navData.find((d: any) => d.date.slice(0, 10) === sig.date)
          sig.nav = match ? (match.nav || match.adjusted_nav) : 0
        }
        const chart = renderTimingChart(chartEl, points, buySignals, sellSignals)
        this.charts.push(chart)
      }

      if (detailEl) {
        detailEl.innerHTML = `<h4>信号详情</h4><pre class="fq-pre">${JSON.stringify(evalData.fusion_signal || evalData.signals || [], null, 2)}</pre>`
      }
    } catch (e) {
      if (chartEl) chartEl.innerHTML = '<div class="fq-error">评估失败</div>'
    }
  }

  // ═════════════════════════════════════════
  // 选基视图
  // ═════════════════════════════════════════

  private showSelectionView() {
    const content = this.container?.querySelector('#fq-content')
    if (!content) return
    content.innerHTML = `
      <div class="fq-view">
        <div class="fq-section-title">基金筛选</div>
        <div class="fq-form-row">
          <select id="fq-sel-type" class="input">
            <option value="stock">股票型</option>
            <option value="hybrid">混合型</option>
            <option value="bond">债券型</option>
            <option value="index">指数型</option>
          </select>
          <input type="number" id="fq-sel-top" value="5" min="1" max="20" class="input" style="width:80px" />
          <button class="btn btn-primary" id="fq-sel-btn">筛选</button>
        </div>
        <div id="fq-sel-chart" class="fq-chart"></div>
        <div id="fq-sel-rank" class="fq-result-area"></div>
      </div>`
    content.querySelector('#fq-sel-btn')?.addEventListener('click', () => this.doSelection())
  }

  private async doSelection() {
    const content = this.container?.querySelector('#fq-content')
    const fundType = (content?.querySelector('#fq-sel-type') as HTMLSelectElement)?.value
    const topN = parseInt((content?.querySelector('#fq-sel-top') as HTMLInputElement)?.value || '5')
    const chartEl = content?.querySelector('#fq-sel-chart') as HTMLElement
    const rankEl = content?.querySelector('#fq-sel-rank') as HTMLElement

    try {
      const res = await api.post(`${BASE}/selection/screen`, { fund_type: fundType, top_n: topN })
      const rankings = res.data?.rankings || []
      if (!rankings.length) {
        if (chartEl) chartEl.innerHTML = '<div class="fq-hint">无数据，请先采集基金数据</div>'
        return
      }

      // 对排名第一的基金画雷达图
      if (chartEl) {
        const top = rankings[0]
        const factors = top.factors || {}
        const indicators = Object.entries(factors).map(([k, v]) => ({
          name: k, value: Math.min(Math.abs(v as number) / 2, 1),
        }))
        if (indicators.length) {
          const chart = renderRadarChart(chartEl, indicators, `${top.fund_name} (${top.fund_code})`)
          this.charts.push(chart)
        }
      }

      if (rankEl) {
        rankEl.innerHTML = `<h4>排名</h4>
          <table class="fq-table">
            <tr><th>#</th><th>代码</th><th>名称</th><th>总分</th></tr>
            ${rankings.slice(0, 10).map((r: any, i: number) => `
              <tr><td>${i + 1}</td><td>${r.fund_code}</td><td>${r.fund_name}</td>
              <td class="${r.total_score >= 0 ? 'positive' : 'negative'}">${r.total_score.toFixed(4)}</td></tr>
            `).join('')}
          </table>`
      }
    } catch (e) {
      if (chartEl) chartEl.innerHTML = '<div class="fq-error">筛选失败</div>'
    }
  }

  // ═════════════════════════════════════════
  // 配置视图
  // ═════════════════════════════════════════

  private showAllocationView() {
    const content = this.container?.querySelector('#fq-content')
    if (!content) return
    content.innerHTML = `
      <div class="fq-view">
        <div class="fq-section-title">配置优化</div>
        <div class="fq-form-row">
          <input type="text" id="fq-alloc-codes" value="000001,110011,007016" placeholder="基金代码（逗号分隔）" class="input" />
          <button class="btn btn-primary" id="fq-alloc-btn">优化</button>
        </div>
        <div id="fq-alloc-chart" class="fq-chart"></div>
        <div id="fq-alloc-detail" class="fq-result-area"></div>
      </div>`
    content.querySelector('#fq-alloc-btn')?.addEventListener('click', () => this.doAllocation())
  }

  private async doAllocation() {
    const content = this.container?.querySelector('#fq-content')
    const codes = (content?.querySelector('#fq-alloc-codes') as HTMLInputElement)?.value.trim()
    if (!codes) return toast.warning('请输入基金代码')
    const chartEl = content?.querySelector('#fq-alloc-chart') as HTMLElement
    const detailEl = content?.querySelector('#fq-alloc-detail') as HTMLElement

    try {
      const res = await api.post(`${BASE}/allocation/optimize`, {
        fund_codes: codes.split(',').map(c => c.trim()),
      })
      const data = res.data || {}
      const weights = data.weights || {}

      if (chartEl && Object.keys(weights).length) {
        const pieData = Object.entries(weights).map(([k, v]) => ({
          name: k, value: parseFloat((v as number * 100).toFixed(1)),
        }))
        const chart = renderPieChart(chartEl, pieData, '配置权重')
        this.charts.push(chart)
      }

      if (detailEl) {
        detailEl.innerHTML = `<h4>详情</h4>
          <p>预期年化: ${(data.expected_return || 0).toFixed(2)}% &nbsp;|&nbsp;
          波动率: ${(data.portfolio_volatility || 0).toFixed(2)}% &nbsp;|&nbsp;
          夏普: ${(data.sharpe_ratio || 0).toFixed(2)} &nbsp;|&nbsp;
          方法: ${data.method || data.status || '-'}</p>`
      }
    } catch (e) {
      if (chartEl) chartEl.innerHTML = '<div class="fq-error">优化失败</div>'
    }
  }

  // ═════════════════════════════════════════
  // 回测视图
  // ═════════════════════════════════════════

  private showBacktestView() {
    const content = this.container?.querySelector('#fq-content')
    if (!content) return
    content.innerHTML = `
      <div class="fq-view">
        <div class="fq-section-title">策略回测</div>
        <div class="fq-form-row">
          <select id="fq-bt-strategy" class="input" style="width:160px">
            <option value="momentum">动量择时</option>
            <option value="valuation_deviation">估值偏差</option>
            <option value="smart_dca">智能定投</option>
            <option value="multi_factor">多因子选基</option>
            <option value="risk_parity">风险平价</option>
          </select>
          <input type="text" id="fq-bt-codes" value="000001" placeholder="基金代码" class="input" />
          <input type="text" id="fq-bt-start" value="2023-01-01" class="input" style="width:120px" />
          <input type="text" id="fq-bt-end" value="2025-12-31" class="input" style="width:120px" />
          <button class="btn btn-primary" id="fq-bt-btn">回测</button>
        </div>
        <div id="fq-bt-chart" class="fq-chart"></div>
        <div id="fq-bt-metrics" class="fq-metrics"></div>
        <div id="fq-bt-detail" class="fq-result-area"></div>
      </div>`
    content.querySelector('#fq-bt-btn')?.addEventListener('click', () => this.doBacktest())
  }

  private async doBacktest() {
    const content = this.container?.querySelector('#fq-content')
    const strategy = (content?.querySelector('#fq-bt-strategy') as HTMLSelectElement)?.value
    const codes = (content?.querySelector('#fq-bt-codes') as HTMLInputElement)?.value.trim()
    const start = (content?.querySelector('#fq-bt-start') as HTMLInputElement)?.value.trim()
    const end = (content?.querySelector('#fq-bt-end') as HTMLInputElement)?.value.trim()
    if (!codes) return toast.warning('请输入基金代码')

    const chartEl = content?.querySelector('#fq-bt-chart') as HTMLElement
    const metricsEl = content?.querySelector('#fq-bt-metrics') as HTMLElement
    const detailEl = content?.querySelector('#fq-bt-detail') as HTMLElement
    if (chartEl) chartEl.innerHTML = '<div class="fq-loading">回测中...</div>'

    try {
      const res = await api.post(`${BASE}/backtest/run`, {
        strategy_name: strategy, fund_codes: codes.split(',').map(c => c.trim()),
        start_date: start, end_date: end,
      })
      const id = res.data?.backtest_id
      if (!id) throw new Error('无回测ID')

      // poll for result
      for (let i = 0; i < 30; i++) {
        await new Promise(r => setTimeout(r, 500))
        const btRes = await api.get(`${BASE}/backtest/result/${id}`)
        const bt = btRes.data || {}
        if (bt.status === 'completed' || bt.status === 'failed' || bt.result) break
      }

      // get result again
      const btRes = await api.get(`${BASE}/backtest/result/${id}`)
      const bt = btRes.data?.result || btRes.data || {}

      const equity = bt.equity_curve || []
      if (chartEl && equity.length > 1) {
        const eq = equity.map((e: any) => ({ date: e.date, value: e.total_value }))
        const dd = equity.map((e: any) => ({
          date: e.date,
          value: (e.total_value / Math.max(...equity.slice(0, equity.indexOf(e) + 1).map((x: any) => x.total_value)) - 1) * 100,
        }))
        const chart = renderBacktestChart(chartEl, eq, dd)
        this.charts.push(chart)
      }

      if (metricsEl) {
        const p = bt
        metricsEl.innerHTML = `
          <div class="metric-card"><span>总收益</span><span class="${p.total_return >= 0 ? 'positive' : 'negative'}">${(p.total_return * 100).toFixed(2)}%</span></div>
          <div class="metric-card"><span>年化收益</span><span>${(p.annual_return * 100).toFixed(2)}%</span></div>
          <div class="metric-card"><span>最大回撤</span><span class="negative">${(p.max_drawdown * 100).toFixed(2)}%</span></div>
          <div class="metric-card"><span>夏普比率</span><span>${(p.sharpe_ratio || 0).toFixed(2)}</span></div>
          <div class="metric-card"><span>胜率</span><span>${(p.win_rate * 100).toFixed(1)}%</span></div>
          <div class="metric-card"><span>交易次数</span><span>${p.total_trades || 0}</span></div>`
      }
      if (detailEl) {
        detailEl.innerHTML = `<h4>分年度收益</h4><pre class="fq-pre">${JSON.stringify(bt.period_returns || {}, null, 2)}</pre>`
      }
    } catch (e) {
      if (chartEl) chartEl.innerHTML = '<div class="fq-error">回测失败</div>'
    }
  }

  // ═════════════════════════════════════════
  // 信号视图
  // ═════════════════════════════════════════

  private showSignalView() {
    const content = this.container?.querySelector('#fq-content')
    if (!content) return
    content.innerHTML = `
      <div class="fq-view">
        <div class="fq-section-title">信号中心</div>
        <div class="fq-form-row">
          <input type="text" id="fq-sig-code" placeholder="基金代码（可选）" class="input" />
          <button class="btn btn-primary" id="fq-sig-btn">查询</button>
          <button class="btn btn-outline" id="fq-sse-btn">📡 订阅推送</button>
        </div>
        <div id="fq-sig-chart" class="fq-chart"></div>
        <div id="fq-sig-list" class="fq-result-area"></div>
        <div id="fq-sse-status" class="fq-hint"></div>
      </div>`

    content.querySelector('#fq-sig-btn')?.addEventListener('click', () => this.doSignals())
    content.querySelector('#fq-sse-btn')?.addEventListener('click', () => this.toggleSSE())

    // auto load signals
    this.doSignals()
  }

  private async doSignals() {
    const content = this.container?.querySelector('#fq-content')
    const code = (content?.querySelector('#fq-sig-code') as HTMLInputElement)?.value.trim()
    const chartEl = content?.querySelector('#fq-sig-chart') as HTMLElement
    const listEl = content?.querySelector('#fq-sig-list') as HTMLElement

    try {
      const url = code ? `${BASE}/signal/history?fund_code=${code}&limit=50` : `${BASE}/signal/history?limit=50`
      const res = await api.get(url)
      const signals = res.data || []
      const items = Array.isArray(signals) ? signals : []

      if (chartEl && items.length) {
        const timeline = items.map((s: any) => ({
          time: (s.created_at || s.timestamp || '').slice(0, 16),
          name: s.fund_code,
          type: s.direction || 'hold',
          confidence: s.confidence || 0.5,
        })).slice(0, 30).reverse()
        const chart = renderSignalTimeline(chartEl, timeline)
        this.charts.push(chart)
      }

      if (listEl) {
        listEl.innerHTML = `<h4>信号记录 (${items.length})</h4>
          <table class="fq-table">
            <tr><th>时间</th><th>基金</th><th>方向</th><th>置信度</th><th>策略</th></tr>
            ${items.slice(0, 20).map((s: any) => `
              <tr>
                <td>${(s.created_at || s.timestamp || '').slice(0, 16)}</td>
                <td>${s.fund_code}</td>
                <td class="tag-${s.direction}">${s.direction}</td>
                <td>${(s.confidence * 100).toFixed(0)}%</td>
                <td>${s.strategy_name || '-'}</td>
              </tr>
            `).join('')}
          </table>`
      }
    } catch (e) {
      if (listEl) listEl.innerHTML = '<div class="fq-error">查询失败</div>'
    }
  }

  private toggleSSE() {
    const statusEl = document.getElementById('fq-sse-status')
    if (this.sseSource) {
      this.sseSource.close()
      this.sseSource = null
      if (statusEl) statusEl.textContent = '📡 SSE 已断开'
      return
    }
    this.sseSource = new EventSource(`${BASE}/signal/stream`)
    this.sseSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'heartbeat') return
        toast.info(`📡 新信号: ${data.fund?.code || ''} ${data.action?.direction || ''} (${(data.analysis?.confidence * 100).toFixed(0)}%)`)
        // refresh list
        this.doSignals()
      } catch { /* ignore */ }
    }
    this.sseSource.onerror = () => {
      if (statusEl) statusEl.textContent = '📡 SSE 连接异常，10秒后重连...'
      setTimeout(() => { this.sseSource = null; this.toggleSSE() }, 10000)
    }
    if (statusEl) statusEl.textContent = '📡 SSE 已连接'
  }

  // ═════════════════════════════════════════
  // 组合视图
  // ═════════════════════════════════════════

  private async showPortfolioView() {
    const content = this.container?.querySelector('#fq-content')
    if (!content) return
    try {
      const res = await api.get(`${BASE}/portfolio/status`)
      const data = res.data || {}
      const positions = data.positions || {}
      const posList = Object.entries(positions).map(([k, v]) => ({ name: k, value: parseFloat((v as number * 100).toFixed(1)) }))

      content.innerHTML = `
        <div class="fq-view">
          <div class="fq-section-title">模拟组合</div>
          <div class="portfolio-summary">
            <div class="portfolio-stat"><span class="stat-label">总值</span><span class="stat-value">¥${(data.total_value || 0).toFixed(2)}</span></div>
            <div class="portfolio-stat"><span class="stat-label">现金</span><span class="stat-value">¥${(data.cash || 0).toFixed(2)}</span></div>
            <div class="portfolio-stat ${(data.return_pct || 0) >= 0 ? 'positive' : 'negative'}">
              <span class="stat-label">收益</span><span class="stat-value">${(data.return_pct || 0).toFixed(2)}%</span></div>
            <div class="portfolio-stat"><span class="stat-label">持仓</span><span class="stat-value">${data.position_count || 0}</span></div>
          </div>
          <div id="fq-port-chart" class="fq-chart" style="height:260px"></div>
          <div class="fq-form-row mt-1">
            <button class="btn btn-outline" id="fq-port-refresh">🔄 刷新</button>
            <button class="btn btn-outline" id="fq-port-update-nav">📈 更新净值</button>
          </div>
        </div>`

      if (posList.length) {
        const chartEl = content.querySelector('#fq-port-chart') as HTMLElement
        if (chartEl) {
          const chart = renderPieChart(chartEl, posList, '持仓分布')
          this.charts.push(chart)
        }
      }

      content.querySelector('#fq-port-refresh')?.addEventListener('click', () => this.showPortfolioView())
      content.querySelector('#fq-port-update-nav')?.addEventListener('click', async () => {
        toast.info('更新中...')
        // 触发组合净值刷新
        await api.post(`${BASE}/portfolio/status`)  // dummy
        toast.success('已刷新')
        this.showPortfolioView()
      })
    } catch (e) {
      content.innerHTML = '<div class="fq-error">获取组合状态失败</div>'
    }
  }
}
