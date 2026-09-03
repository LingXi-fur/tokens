(function () {
  'use strict';

  var isZh = (document.documentElement.lang || '').toLowerCase().indexOf('zh') === 0;
  var labels = isZh ? {
    pages: [
      { title: '首页', url: 'index.html', desc: '项目能力、安装入口与合成数据预览', keywords: '首页 tokens token 统计 文档' },
      { title: '快速开始', url: 'getting-started.html', desc: '安装、首次运行、生成报告和常见配置', keywords: '安装 pipx python 开始 html dashboard' },
      { title: 'CLI 参考', url: 'cli.html', desc: 'day、week、month、all、dashboard 与全部参数', keywords: '命令行 参数 source since until cache open' },
      { title: 'Dashboard', url: 'dashboard.html', desc: '交互功能、快捷键、导出与合成演示', keywords: '图表 模型 筛选 成就 年鉴 星云 导出' },
      { title: '数据与隐私', url: 'data-and-privacy.html', desc: '日志路径、缓存、报告敏感信息与安全分享', keywords: '隐私 本地 日志 会话 cwd 路径 上传' },
      { title: '架构', url: 'architecture.html', desc: '读取、统一记录、聚合与报告生成流程', keywords: 'readers aggregate report config stdlib 架构' },
      { title: 'FAQ', url: 'faq.html', desc: '日志缺失、统计差异、主题、平台支持等问题', keywords: '问题 帮助 日志 无数据 时区 windows' }
    ],
    theme: { light: '亮色', dark: '暗色', auto: '自动' }, copy: '复制', copied: '已复制',
    empty: '没有匹配结果。试试“隐私”“dashboard”或“source”。', synthetic: '合成数据：', locale: 'zh-CN'
  } : {
    pages: [
      { title: 'Home', url: 'index.html', desc: 'Capabilities, installation, and synthetic preview', keywords: 'home tokens usage analytics local' },
      { title: 'Get started', url: 'getting-started.html', desc: 'Install, diagnose, and generate the first report', keywords: 'install pipx python doctor dashboard' },
      { title: 'CLI reference', url: 'cli.html', desc: 'Commands, ranges, sources, timezone, and output', keywords: 'command options source since until cache output' },
      { title: 'Dashboard', url: 'dashboard.html', desc: 'Core analysis, Data Trail, labs, and shortcuts', keywords: 'chart model filter session context export' },
      { title: 'Data and privacy', url: 'data-and-privacy.html', desc: 'Local paths, cache, reports, and safe sharing', keywords: 'privacy local logs session cwd pseudonymize' },
      { title: 'Architecture', url: 'architecture.html', desc: 'Package structure and local data flow', keywords: 'readers aggregate package stdlib architecture' },
      { title: 'FAQ', url: 'faq.html', desc: 'Installation, missing logs, timezone, cache, and privacy', keywords: 'help no logs timezone windows browser' }
    ],
    theme: { light: 'light', dark: 'dark', auto: 'system' }, copy: 'Copy', copied: 'Copied',
    empty: 'No matching results. Try “privacy”, “dashboard”, or “source”.', synthetic: 'Synthetic data: ', locale: 'en-US'
  };
  var pages = labels.pages;

  var root = document.documentElement;
  var basePrefix = location.pathname.indexOf('/docs/') >= 0 ? '' : '';

  function setTheme(theme) {
    if (theme === 'light' || theme === 'dark') root.setAttribute('data-theme', theme);
    else root.removeAttribute('data-theme');
    try { localStorage.setItem('tokens-docs-theme', theme); } catch (e) {}
    document.querySelectorAll('[data-theme-choice]').forEach(function (button) {
      button.classList.toggle('active', button.getAttribute('data-theme-choice') === theme);
    });
    var trigger = document.querySelector('[data-theme-trigger]');
    if (trigger) {
      trigger.textContent = theme === 'light' ? '☀' : theme === 'dark' ? '☾' : '◐';
      trigger.setAttribute('aria-label', (isZh ? '当前主题：' : 'Current theme: ') + labels.theme[theme]);
    }
  }

  function currentTheme() {
    try { return localStorage.getItem('tokens-docs-theme') || 'auto'; } catch (e) { return 'auto'; }
  }

  setTheme(currentTheme());

  var themeTrigger = document.querySelector('[data-theme-trigger]');
  var themeMenu = document.querySelector('[data-theme-menu]');
  if (themeTrigger && themeMenu) {
    themeTrigger.addEventListener('click', function (event) {
      event.stopPropagation();
      var rect = themeTrigger.getBoundingClientRect();
      themeMenu.style.top = (rect.bottom + 8) + 'px';
      themeMenu.style.left = Math.max(10, rect.right - 150) + 'px';
      themeMenu.classList.toggle('open');
    });
    themeMenu.querySelectorAll('[data-theme-choice]').forEach(function (button) {
      button.addEventListener('click', function () {
        setTheme(button.getAttribute('data-theme-choice'));
        themeMenu.classList.remove('open');
      });
    });
    document.addEventListener('click', function () { themeMenu.classList.remove('open'); });
  }

  var mobileButton = document.querySelector('[data-mobile-trigger]');
  var mobilePanel = document.querySelector('[data-mobile-panel]');
  if (mobileButton && mobilePanel) {
    mobileButton.addEventListener('click', function () {
      var open = mobilePanel.classList.toggle('open');
      mobileButton.setAttribute('aria-expanded', String(open));
    });
    mobilePanel.querySelectorAll('a').forEach(function (link) {
      link.addEventListener('click', function () {
        mobilePanel.classList.remove('open');
        mobileButton.setAttribute('aria-expanded', 'false');
      });
    });
  }

  document.querySelectorAll('pre').forEach(function (pre) {
    if (pre.querySelector('.copy-button')) return;
    var button = document.createElement('button');
    button.className = 'copy-button';
    button.type = 'button';
    button.textContent = labels.copy;
    button.setAttribute('aria-label', isZh ? '复制代码' : 'Copy code');
    button.addEventListener('click', function () {
      var text = pre.innerText.replace(new RegExp('^' + labels.copy + '\\s*'), '');
      function done() {
        button.textContent = labels.copied;
        button.classList.add('copied');
        setTimeout(function () { button.textContent = labels.copy; button.classList.remove('copied'); }, 1600);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () {});
      } else {
        var area = document.createElement('textarea');
        area.value = text; document.body.appendChild(area); area.select();
        try { document.execCommand('copy'); done(); } catch (e) {}
        area.remove();
      }
    });
    pre.appendChild(button);
  });

  var progress = document.querySelector('[data-progress]');
  function updateProgress() {
    if (!progress) return;
    var max = document.documentElement.scrollHeight - innerHeight;
    progress.style.width = (max > 0 ? Math.min(100, scrollY / max * 100) : 0) + '%';
  }
  addEventListener('scroll', updateProgress, { passive: true });
  addEventListener('resize', updateProgress);
  updateProgress();

  var headingLinks = [];
  document.querySelectorAll('main h2[id], main h3[id]').forEach(function (heading) {
    headingLinks.push({ id: heading.id, el: heading });
  });
  var sideLinks = Array.prototype.slice.call(document.querySelectorAll('.sidebar a[href^="#"]'));
  function updateSidebar() {
    if (!headingLinks.length || !sideLinks.length) return;
    var active = headingLinks[0].id;
    headingLinks.forEach(function (item) {
      if (item.el.getBoundingClientRect().top <= 135) active = item.id;
    });
    sideLinks.forEach(function (link) { link.classList.toggle('active', link.getAttribute('href') === '#' + active); });
  }
  addEventListener('scroll', updateSidebar, { passive: true });
  updateSidebar();

  var searchModal = document.querySelector('[data-search-modal]');
  var searchInput = document.querySelector('[data-search-input]');
  var searchResults = document.querySelector('[data-search-results]');
  var searchButtons = document.querySelectorAll('[data-search-trigger]');
  var activeIndex = 0;
  var currentResults = [];

  function renderSearch(query) {
    if (!searchResults) return;
    var q = query.trim().toLowerCase();
    currentResults = pages.filter(function (page) {
      return !q || (page.title + ' ' + page.desc + ' ' + page.keywords).toLowerCase().indexOf(q) !== -1;
    });
    activeIndex = 0;
    if (!currentResults.length) {
      searchResults.innerHTML = '<div class="search-empty">' + labels.empty + '</div>';
      return;
    }
    searchResults.innerHTML = currentResults.map(function (page, index) {
      return '<a class="search-result' + (index === 0 ? ' active' : '') + '" data-search-index="' + index + '" href="' + basePrefix + page.url + '"><b>' + page.title + '</b><span>' + page.desc + '</span></a>';
    }).join('');
  }

  function openSearch() {
    if (!searchModal || !searchInput) return;
    searchModal.classList.add('open');
    searchModal.setAttribute('aria-hidden', 'false');
    renderSearch(searchInput.value);
    setTimeout(function () { searchInput.focus(); searchInput.select(); }, 20);
  }
  function closeSearch() {
    if (!searchModal) return;
    searchModal.classList.remove('open');
    searchModal.setAttribute('aria-hidden', 'true');
  }
  function setActive(index) {
    var links = searchResults ? searchResults.querySelectorAll('.search-result') : [];
    if (!links.length) return;
    activeIndex = (index + links.length) % links.length;
    links.forEach(function (link, i) { link.classList.toggle('active', i === activeIndex); });
    links[activeIndex].scrollIntoView({ block: 'nearest' });
  }

  searchButtons.forEach(function (button) { button.addEventListener('click', openSearch); });
  if (searchInput) {
    searchInput.addEventListener('input', function () { renderSearch(searchInput.value); });
    searchInput.addEventListener('keydown', function (event) {
      if (event.key === 'ArrowDown') { event.preventDefault(); setActive(activeIndex + 1); }
      else if (event.key === 'ArrowUp') { event.preventDefault(); setActive(activeIndex - 1); }
      else if (event.key === 'Enter' && currentResults[activeIndex]) { location.href = basePrefix + currentResults[activeIndex].url; }
      else if (event.key === 'Escape') closeSearch();
    });
  }
  if (searchModal) searchModal.addEventListener('click', function (event) { if (event.target === searchModal) closeSearch(); });
  document.addEventListener('keydown', function (event) {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); searchModal && searchModal.classList.contains('open') ? closeSearch() : openSearch(); }
    else if (event.key === 'Escape') {
      closeSearch();
      if (mobilePanel) mobilePanel.classList.remove('open');
      if (mobileButton) mobileButton.setAttribute('aria-expanded', 'false');
    }
  });

  function syntheticSeries(seed) {
    var variants = [
      [31, 44, 37, 58, 49, 72, 66, 82, 64, 91, 75, 87],
      [22, 35, 48, 39, 62, 55, 77, 69, 84, 73, 92, 80],
      [41, 29, 52, 67, 46, 78, 59, 88, 71, 83, 96, 86]
    ];
    return variants[seed % variants.length];
  }

  document.querySelectorAll('[data-demo]').forEach(function (demo, demoIndex) {
    var seed = demoIndex;
    var totalEl = demo.querySelector('[data-demo-total]');
    var callsEl = demo.querySelector('[data-demo-calls]');
    var bars = demo.querySelectorAll('[data-demo-bar]');
    var refresh = demo.querySelector('[data-demo-refresh]');
    function draw() {
      var values = syntheticSeries(seed++);
      var total = values.reduce(function (sum, value) { return sum + value; }, 0) * 12800;
      if (totalEl) totalEl.textContent = (total / 1000000).toFixed(2) + 'M';
      if (callsEl) callsEl.textContent = String(830 + (seed % 3) * 47);
      bars.forEach(function (bar, index) {
        bar.style.setProperty('--h', values[index % values.length] + '%');
        bar.title = labels.synthetic + (values[index % values.length] * 12800).toLocaleString(labels.locale) + ' token';
      });
    }
    if (refresh) refresh.addEventListener('click', draw);
    draw();
  });
})();
