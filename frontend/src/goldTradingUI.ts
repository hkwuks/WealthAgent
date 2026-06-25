import { api } from './api'
import { toast } from './toast'

const STRATEGY_LABELS: Record<string, { name: string; icon: string; desc: string }> = {
  trend_following: { name: '趋势跟踪', icon: '📈', desc: 'MA排列 + Donchian突破 + ATR止损' },
  mean_reversion: { name: '均值回归', icon: '🔄', desc: 'BB下轨+RSI超卖做多 / BB上轨+RSI超买做空' },
  ml_predictor: { name: 'ML预测', icon: '🤖', desc: 'LightGBM/XGBoost/Ridge滑动窗口预测' },
}

export class GoldTradingUI {
  private container: HTMLDivElement | null = null
  private strategies: any[] = []
  private isBacktesting = false
  private isComparing = false
  private isGeneratingSignal = false
  private isRunningSensitivity = false
  private isRunningValidation = false

  init(container: HTMLDivElement) {
    this.container = container
    this.render()
    this.bindEvents()
    this.loadStrategies()
  }

  private render() {
    if (!this.container) return

    this.container.innerHTML = `
      <div class="gold-trading-page">
        <div class="section-card">
          <div class="section-header">
            <h2>📊 黄金量化交易</h2>
          </div>

          <!-- 策略列表 -->
          <div class="prediction-settings">
            <h3>可用策略</h3>
            <div id="strategy-cards" class="market-cards">
              <div class="market-card" style="text-align:center;color:#888;">加载中...</div>
            </div>
          </div>

          <!-- 信号生成 -->
          <div class="prediction-settings">
            <h3>交易建议生成</h3>
            <div class="settings-row">
              <label>策略:</label>
              <select id="sig-strategy-select">
                <option value="trend_following">趋势跟踪</option>
                <option value="mean_reversion">均值回归</option>
                <option value="ml_predictor">ML预测</option>
              </select>
              <button class="btn btn-primary" id="sig-generate-btn">生成交易建议</button>
            </div>
            <div id="sig-result" style="display:none;margin-top:12px;"></div>
          </div>

          <!-- 单策略回测 -->
          <div class="backtest-settings">
            <h3>策略回测</h3>
            <div class="settings-row">
              <label>策略:</label>
              <select id="bt-strategy-select">
                <option value="trend_following">趋势跟踪</option>
                <option value="mean_reversion">均值回归</option>
                <option value="ml_predictor">ML预测</option>
              </select>
              <label>合约:</label>
              <select id="bt-symbol-select">
                <option value="AU0">AU0 (主力)</option>
              </select>
              <label>起始日:</label>
              <input type="date" id="bt-start-date" value="2024-01-01" />
              <label>截止日:</label>
              <input type="date" id="bt-end-date" value="2025-12-31" />
              <label>资金:</label>
              <input type="number" id="bt-capital" value="1000000" min="100000" step="100000" style="width:120px" />
              <button class="btn btn-primary" id="bt-run-btn">运行回测</button>
            </div>
            <div id="bt-params-container" style="margin-top:8px;display:none;">
              <h4>策略参数</h4>
              <div id="bt-params-row" class="settings-row"></div>
            </div>
          </div>
          <div class="backtest-results" id="bt-results" style="display:none;">
            <h3>回测结果</h3>
            <div id="bt-report"></div>
          </div>

          <!-- 多策略对比 -->
          <div class="backtest-settings">
            <h3>多策略对比</h3>
            <div class="settings-row">
              <label>起始日:</label>
              <input type="date" id="cmp-start-date" value="2024-01-01" />
              <label>截止日:</label>
              <input type="date" id="cmp-end-date" value="2025-12-31" />
              <button class="btn btn-secondary" id="cmp-run-btn">运行对比</button>
            </div>
          </div>
          <div class="backtest-results" id="cmp-results" style="display:none;">
            <h3>对比结果</h3>
            <div id="cmp-report"></div>
          </div>

          <!-- 参数敏感性分析 -->
          <div class="backtest-settings">
            <h3>参数敏感性分析</h3>
            <div class="settings-row">
              <label>策略:</label>
              <select id="sens-strategy-select">
                <option value="trend_following">趋势跟踪</option>
                <option value="mean_reversion">均值回归</option>
              </select>
              <label>起始日:</label>
              <input type="date" id="sens-start-date" value="2024-01-01" />
              <label>截止日:</label>
              <input type="date" id="sens-end-date" value="2024-12-31" />
              <button class="btn btn-secondary" id="sens-run-btn">运行敏感性分析</button>
            </div>
          </div>
          <div class="backtest-results" id="sens-results" style="display:none;">
            <h3>敏感性分析结果</h3>
            <div id="sens-report"></div>
          </div>

          <!-- In/Out样本验证 + 场景验证 -->
          <div class="backtest-settings">
            <h3>In/Out样本验证 + 场景验证</h3>
            <div class="settings-row">
              <label>策略:</label>
              <select id="val-strategy-select">
                <option value="trend_following">趋势跟踪</option>
                <option value="mean_reversion">均值回归</option>
              </select>
              <label>起始日:</label>
              <input type="date" id="val-start-date" value="2020-01-01" />
              <label>截止日:</label>
              <input type="date" id="val-end-date" value="2025-12-31" />
              <button class="btn btn-secondary" id="val-run-btn">运行验证</button>
            </div>
          </div>
          <div class="backtest-results" id="val-results" style="display:none;">
            <h3>验证结果</h3>
            <div id="val-report"></div>
          </div>

          <!-- 最近信号 -->
          <div class="prediction-settings">
            <h3>最近信号</h3>
            <button class="btn btn-secondary" id="signals-btn">刷新信号</button>
            <div id="signals-list" style="margin-top:12px;"></div>
          </div>

          <!-- 风控状态 -->
          <div class="prediction-settings">
            <h3>风控状态</h3>
            <button class="btn btn-secondary" id="risk-btn">查看风控</button>
            <div id="risk-status" style="margin-top:12px;"></div>
          </div>

          <!-- 数据同步 -->
          <div class="prediction-settings">
            <h3>数据同步</h3>
            <div class="settings-row">
              <button class="btn btn-secondary" id="sync-btn">同步K线数据</button>
            </div>
          </div>
        </div>
      </div>
    `
  }

