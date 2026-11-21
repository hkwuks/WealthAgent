/**
 * P10 因子暴露面板 — L3 研究区内的因子分析面板
 *
 * 功能：
 * 1. 因子贡献雷达图 — 按算子聚合（7 个轴），28 个窗口值挤一张图看不出东西
 * 2. 因子明细表 — 值 / 权重 / 同类百分位；分位算不出时整列不显示
 * 3. 因子历史变化 — 后端按 as_of 回算的真实月度曲线
 *
 * 数据契约见 ../api.ts 的 FactorExposureData / FactorHistoryData。
 */

import * as echarts from 'echarts'
import { fundQuantApi, type FactorExposureData, type FactorHistoryData } from '../api'
import { getChartTheme } from '../../fundQuantCharts'

/** 算子 -> 中文名。与 backend/fund_quant/factors/technical.py 的 OPS 对应 */
const OP_LABELS: Record<string, string> = {
  roc: '收益率',
  ma_gap: '均线偏离',
  std: '波动率',
  max_gap: '距高点',
  rsv: 'RSV',
  rank: '涨幅分位',
  skew: '收益偏度',
}

/** tech_ma_gap_10 -> ma_gap（与后端 normalize.op_of 同规则） */
function opOf(name: string): string | null {
  if (!name.startsWith('tech_')) return null
  const body = name.slice(5)
  const i = body.lastIndexOf('_')
  if (i <= 0) return null
  const win = body.slice(i + 1)
  return /^\d+$/.test(win) ? body.slice(0, i) : null
}

export class FactorExposure {
  private el: HTMLElement | null = null
  private chart: echarts.ECharts | null = null
  private historyChart: echarts.ECharts | null = null

  init(el: HTMLElement): void {
    this.el = el
    this.el.innerHTML = this.renderHTML()
  }

  private renderHTML(): string {
    return `
      <div class="research-scroll" style="display:flex;flex-direction:column;gap:12px;">
        <div class="fx-main-row">
          <div>
            <div class="research-section-title">因子贡献（按算子聚合）</div>
            <div class="fx-radar-chart"></div>
          </div>
          <div>
            <div class="research-section-title">因子明细</div>
            <div class="fx-table-wrapper">
              <table class="fx-table">
                <thead class="fx-thead"></thead>
                <tbody class="fx-tbody"></tbody>
              </table>
            </div>
            <div class="fx-score-row">
              总分 <span class="fx-total-score">--</span>
              <span class="fx-pool-info"></span>
            </div>
          </div>
        </div>

        <div class="fx-history-block">
          <div class="research-section-title">历史因子暴露变化（近 1 年，真实回溯）</div>
          <div class="fx-history-chart"></div>
        </div>
      </div>`
  }

  show(fundCode: string): void {
    this.loadExposure(fundCode)
  }

  private async loadExposure(fundCode: string): Promise<void> {
    if (!this.el) return
    try {
      const res = await fundQuantApi.getFactorExposure(fundCode)
      if (!res.success) {
        this.showNoData()
        return
      }
      this.renderRadar(res.data)
      this.renderTable(res.data)
      this.el.querySelector('.fx-total-score')!.textContent = res.data.total_score.toFixed(4)

      const pool = this.el.querySelector('.fx-pool-info')!
      pool.textContent = res.data.n_funds_in_category
        ? `　同类 ${res.data.n_funds_in_category} 只`
        : '　同类池不足，无百分位'
    } catch {
      this.showNoData()
      return
    }
    this.loadHistory(fundCode)
  }

  private async loadHistory(fundCode: string): Promise<void> {
    const block = this.el?.querySelector<HTMLElement>('.fx-history-block')
    if (!block) return
    try {
      const res = await fundQuantApi.getFactorHistory(fundCode, 12)
      if (!res.success || !res.data.points.length) {
        block.style.display = 'none'   // 拿不到真历史就整块隐藏，不画假柱
        return
      }
      block.style.display = ''
      this.renderHistory(res.data)
    } catch {
      block.style.display = 'none'
    }
  }

  private showNoData(): void {
    const el = this.el?.querySelector('.fx-radar-chart')
    if (el) {
      el.innerHTML = '<div class="fx-empty">暂无因子数据<br>'
        + '<span>需要在基金量化 Tab 里先同步该基金的净值</span></div>'
    }
    this.el?.querySelector<HTMLElement>('.fx-history-block')?.style.setProperty('display', 'none')
  }

