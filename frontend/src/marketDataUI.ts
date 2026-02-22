import { api } from './api';
import { toast } from './toast';
import type { MarketData } from './types';

class MarketDataUI {
  private container: HTMLDivElement;
  private currentTab: string = 'indices';
  private marketData: Record<string, MarketData> = {};
  private supportedIndices: any = null;

  init(container: HTMLDivElement) {
    this.container = container;
    this.render();
    this.loadSupportedIndices();
  }

  private render() {
    this.container.innerHTML = `
      <div class="market-data-container">
        <h2>市场数据</h2>
        
        <div class="market-tabs">
          <button class="market-tab-button ${this.currentTab === 'indices' ? 'active' : ''}" data-tab="indices">指数行情</button>
          <button class="market-tab-button ${this.currentTab === 'search' ? 'active' : ''}" data-tab="search">行情查询</button>
          <button class="market-tab-button ${this.currentTab === 'details' ? 'active' : ''}" data-tab="details">数据详情</button>
        </div>

        <div class="market-tab-content">
          ${this.renderIndicesTab()}
          ${this.renderSearchTab()}
          ${this.renderDetailsTab()}
        </div>
      </div>
    `;

    this.bindEvents();
  }

  private bindEvents() {
    const tabButtons = this.container.querySelectorAll<HTMLButtonElement>('.market-tab-button');
    tabButtons.forEach(button => {
      button.addEventListener('click', () => {
        this.currentTab = button.dataset.tab || 'indices';
        this.render();
      });
    });

    // 搜索按钮事件
    const searchButton = this.container.querySelector<HTMLButtonElement>('#search-button');
    if (searchButton) {
      searchButton.addEventListener('click', () => {
        this.handleSearch();
      });
    }

    // 清除缓存按钮事件
    const clearCacheButton = this.container.querySelector<HTMLButtonElement>('#clear-cache-button');
    if (clearCacheButton) {
      clearCacheButton.addEventListener('click', async () => {
        const success = await api.clearCache();
        if (success) {
          toast.success('缓存清除成功');
          this.loadSupportedIndices();
        } else {
          toast.error('缓存清除失败');
        }
      });
    }

    // 返回按钮事件
    const backButton = this.container.querySelector<HTMLButtonElement>('#back-to-indices');
    if (backButton) {
      backButton.addEventListener('click', () => {
        this.currentTab = 'indices';
        this.render();
        this.loadSupportedIndices();
      });
    }
  }

  private renderIndicesTab() {
    return `
      <div class="indices-tab ${this.currentTab === 'indices' ? 'active' : ''}">
        <div class="indices-section">
          <h3>国内指数</h3>
          <div id="domestic-indices" class="indices-grid">
            ${this.renderIndicesLoader()}
          </div>
        </div>

        <div class="indices-section">
          <h3>海外指数</h3>
          <div id="global-indices" class="indices-grid">
            ${this.renderIndicesLoader()}
          </div>
        </div>

        <button id="clear-cache-button" class="clear-cache-button">
          清除缓存
        </button>
      </div>
    `;
  }

  private renderSearchTab() {
    return `
      <div class="search-tab ${this.currentTab === 'search' ? 'active' : ''}">
        <div class="search-container">
          <div class="search-input-group">
            <select id="asset-type">
              <option value="stock">股票</option>
              <option value="etf">ETF</option>
              <option value="index">指数</option>
              <option value="global-index">海外指数</option>
            </select>
            <input type="text" id="asset-code" placeholder="请输入代码" />
            <button id="search-button">查询</button>
          </div>
          <div id="search-result" class="search-result">
            请输入代码进行查询
          </div>
        </div>
      </div>
    `;
  }

  private renderDetailsTab() {
    return `
      <div class="details-tab ${this.currentTab === 'details' ? 'active' : ''}">
        <div class="details-container">
          <h3>市场数据详情</h3>
          <div id="market-details" class="market-details">
            请先在搜索或指数页面选择一个资产查看详情
          </div>
        </div>
      </div>
    `;
  }

