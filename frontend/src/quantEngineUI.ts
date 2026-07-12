import { api } from './api'
import { toast } from './toast'

const BASE = '/fund-quant'

export class QuantEngineUI {
  private container: HTMLDivElement | null = null
  private currentView = 'overview'

  init(container: HTMLDivElement) {
    this.container = container
    this.render()
    this.bindNav()
    this.loadOverview()
  }

  private render() {
    if (!this.container) return
    this.container.innerHTML = `
      <div class="quant-engine-page">
        <div class="section-card">
          <div class="section-header">
            <h2>🧠 量化引擎</h2>
            <span class="section-badge">AuroraCore</span>
          </div>
          <nav class="qe-nav" id="qe-nav">
            <button class="qe-nav-btn active" data-view="overview">📊 总览</button>
            <button class="qe-nav-btn" data-view="strategies">📋 策略</button>
            <button class="qe-nav-btn" data-view="factors">🧪 因子</button>
            <button class="qe-nav-btn" data-view="audit">📈 审计</button>
            <button class="qe-nav-btn" data-view="mining">⛏️ 挖掘</button>
          </nav>
          <div id="qe-content" class="qe-content">
            <div class="fq-loading">加载中...</div>
          </div>
        </div>
      </div>`
  }

  private bindNav() {
    const nav = this.container?.querySelector('#qe-nav')
    nav?.addEventListener('click', (e) => {
      const btn = (e.target as HTMLElement).closest('.qe-nav-btn') as HTMLElement
      if (!btn) return
      nav.querySelectorAll('.qe-nav-btn').forEach(b => b.classList.remove('active'))
      btn.classList.add('active')
      this.currentView = btn.dataset.view || 'overview'
      this.loadView(this.currentView)
    })
  }

  private loadView(view: string) {
    switch (view) {
      case 'overview': this.loadOverview(); break
      case 'strategies': this.loadStrategies(); break
      case 'factors': this.loadFactors(); break
      case 'audit': this.loadAudit(); break
      case 'mining': this.loadMining(); break
    }
  }

  // ═════════════════════════════════════════
  // 总览
  // ═════════════════════════════════════════

  private async loadOverview() {
    const el = this.container?.querySelector('#qe-content')
    if (!el) return
    // 获取策略数量和因子数量
    let strategyCount = 0, factorCount = 0, allFactors: any[] = []
    try {
      const fRes = await api.get(`${BASE}/factors/list?domain=fund`)
      const gRes = await api.get(`${BASE}/factors/list?domain=gold`)
      const strategyRes = await api.get(`${BASE}/strategy/list`)
      const allF = [...(fRes.data || []), ...(gRes.data || [])]
      allFactors = allF
      factorCount = allF.length
      strategyCount = (strategyRes.data || []).length
    } catch {}

    const factorTypes: Record<string, number> = {}
    allFactors.forEach((f: any) => { factorTypes[f.category] = (factorTypes[f.category] || 0) + 1 })

    el.innerHTML = `
      <div class="qe-overview">
        <div class="qe-stats-row">
          <div class="qe-stat-card"><div class="qe-stat-num">${strategyCount}</div><div class="qe-stat-label">已注册策略</div></div>
          <div class="qe-stat-card"><div class="qe-stat-num">${factorCount}</div><div class="qe-stat-label">已注册因子</div></div>
          <div class="qe-stat-card"><div class="qe-stat-num">${Object.keys(factorTypes).length}</div><div class="qe-stat-label">因子类别</div></div>
          <div class="qe-stat-card"><div class="qe-stat-num">core/factor/</div><div class="qe-stat-label">引擎路径</div></div>
        </div>
        <div class="qe-section-title">因子类别分布</div>
        <table class="data-table">
          <thead><tr><th>类别</th><th>数量</th><th>说明</th></tr></thead>
          <tbody>
            ${Object.entries(factorTypes).map(([cat, count]) => `
              <tr><td><span class="tag-${cat} factor-cat">${cat}</span></td><td>${count}</td><td>${this.catExplain(cat)}</td></tr>
            `).join('')}
          </tbody>
        </table>
      </div>`
  }

