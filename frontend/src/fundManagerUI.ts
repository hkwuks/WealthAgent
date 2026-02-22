import { fundManager } from './fundManager';
import { api } from './api';
import { toast } from './toast';
import type { Fund } from './types';

class FundManagerUI {
  private container: HTMLElement | null = null;
  private eventsBound: boolean = false;
  private refreshInterval: number | null = null;
  private static readonly REFRESH_INTERVAL_MS = 300000;

  async init(container: HTMLElement): Promise<void> {
    this.container = container;
    await fundManager.init();
    await this.render();
    this.bindEventsOnce();
    await this.refreshValuations();
    this.startAutoRefresh();
  }

  async render(): Promise<void> {
    if (!this.container) return;

    const funds = fundManager.getFunds();

    this.container.innerHTML = `
      <div class="fund-manager">
        <h2>基金管理</h2>
        
        <div class="fund-form">
          <h3>添加基金</h3>
          <form id="add-fund-form">
            <div class="form-group">
              <label for="fund-code">基金代码:</label>
              <div style="display: flex; gap: 8px;">
                <input type="text" id="fund-code" required style="flex: 1;">
                <button type="button" id="query-fund-btn" style="white-space: nowrap;">查询</button>
              </div>
            </div>
            <div class="form-group">
              <label for="fund-name">基金名称:</label>
              <input type="text" id="fund-name" required>
            </div>
            <div class="form-group">
              <label for="fund-type">基金类型:</label>
              <input type="text" id="fund-type" required>
            </div>
            <div class="form-group">
              <label for="total-shares">持有份额:</label>
              <input type="number" id="total-shares" step="0.001" required>
            </div>
            <button type="submit">添加基金</button>
          </form>
        </div>

        <div class="fund-list">
          <h3>基金列表 <span class="refresh-info">(每分钟自动刷新估值)</span></h3>
          ${funds.length > 0 ? `
            <table>
              <thead>
                <tr>
                  <th>基金代码</th>
                  <th>基金名称</th>
                  <th>基金类型</th>
                  <th>持有份额</th>
                  <th>最新净值</th>
                  <th>预估净值</th>
                  <th>预估涨跌幅</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                ${funds.map(fund => `
                  <tr>
                    <td>${fund.fund_code}</td>
                    <td>${fund.fund_name}</td>
                    <td>${fund.fund_type}</td>
                    <td>${fund.total_shares}</td>
                    <td>${fund.nav ? fund.nav.toFixed(4) : '-'}</td>
                    <td>${fund.estimated_nav ? fund.estimated_nav.toFixed(4) : '-'}</td>
                    <td class="${fund.estimated_change_percent && fund.estimated_change_percent >= 0 ? 'positive' : 'negative'}">
                      ${fund.estimated_change_percent !== undefined ? (fund.estimated_change_percent >= 0 ? '+' : '') + fund.estimated_change_percent.toFixed(2) + '%' : '-'}
                    </td>
                    <td>
                      <button class="delete-fund" data-code="${fund.fund_code}">删除</button>
                    </td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          ` : `
            <p>暂无基金数据，请添加基金</p>
          `}
        </div>
      </div>
    `;
  }

  private bindEventsOnce(): void {
    if (this.eventsBound || !this.container) return;
    this.eventsBound = true;

    this.container.addEventListener('submit', async (e) => {
      const target = e.target as HTMLElement;
      if (target.id === 'add-fund-form') {
        e.preventDefault();
        await this.handleAddFund(target as HTMLFormElement);
      }
    });

    this.container.addEventListener('click', async (e) => {
      const target = e.target as HTMLElement;

      if (target.id === 'query-fund-btn') {
        e.preventDefault();
        await this.handleQueryFund();
      }

      if (target.classList.contains('delete-fund')) {
        const fundCode = target.dataset.code;
        if (fundCode) {
          await this.handleDeleteFund(fundCode);
        }
      }
    });
  }

  async handleQueryFund(): Promise<void> {
    try {
      const fundCodeInput = this.container?.querySelector('#fund-code') as HTMLInputElement;
      const fundCode = fundCodeInput?.value.trim();

      if (!fundCode) {
        toast.warning('请输入基金代码');
        return;
      }

      console.log('开始查询基金信息:', fundCode);

      const fundInfo = await api.queryFundInfo(fundCode);
      console.log('查询到的基金信息:', fundInfo);

      const fundNameInput = this.container?.querySelector('#fund-name') as HTMLInputElement;
      const fundTypeInput = this.container?.querySelector('#fund-type') as HTMLInputElement;

      if (fundNameInput && fundTypeInput) {
        fundNameInput.value = fundInfo.fund_name;
        fundTypeInput.value = fundInfo.fund_type;
        toast.success('基金信息查询成功，已自动填充到表单');
      }
    } catch (error) {
      console.error('查询基金信息失败:', error);
      toast.error('查询基金信息失败，请检查基金代码是否正确');
    }
  }

  async handleAddFund(form: HTMLFormElement): Promise<void> {
    try {
      const fundCode = (form.querySelector('#fund-code') as HTMLInputElement).value;
      const fundName = (form.querySelector('#fund-name') as HTMLInputElement).value;
      const fundType = (form.querySelector('#fund-type') as HTMLInputElement).value;
      const totalShares = parseFloat((form.querySelector('#total-shares') as HTMLInputElement).value);

      console.log('添加基金表单数据:', { fundCode, fundName, fundType, totalShares });

      const newFund: Fund = {
        fund_code: fundCode,
        fund_name: fundName,
        fund_type: fundType,
        total_shares: totalShares,
        holdings: [],
      };

      console.log('创建基金对象:', newFund);

      const success = await fundManager.addFund(newFund);
      console.log('添加基金结果:', success);

      if (success) {
        toast.success('基金添加成功');
        form.reset();
        await this.render();
      } else {
        toast.error('基金添加失败，可能是基金已存在或其他原因');
      }
    } catch (error) {
      console.error('处理添加基金时出错:', error);
      toast.error('添加基金时发生错误，请检查控制台');
    }
  }

  async handleDeleteFund(fundCode: string): Promise<void> {
    if (confirm(`确定要删除基金 ${fundCode} 吗？`)) {
      const success = await fundManager.deleteFund(fundCode);
      if (success) {
        toast.success('基金删除成功');
        await this.render();
      } else {
        toast.error('基金删除失败，可能是基金不存在或其他原因');
      }
    }
  }

  async refreshValuations(): Promise<void> {
    const funds = fundManager.getFunds();
    if (funds.length === 0) return;

    try {
      const fundCodes = funds.map(f => f.fund_code);
      const results = await api.getFundValuationBatch(fundCodes, true);

      for (const result of results) {
        const fund = fundManager.getFund(result.fund_code);
        if (fund) {
          fund.estimated_nav = result.estimated_nav;
          fund.estimated_change_percent = result.estimated_change_percent;
          fund.last_update = result.timestamp;
        }
      }

      await this.render();
    } catch (error) {
      console.error('刷新估值失败:', error);
    }
  }

  startAutoRefresh(): void {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
    }

    this.refreshInterval = window.setInterval(() => {
      this.refreshValuations();
    }, FundManagerUI.REFRESH_INTERVAL_MS);
  }

  stopAutoRefresh(): void {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
      this.refreshInterval = null;
    }
  }
}

export const fundManagerUI = new FundManagerUI();