  private bindEvents() {
    document.getElementById('bt-run-btn')?.addEventListener('click', () => this.runBacktest())
    document.getElementById('cmp-run-btn')?.addEventListener('click', () => this.runCompare())
    document.getElementById('sig-generate-btn')?.addEventListener('click', () => this.generateSignal())
    document.getElementById('sens-run-btn')?.addEventListener('click', () => this.runSensitivity())
    document.getElementById('val-run-btn')?.addEventListener('click', () => this.runValidation())
    document.getElementById('signals-btn')?.addEventListener('click', () => this.loadSignals())
    document.getElementById('risk-btn')?.addEventListener('click', () => this.loadRiskStatus())
    document.getElementById('sync-btn')?.addEventListener('click', () => this.syncData())

    document.getElementById('bt-strategy-select')?.addEventListener('change', (e) => {
      const name = (e.target as HTMLSelectElement).value
      this.renderStrategyParams(name)
    })
  }

  private async loadStrategies() {
    try {
      const resp = await api.getTradingStrategies()
      if (resp.success && resp.data) {
        this.strategies = resp.data
        this.renderStrategyCards()
        this.renderStrategyParams('trend_following')
      }
    } catch (e) {
      console.error('Failed to load strategies:', e)
    }
  }

  private renderStrategyCards() {
    const container = document.getElementById('strategy-cards')
    if (!container) return

    container.innerHTML = this.strategies.map(s => {
      const label = STRATEGY_LABELS[s.strategy_id] || { name: s.strategy_name, icon: '📊', desc: s.description }
      return `
        <div class="market-card" style="cursor:default;">
          <div class="market-card-title">${label.icon} ${label.name}</div>
          <div style="font-size:12px;color:#888;margin-top:4px;">${label.desc}</div>
        </div>
      `
    }).join('')
  }

