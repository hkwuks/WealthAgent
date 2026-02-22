export class ChartRenderer {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('Could not get 2D context');
    this.ctx = ctx;
  }

  clear(): void {
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
  }

  drawPieChart(data: Array<{ label: string; value: number; color: string }>): void {
    const centerX = this.canvas.width / 2;
    const centerY = this.canvas.height / 2;
    const radius = Math.min(centerX, centerY) - 20;

    const total = data.reduce((sum, item) => sum + item.value, 0);
    let startAngle = -Math.PI / 2;

    data.forEach((item) => {
      const sliceAngle = (item.value / total) * 2 * Math.PI;
      
      this.ctx.beginPath();
      this.ctx.moveTo(centerX, centerY);
      this.ctx.arc(centerX, centerY, radius, startAngle, startAngle + sliceAngle);
      this.ctx.closePath();
      this.ctx.fillStyle = item.color;
      this.ctx.fill();

      startAngle += sliceAngle;
    });

    this.drawLegend(data, centerX, centerY, radius);
  }

  private drawLegend(data: Array<{ label: string; value: number; color: string }>, centerX: number, centerY: number, radius: number): void {
    const legendX = centerX + radius + 20;
    const legendY = centerY - (data.length * 25) / 2;

    data.forEach((item, index) => {
      const y = legendY + index * 25;
      
      this.ctx.fillStyle = item.color;
      this.ctx.fillRect(legendX, y, 15, 15);
      
      this.ctx.fillStyle = '#374151';
      this.ctx.font = '12px sans-serif';
      this.ctx.fillText(`${item.label}: ${item.value.toFixed(2)}`, legendX + 20, y + 12);
    });
  }

  drawBarChart(data: Array<{ label: string; value: number }>, maxValue?: number): void {
    const padding = 40;
    const chartWidth = this.canvas.width - padding * 2;
    const chartHeight = this.canvas.height - padding * 2;
    const barWidth = chartWidth / data.length - 10;
    const maxVal = maxValue || Math.max(...data.map(d => d.value));

    this.ctx.fillStyle = '#6366f1';
    data.forEach((item, index) => {
      const barHeight = (item.value / maxVal) * chartHeight;
      const x = padding + index * (barWidth + 10);
      const y = this.canvas.height - padding - barHeight;

      this.ctx.fillRect(x, y, barWidth, barHeight);

      this.ctx.fillStyle = '#374151';
      this.ctx.font = '10px sans-serif';
      this.ctx.textAlign = 'center';
      this.ctx.fillText(item.label, x + barWidth / 2, this.canvas.height - padding + 15);
      this.ctx.fillText(item.value.toFixed(2), x + barWidth / 2, y - 5);
      this.ctx.fillStyle = '#6366f1';
    });
  }

  resize(width: number, height: number): void {
    this.canvas.width = width;
    this.canvas.height = height;
  }
}
