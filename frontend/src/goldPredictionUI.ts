import { api } from './api'
import { toast } from './toast'

export class GoldPredictionUI {
  private container: HTMLDivElement | null = null
  private isPredicting = false
  private isBacktesting = false

  init(container: HTMLDivElement) {
    this.container = container
    this.render()
    this.bindEvents()
    this.loadCurrentData()
  }

  private render() {
    if (!this.container) return

    this.container.innerHTML = `
      <div class="gold-prediction-page">
        <div class="section-card">
          <div class="section-header">
            <h2>🥇 黄金预测</h2>
          </div>

          <!-- 当前市场数据 -->
          <div class="market-data-section">
            <h3>当前市场数据</h3>
            <div class="market-cards" id="gold-market-cards">
              <div class="market-card">
                <div class="market-card-title">COMEX黄金</div>
                <div class="market-card-value" id="gold-price">--</div>
                <div class="market-card-change" id="gold-change">--</div>
              </div>
              <div class="market-card">
                <div class="market-card-title">美元指数</div>
                <div class="market-card-value" id="dxy-value">--</div>
              </div>
              <div class="market-card">
                <div class="market-card-title">恐慌指数</div>
                <div class="market-card-value" id="vix-value">--</div>
              </div>
              <div class="market-card">
                <div class="market-card-title">美债10年期</div>
                <div class="market-card-value" id="us10y-value">--</div>
              </div>
            </div>
          </div>

          <!-- 预测设置 -->
          <div class="prediction-settings">
            <h3>预测设置</h3>
            <div class="settings-row">
              <label>预测周期:</label>
              <select id="horizon-select">
                <option value="1">1天</option>
                <option value="5">5天</option>
                <option value="20">20天</option>
              </select>
              <button class="btn btn-primary" id="predict-btn">开始预测</button>
            </div>
          </div>

          <!-- 预测结果 -->
          <div class="prediction-results" id="prediction-results" style="display: none;">
            <h3>三模型预测结果</h3>
            <div class="prediction-cards" id="prediction-cards"></div>
            <div class="ensemble-result" id="ensemble-result"></div>
          </div>

          <!-- 回测设置 -->
          <div class="backtest-settings">
            <h3>模型回测</h3>
            <div class="settings-row">
              <label>回测周期:</label>
              <select id="backtest-years-select">
                <option value="1">1年</option>
                <option value="2">2年</option>
                <option value="3">3年</option>
              </select>
              <label>预测周期:</label>
              <select id="backtest-horizon-select">
                <option value="1">1天</option>
                <option value="5">5天</option>
                <option value="20">20天</option>
              </select>
              <button class="btn btn-secondary" id="backtest-btn">开始回测</button>
            </div>
          </div>

          <!-- 回测结果 -->
          <div class="backtest-results" id="backtest-results" style="display: none;">
            <h3>回测结果</h3>
            <canvas id="backtest-chart"></canvas>
            <div class="metrics-table-container">
              <table class="metrics-table" id="metrics-table">
                <thead>
                  <tr>
                    <th>指标</th>
                    <th>XGBoost</th>
                    <th>LSTM</th>
                    <th>Transformer</th>
                    <th>基准(买入持有)</th>
                  </tr>
                </thead>
                <tbody id="metrics-tbody"></tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    `
  }

  private bindEvents() {
    const predictBtn = document.getElementById('predict-btn')
    const backtestBtn = document.getElementById('backtest-btn')

    predictBtn?.addEventListener('click', () => this.runPrediction())
    backtestBtn?.addEventListener('click', () => this.runBacktest())
  }

  private async loadCurrentData() {
    try {
      const response = await api.getGoldCurrent()
      if (response.success && response.data) {
        this.updateMarketData(response.data)
      }
    } catch (error) {
      console.error('Failed to load current data:', error)
    }
  }

