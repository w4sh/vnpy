/**
 * 持仓概览页面 JavaScript
 * 负责数据获取、图表渲染、表格更新
 */

// 全局变量
let positionsData = [];
let strategiesData = [];
let distributionChart = null;
let comparisonChart = null;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    initCharts();
    loadDashboardData();

    // 绑定搜索事件
    document.getElementById('search-input').addEventListener('input', filterPositions);
    document.getElementById('strategy-filter').addEventListener('change', filterPositions);
    document.getElementById('profit-filter').addEventListener('change', filterPositions);

    // 定时刷新（每30秒）
    setInterval(refreshData, 30000);
});

/**
 * 初始化图表
 */
function initCharts() {
    // 持仓分布饼图
    const distCtx = document.getElementById('position-distribution-chart').getContext('2d');
    distributionChart = new Chart(distCtx, {
        type: 'pie',
        data: {
            labels: [],
            datasets: [{
                data: [],
                backgroundColor: [
                    '#FF6384',
                    '#36A2EB',
                    '#FFCE56',
                    '#4BC0C0',
                    '#9966FF',
                    '#FF9F40',
                    '#FF6384',
                    '#C9CBCF'
                ]
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom'
                }
            }
        }
    });

    // 策略对比柱状图
    const compCtx = document.getElementById('strategy-comparison-chart').getContext('2d');
    comparisonChart = new Chart(compCtx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [
                {
                    label: '总资产',
                    data: [],
                    backgroundColor: 'rgba(54, 162, 235, 0.8)',
                    borderColor: 'rgba(54, 162, 235, 1)',
                    borderWidth: 1
                },
                {
                    label: '收益率(%)',
                    data: [],
                    backgroundColor: 'rgba(255, 99, 132, 0.8)',
                    borderColor: 'rgba(255, 99, 132, 1)',
                    borderWidth: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true
                }
            },
            plugins: {
                legend: {
                    position: 'top'
                }
            }
        }
    });
}

/**
 * 加载仪表盘数据
 */
async function loadDashboardData() {
    try {
        // 并行加载所有数据
        const [analytics, positions, strategies] = await Promise.all([
            fetch('/api/analytics/portfolio').then(r => r.json()),
            fetch('/api/positions').then(r => r.json()),
            fetch('/api/strategies').then(r => r.json())
        ]);

        // 更新指标卡片
        updateMetricsCards(analytics);

        // 更新图表
        updateCharts(analytics, positions);

        // 更新表格
        positionsData = positions.positions || [];
        strategiesData = strategies.strategies || [];
        renderPositionsTable(positionsData);

        // 更新策略筛选器
        updateStrategyFilter(strategiesData);

    } catch (error) {
        console.error('加载数据失败:', error);
        showError('数据加载失败，请刷新页面重试');
    }
}

/**
 * 更新指标卡片
 */
function updateMetricsCards(analytics) {
    if (!analytics.success || !analytics.analytics) {
        return;
    }

    const summary = analytics.analytics.summary;
    document.getElementById('total-assets').textContent =
        formatCurrency(summary.total_assets || 0);
    document.getElementById('total-profit').textContent =
        formatCurrency(summary.total_profit || 0);
    document.getElementById('total-return-pct').textContent =
        formatPercent(summary.total_profit_pct || 0);
    document.getElementById('position-count').textContent =
        (summary.position_count || 0) + ' 只';

    // 根据盈亏设置颜色
    const profitElement = document.getElementById('total-profit');
    if (summary.total_profit >= 0) {
        profitElement.classList.add('profit-positive');
        profitElement.classList.remove('profit-negative');
    } else {
        profitElement.classList.add('profit-negative');
        profitElement.classList.remove('profit-positive');
    }
}

/**
 * 更新图表
 */
function updateCharts(analytics, positions) {
    if (!analytics.success || !analytics.analytics) {
        return;
    }

    const distribution = analytics.analytics.distribution || [];

    // 更新持仓分布饼图
    distributionChart.data.labels = distribution.map(d => d.name || d.symbol);
    distributionChart.data.datasets[0].data = distribution.map(d => d.market_value);
    distributionChart.update();

    // 更新策略对比图表
    // TODO: 从API获取策略对比数据
}

/**
 * 渲染持仓表格
 */
