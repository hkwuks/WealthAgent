import type { Fund } from './types';

export class StorageService {
  private static readonly FUNDS_KEY = 'fund_valuation_funds';

  // 保存基金数据到本地存储
  static saveFunds(funds: Fund[]): void {
    localStorage.setItem(this.FUNDS_KEY, JSON.stringify(funds));
  }

  // 从本地存储加载基金数据
  static loadFunds(): Fund[] {
    const data = localStorage.getItem(this.FUNDS_KEY);
    return data ? JSON.parse(data) : [];
  }

  // 清除本地存储中的基金数据
  static clearFunds(): void {
    localStorage.removeItem(this.FUNDS_KEY);
  }

  // 保存基金数据到后端文件 (data/funds.json)
  static async saveFundsToFile(funds: Fund[]): Promise<boolean> {
    try {
      const response = await fetch('/api/funds/save', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ funds }),
      });
      return response.ok;
    } catch (error) {
      console.error('保存基金数据到文件失败:', error);
      return false;
    }
  }

  // 从后端文件加载基金数据
  static async loadFundsFromFile(): Promise<Fund[]> {
    try {
      const response = await fetch('/api/funds');
      if (!response.ok) {
        throw new Error('加载基金数据失败');
      }
      const data = await response.json();
      return data.success ? data.data.funds : [];
    } catch (error) {
      console.error('从文件加载基金数据失败:', error);
      return [];
    }
  }
}