  private updateMarketData(data: any) {
    const goldPriceEl = document.getElementById('gold-price')
    const goldChangeEl = document.getElementById('gold-change')
    const dxyEl = document.getElementById('dxy-value')
    const vixEl = document.getElementById('vix-value')
    const us10yEl = document.getElementById('us10y-value')

    if (goldPriceEl) {
      goldPriceEl.textContent = `$${data.gold_price.toFixed(2)}`
    }

    if (goldChangeEl && data.gold_change_percent !== undefined) {
      const changePercent = data.gold_change_percent
      const sign = changePercent >= 0 ? '+' : ''
      goldChangeEl.textContent = `${sign}${changePercent.toFixed(2)}%`
      goldChangeEl.className = `market-card-change ${changePercent >= 0 ? 'positive' : 'negative'}`
    }

    if (dxyEl) dxyEl.textContent = data.dxy?.toFixed(2) || '--'
    if (vixEl) vixEl.textContent = data.vix?.toFixed(2) || '--'
    if (us10yEl) us10yEl.textContent = data.us10y ? `${data.us10y.toFixed(2)}%` : '--'
  }

  private async runPrediction() {
    if (this.isPredicting) return

    const horizonSelect = document.getElementById('horizon-select') as HTMLSelectElement
    const horizon = parseInt(horizonSelect?.value || '1')

    this.isPredicting = true
    const predictBtn = document.getElementById('predict-btn') as HTMLButtonElement
    if (predictBtn) {
      predictBtn.disabled = true
      predictBtn.textContent = '预测中...'
    }

    try {
      const response = await api.predictGoldPrice(horizon)
      if (response.success && response.data) {
        this.displayPredictionResults(response.data)
        toast.success('预测完成')
      } else {
        toast.error(response.error_message || '预测失败')
      }
    } catch (error) {
      console.error('Prediction failed:', error)
      toast.error('预测失败')
    } finally {
      this.isPredicting = false
      if (predictBtn) {
        predictBtn.disabled = false
        predictBtn.textContent = '开始预测'
      }
    }
  }

  private displayPredictionResults(data: any) {
    const resultsContainer = document.getElementById('prediction-results')
    const cardsContainer = document.getElementById('prediction-cards')
    const ensembleContainer = document.getElementById('ensemble-result')

    if (!resultsContainer || !cardsContainer || !ensembleContainer) return

    resultsContainer.style.display = 'block'

    // 显示三个模型的预测结果
    cardsContainer.innerHTML = data.predictions.map((pred: any) => {
      const changeSign = pred.predicted_change_percent >= 0 ? '+' : ''
      const changeClass = pred.predicted_change_percent >= 0 ? 'positive' : 'negative'

      return `
        <div class="prediction-card ${changeClass}">
          <div class="prediction-model">${this.getModelDisplayName(pred.model_type)}</div>
          <div class="prediction-icon">${this.getModelIcon(pred.model_type)}</div>
          <div class="prediction-item">
            <span class="label">预测价格</span>
            <span class="value">$${pred.predicted_price.toFixed(2)}</span>
          </div>
          <div class="prediction-item">
            <span class="label">涨跌额</span>
            <span class="value">${changeSign}$${pred.predicted_change.toFixed(2)}</span>
          </div>
          <div class="prediction-item">
            <span class="label">涨跌幅</span>
            <span class="value ${changeClass}">${changeSign}${pred.predicted_change_percent.toFixed(2)}%</span>
          </div>
          </div>
        </div>
      `
    }).join('')

    // 显示综合预测
    const ensemble = data.ensemble_prediction
    const ensembleSign = ensemble.predicted_change_percent >= 0 ? '+' : ''
    const ensembleClass = ensemble.predicted_change_percent >= 0 ? 'positive' : 'negative'

    ensembleContainer.innerHTML = `
      <div class="ensemble-card ${ensembleClass}">
        <span class="ensemble-label">综合预测:</span>
        <span class="ensemble-price">$${ensemble.predicted_price.toFixed(2)}</span>
        <span class="ensemble-change">${ensembleSign}${ensemble.predicted_change_percent.toFixed(2)}%</span>
      </div>
    `
  }