  private renderStrategyParams(strategyName: string) {
    const strategy = this.strategies.find(s => s.strategy_id === strategyName)
    const container = document.getElementById('bt-params-container')
    const row = document.getElementById('bt-params-row')
    if (!container || !row || !strategy) {
      if (container) container.style.display = 'none'
      return
    }

    const ranges = strategy.param_ranges || {}
    const defaults = strategy.default_params || {}
    const paramKeys = Object.keys(ranges)

    if (paramKeys.length === 0) {
      container.style.display = 'none'
      return
    }

    container.style.display = 'block'
    row.innerHTML = paramKeys.map(key => {
      const options = ranges[key] as number[]
      const defaultVal = defaults[key]
      const label = this.getParamLabel(key)
      return `
        <label>${label}:</label>
        <select id="bt-param-${key}">
          ${options.map(v => `<option value="${v}" ${v === defaultVal || String(v) === String(defaultVal) ? 'selected' : ''}>${v}</option>`).join('')}
        </select>
      `
    }).join('')
  }

  private getParamLabel(key: string): string {
    const labels: Record<string, string> = {
      ma_periods: 'MA周期', atr_period: 'ATR周期', atr_stop_multiplier: 'ATR止损倍数',
      donchian_entry: 'Donchian入场', donchian_exit: 'Donchian出场', position_size: '仓位',
      boll_period: 'BB周期', boll_dev: 'BB标准差', rsi_period: 'RSI周期',
      rsi_overbought: 'RSI超买', rsi_oversold: 'RSI超卖', window_size: '窗口大小',
      predict_interval: '预测间隔', change_threshold: '涨跌阈值', max_holding_bars: '最大持仓',
    }
    return labels[key] || key
  }

  // ===== 信号生成 =====

  private async generateSignal() {
    if (this.isGeneratingSignal) return

    const strategyName = (document.getElementById('sig-strategy-select') as HTMLSelectElement)?.value || 'trend_following'
    this.isGeneratingSignal = true
    const btn = document.getElementById('sig-generate-btn') as HTMLButtonElement
    if (btn) { btn.disabled = true; btn.textContent = '生成中...' }

    try {
      const resp = await api.generateTradingSignal(strategyName)
      if (resp.success && resp.data) {
        this.displaySignalResult(resp.data)
        toast.success('交易建议已生成')
      } else {
        toast.error('信号生成失败')
      }
    } catch (e) {
      console.error('Signal generation failed:', e)
      toast.error('信号生成失败')
    } finally {
      this.isGeneratingSignal = false
      if (btn) { btn.disabled = false; btn.textContent = '生成交易建议' }
    }
  }

  private displaySignalResult(data: any) {
    const container = document.getElementById('sig-result')
    if (!container) return
    container.style.display = 'block'

    if (!data.signal && !data.direction) {
      container.innerHTML = '<p style="color:#888;">当前无交易信号</p>'
      return
    }

    const dir = data.direction || ''
    const dirLabel: Record<string, string> = { long: '做多', short: '做空', close_long: '平多', close_short: '平空' }
    const isBullish = dir === 'long'
    const cls = isBullish ? 'positive' : dir === 'short' ? 'negative' : ''
    const riskPassed = data.risk_check?.passed !== false

    container.innerHTML = `
      <div class="prediction-card ${cls}">
        <div class="prediction-model">${data.strategy || '--'} 交易建议</div>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin-top:8px;">
          ${this.cell('方向', dirLabel[dir] || dir, cls)}
          ${this.cell('合约', data.symbol || '--')}
          ${this.cell('价格', data.price ? `¥${data.price}` : '--')}
          ${this.cell('数量', `${data.volume ?? 1}手`)}
          ${this.cell('止损', data.stop_loss ? `¥${data.stop_loss}` : '--')}
          ${this.cell('止盈', data.take_profit ? `¥${data.take_profit}` : '--')}
          ${this.cell('置信度', data.confidence != null ? `${(data.confidence * 100).toFixed(0)}%` : '--')}
          ${this.cell('风控', riskPassed ? '✅ 通过' : `⚠️ ${data.risk_check?.reason || '未通过'}`, riskPassed ? '' : 'negative')}
        </div>
        <div style="margin-top:8px;font-size:12px;color:#888;">${data.reason || ''}</div>
      </div>
    `
  }