function renderPositionsTable(positions) {
    const tbody = document.getElementById('positions-table-body');

    if (!positions || positions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="text-center">暂无持仓数据</td></tr>';
        return;
    }

    tbody.innerHTML = positions.map(p => 
        '<tr>' +
            '<td><strong>' + p.symbol + '</strong></td>' +
            '<td>' + (p.name || '-') + '</td>' +
            '<td>' + p.quantity.toLocaleString() + '</td>' +
            '<td>¥' + p.cost_price.toFixed(2) + '</td>' +
            '<td>¥' + (p.current_price || 0).toFixed(2) + '</td>' +
            '<td>¥' + (p.market_value || 0).toLocaleString() + '</td>' +
            '<td class="' + (p.profit_loss >= 0 ? 'profit-positive' : 'profit-negative') + '">' +
            '¥' + (p.profit_loss || 0).toLocaleString() +
            '</td>' +
            '<td class="' + ((p.profit_loss_pct || 0) >= 0 ? 'profit-positive' : 'profit-negative') + '">' +
            formatPercent(p.profit_loss_pct || 0) +
            '</td>' +
            '<td>' + (p.strategy_name || '-') + '</td>' +
            '<td>' +
            '<button class="btn btn-sm btn-outline-primary" onclick="viewPositionDetail(' + p.id + ')">详情</button>' +
            '</td>' +
        '</tr>'
    ).join('');
}

/**
 * 更新策略筛选器
 */
function updateStrategyFilter(strategies) {
    const select = document.getElementById('strategy-filter');
    select.innerHTML = '<option value="">所有策略</option>';

    strategies.forEach(s => {
        const option = document.createElement('option');
        option.value = s.id;
        option.textContent = s.name;
        select.appendChild(option);
    });
}

/**
 * 筛选持仓
 */
function filterPositions() {
    const searchText = document.getElementById('search-input').value.toLowerCase();
    const strategyId = document.getElementById('strategy-filter').value;
    const profitFilter = document.getElementById('profit-filter').value;

    const filtered = positionsData.filter(p => {
        // 搜索过滤
        const matchSearch = !searchText ||
            p.symbol.toLowerCase().includes(searchText) ||
            (p.name && p.name.toLowerCase().includes(searchText));

        // 策略过滤
        const matchStrategy = !strategyId || p.strategy_id == strategyId;

        // 盈亏过滤
        let matchProfit = true;
        if (profitFilter === 'profit') {
            matchProfit = p.profit_loss > 0;
        } else if (profitFilter === 'loss') {
            matchProfit = p.profit_loss < 0;
        }

        return matchSearch && matchStrategy && matchProfit;
    });

    renderPositionsTable(filtered);
}

/**
 * 刷新数据
 */
function refreshData() {
    loadDashboardData();
}

/**
 * 导出数据
 */
function exportData() {
    // 导出为CSV
    const headers = ['股票代码', '股票名称', '持仓数量', '成本价', '当前价', '市值', '盈亏', '盈亏%', '策略'];
    const rows = positionsData.map(p => [
        p.symbol,
        p.name || '',
        p.quantity,
        p.cost_price,
        p.current_price || 0,
        p.market_value || 0,
        p.profit_loss || 0,
        p.profit_loss_pct || 0,
        p.strategy_name || ''
    ]);

    const csvContent = [
        headers.join(','),
        ...rows.map(row => row.map(cell => '"' + cell + '"').join(','))
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = '持仓数据_' + new Date().toISOString().slice(0,10) + '.csv';
    link.click();
}

/**
 * 查看持仓详情
 */
function viewPositionDetail(positionId) {
    // TODO: 打开详情模态框或跳转到详情页
    alert('查看持仓详情: ' + positionId + '\n此功能待实现');
}

/**
 * 格式化货币
 */
function formatCurrency(value) {
    if (value >= 0) {
        return '¥' + value.toLocaleString('zh-CN', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    } else {
        return '-¥' + Math.abs(value).toLocaleString('zh-CN', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    }
}

/**
 * 格式化百分比
 */
function formatPercent(value) {
    const sign = value >= 0 ? '+' : '';
    return sign + value.toFixed(2) + '%';
}

/**
 * 显示错误消息
 */
function showError(message) {
    alert(message);
}