  private getModelDisplayName(modelType: string): string {
    const names: Record<string, string> = {
      'xgboost': 'XGBoost',
      'lstm': 'LSTM',
      'transformer': 'Transformer'
    }
    return names[modelType] || modelType
  }

  private getModelIcon(modelType: string): string {
    const icons: Record<string, string> = {
      'xgboost': '🌳',
      'lstm': '🧠',
      'transformer': '🔄'
    }
    return icons[modelType] || '📊'
  }

  private async runBacktest() {
    if (this.isBacktesting) return

    const yearsSelect = document.getElementById('backtest-years-select') as HTMLSelectElement
    const horizonSelect = document.getElementById('backtest-horizon-select') as HTMLSelectElement
    const years = parseInt(yearsSelect?.value || '1')
    const horizonDays = parseInt(horizonSelect?.value || '1')

    this.isBacktesting = true
    const backtestBtn = document.getElementById('backtest-btn') as HTMLButtonElement
    if (backtestBtn) {
      backtestBtn.disabled = true
      backtestBtn.textContent = '回测中...'
    }

    try {
      const response = await api.runGoldBacktest(years, horizonDays)
      if (response.success && response.data) {
        this.displayBacktestResults(response.data)
        toast.success('回测完成')
      } else {
        toast.error(response.error_message || '回测失败')
      }
    } catch (error) {
      console.error('Backtest failed:', error)
      toast.error('回测失败')
    } finally {
      this.isBacktesting = false
      if (backtestBtn) {
        backtestBtn.disabled = false
        backtestBtn.textContent = '开始回测'
      }
    }
  }

  private displayBacktestResults(data: any) {
    const resultsContainer = document.getElementById('backtest-results')
    if (!resultsContainer) return

    resultsContainer.style.display = 'block'

    // 绘制权益曲线图表
    this.drawEquityCurveChart(data.results)

    // 显示指标表格
    this.displayMetricsTable(data.results)
  }