  private catExplain(cat: string): string {
    const m: Record<string, string> = {
      risk_adjusted: '风险调整收益', risk: '风险度量', flow: '资金流',
      structural: '结构特征', concentration: '集中度', manager: '基金经理',
      behavioral: '行为金融', futures: '期货结构', momentum: '动量趋势',
      sentiment: '市场情绪', fundamental: '基本面',
    }
    return m[cat] || cat
  }

  // ═════════════════════════════════════════
  // 策略浏览
  // ═════════════════════════════════════════

  private async loadStrategies() {
    const el = this.container?.querySelector('#qe-content')
    if (!el) return
    el.innerHTML = '<div class="fq-loading">加载中...</div>'
    try {
      const res = await api.get(`${BASE}/strategy/list`)
      const strategies = res.data || []
      const byType: Record<string, any[]> = {}
      strategies.forEach((s: any) => { (byType[s.type] = byType[s.type] || []).push(s) })

      el.innerHTML = Object.entries(byType).map(([type, list]) => `
        <div class="qe-section-title">${type} (${list.length})</div>
        <div class="strategy-grid">
          ${list.map((s: any) => `
            <div class="strategy-card">
              <div class="strategy-name">${s.name}</div>
              <div class="strategy-type tag-${s.type}">${s.type}</div>
              <div class="strategy-desc">${s.description || '-'}</div>
              <button class="btn btn-sm btn-outline mt-1" data-strategy='${JSON.stringify(s)}'>参数</button>
            </div>
          `).join('')}
        </div>
      `).join('')

      el.querySelectorAll('[data-strategy]').forEach(b => {
        b.addEventListener('click', () => {
          const s = JSON.parse((b as HTMLElement).dataset.strategy || '{}')
          toast.info(`${s.name} 参数: ${JSON.stringify(s.default_params, null, 2)}`)
        })
      })
    } catch { el.innerHTML = '<div class="fq-error">获取策略列表失败</div>' }
  }

  // ═════════════════════════════════════════
  // 因子管理
  // ═════════════════════════════════════════

  private async loadFactors() {
    const el = this.container?.querySelector('#qe-content')
    if (!el) return
    el.innerHTML = `
      <div class="qe-toolbar">
        <select id="qe-factor-domain" class="input" style="width:120px">
          <option value="fund">基金因子</option>
          <option value="gold">黄金因子</option>
          <option value="all">全部</option>
        </select>
        <button class="btn btn-primary" id="qe-reg-btn">注册因子</button>
        <button class="btn btn-outline" id="qe-refresh-btn">刷新</button>
      </div>
      <div id="qe-factor-table"><div class="fq-loading">加载中...</div></div>
      <div id="qe-factor-detail"></div>`

    this.refreshFactorTable()

    el.querySelector('#qe-reg-btn')?.addEventListener('click', () => this.registerFactors())
    el.querySelector('#qe-refresh-btn')?.addEventListener('click', () => this.refreshFactorTable())
    el.querySelector('#qe-factor-domain')?.addEventListener('change', () => this.refreshFactorTable())
  }

  private async refreshFactorTable() {
    const el = this.container?.querySelector('#qe-factor-table')
    if (!el) return
    const domain = (this.container?.querySelector('#qe-factor-domain') as HTMLSelectElement)?.value || 'fund'
    try {
      const domains = domain === 'all' ? ['fund', 'gold'] : [domain]
      let allFactors: any[] = []
      for (const d of domains) {
        const res = await api.get(`${BASE}/factors/list?domain=${d}`)
        allFactors = allFactors.concat(res.data || [])
      }

      el.innerHTML = `
        <div style="margin-bottom:8px;color:var(--text-secondary)">共 ${allFactors.length} 个因子</div>
        <table class="data-table">
          <thead><tr><th>名称</th><th>显示名</th><th>域</th><th>类别</th><th>方向</th><th>操作</th></tr></thead>
          <tbody>
            ${allFactors.map((f: any) => `
              <tr>
                <td><code>${f.name}</code></td>
                <td>${f.display_name}</td>
                <td>${f.domain === 'fund' ? '🏦' : '🥇'} ${f.domain}</td>
                <td><span class="tag-${f.category} factor-cat">${f.category}</span></td>
                <td>${f.direction > 0 ? '⬆️' : '⬇️'}</td>
                <td><button class="btn btn-sm btn-ghost qe-detail-btn" data-name="${f.name}">详情</button></td>
              </tr>
            `).join('')}
          </tbody>
        </table>`
      el.querySelectorAll('.qe-detail-btn').forEach(b => {
        b.addEventListener('click', () => {
          const name = (b as HTMLElement).dataset.name
          if (name) this.showFactorDetail(name)
        })
      })
    } catch { el.innerHTML = '<div class="fq-error">获取失败</div>' }
  }