  private renderIndicesLoader() {
    return `
      <div class="loader">
        <div class="loading-spinner"></div>
        <p>加载中...</p>
      </div>
    `;
  }

  private async loadSupportedIndices() {
    try {
      this.supportedIndices = await api.getSupportedIndices();
      if (this.supportedIndices) {
        this.renderIndices();
      }
    } catch (error) {
      console.error('加载支持的指数列表失败', error);
    }
  }

  private async renderIndices() {
    if (!this.supportedIndices) return;

    const domesticIndicesContainer = this.container.querySelector('#domestic-indices');
    const globalIndicesContainer = this.container.querySelector('#global-indices');

    if (domesticIndicesContainer) {
      domesticIndicesContainer.innerHTML = '';
      if (this.supportedIndices.domestic) {
        for (const index of this.supportedIndices.domestic) {
          const indexElement = this.createIndexElement(index, false);
          domesticIndicesContainer.appendChild(indexElement);
        }
      }
    }

    if (globalIndicesContainer) {
      globalIndicesContainer.innerHTML = '';
      if (this.supportedIndices.global) {
        for (const index of this.supportedIndices.global) {
          const indexElement = this.createIndexElement(index, true);
          globalIndicesContainer.appendChild(indexElement);
        }
      }
    }
  }

  private async createIndexElement(index: any, isGlobal: boolean) {
    const indexElement = document.createElement('div');
    indexElement.className = 'index-card';
    indexElement.innerHTML = this.renderIndicesLoader();

    try {
      let marketData: MarketData | null;
      if (isGlobal) {
        marketData = await api.getGlobalIndexPrice(index.code);
      } else {
        marketData = await api.getIndexPrice(index.code);
      }

      if (marketData) {
        this.marketData[marketData.code] = marketData;
        indexElement.innerHTML = this.renderIndexCard(marketData);
        indexElement.addEventListener('click', () => {
          this.showMarketDetails(marketData!);
        });
      } else {
        indexElement.innerHTML = `
          <div class="index-card error">
            <h4>${index.name}</h4>
            <p class="code">${index.code}</p>
            <p class="error-message">获取数据失败</p>
          </div>
        `;
      }
    } catch (error) {
      console.error(`获取指数数据失败: ${index.code}`, error);
      indexElement.innerHTML = `
        <div class="index-card error">
          <h4>${index.name}</h4>
          <p class="code">${index.code}</p>
          <p class="error-message">获取数据失败</p>
        </div>
      `;
    }

    return indexElement;
  }

  private renderIndexCard(data: MarketData) {
    const changeClass = data.change_percent && data.change_percent >= 0 ? 'positive' : 'negative';
    return `
      <div class="index-card">
        <h4>${data.name}</h4>
        <p class="code">${data.code}</p>
        <div class="price-info">
          <p class="price">${data.price.toFixed(2)}</p>
          <div class="change ${changeClass}">
            <span class="change-percent">${data.change_percent ? data.change_percent.toFixed(2) + '%' : 'N/A'}</span>
            ${data.change ? `<span class="change-value">${data.change >= 0 ? '+' : ''}${data.change.toFixed(2)}</span>` : ''}
          </div>
        </div>
        <p class="timestamp">${new Date(data.timestamp).toLocaleString()}</p>
      </div>
    `;
  }

