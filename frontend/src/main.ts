import './style.css'
import { toast } from './toast'
import { fundManagerUI } from './fundManagerUI'
import { marketDataUI } from './marketDataUI'
import { goldTradingUI } from './goldTradingUI'
import { FundQuantUI } from './fundQuantUI'

toast.init();

// 主题管理
class ThemeManager {
  private static readonly THEME_KEY = 'fund-valuation-theme';

  static init(): void {
    const savedTheme = localStorage.getItem(this.THEME_KEY);
    if (savedTheme === 'dark') {
      document.body.classList.add('dark-mode');
    } else if (savedTheme === 'light') {
      document.body.classList.remove('dark-mode');
    } else {
      if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
        document.body.classList.add('dark-mode');
      }
    }
  }

  static toggle(): void {
    document.body.classList.toggle('dark-mode');
    const isDark = document.body.classList.contains('dark-mode');
    localStorage.setItem(this.THEME_KEY, isDark ? 'dark' : 'light');
  }

  static isDark(): boolean {
    return document.body.classList.contains('dark-mode') || window.matchMedia('(prefers-color-scheme: dark)').matches;
  }
}

ThemeManager.init();

document.querySelector<HTMLDivElement>('#app')!.innerHTML = `
  <div class="app">
    <header class="app-header">
      <div class="app-title">
        <div class="app-title-icon">📈</div>
        <div>
          <h1>智能理财Agent</h1>
          <p class="app-title-subtitle">Intelligent Wealth Agent - 智能投资 · 精准预测</p>
        </div>
      </div>
      <div class="app-nav">
        <button class="btn btn-ghost btn-icon" id="theme-toggle" title="切换主题">🌓</button>
      </div>
    </header>

    <nav class="tabs" role="tablist">
      <button class="tab-button active" data-tab="fund-manager" role="tab" aria-selected="true">
        <span class="tab-button-icon">💼</span> 基金管理
      </button>
      <button class="tab-button" data-tab="gold-trading" role="tab" aria-selected="false">
        <span class="tab-button-icon">📊</span> 黄金量化
      </button>
      <button class="tab-button" data-tab="market-data" role="tab" aria-selected="false">
        <span class="tab-button-icon">🌍</span> 市场数据
      </button>
      <button class="tab-button" data-tab="fund-quant" role="tab" aria-selected="false">
        <span class="tab-button-icon">📈</span> 基金量化
      </button>
    </nav>

    <main>
      <div class="tab-content active" id="fund-manager-container" role="tabpanel"></div>
      <div class="tab-content" id="gold-trading-container" role="tabpanel"></div>
      <div class="tab-content" id="market-data-container" role="tabpanel"></div>
      <div class="tab-content" id="fund-quant-container" role="tabpanel"></div>
    </main>
  </div>
`

const themeToggleBtn = document.getElementById('theme-toggle');
if (themeToggleBtn) {
  themeToggleBtn.addEventListener('click', () => {
    ThemeManager.toggle();
    const icon = themeToggleBtn as HTMLElement;
    icon.textContent = ThemeManager.isDark() ? '☀️' : '🌙';
  });
}

async function initApp() {
  const fundManagerContainer = document.querySelector<HTMLDivElement>('#fund-manager-container')!
  fundManagerUI.init(fundManagerContainer).catch(console.error)

  const goldTradingContainer = document.querySelector<HTMLDivElement>('#gold-trading-container')!
  goldTradingUI.init(goldTradingContainer)

  const marketDataContainer = document.querySelector<HTMLDivElement>('#market-data-container')!
  marketDataUI.init(marketDataContainer)

  const fundQuantContainer = document.querySelector<HTMLDivElement>('#fund-quant-container')!
  const fundQuantUI = new FundQuantUI()
  fundQuantUI.init(fundQuantContainer)
}

initApp().catch(console.error)

function setupTabSwitching() {
  const tabButtons = document.querySelectorAll<HTMLButtonElement>('.tab-button')
  const tabContents = document.querySelectorAll<HTMLDivElement>('.tab-content')

  tabContents.forEach(content => {
    if (!content.classList.contains('active')) {
      content.style.display = 'none'
    }
  })

  function switchTab(tabId: string) {
    tabButtons.forEach(btn => {
      btn.classList.remove('active')
      btn.setAttribute('aria-selected', 'false')
    })
    const targetBtn = document.querySelector<HTMLButtonElement>(`.tab-button[data-tab="${tabId}"]`)
    if (targetBtn) {
      targetBtn.classList.add('active')
      targetBtn.setAttribute('aria-selected', 'true')
    }

    const targetContent = document.getElementById(`${tabId}-container`)
    if (!targetContent) return

    tabContents.forEach(content => {
      content.classList.remove('active')
      content.style.display = 'none'
    })

    targetContent.classList.add('active')
    targetContent.style.display = 'block'

    if (tabId === 'gold-trading') {
      goldTradingUI.onActivated()
    }

    targetContent.style.animation = 'none'
    targetContent.offsetHeight
    targetContent.style.animation = 'fadeIn 0.3s ease-out'

    localStorage.setItem('active_tab', tabId)
  }

  tabButtons.forEach(button => {
    button.addEventListener('click', () => {
      const tabId = button.dataset.tab
      if (!tabId) return
      switchTab(tabId)
    })
  })

  const savedTab = localStorage.getItem('active_tab')
  if (savedTab && document.querySelector(`.tab-button[data-tab="${savedTab}"]`)) {
    switchTab(savedTab)
  }
}

setupTabSwitching()
