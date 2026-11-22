/**
 * P10 策略暴露面板 — L3 研究区内的策略分析面板
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

/**
 * tech_ma_gap_10 -> { op: 'ma_gap', win: 10 }
 * 与后端 normalize.op_of 同规则：末尾那段一定是窗口数字。
 */
function splitName(name: string): { op: string; win: number } | null {
  if (!name.startsWith('tech_')) return null
  const body = name.slice(5)
  const i = body.lastIndexOf('_')
  if (i <= 0) return null
  const win = body.slice(i + 1)
  return /^\d+$/.test(win) ? { op: body.slice(0, i), win: +win } : null
}

/** 因子名 -> 可读中文，如「均线偏离 10日」 */
function labelOf(name: string): string {
  const s = splitName(name)
  if (!s) return name
  return `${OP_LABELS[s.op] || s.op} ${s.win}日`
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
      <div class="research-scroll fx-root">
        <!-- 摘要条：总分是核心输出，单独给视觉重量 -->
        <div class="fx-summary">
          <div class="fx-score">
            <span class="fx-score-label">综合得分</span>
            <span class="fx-total-score">--</span>
          </div>
          <div class="fx-summary-facts">
            <div class="fx-fact">
              <span class="fx-fact-num fx-alive-count">--</span>
              <span class="fx-fact-label">有效因子</span>
            </div>
            <div class="fx-fact">
              <span class="fx-fact-num fx-dead-count">--</span>
              <span class="fx-fact-label">已淘汰</span>
            </div>
            <div class="fx-fact">
              <span class="fx-fact-num fx-pool-count">--</span>
              <span class="fx-fact-label">同类基金</span>
            </div>
          </div>
        </div>

        <div class="fx-main-row">
          <div class="fx-card">
            <div class="research-section-title">因子贡献</div>
            <div class="fx-radar-chart"></div>
          </div>
          <div class="fx-card">
            <div class="research-section-title">因子明细</div>
            <div class="fx-table-wrapper">
              <table class="fx-table">
                <thead class="fx-thead"></thead>
                <tbody class="fx-tbody"></tbody>
              </table>
            </div>
          </div>
        </div>

        <div class="fx-card fx-history-block">
          <div class="research-section-title">历史因子暴露变化
            <span class="fx-sub">近 1 年 · 按权重取前 5</span>
          </div>
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
      this.renderSummary(res.data)
      this.renderRadar(res.data)
      this.renderTable(res.data)
    } catch {
      this.showNoData()
      return
    }
    this.loadHistory(fundCode)
  }

  private renderSummary(data: FactorExposureData): void {
    const items = Object.values(data.factors)
    const alive = items.filter(f => f.weight > 0).length
    this.el!.querySelector('.fx-total-score')!.textContent = data.total_score.toFixed(4)
    this.el!.querySelector('.fx-alive-count')!.textContent = String(alive)
    this.el!.querySelector('.fx-dead-count')!.textContent = String(items.length - alive)
    this.el!.querySelector('.fx-pool-count')!.textContent =
      data.n_funds_in_category ? String(data.n_funds_in_category) : '—'
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
      const s = splitName(name)
      if (!s || item.weight <= 0) continue          // 淘汰因子不进雷达图
      ;(groups[s.op] ||= []).push(item.value)
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

    const isDark = document.body.classList.contains('dark-mode')
    const theme = getChartTheme(isDark)
    const axis = isDark ? '#2a4060' : '#cbd5e1'
    const label = isDark ? '#8494ad' : '#475569'

    this.chart.setOption({
      ...theme,
      tooltip: {
        ...theme.tooltip,
        trigger: 'item',
        formatter: () => ops.map((op, i) =>
          `${OP_LABELS[op] || op}　<b>${values[i].toFixed(2)}</b>`).join('<br>'),
      },
      radar: {
        indicator: indicators,
        shape: 'polygon',
        radius: '58%',
        center: ['50%', '50%'],
        splitNumber: 4,
        axisName: {
          color: label, fontSize: 11,
          // 标签放到轴外侧，避免压在图形和容器边缘上
          padding: [2, 4],
        },
        splitLine: { lineStyle: { color: axis, opacity: 0.6 } },
        splitArea: {
          areaStyle: { color: isDark
            ? ['rgba(232,168,56,0.02)', 'rgba(232,168,56,0.05)']
            : ['rgba(232,168,56,0.03)', 'rgba(232,168,56,0.08)'] },
        },
        axisLine: { lineStyle: { color: axis, opacity: 0.6 } },
      },
      legend: { show: false },
      series: [{
        type: 'radar',
        symbolSize: 3,
        data: [{
          value: values,
          // 不设 name：否则底部会渲染一个系列标签，压住最下方的轴名
          // 系统强调色是琥珀金，不是蓝色
          areaStyle: { color: 'rgba(232,168,56,0.18)' },
          lineStyle: { color: '#e8a838', width: 2 },
          itemStyle: { color: '#e8a838' },
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
      <th>因子</th><th class="num">强度</th><th class="num">权重</th>
      ${showPct ? '<th class="pct-col">同类百分位</th>' : ''}
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
            const tone = pct >= 80 ? 'hi' : pct >= 60 ? 'up' : pct >= 40 ? 'mid' : 'lo'
            // 迷你条：让百分位可一眼横向比较，而不是读一串数字
            pctCell = `<td class="pct-col">
              <div class="fx-pct">
                <div class="fx-pct-bar"><i class="${tone}" style="width:${pct}%"></i></div>
                <span class="fx-pct-num ${tone}">${pct}</span>
              </div>
            </td>`
          } else {
            pctCell = '<td class="pct-col muted">—</td>'
          }
        }
        return `<tr${cls}>
          <td class="fx-name" title="${name}">${labelOf(name)}${
            dead ? ' <span class="fx-tag">淘汰</span>' : ''}</td>
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

    // 10 条线会糊成一团。只画权重最高的 5 个，其余是噪声。
    const top = [...data.series].sort((a, b) => b.weight - a.weight).slice(0, 5)
    const dates = data.points.map(p => p.date)
    const isDark = document.body.classList.contains('dark-mode')
    const theme = getChartTheme(isDark)

    // 暖色系，与终端琥珀主题一致；深色背景上提高亮度
    const colors = isDark
      ? ['#e8a838', '#4a90d9', '#22c55e', '#ef4444', '#a78bfa']
      : ['#c08828', '#3b7dd0', '#16a34a', '#dc2626', '#7c3aed']

    this.historyChart.setOption({
      ...theme,
      tooltip: {
        ...theme.tooltip,
        valueFormatter: (v: unknown) => (typeof v === 'number' ? v.toFixed(3) : '—'),
      },
      legend: {
        bottom: 0, icon: 'roundRect', itemWidth: 8, itemHeight: 8, itemGap: 10,
        textStyle: { fontSize: 10, color: isDark ? '#8494ad' : '#475569' },
      },
      grid: { left: 40, right: 14, top: 10, bottom: 62 },
      xAxis: {
        type: 'category',
        data: dates,
        boundaryGap: false,
        axisLine: { lineStyle: { color: isDark ? '#1e2d42' : '#e2e8f0' } },
        axisLabel: { fontSize: 10, color: isDark ? '#546478' : '#64748b' },
      },
      yAxis: {
        type: 'value', min: 0, max: 1,
        splitLine: { lineStyle: { color: isDark ? '#152238' : '#f1f5f9' } },
        axisLabel: { fontSize: 10, color: isDark ? '#546478' : '#64748b' },
      },
      series: top.map((s, i) => ({
        name: labelOf(s.name),
        type: 'line',
        smooth: true,
        showSymbol: false,
        emphasis: { focus: 'series' },
        data: data.points.map(p => p.factors[s.name] ?? null),
        lineStyle: { width: 1.8, color: colors[i % colors.length] },
        itemStyle: { color: colors[i % colors.length] },
        areaStyle: i === 0 ? {
          opacity: 0.10,
          color: colors[0],
        } : undefined,
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
