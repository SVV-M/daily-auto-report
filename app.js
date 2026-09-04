// AI生成
/* ============================================
   每日案例报告站 · 应用逻辑 v3
   案例级收藏 + 维度分Tab + 深度下钻
   ============================================ */

(function() {
  'use strict';

  // --- 状态管理 ---
  const state = {
    currentView: 'calendar',
    currentYear: new Date().getFullYear(),
    currentMonth: new Date().getMonth(),
    activeCategories: new Set(),
    bookmarkFilter: false,
    sortMode: 'date-desc',
    // 收藏改为案例级：key = caseId (如 "2026-09-03-emotional-econ")
    bookmarks: new Set(JSON.parse(localStorage.getItem('report-case-bookmarks') || '[]')),
    currentReportDate: null,
    currentDimTab: '__all__'  // 弹窗内当前维度Tab
  };

  // --- DOM 引用 ---
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  // --- 工具函数 ---
  function formatDate(dateStr) {
    const [y, m, d] = dateStr.split('-');
    return `${y}年${parseInt(m)}月${parseInt(d)}日`;
  }

  function formatDateShort(dateStr) {
    const [y, m, d] = dateStr.split('-');
    return `${parseInt(m)}月${parseInt(d)}日`;
  }

  function showToast(msg) {
    const toast = $('#toast');
    toast.textContent = msg;
    toast.classList.add('show');
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => toast.classList.remove('show'), 2500);
  }

  // 获取某日有哪些案例被收藏
  function getBookmarkedCaseIdsForDate(date) {
    return [...state.bookmarks].filter(id => id.startsWith(date + '-'));
  }

  // 某日是否有任何收藏
  function hasAnyBookmarkForDate(date) {
    return [...state.bookmarks].some(id => id.startsWith(date + '-'));
  }

  // 案例级收藏切换
  function toggleCaseBookmark(caseId) {
    if (state.bookmarks.has(caseId)) {
      state.bookmarks.delete(caseId);
      showToast('已取消收藏');
    } else {
      state.bookmarks.add(caseId);
      showToast('⭐ 已收藏该案例');
    }
    localStorage.setItem('report-case-bookmarks', JSON.stringify([...state.bookmarks]));
    updateBookmarkUI();
    renderCurrentView();
    // 如果弹窗打开，也刷新弹窗内容
    if (state.currentReportDate) {
      renderModalCases(state.currentReportDate, state.currentDimTab);
    }
  }

  function updateBookmarkUI() {
    const btn = $('#bookmark-filter-btn');
    btn.classList.toggle('active', state.bookmarkFilter);
    $('#total-bookmarks').textContent = state.bookmarks.size;
  }

  // --- 数字跳动动画 ---
  function animateValue(el, newVal) {
    const current = parseInt(el.textContent) || 0;
    const target = parseInt(newVal) || 0;
    if (current === target) { el.textContent = target; return; }
    const duration = 400;
    const start = performance.now();
    function step(now) {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      el.textContent = Math.round(current + (target - current) * eased);
      if (progress < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  // --- 辅助：从 report.cases 提取 category 列表 ---
  function getReportCategories(report) {
    if (report.cases) {
      return [...new Set(report.cases.map(c => c.category))];
    }
    return report.categories || [];
  }

  // --- 分类渲染 ---
  function renderCategories() {
    const list = $('#category-list');
    list.innerHTML = '';

    const allItem = document.createElement('div');
    allItem.className = 'category-item' + (state.activeCategories.size === 0 ? ' active' : '');
    allItem.innerHTML = `
      <span class="category-dot" style="background: var(--c-primary)"></span>
      <span>全部</span>
      <span class="category-count">${REPORT_DATA.reports.length}</span>
    `;
    allItem.addEventListener('click', () => {
      state.activeCategories.clear();
      renderCategories();
      renderCurrentView();
    });
    list.appendChild(allItem);

    REPORT_DATA.categories.forEach(cat => {
      const count = REPORT_DATA.reports.filter(r => getReportCategories(r).includes(cat.id)).length;
      const item = document.createElement('div');
      item.className = 'category-item' + (state.activeCategories.has(cat.id) ? ' active' : '');
      item.innerHTML = `
        <span class="category-dot" style="background: ${cat.color}"></span>
        <span>${cat.icon} ${cat.name}</span>
        <span class="category-count">${count}</span>
      `;
      item.addEventListener('click', () => {
        if (state.activeCategories.has(cat.id)) {
          state.activeCategories.delete(cat.id);
        } else {
          state.activeCategories.add(cat.id);
        }
        renderCategories();
        renderCurrentView();
      });
      list.appendChild(item);
    });
  }

  // --- 筛选逻辑 ---
  function getFilteredReports() {
    let reports = [...REPORT_DATA.reports];

    if (state.activeCategories.size > 0) {
      reports = reports.filter(r =>
        getReportCategories(r).some(c => state.activeCategories.has(c))
      );
    }

    if (state.bookmarkFilter) {
      // 案例级收藏过滤：某日有任一案例被收藏则显示
      reports = reports.filter(r => hasAnyBookmarkForDate(r.date));
    }

    reports.sort((a, b) => {
      const diff = a.date.localeCompare(b.date);
      return state.sortMode === 'date-desc' ? -diff : diff;
    });

    return reports;
  }

  // --- 日历渲染 ---
  function renderCalendar() {
    const { currentYear, currentMonth } = state;
    const filtered = getFilteredReports();
    const filteredDates = new Set(filtered.map(r => r.date));

    $('#current-month').textContent = `${currentYear}年${currentMonth + 1}月`;

    const firstDay = new Date(currentYear, currentMonth, 1).getDay();
    const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
    const daysInPrevMonth = new Date(currentYear, currentMonth, 0).getDate();
    const today = new Date();
    const todayStr = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;

    const grid = $('#calendar-grid');
    grid.innerHTML = '';

    for (let i = firstDay - 1; i >= 0; i--) {
      const day = daysInPrevMonth - i;
      grid.appendChild(createDayCell(day, true));
    }

    for (let d = 1; d <= daysInMonth; d++) {
      const dateStr = `${currentYear}-${String(currentMonth+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
      const report = REPORT_DATA.reports.find(r => r.date === dateStr);
      const isToday = dateStr === todayStr;
      const hasReport = report && filteredDates.has(dateStr);
      grid.appendChild(createDayCell(d, false, isToday, hasReport, report, dateStr));
    }

    const totalCells = firstDay + daysInMonth;
    const remaining = (7 - totalCells % 7) % 7;
    for (let i = 1; i <= remaining; i++) {
      grid.appendChild(createDayCell(i, true));
    }
  }

  function createDayCell(day, otherMonth, isToday, hasReport, report, dateStr) {
    const cell = document.createElement('div');
    cell.className = 'calendar-day';
    if (otherMonth) cell.classList.add('other-month');
    if (isToday) cell.classList.add('today');
    if (hasReport) cell.classList.add('has-report');

    cell.innerHTML = `<span>${day}</span>`;

    if (hasReport && report) {
      const dotsDiv = document.createElement('div');
      dotsDiv.className = 'calendar-dots';
      const cats = getReportCategories(report);
      const uniqueCats = [...new Set(cats)].slice(0, 4);
      uniqueCats.forEach(catId => {
        const cat = REPORT_DATA.categories.find(c => c.id === catId);
        if (cat) {
          const dot = document.createElement('span');
          dot.className = 'calendar-dot';
          dot.style.background = cat.color;
          dotsDiv.appendChild(dot);
        }
      });
      cell.appendChild(dotsDiv);

      if (hasAnyBookmarkForDate(dateStr)) {
        const bm = document.createElement('span');
        bm.className = 'calendar-bookmark';
        bm.textContent = '⭐';
        cell.appendChild(bm);
      }

      cell.addEventListener('click', () => openReport(dateStr));
    }

    return cell;
  }

  // --- 列表渲染 ---
  function renderTimeline() {
    const filtered = getFilteredReports();
    const list = $('#timeline-list');
    const empty = $('#empty-state');

    if (filtered.length === 0) {
      list.innerHTML = '';
      empty.style.display = 'block';
      return;
    }
    empty.style.display = 'none';

    list.innerHTML = filtered.map((report, i) => {
      const bmCount = getBookmarkedCaseIdsForDate(report.date).length;
      const cats = getReportCategories(report);
      const tags = cats.map(catId => {
        const cat = REPORT_DATA.categories.find(c => c.id === catId);
        if (!cat) return '';
        return `<span class="tag" style="color:${cat.color};border-color:${cat.color}30;background:${cat.color}10">${cat.icon} ${cat.name}</span>`;
      }).join('');

      return `
        <div class="report-card" style="animation-delay:${i * 60}ms" data-date="${report.date}">
          <div class="report-card-header">
            <span class="report-card-date">${formatDateShort(report.date)}</span>
            <div class="report-card-title">${report.title}</div>
            <button class="report-card-bookmark ${bmCount > 0 ? 'bookmarked' : ''}" data-date="${report.date}" title="${bmCount > 0 ? bmCount + '个案例已收藏' : '点击查看'}">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="${bmCount > 0 ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
              ${bmCount > 0 ? `<span class="bm-badge">${bmCount}</span>` : ''}
            </button>
          </div>
          <div class="report-card-summary">${report.summary}</div>
          <div class="report-card-tags">${tags}</div>
        </div>
      `;
    }).join('');

    list.querySelectorAll('.report-card').forEach(card => {
      card.addEventListener('click', (e) => {
        if (e.target.closest('.report-card-bookmark')) {
          e.stopPropagation();
          // 点击收藏图标直接打开报告弹窗
          openReport(card.dataset.date);
          return;
        }
        openReport(card.dataset.date);
      });
    });
  }

  // --- 弹窗内：渲染维度Tab栏 ---
  function renderDimTabs(dateStr, activeTab) {
    const report = REPORT_DATA.reports.find(r => r.date === dateStr);
    if (!report || !report.cases) return;

    const tabBar = $('#modal-dim-tabs');
    const cats = getReportCategories(report);

    // "全部"Tab
    let html = `<button class="dim-tab ${activeTab === '__all__' ? 'active' : ''}" data-dim="__all__">全部 (${report.cases.length})</button>`;

    // 各维度Tab
    cats.forEach(catId => {
      const cat = REPORT_DATA.categories.find(c => c.id === catId);
      if (!cat) return;
      const count = report.cases.filter(c => c.category === catId).length;
      html += `<button class="dim-tab ${activeTab === catId ? 'active' : ''}" data-dim="${catId}" style="--tab-color:${cat.color}">${cat.icon} ${cat.name} (${count})</button>`;
    });

    tabBar.innerHTML = html;

    // 绑定Tab点击
    tabBar.querySelectorAll('.dim-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        state.currentDimTab = btn.dataset.dim;
        renderDimTabs(dateStr, state.currentDimTab);
        renderModalCases(dateStr, state.currentDimTab);
      });
    });
  }

  // --- 弹窗内：渲染案例卡片 ---
  function renderModalCases(dateStr, dimFilter) {
    const report = REPORT_DATA.reports.find(r => r.date === dateStr);
    if (!report || !report.cases) return;

    const container = $('#modal-cases');
    let cases = report.cases;

    if (dimFilter !== '__all__') {
      cases = cases.filter(c => c.category === dimFilter);
    }

    container.innerHTML = cases.map(c => {
      const cat = REPORT_DATA.categories.find(ct => ct.id === c.category);
      if (!cat) return '';
      const isBm = state.bookmarks.has(c.id);

      const sectionsHtml = (c.sections || []).map(s => `
        <div class="case-section">
          <h4>${s.label}</h4>
          <p>${s.content}</p>
        </div>
      `).join('');

      const metricsHtml = (c.metrics || []).map(m => `
        <span class="metric">${m.label} <strong>${m.value}</strong></span>
      `).join('');

      return `
        <div class="case-card" data-case-id="${c.id}">
          <div class="case-card-header">
            <span class="case-cat" style="background:${cat.color}18;color:${cat.color};border:1px solid ${cat.color}30">${cat.icon} ${cat.name}</span>
            <span class="case-card-title">${c.title}</span>
            <button class="case-bookmark-btn ${isBm ? 'bookmarked' : ''}" data-case-id="${c.id}" title="${isBm ? '取消收藏' : '收藏该案例'}">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="${isBm ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
            </button>
          </div>
          <p class="case-brand">品牌：${c.brand} | 类型：${c.type}</p>
          ${sectionsHtml}
          ${metricsHtml ? `<div class="case-metrics">${metricsHtml}</div>` : ''}
        </div>
      `;
    }).join('');

    // 绑定案例级收藏按钮
    container.querySelectorAll('.case-bookmark-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleCaseBookmark(btn.dataset.caseId);
      });
    });
  }

  // --- 打开报告弹窗 ---
  function openReport(dateStr) {
    const report = REPORT_DATA.reports.find(r => r.date === dateStr);
    if (!report) return;

    state.currentReportDate = dateStr;
    state.currentDimTab = '__all__';
    const overlay = $('#modal-overlay');

    $('#modal-title').textContent = report.title + ' · ' + formatDate(dateStr);

    // 摘要
    $('#modal-summary-text').textContent = report.summary;

    // 维度Tab
    renderDimTabs(dateStr, '__all__');

    // 案例卡片
    renderModalCases(dateStr, '__all__');

    overlay.classList.add('open');
    document.body.style.overflow = 'hidden';
  }

  function closeReport() {
    $('#modal-overlay').classList.remove('open');
    document.body.style.overflow = '';
    state.currentReportDate = null;
    state.currentDimTab = '__all__';
  }

  // --- 视图切换 ---
  function renderCurrentView() {
    if (state.currentView === 'calendar') {
      renderCalendar();
    } else {
      renderTimeline();
    }
    updateStats();
  }

  function switchView(view) {
    state.currentView = view;
    $$('.view-toggle').forEach(btn => btn.classList.toggle('active', btn.dataset.view === view));
    $$('.view').forEach(v => v.classList.remove('active'));
    $(`#${view}-view`).classList.add('active');
    renderCurrentView();
  }

  // --- 统计更新（带动画） ---
  function updateStats() {
    const filtered = getFilteredReports();
    animateValue($('#total-reports'), filtered.length);
    animateValue($('#total-bookmarks'), state.bookmarks.size);
    const uniqueDays = new Set(REPORT_DATA.reports.map(r => r.date));
    animateValue($('#total-days'), uniqueDays.size);
  }

  // --- 主题切换 ---
  function toggleTheme() {
    const html = document.documentElement;
    const current = html.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('report-theme', next);
  }

  // --- 初始化 ---
  function init() {
    const savedTheme = localStorage.getItem('report-theme');
    if (savedTheme) document.documentElement.setAttribute('data-theme', savedTheme);
    else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
      document.documentElement.setAttribute('data-theme', 'dark');
    }

    renderCategories();
    renderCurrentView();

    $$('.view-toggle').forEach(btn => {
      btn.addEventListener('click', () => switchView(btn.dataset.view));
    });

    $('#prev-month').addEventListener('click', () => {
      state.currentMonth--;
      if (state.currentMonth < 0) { state.currentMonth = 11; state.currentYear--; }
      renderCalendar();
    });
    $('#next-month').addEventListener('click', () => {
      state.currentMonth++;
      if (state.currentMonth > 11) { state.currentMonth = 0; state.currentYear++; }
      renderCalendar();
    });

    $('#bookmark-filter-btn').addEventListener('click', () => {
      state.bookmarkFilter = !state.bookmarkFilter;
      updateBookmarkUI();
      renderCurrentView();
    });

    $$('.sort-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        state.sortMode = btn.dataset.sort;
        $$('.sort-btn').forEach(b => b.classList.toggle('active', b === btn));
        renderTimeline();
      });
    });

    $('#theme-toggle').addEventListener('click', toggleTheme);

    $('#modal-close').addEventListener('click', closeReport);
    $('#modal-overlay').addEventListener('click', (e) => {
      if (e.target === e.currentTarget) closeReport();
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeReport();
    });

    const sidebar = $('#sidebar');
    $('#mobile-filter-btn')?.addEventListener('click', () => sidebar.classList.add('open'));
    $('#sidebar-close')?.addEventListener('click', () => sidebar.classList.remove('open'));

    document.addEventListener('click', (e) => {
      if (sidebar.classList.contains('open') &&
          !sidebar.contains(e.target) &&
          !$('#mobile-filter-btn').contains(e.target)) {
        sidebar.classList.remove('open');
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