  private cell(label: string, value: string, cls?: string): string {
    return `<div style="padding:4px 6px;background:rgba(0,0,0,0.03);border-radius:4px;">
      <div style="font-size:10px;color:#888;">${label}</div>
      <div style="font-size:13px;font-weight:600;${cls === 'positive' ? 'color:#22c55e' : cls === 'negative' ? 'color:#ef4444' : ''}">${value}</div>
    </div>`
  }

  // ===== 回测 =====

  private async runBacktest() {
    if (this.isBacktesting) return

    const strategyName = (document.getElementById('bt-strategy-select') as HTMLSelectElement)?.value || 'trend_following'
    const symbol = (document.getElementById('bt-symbol-select') as HTMLSelectElement)?.value || 'AU0'
    const startDate = (document.getElementById('bt-start-date') as HTMLInputElement)?.value || '2024-01-01'
    const endDate = (document.getElementById('bt-end-date') as HTMLInputElement)?.value || '2025-12-31'
    const capital = Number((document.getElementById('bt-capital') as HTMLInputElement)?.value || 1000000)
    const params = this.collectParams(strategyName)

    this.isBacktesting = true
    const btn = document.getElementById('bt-run-btn') as HTMLButtonElement
    if (btn) { btn.disabled = true; btn.textContent = '回测中...' }

    try {
      const resp = await api.runTradingBacktest({
        strategy_name: strategyName, symbol, period: 'd',
        start_date: startDate, end_date: endDate,
        capital, params: Object.keys(params).length > 0 ? params : undefined,
      })
      if (resp.success && resp.data) {
        this.displayBacktestReport(resp.data)
        toast.success('回测完成')
      } else {
        toast.error('回测失败')
      }
    } catch (e) {
      console.error('Backtest failed:', e)
      toast.error('回测失败')
    } finally {
      this.isBacktesting = false
      if (btn) { btn.disabled = false; btn.textContent = '运行回测' }
    }
  }

  private collectParams(strategyName: string): Record<string, any> {
    const strategy = this.strategies.find(s => s.strategy_id === strategyName)
    if (!strategy) return {}

    const ranges = strategy.param_ranges || {}
    const defaults = strategy.default_params || {}
    const params: Record<string, any> = {}

    for (const key of Object.keys(ranges)) {
      const el = document.getElementById(`bt-param-${key}`) as HTMLSelectElement
      if (el) {
        const val = el.value
        if (key === 'ma_periods') {
          params[key] = val.split(',').map(Number)
        } else {
          params[key] = Number(val)
        }
      }
    }

    const diff: Record<string, any> = {}
    for (const [k, v] of Object.entries(params)) {
      const def = defaults[k]
      if (JSON.stringify(v) !== JSON.stringify(def)) {
        diff[k] = v
      }
    }
    return diff
  }