  private async handleSearch() {
    const assetTypeSelect = this.container.querySelector<HTMLSelectElement>('#asset-type');
    const assetCodeInput = this.container.querySelector<HTMLInputElement>('#asset-code');
    const searchResultContainer = this.container.querySelector('#search-result');

    if (!assetTypeSelect || !assetCodeInput || !searchResultContainer) return;

    const assetType = assetTypeSelect.value;
    const assetCode = assetCodeInput.value.trim();

    if (!assetCode) {
      searchResultContainer.innerHTML = '请输入资产代码';
      return;
    }

    searchResultContainer.innerHTML = this.renderIndicesLoader();

    try {
      let marketData: MarketData | null;
      switch (assetType) {
        case 'stock':
          marketData = await api.getStockPrice(assetCode);
          break;
        case 'etf':
          marketData = await api.getEtfPrice(assetCode);
          break;
        case 'index':
          marketData = await api.getIndexPrice(assetCode);
          break;
        case 'global-index':
          marketData = await api.getGlobalIndexPrice(assetCode);
          break;
        default:
          marketData = null;
      }

      if (marketData) {
        this.marketData[marketData.code] = marketData;
        searchResultContainer.innerHTML = this.renderSearchResult(marketData);

        // 添加查看详情按钮事件
        const viewDetailsButton = searchResultContainer.querySelector<HTMLButtonElement>('.view-details-button');
        if (viewDetailsButton) {
          viewDetailsButton.addEventListener('click', () => {
            this.showMarketDetails(marketData!);
          });
        }
      } else {
        searchResultContainer.innerHTML = `
          <div class="search-result error">
            <h4>查询失败</h4>
            <p>无法获取 ${assetCode} 的市场数据</p>
          </div>
        `;
      }
    } catch (error) {
      console.error(`查询市场数据失败: ${assetCode}`, error);
      searchResultContainer.innerHTML = `
        <div class="search-result error">
          <h4>查询失败</h4>
          <p>获取市场数据时发生错误</p>
        </div>
      `;
    }
  }

  private renderSearchResult(data: MarketData) {
    const changeClass = data.change_percent && data.change_percent >= 0 ? 'positive' : 'negative';
    return `
      <div class="search-result success">
        <h4>${data.name}</h4>
        <p class="code">${data.code}</p>
        <div class="price-info">
          <p class="price">${data.price.toFixed(2)}</p>
          <div class="change ${changeClass}">
            <span class="change-percent">${data.change_percent ? data.change_percent.toFixed(2) + '%' : 'N/A'}</span>
            ${data.change ? `<span class="change-value">${data.change >= 0 ? '+' : ''}${data.change.toFixed(2)}</span>` : ''}
          </div>
        </div>
        ${data.volume ? `<p class="volume">成交量: ${data.volume}</p>` : ''}
        <p class="timestamp">${new Date(data.timestamp).toLocaleString()}</p>
        <button class="view-details-button">查看详情</button>
      </div>
    `;
  }

  private showMarketDetails(data: MarketData) {
    this.currentTab = 'details';
    this.render();

    const marketDetailsContainer = this.container.querySelector('#market-details');
    if (marketDetailsContainer) {
      marketDetailsContainer.innerHTML = this.renderMarketDetails(data);
    }
  }

  private renderMarketDetails(data: MarketData) {
    const changeClass = data.change_percent && data.change_percent >= 0 ? 'positive' : 'negative';
    return `
      <div class="market-details-content">
        <div class="details-header">
          <button class="back-button" id="back-to-indices">← 返回</button>
          <h4>${data.name}</h4>
        </div>
        <p class="code">${data.code}</p>
        
        <div class="details-grid">
          <div class="detail-item">
            <span class="label">当前价格:</span>
            <span class="value price">${data.price.toFixed(2)}</span>
          </div>
          
          ${data.change ? `
            <div class="detail-item">
              <span class="label">涨跌额:</span>
              <span class="value ${changeClass}">${data.change >= 0 ? '+' : ''}${data.change.toFixed(2)}</span>
            </div>
          ` : ''}
          
          ${data.change_percent ? `
            <div class="detail-item">
              <span class="label">涨跌幅:</span>
              <span class="value ${changeClass}">${data.change_percent.toFixed(2)}%</span>
            </div>
          ` : ''}
          
          ${data.volume ? `
            <div class="detail-item">
              <span class="label">成交量:</span>
              <span class="value">${data.volume}</span>
            </div>
          ` : ''}
          
          <div class="detail-item">
            <span class="label">更新时间:</span>
            <span class="value">${new Date(data.timestamp).toLocaleString()}</span>
          </div>
        </div>
        
        <div class="chart-container">
          <h5>价格走势</h5>
          <div id="price-chart" class="price-chart">
            <canvas width="600" height="300"></canvas>
          </div>
        </div>
      </div>
    `;
  }
}

export const marketDataUI = new MarketDataUI();