  private async showFactorDetail(name: string) {
    const el = this.container?.querySelector('#qe-factor-detail')
    if (!el) return
    try {
      const res = await api.get(`${BASE}/factors/${name}`)
      if (!res.success) { el.innerHTML = `<div class="fq-error">${res.message}</div>`; return }
      const m = res.data
      el.innerHTML = `
        <div class="qe-section-title">📋 ${m.display_name} (${m.name})</div>
        <table class="data-table">
          <tr><td style="width:100px">类别</td><td><span class="tag-${m.category} factor-cat">${m.category}</span></td></tr>
          <tr><td>域</td><td>${m.domain}</td></tr>
          <tr><td>方向</td><td>${m.direction > 0 ? '⬆️ 越大越好' : '⬇️ 越小越好'}</td></tr>
          <tr><td>公式</td><td><code>${m.formula || '-'}</code></td></tr>
          <tr><td>参数</td><td><pre style="margin:0;font-size:.85em">${JSON.stringify(m.params, null, 2)}</pre></td></tr>
          <tr><td>说明</td><td>${m.description}</td></tr>
        </table>
        <button class="btn btn-sm btn-outline mt-1" onclick="this.closest('#qe-factor-detail').innerHTML=''">关闭</button>`
    } catch { el.innerHTML = '<div class="fq-error">获取详情失败</div>' }
  }

  private async registerFactors() {
    try {
      const res = await api.post(`${BASE}/factors/register`)
      if (res.success) {
        toast.success(`注册完成: 共 ${res.data.total} 个因子`)
        this.refreshFactorTable()
      }
    } catch { toast.error('注册失败') }
  }

  // ═════════════════════════════════════════
  // 因子审计
  // ═════════════════════════════════════════

  private async loadAudit() {
    const el = this.container?.querySelector('#qe-content')
    if (!el) return
    el.innerHTML = `
      <div class="qe-toolbar">
        <select id="qe-audit-domain" class="input" style="width:120px">
          <option value="fund">基金因子</option>
          <option value="gold">黄金因子</option>
        </select>
        <button class="btn btn-primary" id="qe-audit-run">运行审计</button>
      </div>
      <div class="qe-hint" style="margin-top:8px;color:var(--text-secondary);font-size:.85em">
        审计对所有已注册因子跑 IC 分析、Rank IC、IC_IR、分组收益 t 值、换手率。
        需要真实的净值/K线数据才能得到有效结果。
      </div>
      <div id="qe-audit-result" class="qe-result-area"></div>`

    el.querySelector('#qe-audit-run')?.addEventListener('click', () => this.runAudit())
  }

  private async runAudit() {
    const el = this.container?.querySelector('#qe-audit-result')
    if (!el) return
    const domain = (this.container?.querySelector('#qe-audit-domain') as HTMLSelectElement)?.value || 'fund'
    el.innerHTML = '<div class="fq-loading">⏳ 审计进行中（可能需要几秒到几十秒）...</div>'
    try {
      const res = await api.get(`${BASE}/factors/audit?domain=${domain}&years=3`)
      const rows = res.data || []
      if (!rows.length) {
        el.innerHTML = '<div class="qe-warning">审计完成但无有效数据，需要真实数据源才能计算IC。</div>'
        return
      }
      const mapV = (v: string) => {
        const vv = v.toLowerCase()
        if (vv === 'strong') return 0; if (vv === 'usable') return 1
        if (vv === 'weak') return 2; return 3
      }
      rows.sort((a: any, b: any) => mapV(a['结论']) - mapV(b['结论']))

      el.innerHTML = `
        <div style="margin-bottom:8px;color:var(--text-secondary)">审计 ${rows.length} 个 ${domain} 域因子</div>
        <table class="data-table">
          <thead><tr><th>因子</th><th>类别</th><th>Rank IC</th><th>IC_IR</th><th>Spread t</th><th>换手率</th><th>结论</th></tr></thead>
          <tbody>
            ${rows.map((r: any) => `
              <tr>
                <td><code>${r['因子']}</code></td>
                <td><span class="tag-${r['类别']} factor-cat">${r['类别']}</span></td>
                <td>${r['Rank IC']}</td>
                <td>${r['IC_IR']}</td>
                <td>${r['Spread t']}</td>
                <td>${r['换手率']}</td>
                <td><span class="factor-verdict-${r['结论']}">${r['结论']}</span></td>
              </tr>
            `).join('')}
          </tbody>
        </table>`
    } catch { el.innerHTML = '<div class="fq-error">审计失败，请确保已注册因子</div>' }
  }