  private displayBacktestReport(data: any) {
    const container = document.getElementById('bt-results')
    const report = document.getElementById('bt-report')
    if (!container || !report) return

    container.style.display = 'block'
    const perf = data.report?.performance || {}
    const risk = data.report?.risk || {}
    const trades = data.report?.trades || {}
    const cost = data.report?.cost || {}
    const meta = data.report?.meta || {}

    const label = STRATEGY_LABELS[data.strategy] || { name: data.strategy, icon: '📊' }
    const ret = perf.total_return ?? 0
    const retClass = ret >= 0 ? 'positive' : 'negative'

    report.innerHTML = `
      <div class="prediction-card ${retClass}">
        <div class="prediction-model">${label.icon} ${label.name} 回测报告</div>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px;margin-top:12px;">
          ${this.reportCell('总收益率', `${ret >= 0 ? '+' : ''}${ret}%`, retClass)}
          ${this.reportCell('年化收益', `${perf.annualized_return ?? 0}%`, (perf.annualized_return ?? 0) >= 0 ? 'positive' : 'negative')}
          ${this.reportCell('夏普比率', `${perf.sharpe_ratio ?? 0}`)}
          ${this.reportCell('Sortino', `${perf.sortino_ratio ?? 0}`)}
          ${this.reportCell('Calmar', `${perf.calmar_ratio ?? 0}`)}
          ${this.reportCell('胜率', `${perf.win_rate ?? 0}%`)}
          ${this.reportCell('盈亏比', perf.profit_factor != null ? `${perf.profit_factor}` : '--')}
          ${this.reportCell('最大回撤', `${risk.max_drawdown ?? 0}%`, 'negative')}
          ${this.reportCell('VaR(95%)', `¥${risk.var_95 ?? 0}`)}
          ${this.reportCell('CVaR(95%)', `¥${risk.cvar_95 ?? 0}`)}
          ${this.reportCell('波动率', `${risk.volatility ?? 0}%`)}
          ${this.reportCell('交易次数', `${trades.total_count ?? 0}`)}
          ${this.reportCell('平均持仓', `${trades.avg_holding_bars ?? 0} bar`)}
          ${this.reportCell('总手续费', `¥${cost.total_commission ?? 0}`)}
          ${this.reportCell('净盈亏', `¥${cost.net_pnl ?? 0}`)}
        </div>
        <div style="margin-top:12px;font-size:12px;color:#888;">
          资金: ¥${(meta.capital ?? 0).toLocaleString()} | ${meta.start_date ?? ''} ~ ${meta.end_date ?? ''} | ${meta.total_days ?? 0}天 | 信号:${data.signal_count ?? 0} 成交:${data.trade_count ?? 0}
        </div>
      </div>
    `
  }

  private reportCell(label: string, value: string, cls?: string): string {
    return `<div style="padding:6px 8px;background:rgba(0,0,0,0.03);border-radius:4px;">
      <div style="font-size:11px;color:#888;">${label}</div>
      <div style="font-size:14px;font-weight:600;${cls === 'positive' ? 'color:#22c55e' : cls === 'negative' ? 'color:#ef4444' : ''}">${value}</div>
    </div>`
  }

  // ===== 多策略对比 =====

  private async runCompare() {
    if (this.isComparing) return

    const startDate = (document.getElementById('cmp-start-date') as HTMLInputElement)?.value || '2024-01-01'
    const endDate = (document.getElementById('cmp-end-date') as HTMLInputElement)?.value || '2025-12-31'

    this.isComparing = true
    const btn = document.getElementById('cmp-run-btn') as HTMLButtonElement
    if (btn) { btn.disabled = true; btn.textContent = '对比中...' }

    try {
      const resp = await api.compareStrategies({
        strategy_names: ['trend_following', 'mean_reversion', 'ml_predictor'],
        symbol: 'AU0', period: 'd',
        start_date: startDate, end_date: endDate, capital: 1000000,
      })
      if (resp.success && resp.data) {
        this.displayCompareReport(resp.data)
        toast.success('对比完成')
      } else {
        toast.error('对比失败')
      }
    } catch (e) {
      console.error('Compare failed:', e)
      toast.error('对比失败')
    } finally {
      this.isComparing = false
      if (btn) { btn.disabled = false; btn.textContent = '运行对比' }
    }
  }

