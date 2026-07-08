import { api } from './api'
import { toast } from './toast'

const BASE = '/api/fund-quant'

export class FundQuantUI {
  private container: HTMLDivElement | null = null
  private currentTab = 'strategy'

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
            <span class="section-badge">V1</span>
          </div>

          <!-- 子导航 -->
          <nav class="sub-tabs" id="fq-sub-tabs">
            <button class="sub-tab active" data-view="strategy">策略</button>
            <button class="sub-tab" data-view="timing">择时</button>
            <button class="sub-tab" data-view="selection">选基</button>
            <button class="sub-tab" data-view="allocation">配置</button>
            <button class="sub-tab" data-view="backtest">回测</button>
            <button class="sub-tab" data-view="signal">信号</button>
            <button class="sub-tab" data-view="portfolio">组合</button>
          </nav>

          <!-- 内容区 -->
          <div id="fq-content">
            <div class="fq-loading">加载中...</div>
          </div>
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
        this.loadView(this.currentTab)
      })
    })
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

  private async loadStrategies() {
    const content = this.container?.querySelector('#fq-content')
    if (!content) return
    try {
      const res = await api.get(`${BASE}/strategy/list`)
      const strategies = res.data || []
      content.innerHTML = `
        <div class="strategy-list">
          <div class="fq-section-title">可用策略 (${strategies.length})</div>
          <div class="strategy-grid">
            ${strategies.map((s: any) => `
              <div class="strategy-card">
                <div class="strategy-name">${s.name}</div>
                <div class="strategy-type tag-${s.type}">${s.type}</div>
                <div class="strategy-desc">${s.description || '-'}</div>
                <button class="btn btn-sm btn-outline" onclick="window.fqViewParams('${s.name}')">查看参数</button>
              </div>
            `).join('')}
          </div>
        </div>`
    } catch (e) {
      content.innerHTML = '<div class="fq-error">获取策略列表失败</div>'
    }
  }

  private showTimingView() {
    const content = this.container?.querySelector('#fq-content')
    if (!content) return
    content.innerHTML = `
      <div class="fq-view">
        <div class="fq-section-title">择时评估</div>
        <div class="fq-form-row">
          <input type="text" id="fq-timing-code" placeholder="基金代码，如 000001" class="input" />
          <button class="btn btn-primary" id="fq-timing-btn">评估</button>
        </div>
        <div id="fq-timing-result" class="fq-result-area"></div>
      </div>`
    content.querySelector('#fq-timing-btn')?.addEventListener('click', async () => {
      const code = (content.querySelector('#fq-timing-code') as HTMLInputElement)?.value.trim()
      if (!code) return toast.warning('请输入基金代码')
      const resultEl = content.querySelector('#fq-timing-result')
      if (resultEl) resultEl.innerHTML = '<div class="fq-loading">评估中...</div>'
      try {
        const res = await api.post(`${BASE}/timing/evaluate`, { fund_code: code })
        const data = res.data || {}
        if (resultEl) resultEl.innerHTML = `<pre>${JSON.stringify(data, null, 2)}</pre>`
      } catch (e) {
        if (resultEl) resultEl.innerHTML = '<div class="fq-error">评估失败</div>'
      }
    })
  }

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
          <input type="number" id="fq-sel-top" value="10" min="1" max="50" class="input" style="width:80px" />
          <button class="btn btn-primary" id="fq-sel-btn">筛选</button>
        </div>
        <div id="fq-sel-result" class="fq-result-area"></div>
      </div>`
    content.querySelector('#fq-sel-btn')?.addEventListener('click', async () => {
      const fundType = (content.querySelector('#fq-sel-type') as HTMLSelectElement)?.value
      const topN = parseInt((content.querySelector('#fq-sel-top') as HTMLInputElement)?.value || '10')
      const resultEl = content.querySelector('#fq-sel-result')
      if (resultEl) resultEl.innerHTML = '<div class="fq-loading">筛选中...</div>'
      try {
        const res = await api.post(`${BASE}/selection/screen`, { fund_type: fundType, top_n: topN })
        if (resultEl) resultEl.innerHTML = `<pre>${JSON.stringify(res.data || {}, null, 2)}</pre>`
      } catch (e) {
        if (resultEl) resultEl.innerHTML = '<div class="fq-error">筛选失败</div>'
      }
    })
  }

  private showAllocationView() {
    const content = this.container?.querySelector('#fq-content')
    if (!content) return
    content.innerHTML = `
      <div class="fq-view">
        <div class="fq-section-title">配置优化</div>
        <div class="fq-form-row">
          <input type="text" id="fq-alloc-codes" placeholder="基金代码（逗号分隔）" class="input" />
          <button class="btn btn-primary" id="fq-alloc-btn">优化</button>
        </div>
        <div id="fq-alloc-result" class="fq-result-area"></div>
      </div>`
    content.querySelector('#fq-alloc-btn')?.addEventListener('click', async () => {
      const codes = (content.querySelector('#fq-alloc-codes') as HTMLInputElement)?.value.trim()
      if (!codes) return toast.warning('请输入基金代码')
      const resultEl = content.querySelector('#fq-alloc-result')
      if (resultEl) resultEl.innerHTML = '<div class="fq-loading">优化中...</div>'
      try {
        const res = await api.post(`${BASE}/allocation/optimize`, {
          fund_codes: codes.split(',').map(c => c.trim())
        })
        if (resultEl) resultEl.innerHTML = `<pre>${JSON.stringify(res.data || {}, null, 2)}</pre>`
      } catch (e) {
        if (resultEl) resultEl.innerHTML = '<div class="fq-error">优化失败</div>'
      }
    })
  }

  private showBacktestView() {
    const content = this.container?.querySelector('#fq-content')
    if (!content) return
    content.innerHTML = `
      <div class="fq-view">
        <div class="fq-section-title">策略回测</div>
        <div class="fq-form">
          <div class="fq-form-row"><input type="text" id="fq-bt-strategy" value="valuation_deviation" class="input" placeholder="策略名称" /></div>
          <div class="fq-form-row"><input type="text" id="fq-bt-codes" placeholder="基金代码（逗号分隔）" class="input" /></div>
          <div class="fq-form-row">
            <input type="text" id="fq-bt-start" value="2020-01-01" class="input" style="width:140px" placeholder="开始日期" />
            <input type="text" id="fq-bt-end" value="2025-12-31" class="input" style="width:140px" placeholder="结束日期" />
          </div>
          <div class="fq-form-row"><button class="btn btn-primary" id="fq-bt-btn">运行回测</button></div>
        </div>
        <div id="fq-bt-result" class="fq-result-area"></div>
      </div>`
    content.querySelector('#fq-bt-btn')?.addEventListener('click', async () => {
      const strategy = (content.querySelector('#fq-bt-strategy') as HTMLInputElement)?.value.trim()
      const codes = (content.querySelector('#fq-bt-codes') as HTMLInputElement)?.value.trim()
      const start = (content.querySelector('#fq-bt-start') as HTMLInputElement)?.value.trim()
      const end = (content.querySelector('#fq-bt-end') as HTMLInputElement)?.value.trim()
      if (!codes) return toast.warning('请输入基金代码')
      const resultEl = content.querySelector('#fq-bt-result')
      if (resultEl) resultEl.innerHTML = '<div class="fq-loading">回测中...</div>'
      try {
        const res = await api.post(`${BASE}/backtest/run`, {
          strategy_name: strategy, fund_codes: codes.split(',').map(c => c.trim()),
          start_date: start, end_date: end,
        })
        const data = res.data || {}
        if (resultEl) {
          resultEl.innerHTML = `
            <div class="bt-result">
              <div class="bt-id">回测ID: ${data.backtest_id || '-'} | 状态: ${data.status || '-'}</div>
              <button class="btn btn-sm btn-outline mt-1" onclick="window.fqLoadBTResult('${data.backtest_id || ''}')">查看详情</button>
            </div>`
        }
      } catch (e) {
        if (resultEl) resultEl.innerHTML = '<div class="fq-error">回测失败</div>'
      }
    })
  }

  private showSignalView() {
    const content = this.container?.querySelector('#fq-content')
    if (!content) return
    content.innerHTML = `
      <div class="fq-view">
        <div class="fq-section-title">信号中心</div>
        <div class="fq-form-row">
          <input type="text" id="fq-sig-code" placeholder="基金代码（可选）" class="input" />
          <button class="btn btn-primary" id="fq-sig-btn">查询</button>
        </div>
        <div id="fq-sig-result" class="fq-result-area">
          <div class="fq-hint">点击查询查看最新信号</div>
        </div>
      </div>`
    content.querySelector('#fq-sig-btn')?.addEventListener('click', async () => {
      const code = (content.querySelector('#fq-sig-code') as HTMLInputElement)?.value.trim()
      const resultEl = content.querySelector('#fq-sig-result')
      if (resultEl) resultEl.innerHTML = '<div class="fq-loading">查询中...</div>'
      try {
        const url = code ? `${BASE}/signal/latest?fund_code=${code}` : `${BASE}/signal/latest`
        const res = await api.get(url)
        if (resultEl) resultEl.innerHTML = `<pre>${JSON.stringify(res.data || [], null, 2)}</pre>`
      } catch (e) {
        if (resultEl) resultEl.innerHTML = '<div class="fq-error">查询失败</div>'
      }
    })
  }

  private async showPortfolioView() {
    const content = this.container?.querySelector('#fq-content')
    if (!content) return
    try {
      const res = await api.get(`${BASE}/portfolio/status`)
      const data = res.data || {}
      content.innerHTML = `
        <div class="fq-view">
          <div class="fq-section-title">模拟组合</div>
          <div class="portfolio-summary">
            <div class="portfolio-stat">
              <span class="stat-label">总值</span>
              <span class="stat-value">¥${(data.total_value || 0).toFixed(2)}</span>
            </div>
            <div class="portfolio-stat">
              <span class="stat-label">现金</span>
              <span class="stat-value">¥${(data.cash || 0).toFixed(2)}</span>
            </div>
            <div class="portfolio-stat ${(data.return_pct || 0) >= 0 ? 'positive' : 'negative'}">
              <span class="stat-label">收益</span>
              <span class="stat-value">${(data.return_pct || 0).toFixed(2)}%</span>
            </div>
            <div class="portfolio-stat">
              <span class="stat-label">持仓</span>
              <span class="stat-value">${data.position_count || 0}</span>
            </div>
          </div>
          <pre class="mt-1">${JSON.stringify(data.positions || {}, null, 2)}</pre>
        </div>`
    } catch (e) {
      content.innerHTML = '<div class="fq-error">获取组合状态失败</div>'
    }
  }
}

// 暴露全局辅助方法
;(window as any).fqViewParams = async (name: string) => {
  try {
    const res = await api.get(`${BASE}/strategy/params/${name}`)
    toast.info(`策略 ${name} 参数: ${JSON.stringify(res.data)}`)
  } catch { /* ignore */ }
}

;(window as any).fqLoadBTResult = async (id: string) => {
  if (!id) return
  try {
    const res = await api.get(`${BASE}/backtest/result/${id}`)
    toast.info(`回测结果: ${JSON.stringify(res.data)}`)
  } catch { /* ignore */ }
}
