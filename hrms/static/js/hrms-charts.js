/**
 * 报表图表的公共封装（FR-RPT-01 ~ FR-RPT-03）。
 *
 * 为什么不每个页面各写一遍 ECharts 配置：
 * 三张报表一共 8 个图表，但只用到饼图 / 柱状图 / 折线图三种图型。
 * 配色、字号、提示格式一旦分散到各页面，改一次样式要翻三个文件，
 * 而且迟早出现「这张图的提示带单位、那张不带」这类不一致。
 *
 * 约定：所有数据一律由后端 JsonResponse 提供，前端不做任何计算——
 * 统计口径必须只有一处定义（apps/reporting/services.py），
 * 前端一旦自己算，就会和指标卡对不上。
 */
(function (global) {
  'use strict';

  // 与 Bootstrap 主题色保持一致的调色板，避免图表看起来像另一套系统
  var PALETTE = [
    '#2563eb', '#0ea5e9', '#22c55e', '#f59e0b',
    '#ef4444', '#8b5cf6', '#64748b', '#14b8a6'
  ];

  // 记录所有已初始化的图表，供统一 resize 使用
  var instances = [];

  /**
   * 取得容器上的图表实例；容器不存在时返回 null 而不是抛错。
   *
   * 复用已有实例，而不是每次 echarts.init()：
   * 切换年份 / 粒度时会重新渲染同一个容器，重复 init 会叠加出多个实例
   * （旧的那份仍占着内存与事件监听），表现为「切换几次之后页面越来越卡」。
   *
   * 配套约定：下面所有的 setOption 都传 notMerge=true。
   * 默认的 merge 模式不会清掉上一次的 series，
   * 从「新增/离职/净增 三条线」切到「一条线」时，旧的两条会留在图上。
   */
  function init(elementId) {
    var element = document.getElementById(elementId);
    if (!element) {
      return null;
    }
    var chart = echarts.getInstanceByDom(element);
    if (chart) {
      return chart;
    }
    chart = echarts.init(element);
    instances.push(chart);
    return chart;
  }

  /** 无数据时在图表中央显示提示，而不是留一片空白。 */
  function showEmpty(chart) {
    chart.setOption({
      title: {
        text: '暂无数据',
        left: 'center',
        top: 'middle',
        textStyle: { color: '#9ca3af', fontSize: 13, fontWeight: 'normal' }
      }
    }, true);
  }

  /** 饼图：适用于性别比例、学历构成（占比类）。 */
  function pie(elementId, data) {
    var chart = init(elementId);
    if (!chart) {
      return;
    }
    var series = (data || []).filter(function (item) { return item.value > 0; });
    if (!series.length) {
      showEmpty(chart);
      return;
    }
    chart.setOption({
      color: PALETTE,
      tooltip: { trigger: 'item', formatter: '{b}<br/>{c} 人（{d}%）' },
      legend: { bottom: 0, itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 12 } },
      series: [{
        type: 'pie',
        radius: ['42%', '66%'],
        center: ['50%', '45%'],
        avoidLabelOverlap: true,
        data: series,
        label: { formatter: '{b}\n{c} 人', fontSize: 11 },
        labelLine: { length: 8, length2: 8 },
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,.18)' } }
      }]
    }, true);
  }

  /** 单系列柱状图：适用于年龄段分布、工龄分布。 */
  function bar(elementId, data, unit) {
    var chart = init(elementId);
    if (!chart) {
      return;
    }
    var items = data || [];
    var total = items.reduce(function (sum, item) { return sum + item.value; }, 0);
    if (!total) {
      showEmpty(chart);
      return;
    }
    chart.setOption({
      color: PALETTE,
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: '{b}<br/>{c} 人'
      },
      grid: { left: 8, right: 16, top: 28, bottom: 4, containLabel: true },
      xAxis: {
        type: 'category',
        // interval: 0 强制显示所有分类名，否则 ECharts 会自动隐藏一部分，
        // 而「年龄段」这类标签一旦缺项，看图的人就会以为漏了一档
        axisLabel: { interval: 0, fontSize: 11 },
        axisTick: { show: false },
        data: items.map(function (item) { return item.name; })
      },
      yAxis: {
        type: 'value',
        minInterval: 1,
        axisLine: { show: false },
        splitLine: { lineStyle: { type: 'dashed', color: '#e2e8f0' } }
      },
      series: [{
        type: 'bar',
        barMaxWidth: 44,
        data: items.map(function (item) { return item.value; }),
        itemStyle: { borderRadius: [4, 4, 0, 0] },
        label: { show: true, position: 'top', fontSize: 11, color: '#475569' }
      }]
    }, true);
  }

  /** 分组柱状图：适用于各部门新增 / 离职对比。 */
  function groupedBar(elementId, labels, series) {
    var chart = init(elementId);
    if (!chart) {
      return;
    }
    if (!labels || !labels.length) {
      showEmpty(chart);
      return;
    }
    chart.setOption({
      color: PALETTE,
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      legend: { top: 0, itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 12 } },
      grid: { left: 8, right: 16, top: 34, bottom: 4, containLabel: true },
      xAxis: {
        type: 'category',
        data: labels,
        axisLabel: { interval: 0, fontSize: 11, rotate: labels.length > 6 ? 25 : 0 },
        axisTick: { show: false }
      },
      yAxis: {
        type: 'value',
        minInterval: 1,
        axisLine: { show: false },
        splitLine: { lineStyle: { type: 'dashed', color: '#e2e8f0' } }
      },
      series: series.map(function (item) {
        return {
          name: item.name,
          type: 'bar',
          barMaxWidth: 28,
          data: item.data,
          itemStyle: { borderRadius: [3, 3, 0, 0] }
        };
      })
    }, true);
  }

  /** 多系列折线图：适用于人员流动趋势、在职人数变化。 */
  function line(elementId, labels, series, unit) {
    var chart = init(elementId);
    if (!chart) {
      return;
    }
    if (!labels || !labels.length) {
      showEmpty(chart);
      return;
    }
    chart.setOption({
      color: PALETTE,
      tooltip: { trigger: 'axis' },
      legend: { top: 0, itemWidth: 10, itemHeight: 10, textStyle: { fontSize: 12 } },
      grid: { left: 8, right: 20, top: 34, bottom: 4, containLabel: true },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: labels,
        axisLabel: { fontSize: 11 },
        axisTick: { show: false }
      },
      yAxis: {
        type: 'value',
        minInterval: 1,
        name: unit || '',
        nameTextStyle: { color: '#94a3b8', fontSize: 11 },
        axisLine: { show: false },
        splitLine: { lineStyle: { type: 'dashed', color: '#e2e8f0' } }
      },
      // smooth 关闭：折线图平滑后会在数据点之间造出实际不存在的起伏，
      // 而月度人数是离散事实，宁可让它看起来「硬」一点
      series: series.map(function (item) {
        return {
          name: item.name,
          type: 'line',
          smooth: false,
          symbolSize: 6,
          data: item.data,
          lineStyle: { width: 2 },
          areaStyle: item.area ? { opacity: 0.12 } : null
        };
      })
    }, true);
  }

  /**
   * 拉取报表数据。
   * 失败时不静默——把所有图表容器替换为提示文案，
   * 否则页面看起来只是「图表是空的」，会被误当作没有数据。
   */
  function fetchData(url, onSuccess) {
    fetch(url, {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin'
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error('HTTP ' + response.status);
        }
        return response.json();
      })
      .then(onSuccess)
      .catch(function (error) {
        // 控制台留详细原因，界面上只给人看得懂的提示
        console.error('[报表] 数据加载失败：', error);
        Array.prototype.forEach.call(
          document.querySelectorAll('.chart-box'),
          function (element) {
            element.innerHTML = '<div class="chart-fallback">数据加载失败，请刷新页面重试</div>';
          }
        );
      });
  }

  /** 窗口尺寸变化时重算所有图表尺寸。 */
  global.addEventListener('resize', function () {
    instances.forEach(function (chart) {
      chart.resize();
    });
  });

  global.HRMSCharts = {
    pie: pie,
    bar: bar,
    groupedBar: groupedBar,
    line: line,
    fetchData: fetchData
  };
})(window);