  private displayCompareReport(data: any) {
    const container = document.getElementById('cmp-results')
    const report = document.getElementById('cmp-report')
    if (!container || !report) return

    container.style.display = 'block'
    const strategies = data.strategies || {}
    const comparison = data.comparison || {}
    const errors = data.errors || []
    const names = Object.keys(strategies)

    if (names.length === 0) {
      report.innerHTML = '<p style="color:#888;">无对比数据</p>'
      return
    }

    const metrics = [
      { key: 'total_return', label: '总收益率', suffix: '%' },
      { key: 'annualized_return', label: '年化收益', suffix: '%' },
      { key: 'sharpe_ratio', label: '夏普', suffix: '' },
      { key: 'sortino_ratio', label: 'Sortino', suffix: '' },
      { key: 'max_drawdown', label: '最大回撤', suffix: '%' },
      { key: 'win_rate', label: '胜率', suffix: '%' },
      { key: 'profit_factor', label: '盈亏比', suffix: '' },
    ]

    report.innerHTML = `
      <div class="metrics-table-container">
        <table class="metrics-table">
          <thead>
            <tr>
              <th>指标</th>
              ${names.map((n: string) => `<th>${(STRATEGY_LABELS[n] || { name: n }).name}</th>`).join('')}
            </tr>
          </thead>
          <tbody>
            ${metrics.map(m => `
              <tr>
                <td>${m.label}</td>
                ${names.map((n: string) => {
                  const perf = strategies[n]?.performance || {}
                  const risk = strategies[n]?.risk || {}
                  const val = perf[m.key] ?? risk[m.key] ?? '--'
                  return `<td>${val !== '--' ? val + m.suffix : '--'}</td>`
                }).join('')}
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
      ${comparison.sharpe_ranking ? `
        <div style="margin-top:12px;font-size:12px;color:#888;">
          夏普排名: ${comparison.sharpe_ranking.map((r: any) => `${(STRATEGY_LABELS[r[0]] || {name: r[0]}).name}(${r[1]})`).join(' > ')}
        </div>
      ` : ''}
      ${errors.length > 0 ? `<div style="margin-top:8px;color:#ef4444;font-size:12px;">错误: ${errors.join('; ')}</div>` : ''}
    `
  }

  // ===== 参数敏感性分析 =====

  private async runSensitivity() {
    if (this.isRunningSensitivity) return

    const strategyName = (document.getElementById('sens-strategy-select') as HTMLSelectElement)?.value || 'trend_following'
    const startDate = (document.getElementById('sens-start-date') as HTMLInputElement)?.value || '2024-01-01'
    const endDate = (document.getElementById('sens-end-date') as HTMLInputElement)?.value || '2024-12-31'

    this.isRunningSensitivity = true
    const btn = document.getElementById('sens-run-btn') as HTMLButtonElement
    if (btn) { btn.disabled = true; btn.textContent = '分析中...' }

    try {
      const resp = await api.runSensitivity({
        strategy_name: strategyName, symbol: 'AU0', period: 'd',
        start_date: startDate, end_date: endDate, capital: 1000000,
      })
      if (resp.success && resp.data) {
        this.displaySensitivityReport(resp.data)
        toast.success('敏感性分析完成')
      } else {
        toast.error('敏感性分析失败')
      }
    } catch (e) {
      console.error('Sensitivity failed:', e)
      toast.error('敏感性分析失败')
    } finally {
      this.isRunningSensitivity = false
      if (btn) { btn.disabled = false; btn.textContent = '运行敏感性分析' }
    }
  }

  private displaySensitivityReport(data: any) {
    const container = document.getElementById('sens-results')
    const report = document.getElementById('sens-report')
    if (!container || !report) return

    container.style.display = 'block'
    const items = data.sensitivity_data || []
    const conclusion = data.conclusion || {}

    // 按参数分组展示
    const byParam: Record<string, any[]> = {}
    for (const item of items) {
      byParam[item.param_name] = byParam[item.param_name] || []
      byParam[item.param_name].push(item)
    }

    let html = ''
    for (const [param, values] of Object.entries(byParam)) {
      const assessment = conclusion[param] || {}
      html += `
        <div style="margin-bottom:16px;">
          <h4>${this.getParamLabel(param)} ${assessment.status ? `— ${assessment.status}` : ''}</h4>
          <table class="metrics-table" style="font-size:12px;">
            <thead><tr><th>参数值</th><th>Sharpe</th><th>MaxDD%</th><th>收益率%</th><th>胜率%</th></tr></thead>
            <tbody>
              ${values.map((v: any) => `<tr>
                <td>${v.param_value}</td>
                <td>${v.sharpe ?? '--'}</td>
                <td>${v.max_dd ?? '--'}</td>
                <td>${v.total_return ?? '--'}</td>
                <td>${v.win_rate ?? '--'}</td>
              </tr>`).join('')}
            </tbody>
          </table>
          ${assessment.detail ? `<div style="font-size:11px;color:#888;margin-top:4px;">${assessment.detail}</div>` : ''}
        </div>
      `
    }

    report.innerHTML = html || '<p style="color:#888;">无敏感性数据</p>'
  }

  // ===== In/Out样本验证 + 场景验证 =====

  private async runValidation() {
    if (this.isRunningValidation) return

    const strategyName = (document.getElementById('val-strategy-select') as HTMLSelectElement)?.value || 'trend_following'
    const startDate = (document.getElementById('val-start-date') as HTMLInputElement)?.value || '2020-01-01'
    const endDate = (document.getElementById('val-end-date') as HTMLInputElement)?.value || '2025-12-31'

    this.isRunningValidation = true
    const btn = document.getElementById('val-run-btn') as HTMLButtonElement
    if (btn) { btn.disabled = true; btn.textContent = '验证中...' }

    try {
      const resp = await api.runValidation({
        strategy_name: strategyName, symbol: 'AU0', period: 'd',
        start_date: startDate, end_date: endDate, capital: 1000000,
      })
      if (resp.success && resp.data) {
        this.displayValidationReport(resp.data)
        toast.success('验证完成')
      } else {
        toast.error('验证失败')
      }
    } catch (e) {
      console.error('Validation failed:', e)
      toast.error('验证失败')
    } finally {
      this.isRunningValidation = false
      if (btn) { btn.disabled = false; btn.textContent = '运行验证' }
    }
  }

  private displayValidationReport(data: any) {
    const container = document.getElementById('val-results')
    const report = document.getElementById('val-report')
    if (!container || !report) return

    container.style.display = 'block'

    const sampleVal = data.sample_validation || {}
    const scenarioVal = data.scenario_validation || {}

    let html = ''

    // In/Out样本
    if (sampleVal.in_sample && sampleVal.out_sample) {
      const deg = sampleVal.sharpe_degradation_pct ?? 0
      const risk = sampleVal.overfitting_risk ?? '--'
      const riskColor = risk === '低' ? '#22c55e' : risk === '中' ? '#f59e0b' : '#ef4444'

      html += `
        <div style="margin-bottom:16px;">
          <h4>In/Out样本验证</h4>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <div>
              <div style="font-size:12px;color:#888;">In-sample (${sampleVal.in_bars ?? 0} bars)</div>
              <div>Sharpe: ${sampleVal.in_sample.performance?.sharpe_ratio ?? '--'} | Return: ${sampleVal.in_sample.performance?.total_return ?? '--'}%</div>
            </div>
            <div>
              <div style="font-size:12px;color:#888;">Out-sample (${sampleVal.out_bars ?? 0} bars)</div>
              <div>Sharpe: ${sampleVal.out_sample.performance?.sharpe_ratio ?? '--'} | Return: ${sampleVal.out_sample.performance?.total_return ?? '--'}%</div>
            </div>
          </div>
          <div style="margin-top:8px;">
            Sharpe退化: <strong>${deg}%</strong> |
            过拟合风险: <strong style="color:${riskColor}">${risk}</strong>
          </div>
        </div>
      `
    }

    // 场景验证
    const scenarios = scenarioVal.results || []
    if (scenarios.length > 0) {
      html += `
        <div>
          <h4>场景验证</h4>
          <table class="metrics-table" style="font-size:12px;">
            <thead><tr><th>场景</th><th>描述</th><th>期望</th><th>状态</th><th>Sharpe</th><th>Return%</th><th>MaxDD%</th></tr></thead>
            <tbody>
              ${scenarios.map((s: any) => `<tr>
                <td>${s.scenario}</td>
                <td>${s.description}</td>
                <td style="font-size:11px;">${s.expected}</td>
                <td style="color:${s.status === '通过' ? '#22c55e' : '#ef4444'}">${s.status}</td>
                <td>${s.report?.sharpe ?? '--'}</td>
                <td>${s.report?.total_return ?? '--'}</td>
                <td>${s.report?.max_drawdown ?? '--'}</td>
              </tr>`).join('')}
            </tbody>
          </table>
          <div style="margin-top:8px;font-size:12px;color:#888;">
            全部通过: ${scenarioVal.all_passed ? '✅ 是' : '❌ 否'}
          </div>
        </div>
      `
    }

    report.innerHTML = html || '<p style="color:#888;">无验证数据</p>'
  }

  // ===== 信号 =====

  private async loadSignals() {
    try {
      const resp = await api.getTradingSignals(undefined, 20)
      if (resp.success && resp.data) {
        this.displaySignals(resp.data)
        toast.success('信号已刷新')
      } else {
        toast.error('获取信号失败')
      }
    } catch (e) {
      console.error('Signals failed:', e)
      toast.error('获取信号失败')
    }
  }

  private displaySignals(signals: any[]) {
    const container = document.getElementById('signals-list')
    if (!container) return

    if (!signals || signals.length === 0) {
      container.innerHTML = '<p style="color:#888;font-size:13px;">暂无信号记录</p>'
      return
    }

    const dirLabel: Record<string, string> = { long: '做多', short: '做空', close_long: '平多', close_short: '平空' }

    container.innerHTML = `
      <table class="metrics-table" style="font-size:12px;">
        <thead><tr><th>时间</th><th>策略</th><th>方向</th><th>价格</th><th>数量</th><th>置信度</th><th>原因</th></tr></thead>
        <tbody>
          ${signals.map(s => {
            const dir = s.direction || ''
            const dirClass = dir.includes('long') && !dir.includes('close') ? 'positive' :
                             dir.includes('short') && !dir.includes('close') ? 'negative' : ''
            return `<tr>
              <td>${s.created_at ? new Date(s.created_at).toLocaleString('zh-CN') : '--'}</td>
              <td>${s.strategy_name || s.strategy_id || '--'}</td>
              <td class="${dirClass}">${dirLabel[dir] || dir}</td>
              <td>${s.price ?? '--'}</td>
              <td>${s.volume ?? 1}</td>
              <td>${s.confidence != null ? (s.confidence * 100).toFixed(0) + '%' : '--'}</td>
              <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${s.reason || ''}">${s.reason || '--'}</td>
            </tr>`
          }).join('')}
        </tbody>
      </table>
    `
  }

  // ===== 风控状态 =====

  private async loadRiskStatus() {
    try {
      const resp = await api.getRiskStatus()
      if (resp.success && resp.data) {
        this.displayRiskStatus(resp.data)
      } else {
        toast.error('获取风控状态失败')
      }
    } catch (e) {
      console.error('Risk status failed:', e)
      toast.error('获取风控状态失败')
    }
  }

  private displayRiskStatus(data: any) {
    const container = document.getElementById('risk-status')
    if (!container) return

    const checks = data.checks || []
    container.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px;">
        ${checks.map((c: any) => `
          <div style="padding:8px;background:rgba(0,0,0,0.03);border-radius:4px;">
            <div style="font-size:11px;color:#888;">${c.name}</div>
            <div>阈值: ${c.threshold} | 状态: <span style="color:#22c55e;">${c.status}</span></div>
          </div>
        `).join('')}
      </div>
      <div style="margin-top:8px;font-size:12px;color:#888;">最近信号数: ${data.recent_signal_count ?? 0}</div>
    `
  }

  // ===== 数据同步 =====

  private async syncData() {
    const btn = document.getElementById('sync-btn') as HTMLButtonElement
    if (btn) { btn.disabled = true; btn.textContent = '同步中...' }

    try {
      const resp = await api.syncGoldBars('AU0', 'd')
      if (resp.success && resp.data) {
        toast.success(`同步完成: ${resp.data.bars_synced} 条K线`)
      } else {
        toast.error('同步失败')
      }
    } catch (e) {
      console.error('Sync failed:', e)
      toast.error('同步失败')
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '同步K线数据' }
    }
  }
}

export const goldTradingUI = new GoldTradingUI()
