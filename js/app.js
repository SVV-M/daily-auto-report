// AI生成
/* ============================================
   七维洞察知识库 · 应用核心
   高端品牌交互模型: 慢·柔·缓
   ============================================ */

(function() {
  'use strict';

  // --- SVG Icon Library (NO EMOJI) ---
  const ICONS = {
    'brand-marketing': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>',
    'user-growth': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    'offline-experience': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>',
    'digital-content': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>',
    'crossover-eco': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="2"/><circle cx="6" cy="6" r="2"/><circle cx="18" cy="6" r="2"/><line x1="12" y1="12" x2="6" y2="6"/><line x1="12" y1="12" x2="18" y2="6"/></svg>',
    'industry-trend': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
    'emotion-economy': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>',
    bar: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 20V10"/><path d="M18 20V4"/><path d="M6 20v-4"/></svg>',
    bookmark: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>',
    bookmarkFill: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>'
  };

  // --- State ---
  const state = {
    activeDim: 'all',
    activeDate: 'all',
    viewMode: 'grid',
    bookmarkFilter: false,
    searchQuery: '',
    bookmarks: new Set(JSON.parse(localStorage.getItem('kb-bookmarks') || '[]')),
    graphOpen: false,
    modalCaseId: null
  };

  const $ = (s) => document.querySelector(s);
  const $$ = (s) => document.querySelectorAll(s);

  // --- Easing Helpers ---
  const EASE = {
    smooth: 'cubic-bezier(0.25, 0.1, 0.25, 1)',
    out: 'cubic-bezier(0.16, 1, 0.3, 1)',
    inOut: 'cubic-bezier(0.4, 0, 0.2, 1)'
  };

  // --- Utilities ---
  // Strip emoji characters (no emoji anywhere per design spec)
  function stripEmoji(str) {
    if (!str) return str;
    return str.replace(/[\u{1F000}-\u{1FFFF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{FE00}-\u{FE0F}\u{200D}]/gu, '').replace(/\s{2,}/g, ' ').trim();
  }

  function showToast(msg) {
    const t = $('#toast');
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(t._t);
    t._t = setTimeout(() => t.classList.remove('show'), 2800);
  }

  function animateNumber(el, target, duration) {
    duration = duration || 1200;
    const current = parseInt(el.textContent) || 0;
    if (current === target) { el.textContent = target; return; }
    const start = performance.now();
    function step(now) {
      const p = Math.min((now - start) / duration, 1);
      const e = 1 - Math.pow(1 - p, 4);
      el.textContent = Math.round(current + (target - current) * e);
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  function getCategoryById(id) {
    return REPORT_DATA.categories.find(c => c.id === id);
  }

  function getAllCases() {
    const cases = [];
    REPORT_DATA.reports.forEach(r => {
      if (r.cases) {
        r.cases.forEach(c => cases.push({ ...c, date: r.date, reportSummary: r.summary }));
      }
    });
    return cases;
  }

  function getUniqueBrands() {
    const brands = new Set();
    getAllCases().forEach(c => { if (c.brand) brands.add(c.brand); });
    return [...brands];
  }

  function toggleBookmark(caseId) {
    if (state.bookmarks.has(caseId)) {
      state.bookmarks.delete(caseId);
      showToast('已取消收藏');
    } else {
      state.bookmarks.add(caseId);
      showToast('已收藏');
    }
    localStorage.setItem('kb-bookmarks', JSON.stringify([...state.bookmarks]));
    updateBookmarkBadge();
    renderCases();
    if (state.modalCaseId) renderModal(state.modalCaseId);
  }

  function updateBookmarkBadge() {
    const badge = $('#bookmark-badge');
    const count = state.bookmarks.size;
    badge.textContent = count;
    badge.classList.toggle('visible', count > 0);
  }

  // --- Theme ---
  function initTheme() {
    const saved = localStorage.getItem('kb-theme');
    if (saved) document.documentElement.setAttribute('data-theme', saved);
  }
  function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('kb-theme', next);
  }

  // --- Preloader ---
  function hidePreloader() {
    const preloader = $('#preloader');
    if (preloader) {
      preloader.classList.add('done');
      setTimeout(() => { preloader.remove(); }, 900);
    }
  }

  // --- Scroll Reveal ---
  function initScrollReveal() {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });

    $$('.reveal').forEach(el => observer.observe(el));
    return observer;
  }

  // --- Weak Parallax ---
  function initParallax() {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    let ticking = false;
    window.addEventListener('scroll', () => {
      if (!ticking) {
        requestAnimationFrame(() => {
          const scrollY = window.scrollY;
          // Subtle parallax on ambient orbs
          const orbs = $$('.ambient-orb');
          orbs.forEach((orb, i) => {
            const speed = 0.02 + i * 0.008;
            orb.style.transform = 'translateY(' + (scrollY * speed) + 'px)';
          });
          ticking = false;
        });
        ticking = true;
      }
    }, { passive: true });
  }

  // --- Dimension Tabs ---
  function renderDimTabs() {
    const container = $('#dim-tabs');
    REPORT_DATA.categories.forEach(cat => {
      const btn = document.createElement('button');
      btn.className = 'dim-tab' + (state.activeDim === cat.id ? ' active' : '');
      btn.dataset.dim = cat.id;
      const shortName = cat.shortName || cat.name;
      btn.innerHTML = `
        <span class="dim-tab-dot" style="background: ${cat.color}"></span>
        <span class="dim-tab-label">${shortName}</span>
      `;
      btn.addEventListener('click', () => {
        state.activeDim = cat.id;
        updateDimTabs();
        renderCases();
        updateCasesTitle();
      });
      container.appendChild(btn);
    });

    container.querySelector('[data-dim="all"]').addEventListener('click', () => {
      state.activeDim = 'all';
      updateDimTabs();
      renderCases();
      updateCasesTitle();
    });

    renderMobileNav();
  }

  function updateDimTabs() {
    $$('.dim-tab').forEach(t => t.classList.toggle('active', t.dataset.dim === state.activeDim));
    $$('.mobile-nav-btn[data-dim]').forEach(b => b.classList.toggle('active', b.dataset.dim === state.activeDim));
  }

  function updateCasesTitle() {
    const title = $('#cases-title');
    if (state.activeDim === 'all') {
      title.textContent = '全部案例';
    } else {
      const cat = getCategoryById(state.activeDim);
      title.textContent = cat ? cat.name : '全部案例';
    }
  }

  // --- Bento Grid ---
  function renderBentoGrid() {
    const grid = $('#bento-grid');
    grid.innerHTML = '';

    const allCases = getAllCases();
    const layoutMap = [
      { wide: true, tall: false },
      { wide: false, tall: false },
      { wide: false, tall: true },
      { wide: false, tall: false },
      { wide: true, tall: false },
      { wide: false, tall: false },
      { wide: false, tall: false },
    ];

    REPORT_DATA.categories.forEach((cat, i) => {
      const count = allCases.filter(c => c.category === cat.id).length;
      const layout = layoutMap[i] || {};
      const card = document.createElement('div');
      card.className = 'bento-card reveal' + (layout.wide ? ' wide' : '') + (layout.tall ? ' tall' : '');
      card.style.transitionDelay = (i * 80) + 'ms';

      const iconSvg = ICONS[cat.id] || ICONS.bar;
      card.innerHTML = `
        <div class="bento-card-glow" style="background: radial-gradient(circle, ${cat.color} 0%, transparent 70%)"></div>
        <div>
          <div class="bento-card-icon" style="border-color: ${cat.color}30; color: ${cat.color}">${iconSvg}</div>
          <div class="bento-card-title">${cat.name}</div>
          <div class="bento-card-desc">${getDimDescription(cat.id)}</div>
        </div>
        <div class="bento-card-stat">
          ${ICONS.bar}
          ${count} Cases
        </div>
      `;
      card.addEventListener('click', () => {
        state.activeDim = cat.id;
        updateDimTabs();
        renderCases();
        updateCasesTitle();
        $('#cases-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
      grid.appendChild(card);
    });

    // Re-observe new reveal elements
    setTimeout(() => initScrollReveal(), 50);
  }

  function getDimDescription(id) {
    const descs = {
      'brand-marketing': '品牌定位、传播策略、视觉焕新、发布会营销与用户共创',
      'user-growth': '私域运营、裂变体系、KOC种草、社群运营与转化漏斗',
      'offline-experience': '场景化试驾、快闪活动、门店体验与线下转化闭环',
      'digital-content': '技术内容营销、数字化工具、内容生态与平台运营',
      'crossover-eco': 'IP联名、异业合作、生态联动与跨界破圈',
      'industry-trend': '市场趋势、竞品对标、政策影响与行业洞察',
      'emotion-economy': '情绪价值、情感共鸣、品牌温度与用户精神连接'
    };
    return descs[id] || '';
  }

  // --- Date Filter ---
  function renderDateFilter() {
    const select = $('#date-select');
    select.innerHTML = '<option value="all">全部日期</option>';
    const dates = [...new Set(REPORT_DATA.reports.map(r => r.date))].sort().reverse();
    dates.forEach(d => {
      const [y, m, day] = d.split('-');
      const opt = document.createElement('option');
      opt.value = d;
      opt.textContent = parseInt(m) + '月' + parseInt(day) + '日';
      select.appendChild(opt);
    });
  }

  // --- Cases ---
  function getFilteredCases() {
    let cases = getAllCases();
    if (state.activeDim !== 'all') cases = cases.filter(c => c.category === state.activeDim);
    if (state.activeDate !== 'all') cases = cases.filter(c => c.date === state.activeDate);
    if (state.bookmarkFilter) cases = cases.filter(c => state.bookmarks.has(c.id));
    if (state.searchQuery) {
      const q = state.searchQuery.toLowerCase();
      cases = cases.filter(c =>
        (c.title && c.title.toLowerCase().includes(q)) ||
        (c.brand && c.brand.toLowerCase().includes(q)) ||
        (c.type && c.type.toLowerCase().includes(q)) ||
        (c.sections && c.sections.some(s => s.content.toLowerCase().includes(q)))
      );
    }
    return cases;
  }

  function renderCases() {
    const grid = $('#cases-grid');
    const empty = $('#empty-state');
    const cases = getFilteredCases();

    grid.innerHTML = '';

    if (cases.length === 0) {
      empty.style.display = 'block';
      return;
    }
    empty.style.display = 'none';

    cases.forEach((c, i) => {
      const cat = getCategoryById(c.category);
      const card = document.createElement('div');
      card.className = 'case-card';
      // Staggered reveal with slow easing
      card.style.opacity = '0';
      card.style.transform = 'translateY(16px)';
      card.style.transition = 'opacity 700ms ' + EASE.out + ' ' + Math.min(i * 60, 600) + 'ms, transform 700ms ' + EASE.out + ' ' + Math.min(i * 60, 600) + 'ms';

      const metricsHtml = (c.metrics || []).slice(0, 3).map(m => `
        <div class="case-metric">
          <span class="case-metric-value">${m.value}</span>
          <span class="case-metric-label">${m.label}</span>
        </div>
      `).join('');

      const isBookmarked = state.bookmarks.has(c.id);
      const bmIcon = isBookmarked ? ICONS.bookmarkFill : ICONS.bookmark;
      const catShortName = cat ? cat.name.replace(/与/g, '/') : '';

      card.innerHTML = `
        <div class="case-card-top">
          <span class="case-card-badge" style="background: ${cat ? cat.color + '10' : 'rgba(184,150,90,0.06)'}; color: ${cat ? cat.color : 'var(--c-accent)'}; border: 1px solid ${cat ? cat.color + '18' : 'rgba(184,150,90,0.10)'}">
            ${catShortName}
          </span>
          <button class="case-card-bookmark ${isBookmarked ? 'active' : ''}" data-case-id="${c.id}" title="收藏" aria-label="收藏">
            ${bmIcon}
          </button>
        </div>
        <div class="case-card-title">${c.title}</div>
        <div class="case-card-brand">${c.brand || ''} ${c.type ? ' / ' + c.type : ''}</div>
        <div class="case-card-metrics">${metricsHtml}</div>
      `;

      // Bookmark click
      card.querySelector('.case-card-bookmark').addEventListener('click', (e) => {
        e.stopPropagation();
        toggleBookmark(c.id);
      });

      // Card click -> open modal
      card.addEventListener('click', () => openModal(c.id));

      grid.appendChild(card);

      // Trigger reveal
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          card.style.opacity = '1';
          card.style.transform = 'translateY(0)';
        });
      });
    });
  }

  // --- Modal ---
  function openModal(caseId) {
    state.modalCaseId = caseId;
    renderModal(caseId);
    const overlay = $('#modal-overlay');
    overlay.style.display = 'flex';
    // Trigger reflow then animate
    overlay.offsetHeight;
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }

  function closeModal() {
    state.modalCaseId = null;
    const overlay = $('#modal-overlay');
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    setTimeout(() => { overlay.style.display = 'none'; }, 700);
  }

  function renderModal(caseId) {
    const allCases = getAllCases();
    const c = allCases.find(x => x.id === caseId);
    if (!c) return;

    const cat = getCategoryById(c.category);

    // Header
    const dimBadge = $('#modal-dim-badge');
    dimBadge.textContent = cat ? cat.name : '';
    dimBadge.style.cssText = 'background: ' + (cat ? cat.color + '10' : 'rgba(184,150,90,0.06)') + '; color: ' + (cat ? cat.color : 'var(--c-accent)') + '; border: 1px solid ' + (cat ? cat.color + '18' : 'rgba(184,150,90,0.10)');

    $('#modal-brand').textContent = c.brand || '';
    $('#modal-type').textContent = c.type || '';
    $('#modal-title').textContent = c.title;

    // Bookmark
    const bmBtn = $('#modal-bookmark');
    bmBtn.classList.toggle('active', state.bookmarks.has(caseId));

    // Summary
    const report = REPORT_DATA.reports.find(r => r.date === c.date);
    $('#modal-summary').textContent = report ? stripEmoji(report.summary) : '';

    // Metrics
    const metricsEl = $('#modal-metrics');
    metricsEl.innerHTML = (c.metrics || []).map(m => `
      <div class="modal-metric">
        <div class="modal-metric-value">${m.value}</div>
        <div class="modal-metric-label">${m.label}</div>
      </div>
    `).join('');

    // STAR
    const starEl = $('#modal-star');
    const starLabels = [
      { key: 'S', cls: 'star-label-s', icon: 'S' },
      { key: 'T', cls: 'star-label-t', icon: 'T' },
      { key: 'A', cls: 'star-label-a', icon: 'A' },
      { key: 'R', cls: 'star-label-r', icon: 'R' }
    ];
    starEl.innerHTML = (c.sections || []).map((s, i) => {
      const star = starLabels[i] || starLabels[0];
      return `
        <div class="star-section">
          <div class="star-label ${star.cls}">${star.icon} — ${s.label}</div>
          <div class="star-content">${s.content}</div>
        </div>
      `;
    }).join('');

    // Related cases
    const relatedEl = $('#modal-related');
    const related = allCases.filter(x =>
      x.id !== caseId && (x.brand === c.brand || x.category === c.category)
    ).slice(0, 4);

    if (related.length > 0) {
      relatedEl.innerHTML = `
        <div class="modal-related-title">相关案例</div>
        <div class="related-cases">
          ${related.map(r => {
            const rc = getCategoryById(r.category);
            return `
              <div class="related-case" data-case-id="${r.id}">
                <span class="related-case-dot" style="background: ${rc ? rc.color : 'var(--c-accent)'}"></span>
                <div class="related-case-info">
                  <div class="related-case-name">${r.title}</div>
                  <div class="related-case-brand">${r.brand || ''} / ${rc ? rc.name.replace(/与/g, '/') : ''}</div>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      `;
      relatedEl.querySelectorAll('.related-case').forEach(el => {
        el.addEventListener('click', () => openModal(el.dataset.caseId));
      });
    } else {
      relatedEl.innerHTML = '';
    }
  }

  // --- Search ---
  function handleSearch(query) {
    state.searchQuery = query;
    const resultsEl = $('#search-results');

    if (!query || query.length < 2) {
      resultsEl.classList.remove('open');
      renderCases();
      return;
    }

    const q = query.toLowerCase();
    const allCases = getAllCases();
    const matches = allCases.filter(c =>
      (c.title && c.title.toLowerCase().includes(q)) ||
      (c.brand && c.brand.toLowerCase().includes(q)) ||
      (c.type && c.type.toLowerCase().includes(q))
    ).slice(0, 8);

    if (matches.length > 0) {
      resultsEl.innerHTML = matches.map(c => {
        const cat = getCategoryById(c.category);
        return `
          <div class="search-result-item" data-case-id="${c.id}">
            <span class="search-result-dot" style="background: ${cat ? cat.color : 'var(--c-accent)'}"></span>
            <div class="search-result-info">
              <div class="search-result-title">${c.title}</div>
              <div class="search-result-meta">${c.brand || ''} / ${cat ? cat.name.replace(/与/g, '/') : ''}</div>
            </div>
          </div>
        `;
      }).join('');
      resultsEl.classList.add('open');

      resultsEl.querySelectorAll('.search-result-item').forEach(el => {
        el.addEventListener('click', () => {
          openModal(el.dataset.caseId);
          resultsEl.classList.remove('open');
          $('#search-input').value = '';
          state.searchQuery = '';
        });
      });
    } else {
      resultsEl.innerHTML = '<div class="search-result-item"><div class="search-result-info"><div class="search-result-title" style="color:var(--c-text-muted)">未找到匹配结果</div></div></div>';
      resultsEl.classList.add('open');
    }

    renderCases();
  }

  // --- Knowledge Graph ---
  function openGraph() {
    state.graphOpen = true;
    const overlay = $('#graph-overlay');
    overlay.style.display = 'flex';
    overlay.offsetHeight;
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    renderGraph();
  }

  function closeGraph() {
    state.graphOpen = false;
    const overlay = $('#graph-overlay');
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    setTimeout(() => { overlay.style.display = 'none'; }, 700);
    if (graphAnimFrame) cancelAnimationFrame(graphAnimFrame);
    const tooltip = $('#graph-tooltip');
    if (tooltip) tooltip.style.display = 'none';
  }

  let graphAnimFrame = null;

  function renderGraph() {
    const canvas = $('#graph-canvas');
    const ctx = canvas.getContext('2d');
    const panel = canvas.parentElement;
    const dpr = window.devicePixelRatio || 1;

    canvas.width = canvas.offsetWidth * dpr;
    canvas.height = canvas.offsetHeight * dpr;
    ctx.scale(dpr, dpr);

    const W = canvas.offsetWidth;
    const H = canvas.offsetHeight;

    // Build nodes
    const nodes = [];
    const edges = [];
    const allCases = getAllCases();
    const brands = getUniqueBrands();

    // Center node
    nodes.push({ id: 'center', label: '七维洞察', x: W/2, y: H/2, r: 28, color: '#b8965a', type: 'center', vx: 0, vy: 0 });

    // Dimension nodes
    const dimCount = REPORT_DATA.categories.length;
    REPORT_DATA.categories.forEach((cat, i) => {
      const angle = (i / dimCount) * Math.PI * 2 - Math.PI / 2;
      const dist = Math.min(W, H) * 0.25;
      nodes.push({
        id: cat.id, label: cat.name.replace(/与/g, '\n'),
        x: W/2 + Math.cos(angle) * dist,
        y: H/2 + Math.sin(angle) * dist,
        r: 20, color: cat.color, type: 'dim', vx: 0, vy: 0
      });
      edges.push({ from: 'center', to: cat.id });
    });

    // Brand nodes
    const brandCount = brands.length;
    brands.forEach((brand, i) => {
      const angle = (i / brandCount) * Math.PI * 2;
      const dist = Math.min(W, H) * 0.42;
      const brandCases = allCases.filter(c => c.brand === brand);
      const dims = [...new Set(brandCases.map(c => c.category))];
      nodes.push({
        id: 'brand-' + i, label: brand,
        x: W/2 + Math.cos(angle) * dist,
        y: H/2 + Math.sin(angle) * dist,
        r: 14, color: '#6b7c93', type: 'brand', vx: 0, vy: 0
      });
      dims.forEach(dim => edges.push({ from: 'brand-' + i, to: dim }));
    });

    // Render legend
    const legend = $('#graph-legend');
    legend.innerHTML = REPORT_DATA.categories.map(cat => `
      <div class="graph-legend-item">
        <span class="graph-legend-dot" style="background: ${cat.color}"></span>
        ${cat.name.replace(/与/g, '/')}
      </div>
    `).join('');

    // Animation
    let hoverNode = null;
    let time = 0;

    function draw() {
      time += 0.003;
      ctx.clearRect(0, 0, W, H);

      // Draw edges
      edges.forEach(e => {
        const from = nodes.find(n => n.id === e.from);
        const to = nodes.find(n => n.id === e.to);
        if (!from || !to) return;

        const isHover = hoverNode && (hoverNode.id === from.id || hoverNode.id === to.id);
        ctx.beginPath();
        ctx.moveTo(from.x, from.y);
        ctx.lineTo(to.x, to.y);
        ctx.strokeStyle = isHover ? 'rgba(184,150,90,0.3)' : 'rgba(184,150,90,0.08)';
        ctx.lineWidth = isHover ? 1.5 : 0.5;
        ctx.stroke();
      });

      // Draw nodes
      nodes.forEach(n => {
        // Subtle float (slower)
        if (n.type !== 'center') {
          n.x += Math.sin(time * 0.8 + n.x * 0.005) * 0.08;
          n.y += Math.cos(time * 0.8 + n.y * 0.005) * 0.08;
        }

        const isHover = hoverNode && hoverNode.id === n.id;
        const r = isHover ? n.r * 1.15 : n.r;

        // Glow
        if (isHover || n.type === 'center') {
          ctx.beginPath();
          const grad = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, r * 2.5);
          grad.addColorStop(0, n.color + '20');
          grad.addColorStop(1, n.color + '00');
          ctx.fillStyle = grad;
          ctx.arc(n.x, n.y, r * 2.5, 0, Math.PI * 2);
          ctx.fill();
        }

        // Circle
        ctx.beginPath();
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
        ctx.fillStyle = n.color + (isHover ? 'aa' : '30');
        ctx.fill();
        ctx.strokeStyle = n.color + (isHover ? 'dd' : '60');
        ctx.lineWidth = isHover ? 2 : 1;
        ctx.stroke();

        // Label
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        ctx.fillStyle = isHover ? (isDark ? '#e8e4dc' : '#1a1a2e') : (isDark ? 'rgba(232,228,220,0.7)' : 'rgba(26,26,46,0.7)');
        ctx.font = (n.type === 'center' ? '500 12px' : n.type === 'dim' ? '400 10px' : '400 9px') + ' "Noto Sans SC", sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        const lines = n.label.split('\n');
        lines.forEach((line, li) => {
          ctx.fillText(line, n.x, n.y + (li - (lines.length - 1) / 2) * 13);
        });
      });

      graphAnimFrame = requestAnimationFrame(draw);
    }

    // Mouse interaction
    canvas.addEventListener('mousemove', (e) => {
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      hoverNode = null;
      for (const n of nodes) {
        const dx = mx - n.x, dy = my - n.y;
        if (dx*dx + dy*dy < n.r*n.r*1.5) {
          hoverNode = n;
          canvas.style.cursor = 'pointer';
          break;
        }
      }
      if (!hoverNode) canvas.style.cursor = 'default';

      const tooltip = $('#graph-tooltip');
      if (hoverNode && hoverNode.type === 'brand') {
        const brandCases = allCases.filter(c => c.brand === hoverNode.label.split('\n')[0]);
        tooltip.innerHTML = '<strong>' + hoverNode.label + '</strong><br>' + brandCases.length + ' Cases';
        tooltip.style.display = 'block';
        tooltip.style.left = (mx + 15) + 'px';
        tooltip.style.top = (my - 10) + 'px';
      } else if (hoverNode && hoverNode.type === 'dim') {
        const cat = REPORT_DATA.categories.find(c => c.id === hoverNode.id);
        const dimCases = allCases.filter(c => c.category === hoverNode.id);
        if (cat) {
          tooltip.innerHTML = '<strong>' + cat.name + '</strong><br>' + dimCases.length + ' Cases';
          tooltip.style.display = 'block';
          tooltip.style.left = (mx + 15) + 'px';
          tooltip.style.top = (my - 10) + 'px';
        }
      } else {
        tooltip.style.display = 'none';
      }
    });

    canvas.addEventListener('click', () => {
      if (hoverNode && hoverNode.type === 'dim') {
        closeGraph();
        state.activeDim = hoverNode.id;
        updateDimTabs();
        renderCases();
        updateCasesTitle();
        $('#cases-section').scrollIntoView({ behavior: 'smooth' });
      }
    });

    draw();
  }

  // --- Mobile Nav ---
  function renderMobileNav() {
    const nav = $('#mobile-nav');
    REPORT_DATA.categories.slice(0, 3).forEach(cat => {
      const btn = document.createElement('button');
      btn.className = 'mobile-nav-btn';
      btn.dataset.dim = cat.id;
      const iconSvg = ICONS[cat.id] || ICONS.bar;
      btn.innerHTML = iconSvg + '<span>' + (cat.shortName || cat.name) + '</span>';
      btn.addEventListener('click', () => {
        state.activeDim = cat.id;
        updateDimTabs();
        renderCases();
        updateCasesTitle();
      });
      nav.insertBefore(btn, $('#mobile-search-btn'));
    });
  }

  // --- Stats ---
  function renderStats() {
    const allCases = getAllCases();
    const brands = getUniqueBrands();
    const dates = [...new Set(REPORT_DATA.reports.map(r => r.date))];
    animateNumber($('#stat-total'), allCases.length, 1400);
    animateNumber($('#stat-brands'), brands.length, 1400);
    animateNumber($('#stat-days'), dates.length, 1400);
  }

  // --- Skeleton Loading ---
  function showSkeleton() {
    const grid = $('#cases-grid');
    grid.innerHTML = '';
    for (let i = 0; i < 6; i++) {
      const card = document.createElement('div');
      card.className = 'skeleton-card';
      card.innerHTML = `
        <div class="skeleton skeleton-line short"></div>
        <div class="skeleton skeleton-line long"></div>
        <div class="skeleton skeleton-line medium"></div>
        <div style="flex:1"></div>
        <div style="display:flex;gap:8px">
          <div class="skeleton skeleton-line short"></div>
          <div class="skeleton skeleton-line short"></div>
        </div>
      `;
      grid.appendChild(card);
    }
  }

  // --- Reduced Motion ---
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // --- Init ---
  function init() {
    initTheme();
    showSkeleton();

    const initDelay = prefersReducedMotion ? 0 : 500;

    setTimeout(() => {
      renderDimTabs();
      renderBentoGrid();
      renderDateFilter();
      renderCases();
      renderStats();
      updateBookmarkBadge();
      initScrollReveal();
      initParallax();

      // Hide preloader after content ready
      setTimeout(hidePreloader, 200);

      // Theme toggle
      $('#theme-toggle').addEventListener('click', toggleTheme);

      // Bookmark filter
      $('#bookmark-toggle').addEventListener('click', () => {
        state.bookmarkFilter = !state.bookmarkFilter;
        $('#bookmark-toggle').classList.toggle('active', state.bookmarkFilter);
        renderCases();
      });

      // Graph
      $('#graph-toggle').addEventListener('click', openGraph);
      $('#graph-close').addEventListener('click', closeGraph);
      $('#graph-overlay').addEventListener('click', (e) => {
        if (e.target === e.currentTarget) closeGraph();
      });

      // Modal
      $('#modal-close').addEventListener('click', closeModal);
      $('#modal-overlay').addEventListener('click', (e) => {
        if (e.target === e.currentTarget) closeModal();
      });
      $('#modal-bookmark').addEventListener('click', () => {
        if (state.modalCaseId) toggleBookmark(state.modalCaseId);
      });
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          if (state.graphOpen) closeGraph();
          else closeModal();
        }
        if (e.key === '/' && !e.ctrlKey && !e.metaKey) {
          e.preventDefault();
          $('#search-input').focus();
        }
      });

      // Search
      let searchTimer;
      $('#search-input').addEventListener('input', (e) => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => handleSearch(e.target.value), 250);
      });
      $('#search-input').addEventListener('focus', () => {
        if ($('#search-input').value.length >= 2) {
          $('#search-results').classList.add('open');
        }
      });
      document.addEventListener('click', (e) => {
        if (!$('.search-box').contains(e.target)) {
          $('#search-results').classList.remove('open');
        }
      });

      // Date filter
      $('#date-select').addEventListener('change', (e) => {
        state.activeDate = e.target.value;
        renderCases();
      });

      // View toggle
      $('#view-grid').addEventListener('click', () => {
        state.viewMode = 'grid';
        $('#cases-grid').classList.remove('list-view');
        $$('.view-btn').forEach(b => b.classList.toggle('active', b.dataset.view === 'grid'));
      });
      $('#view-list').addEventListener('click', () => {
        state.viewMode = 'list';
        $('#cases-grid').classList.add('list-view');
        $$('.view-btn').forEach(b => b.classList.toggle('active', b.dataset.view === 'list'));
      });

      // Mobile nav
      $('#mobile-search-btn')?.addEventListener('click', () => {
        const searchBox = $('.search-box');
        searchBox.style.display = 'flex';
        $('#search-input').focus();
      });
      $('#mobile-graph-btn')?.addEventListener('click', openGraph);
      $('#mobile-bookmark-btn')?.addEventListener('click', () => {
        state.bookmarkFilter = !state.bookmarkFilter;
        $('#bookmark-toggle').classList.toggle('active', state.bookmarkFilter);
        renderCases();
      });
    }, initDelay);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