  private drawEquityCurveChart(results: any) {
    const canvas = document.getElementById('backtest-chart') as HTMLCanvasElement
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // 设置高 DPI 支持
    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()

    // 设置 canvas 实际尺寸（考虑设备像素比）
    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr

    // 缩放上下文以匹配 CSS 尺寸
    ctx.scale(dpr, dpr)

    // 使用 CSS 尺寸进行绘制计算
    const width = rect.width
    const height = rect.height

    // 清空画布
    ctx.clearRect(0, 0, width, height)

    // 设置字体（使用相对于 canvas 尺寸的字体大小）
    ctx.font = `${Math.max(12, height * 0.04)}px Arial`
    ctx.fillStyle = '#333'
    ctx.textAlign = 'center'
    ctx.fillText('累计收益对比', width / 2, height * 0.08)

    // 绘制图例
    const models = ['xgboost', 'lstm', 'transformer', 'benchmark']
    const colors = ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0']
    const legendY = height * 0.15
    const legendItemWidth = width / 5

    models.forEach((model, i) => {
      const x = width * 0.1 + i * legendItemWidth
      ctx.fillStyle = colors[i]
      ctx.fillRect(x, legendY, 20, 10)
      ctx.fillStyle = '#333'
      ctx.textAlign = 'left'
      ctx.font = `${Math.max(10, height * 0.025)}px Arial`
      ctx.fillText(this.getModelDisplayName(model), x + 25, legendY + 9)
    })

    // 绘制坐标轴
    const chartX = width * 0.1
    const chartY = height * 0.25
    const chartWidth = width * 0.8
    const chartHeight = height * 0.6

    ctx.strokeStyle = '#ccc'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(chartX, chartY)
    ctx.lineTo(chartX, chartY + chartHeight)
    ctx.lineTo(chartX + chartWidth, chartY + chartHeight)
    ctx.stroke()

    // 找出最大长度和范围（以1.0为中心，保证涨跌方向可见）
    let maxLen = 0
    let minVal = Infinity
    let maxVal = -Infinity

    models.forEach(model => {
      if (results[model] && results[model].equity_curve) {
        const curve = results[model].equity_curve
        maxLen = Math.max(maxLen, curve.length)
        minVal = Math.min(minVal, ...curve)
        maxVal = Math.max(maxVal, ...curve)
      }
    })

    // 确保有有效的范围，且以1.0为中心显示
    if (minVal === Infinity) minVal = 0.9
    if (maxVal === -Infinity) maxVal = 1.1
    if (minVal === maxVal) {
      minVal = 0.9
      maxVal = 1.1
    }
    // 如果范围太小（权益曲线都在1.0附近），扩展到±5%
    const range = maxVal - minVal
    if (range < 0.05) {
      const center = (minVal + maxVal) / 2
      minVal = center - 0.05
      maxVal = center + 0.05
    }

    // 添加 Y 轴标签
    ctx.fillStyle = '#666'
    ctx.textAlign = 'right'
    ctx.font = `${Math.max(9, height * 0.02)}px Arial`
    const ySteps = 5
    for (let i = 0; i <= ySteps; i++) {
      const val = minVal + (maxVal - minVal) * (i / ySteps)
      const y = chartY + chartHeight - (i / ySteps) * chartHeight
      ctx.fillText(val.toFixed(2), chartX - 5, y + 3)

      // 绘制网格线
      if (i > 0) {
        ctx.strokeStyle = '#eee'
        ctx.beginPath()
        ctx.moveTo(chartX, y)
        ctx.lineTo(chartX + chartWidth, y)
        ctx.stroke()
      }
    }

    // 绘制权益曲线
    models.forEach((model, i) => {
      if (!results[model] || !results[model].equity_curve) return

      const curve = results[model].equity_curve
      ctx.strokeStyle = colors[i]
      ctx.lineWidth = 2
      ctx.beginPath()

      curve.forEach((val: number, j: number) => {
        const x = chartX + (j / (maxLen - 1)) * chartWidth
        const y = chartY + chartHeight - ((val - minVal) / (maxVal - minVal)) * chartHeight

        if (j === 0) {
          ctx.moveTo(x, y)
        } else {
          ctx.lineTo(x, y)
        }
      })

      ctx.stroke()
    })
  }

  private displayMetricsTable(results: any) {
    const tbody = document.getElementById('metrics-tbody')
    if (!tbody) return

    const metrics = [
      { key: 'total_return', label: '总收益率', format: (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%` },
      { key: 'annualized_return', label: '年化收益', format: (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%` },
      { key: 'max_drawdown', label: '最大回撤', format: (v: number) => `${v.toFixed(2)}%` },
      { key: 'sharpe_ratio', label: '夏普比率', format: (v: number) => v.toFixed(2) },
      { key: 'win_rate', label: '胜率', format: (v: number) => v ? `${v.toFixed(1)}%` : '--' },
      { key: 'directional_accuracy', label: 'DA', format: (v: number) => v ? `${v.toFixed(1)}%` : '--' }
    ]

    tbody.innerHTML = metrics.map(metric => `
      <tr>
        <td>${metric.label}</td>
        <td>${results.xgboost ? metric.format(results.xgboost[metric.key]) : '--'}</td>
        <td>${results.lstm ? metric.format(results.lstm[metric.key]) : '--'}</td>
        <td>${results.transformer ? metric.format(results.transformer[metric.key]) : '--'}</td>
        <td>${results.benchmark ? metric.format(results.benchmark[metric.key]) : '--'}</td>
      </tr>
    `).join('')
  }
}

export const goldPredictionUI = new GoldPredictionUI()