  // ═════════════════════════════════════════
  // 因子挖掘
  // ═════════════════════════════════════════

  private async loadMining() {
    const el = this.container?.querySelector('#qe-content')
    if (!el) return
    el.innerHTML = `
      <div class="qe-section-title">⛏️ 因子挖掘管道</div>
      <div class="qe-methods">
        <div class="qe-method-card">
          <div class="qe-method-title">🔗 组合因子搜索</div>
          <div class="qe-method-desc">对已有因子做 {+, -, *, /, ortho} 运算 → IC 筛选。遍历所有二元组合。</div>
          <div class="qe-form-row" style="margin-top:8px">
            <select id="qe-mine-domain" class="input" style="width:120px">
              <option value="fund">基金因子</option>
              <option value="gold">黄金因子</option>
            </select>
            <button class="btn btn-primary" id="qe-mine-run">运行搜索</button>
          </div>
        </div>
        <div class="qe-method-card">
          <div class="qe-method-title">🧬 GP 公式搜索</div>
          <div class="qe-method-desc">遗传规划生成新因子公式（代数=5，种群=50）。交叉+变异→IC适应度评估。</div>
          <div class="qe-form-row" style="margin-top:8px">
            <button class="btn btn-outline" id="qe-mine-gp-run">运行GP（计算量大）</button>
          </div>
        </div>
      </div>
      <div id="qe-mine-result" class="qe-result-area"></div>`

    el.querySelector('#qe-mine-run')?.addEventListener('click', () => this.runMiningCombo())
    el.querySelector('#qe-mine-gp-run')?.addEventListener('click', () => this.runMiningGP())
  }

  private async runMiningCombo() {
    const el = this.container?.querySelector('#qe-mine-result')
    if (!el) return
    el.innerHTML = '<div class="fq-loading">⏳ 组合搜索需要真实数据源才能在当前环境中运行...</div>'
    // 组合搜索需要完整的因子 compute + 数据源，前端只展示概念
    el.innerHTML = `
      <div class="qe-hint">
        <p><strong>组合因子搜索流程：</strong></p>
        <ol style="margin-top:8px;padding-left:20px">
          <li>列举所有基础因子对的 5 种运算 {+, -, *, /, ortho}</li>
          <li>对每个组合因子跑 IC 评价</li>
          <li>按 |Rank IC| 排序，相关性去重 (ρ &lt; 0.7)</li>
          <li>输出通过阈值的候选因子列表</li>
        </ol>
        <p style="margin-top:8px">需要回测服务器端运行，前端为控制面板。</p>
      </div>`
  }

  private async runMiningGP() {
    const el = this.container?.querySelector('#qe-mine-result')
    if (!el) return
    el.innerHTML = `
      <div class="qe-hint">
        <p><strong>GP 公式搜索：</strong></p>
        <ol style="margin-top:8px;padding-left:20px">
          <li>基础算子：+ − × ÷ rank zscore winsorize ts_mean ts_std ts_delta</li>
          <li>种群初始化 → 适应度评估 (IC) → 锦标赛选择</li>
          <li>交叉 + 变异 → 下一代</li>
          <li>5 代后输出 Top-10 候选因子</li>
        </ol>
        <p style="margin-top:8px">GP 搜索计算量较大，建议后端异步运行。</p>
      </div>`
  }
}