  /** 28 个窗口值聚合成 7 个算子轴，取各窗口的均值 */
  private renderRadar(data: FactorExposureData): void {
    const el = this.el?.querySelector<HTMLElement>('.fx-radar-chart')
    if (!el) return
    this.chart?.dispose()
    this.chart = echarts.init(el)

    const groups: Record<string, number[]> = {}
    for (const [name, item] of Object.entries(data.factors)) {
      const op = opOf(name)
      if (!op || item.weight <= 0) continue          // 淘汰因子不进雷达图
      ;(groups[op] ||= []).push(item.value)
    }
    const ops = Object.keys(groups)
    if (!ops.length) {
      el.innerHTML = '<div class="fx-empty">无有效因子</div>'
      return
    }

    const indicators = ops.map(op => ({ name: OP_LABELS[op] || op, max: 1 }))
    const values = ops.map(op => {
      const a = groups[op]
      return +(a.reduce((s, v) => s + v, 0) / a.length).toFixed(3)
    })

    const theme = getChartTheme(document.body.classList.contains('dark-mode'))
    this.chart.setOption({
      ...theme,
      radar: {
        indicator: indicators,
        shape: 'polygon',
        radius: '62%',
        name: { textStyle: { fontSize: 11 } },
      },
      series: [{
        type: 'radar',
        data: [{
          value: values,
          name: data.fund_name,
          areaStyle: { color: 'rgba(59,130,246,0.2)' },
          lineStyle: { color: '#3b82f6', width: 2 },
        }],
      }],
    })
  }

  private renderTable(data: FactorExposureData): void {
    const thead = this.el?.querySelector('.fx-thead')
    const tbody = this.el?.querySelector('.fx-tbody')
    if (!thead || !tbody) return

    // 只要有一个因子能算分位，才显示这一列
    const showPct = Object.values(data.factors).some(f => f.rank_pct !== null)
    thead.innerHTML = `<tr>
      <th>因子</th><th class="num">值</th><th class="num">权重</th>
      ${showPct ? '<th class="num">同类百分位</th>' : ''}
    </tr>`

    const rows = Object.entries(data.factors)
      .sort(([, a], [, b]) => b.weight - a.weight)
      .map(([name, item]) => {
        const dead = item.weight <= 0
        const cls = dead ? ' class="fx-dead"' : ''
        const pct = item.rank_pct
        let pctCell = ''
        if (showPct) {
          if (!dead && pct !== null) {
            const color = pct >= 80 ? 'var(--danger-color)'
              : pct >= 60 ? 'var(--primary-color)'
              : pct >= 40 ? 'var(--text-secondary)' : 'var(--success-color)'
            pctCell = `<td class="num" style="color:${color};font-weight:600;">${pct}%</td>`
          } else {
            pctCell = '<td class="num muted">—</td>'
          }
        }
        return `<tr${cls}>
          <td>${name}${dead ? ' <span class="fx-tag">已淘汰</span>' : ''}</td>
          <td class="num">${item.value.toFixed(2)}</td>
          <td class="num">${(item.weight * 100).toFixed(1)}%</td>
          ${pctCell}
        </tr>`
      })
    tbody.innerHTML = rows.join('')
  }

  /** 真实历史：后端按 as_of 逐月回溯，每点是那个时点算出来的因子值 */
  private renderHistory(data: FactorHistoryData): void {
    const el = this.el?.querySelector<HTMLElement>('.fx-history-chart')
    if (!el) return
    this.historyChart?.dispose()
    this.historyChart = echarts.init(el)

    const dates = data.points.map(p => p.date)
    const colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
      '#ec4899', '#14b8a6', '#f97316', '#6366f1', '#84cc16']
    const theme = getChartTheme(document.body.classList.contains('dark-mode'))

    this.historyChart.setOption({
      ...theme,
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0, textStyle: { fontSize: 10 }, itemWidth: 10, itemHeight: 6 },
      grid: { left: 40, right: 12, top: 10, bottom: 34 },
      xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 10 } },
      yAxis: { type: 'value', min: 0, max: 1, axisLabel: { fontSize: 10 } },
      series: data.series.map((s, i) => ({
        name: s.display_name,
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: data.points.map(p => p.factors[s.name] ?? null),
        lineStyle: { width: 1.5, color: colors[i % colors.length] },
        itemStyle: { color: colors[i % colors.length] },
      })),
    })
  }

  onActivated(): void {
    this.chart?.resize()
    this.historyChart?.resize()
  }

  destroy(): void {
    this.chart?.dispose()
    this.historyChart?.dispose()
    this.el = null
  }
}
