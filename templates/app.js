        // Theme toggle (persisted)
        const safeStorage = {
            get(key) {
                try { return localStorage.getItem(key); } catch (e) { return null; }
            },
            set(key, value) {
                try { localStorage.setItem(key, value); } catch (e) { /* no-op */ }
            }
        };
        const MOBILE_BREAKPOINT = 640;

        // Lazy-load tab data from JSON files
        var _tabDataCache = {};
        function loadTabData(key, url) {
            if (_tabDataCache[key]) return _tabDataCache[key];
            var preKey = key === 'ai' ? 'tab_ai_rankings' : 'tab_' + key;
            if (window.__preloaded && window.__preloaded[preKey]) {
                _tabDataCache[key] = window.__preloaded[preKey].catch(function() { return null; });
                return _tabDataCache[key];
            }
            var p = fetch(url).then(function(r) {
                if (!r.ok) return null;
                return r.json();
            }).catch(function() { return null; });
            _tabDataCache[key] = p;
            return p;
        }
        function _safeLoad(key, url, assignFn) {
            return loadTabData(key, url).then(function(d) { if (d) assignFn(d); });
        }
        function ensureTabData(tab, callback) {
            var loads = [];
            if (tab === 'reports' && !TELEGRAM_REPORTS) {
                loads.push(_safeLoad('telegram', 'static/tab_telegram.json', function(d) { TELEGRAM_REPORTS = d; }));
            }
            if (tab === 'youtube' && !YOUTUBE_VIDEOS) {
                loads.push(_safeLoad('youtube', 'static/tab_youtube.json', function(d) { YOUTUBE_VIDEOS = d; }));
            }
            if ((tab === 'twitter') && !TWITTER_ARTICLES) {
                loads.push(_safeLoad('twitter', 'static/tab_twitter.json', function(d) { TWITTER_ARTICLES = d; }));
            }
            if (tab === 'research' && !RESEARCH_REPORTS) {
                loads.push(_safeLoad('research', 'static/tab_research.json', function(d) { RESEARCH_REPORTS = d; }));
            }
            if (tab === 'papers' && !PAPER_ARTICLES) {
                loads.push(_safeLoad('papers', 'static/tab_papers.json', function(d) { PAPER_ARTICLES = d; }));
            }
            if (tab === 'home' && !SLOW_READS) {
                loads.push(_safeLoad('slow_reads', 'static/tab_slow_reads.json', function(d) { SLOW_READS = d; }));
            }
            if ((tab === 'news' || tab === 'home') && !NEWS_ARTICLES) {
                loads.push(_safeLoad('news', 'static/tab_news.json', function(d) { NEWS_ARTICLES = d; }));
            }
            // Home tab only needs ai_rankings.json (loaded below) — no tab JSON fetches
            if (!AI_RANKINGS_BOOTSTRAP) {
                loads.push(_safeLoad('ai', 'static/tab_ai_rankings.json', function(d) { AI_RANKINGS_BOOTSTRAP = d; }));
            }
            if (loads.length === 0) { callback(); return; }
            Promise.all(loads).then(callback).catch(function() { callback(); });
        }

        let bodyScrollLockDepth = 0;
        let bodyScrollLockY = 0;
        let inFocusOnly = false;

        function isMobileViewport() {
            return window.matchMedia('(max-width: ' + MOBILE_BREAKPOINT + 'px)').matches;
        }

        function lockBodyScroll() {
            if (bodyScrollLockDepth > 0) {
                bodyScrollLockDepth += 1;
                return;
            }
            bodyScrollLockY = window.scrollY || window.pageYOffset || 0;
            if (isMobileViewport()) {
                document.body.style.position = 'fixed';
                document.body.style.top = '-' + bodyScrollLockY + 'px';
                document.body.style.left = '0';
                document.body.style.right = '0';
                document.body.style.width = '100%';
            }
            document.body.style.overflow = 'hidden';
            bodyScrollLockDepth = 1;
        }

        function unlockBodyScroll() {
            if (bodyScrollLockDepth === 0) return;
            bodyScrollLockDepth -= 1;
            if (bodyScrollLockDepth > 0) return;
            const restoreY = bodyScrollLockY;
            const hadFixedLock = document.body.style.position === 'fixed';
            document.body.style.overflow = '';
            document.body.style.position = '';
            document.body.style.top = '';
            document.body.style.left = '';
            document.body.style.right = '';
            document.body.style.width = '';
            if (hadFixedLock) {
                const restore = () => window.scrollTo({ top: restoreY, left: 0, behavior: 'auto' });
                restore();
                window.requestAnimationFrame(restore);
                setTimeout(restore, 80);
            }
        }

        // Expandable search
        var searchWrap = document.getElementById('search-wrap');
        var searchToggle = document.getElementById('search-toggle');
        var globalSearch = document.getElementById('search-input');

        var utilityBar = document.querySelector('.utility');

        // The top bar + tabs are pinned together; day headers stick just below them.
        // Their height changes with screen width and wrapping, so measure it instead of guessing.
        var siteHead = document.querySelector('.site-head');
        function syncSiteHeadHeight() {
            if (siteHead) document.documentElement.style.setProperty('--head-h', siteHead.offsetHeight + 'px');
        }
        syncSiteHeadHeight();
        window.addEventListener('resize', syncSiteHeadHeight);
        if (window.ResizeObserver && siteHead) new ResizeObserver(syncSiteHeadHeight).observe(siteHead);

        var searchClosing = false;

        function openSearch() {
            if (searchWrap) searchWrap.classList.add('open');
            if (utilityBar) utilityBar.classList.add('search-active');
            if (globalSearch) globalSearch.focus();
        }

        function closeSearch() {
            if (searchClosing) return;
            searchClosing = true;
            if (searchWrap) searchWrap.classList.remove('open');
            if (utilityBar) utilityBar.classList.remove('search-active');
            if (globalSearch) {
                var hadValue = globalSearch.value !== '';
                globalSearch.value = '';
                if (hadValue) globalSearch.dispatchEvent(new Event('input'));
                globalSearch.blur();
            }
            searchClosing = false;
        }

        if (searchToggle) searchToggle.addEventListener('click', function() {
            if (searchWrap && searchWrap.classList.contains('open')) {
                closeSearch();
            } else {
                openSearch();
            }
        });

        if (globalSearch) globalSearch.addEventListener('blur', function() {
            if (!globalSearch.value) {
                setTimeout(function() { closeSearch(); }, 150);
            }
        });

        if (globalSearch) globalSearch.addEventListener('keydown', function(ev) {
            if (ev.key === 'Escape') {
                closeSearch();
            }
        });

        function debounce(fn, ms) {
            let timer;
            return function() { clearTimeout(timer); timer = setTimeout(fn, ms); };
        }
        if (globalSearch) globalSearch.addEventListener('input', debounce(onSearchInput, 200));

        const FILTER_COLLAPSE_KEY_PREFIX = 'financeradar_filters_collapsed_';

        function getFilterCollapseStorageKey(tabName) {
            const tab = tabName || getActiveTab() || 'news';
            return FILTER_COLLAPSE_KEY_PREFIX + tab;
        }

        function isFilterCollapsedForTab(tabName) {
            return safeStorage.get(getFilterCollapseStorageKey(tabName)) !== 'false';
        }

        function applyFilterCollapseForTab(tabName) {
            document.documentElement.classList.toggle('filters-collapsed', isFilterCollapsedForTab(tabName));
        }

        // Filter collapse toggle (per-tab memory)
        function toggleFilterCollapse() {
            closeAllDropdowns();
            var active = getActiveTab();
            var nextCollapsed = !document.documentElement.classList.contains('filters-collapsed');
            document.documentElement.classList.toggle('filters-collapsed', nextCollapsed);
            safeStorage.set(getFilterCollapseStorageKey(active), nextCollapsed ? 'true' : 'false');
        }

        // Multi-select publisher filter
        let selectedPublishers = new Set();

        function initPublisherDropdown() {
            const list = document.getElementById('dropdown-list');
            list.innerHTML = '';
            ALL_PUBLISHERS.forEach(pub => {
                const item = document.createElement('div');
                item.className = 'dropdown-item';
                item.dataset.publisher = pub;
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.id = 'pub-' + pub.replace(/\s+/g, '-');
                cb.dataset.publisher = pub;
                cb.addEventListener('change', () => onPublisherCheckChange(pub, cb.checked));
                const lbl = document.createElement('label');
                lbl.htmlFor = cb.id;
                lbl.textContent = pub;
                item.appendChild(cb);
                item.appendChild(lbl);
                item.addEventListener('click', (e) => {
                    if (e.target !== cb) {
                        cb.checked = !cb.checked;
                        onPublisherCheckChange(pub, cb.checked);
                    }
                });
                list.appendChild(item);
            });
        }

        function toggleDropdown() {
            const dd = document.getElementById('publisher-dropdown');
            dd.classList.toggle('open');
            if (dd.classList.contains('open')) {
                document.getElementById('dropdown-search').focus();
            }
        }

        // ── Generic dropdown utilities ──────────────────────────────
        const DROPDOWN_CONFIG = [
            { ddId: 'publisher-dropdown', searchId: 'dropdown-search', listId: 'dropdown-list' },
            { ddId: 'tg-channel-dropdown', searchId: 'tg-dropdown-search', listId: 'tg-dropdown-list' },
            { ddId: 'research-publisher-dropdown', searchId: 'research-dropdown-search', listId: 'research-dropdown-list' },
            { ddId: 'youtube-publisher-dropdown', searchId: 'youtube-dropdown-search', listId: 'youtube-dropdown-list' },
            { ddId: 'twitter-publisher-dropdown', searchId: 'twitter-dropdown-search', listId: 'twitter-dropdown-list' },
        ];

        function filterDropdownList(searchInputId, listId) {
            const query = document.getElementById(searchInputId).value.toLowerCase();
            document.querySelectorAll('#' + listId + ' .dropdown-item').forEach(item => {
                item.classList.toggle('hidden', query && !item.dataset.publisher.toLowerCase().includes(query));
            });
        }

        function closeDropdownById(ddId, searchId, listId) {
            const dd = document.getElementById(ddId);
            if (!dd || !dd.classList.contains('open')) return;
            dd.classList.remove('open');
            const search = document.getElementById(searchId);
            if (search) { search.value = ''; filterDropdownList(searchId, listId); }
        }

        function closeAllDropdowns() {
            DROPDOWN_CONFIG.forEach(d => closeDropdownById(d.ddId, d.searchId, d.listId));
        }
        // ────────────────────────────────────────────────────────────

        function closeDropdown() { closeDropdownById('publisher-dropdown', 'dropdown-search', 'dropdown-list'); }
        function filterPublisherList() { filterDropdownList('dropdown-search', 'dropdown-list'); }

        function selectAllPublishers() {
            selectedPublishers.clear();
            syncCheckboxes();
            syncPresetButtons();
            syncDeskButtons();
            updatePublisherSummary();
            filterArticles();
        }

        function clearAllPublishers() {
            selectedPublishers.clear();
            syncCheckboxes();
            syncPresetButtons();
            syncDeskButtons();
            updatePublisherSummary();
            filterArticles();
        }

        function onPublisherCheckChange(pub, checked) {
            if (checked) {
                selectedPublishers.add(pub);
            } else {
                selectedPublishers.delete(pub);
            }
            syncPresetButtons();
            syncDeskButtons();
            updatePublisherSummary();
            filterArticles();
        }

        function syncCheckboxes() {
            document.querySelectorAll('#dropdown-list input[type="checkbox"]').forEach(cb => {
                cb.checked = selectedPublishers.has(cb.dataset.publisher);
            });
        }

        function togglePreset(name) {
            const pubs = PUBLISHER_PRESETS[name];
            if (!pubs) return;
            const allSelected = pubs.every(p => selectedPublishers.has(p));
            if (allSelected) {
                pubs.forEach(p => selectedPublishers.delete(p));
            } else {
                pubs.forEach(p => selectedPublishers.add(p));
            }
            syncCheckboxes();
            syncPresetButtons();
            syncDeskButtons();
            updatePublisherSummary();
            filterArticles();
        }

        function syncPresetButtons() {
            document.querySelectorAll('.preset-btn').forEach(btn => {
                const name = btn.dataset.preset;
                const pubs = PUBLISHER_PRESETS[name];
                if (!pubs) return;
                const selected = pubs.filter(p => selectedPublishers.has(p));
                if (selectedPublishers.size === 0) {
                    btn.classList.remove('active', 'partial');
                } else if (selected.length === pubs.length) {
                    btn.classList.add('active');
                    btn.classList.remove('partial');
                } else if (selected.length > 0) {
                    btn.classList.remove('active');
                    btn.classList.add('partial');
                } else {
                    btn.classList.remove('active', 'partial');
                }
            });
        }

        // Desk membership lives in aggregator.py (publisher_presets) so there is one list to edit.
        const NEWS_DESKS = {
            'india-desk': PUBLISHER_PRESETS['India Desk'],
            'world-desk': PUBLISHER_PRESETS['World Desk'],
            'indie-voices': PUBLISHER_PRESETS['Indie Voices'],
            'official-channels': PUBLISHER_PRESETS['Official Channels']
        };

        function resolveDeskPubs(deskKey) {
            const deskNames = NEWS_DESKS[deskKey];
            if (!deskNames) return [];
            return ALL_PUBLISHERS.filter(p => deskNames.some(d => p.includes(d)));
        }

        function syncDeskButtons() {
            document.querySelectorAll('.tv-desk-btn').forEach(btn => {
                const deskKey = btn.dataset.desk;
                const deskPubs = resolveDeskPubs(deskKey);
                const selectedCount = deskPubs.filter(p => selectedPublishers.has(p)).length;
                btn.classList.remove('active', 'partial');
                if (selectedPublishers.size > 0 && selectedCount === deskPubs.length && deskPubs.length > 0) {
                    btn.classList.add('active');
                } else if (selectedPublishers.size > 0 && selectedCount > 0) {
                    btn.classList.add('partial');
                }
            });
        }

        function initDeskButtons() {
            document.querySelectorAll('.tv-desk-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const deskKey = btn.dataset.desk;
                    const resolved = resolveDeskPubs(deskKey);
                    const allSelected = resolved.length > 0 && resolved.every(p => selectedPublishers.has(p));
                    if (allSelected) {
                        resolved.forEach(p => selectedPublishers.delete(p));
                    } else {
                        resolved.forEach(p => selectedPublishers.add(p));
                    }
                    currentPage = 1;
                    syncCheckboxes();
                    syncPresetButtons();
                    syncDeskButtons();
                    updatePublisherSummary();
                    filterArticles();
                    applyPagination(true);
                });
            });
        }

        function updatePublisherSummary() {
            const el = document.getElementById('publisher-summary');
            const trigger = document.getElementById('publisher-trigger');
            const effectiveSelected = ALL_PUBLISHERS.filter(p => selectedPublishers.has(p)).length;
            if (effectiveSelected === 0) {
                el.textContent = 'All publishers';
                trigger.classList.remove('has-selection');
            } else if (effectiveSelected === 1) {
                el.textContent = ALL_PUBLISHERS.find(p => selectedPublishers.has(p));
                trigger.classList.add('has-selection');
            } else {
                el.textContent = effectiveSelected + ' of ' + ALL_PUBLISHERS.length + ' publishers';
                trigger.classList.add('has-selection');
            }
        }

        function getActiveTab() {
            return document.querySelector('.tab-pill.tab-active')?.dataset.tab || 'home';
        }

        function onSearchInput() {
            const tab = getActiveTab();
            if (tab === 'home') {
                filterHomeCards();
            } else if (tab === 'reports') {
                filterReports();
            } else if (tab === 'research') {
                filterResearch();
            } else if (tab === 'papers') {
                filterPapers();
            } else if (tab === 'youtube') {
                filterYoutube();
            } else if (tab === 'twitter') {
                filterTwitter();
            } else {
                filterArticles();
            }
        }

        function filterArticles() {
            const query = document.getElementById('search-input').value.toLowerCase();
            const articles = document.querySelectorAll('.article');
            const dateHeaders = document.querySelectorAll('.date-header');

            articles.forEach(article => {
                const text = article.textContent.toLowerCase();
                const publisher = article.dataset.publisher || '';
                const isInFocus = article.dataset.inFocus === 'true';
                const matchesSearch = !query || text.includes(query);
                const matchesPublisher = selectedPublishers.size === 0 || selectedPublishers.has(publisher);
                const matchesInFocus = !inFocusOnly || isInFocus;
                article.classList.toggle('hidden', !(matchesSearch && matchesPublisher && matchesInFocus));
            });

            // Hide empty date headers
            dateHeaders.forEach(header => {
                let next = header.nextElementSibling;
                let hasVisible = false;
                while (next && !next.classList.contains('date-header')) {
                    if (next.classList.contains('article') && !next.classList.contains('hidden')) {
                        hasVisible = true;
                        break;
                    }
                    next = next.nextElementSibling;
                }
                header.classList.toggle('hidden', !hasVisible);
            });

            setPageToToday();
            applyPagination();
        }

        function toggleInFocus() {
            inFocusOnly = !inFocusOnly;
            const btn = document.getElementById('in-focus-toggle');
            if (btn) btn.classList.toggle('active', inFocusOnly);
            filterArticles();
        }

        // Close dropdown on outside click
        document.addEventListener('click', (e) => {
            DROPDOWN_CONFIG.forEach(d => {
                const dd = document.getElementById(d.ddId);
                if (dd && dd.classList.contains('open') && !dd.contains(e.target)) {
                    closeDropdownById(d.ddId, d.searchId, d.listId);
                }
            });
        });

        // Close dropdown on Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                for (const d of DROPDOWN_CONFIG) {
                    const dd = document.getElementById(d.ddId);
                    if (dd && dd.classList.contains('open')) {
                        closeDropdownById(d.ddId, d.searchId, d.listId);
                        e.stopImmediatePropagation();
                        return;
                    }
                }
            }
        });

        // Initialize publisher dropdown
        initPublisherDropdown();
        initDeskButtons();

        // Pagination
        const PAGE_SIZE = 20;
        let currentPage = 1;
        // TODAY_ISO is injected by inline script in aggregator.py

        function getFilteredArticles() {
            return [...document.querySelectorAll('.article:not(.hidden)')];
        }

        // ── Generic pagination builder ──────────────────────────────
        function buildPagination(containerId, activePage, totalPages, onPageChange) {
            const container = document.getElementById(containerId);
            if (!container) return;
            container.innerHTML = '';
            if (totalPages <= 1) return;

            const makeBtn = (label, page, isActive = false, isDisabled = false) => {
                const btn = document.createElement('button');
                btn.className = 'page-btn' + (isActive ? ' active' : '');
                btn.textContent = label;
                if (isDisabled) {
                    btn.disabled = true;
                } else if (!isActive) {
                    btn.addEventListener('click', () => onPageChange(page));
                }
                return btn;
            };
            const makeEllipsis = () => {
                const span = document.createElement('span');
                span.className = 'page-ellipsis';
                span.textContent = '\u2026';
                return span;
            };
            const windowSize = 7;
            const half = Math.floor(windowSize / 2);
            let start = Math.max(1, activePage - half);
            let end = Math.min(totalPages, activePage + half);
            if (end - start + 1 < windowSize) {
                if (start === 1) end = Math.min(totalPages, start + windowSize - 1);
                else if (end === totalPages) start = Math.max(1, end - windowSize + 1);
            }

            const prevBtn = makeBtn('\u2190 Prev', Math.max(1, activePage - 1), false, activePage === 1);
            prevBtn.classList.add('nav', 'prev');
            container.appendChild(prevBtn);
            if (start > 1) {
                container.appendChild(makeBtn('1', 1, activePage === 1));
                if (start > 2) container.appendChild(makeEllipsis());
            }
            for (let i = start; i <= end; i++) {
                container.appendChild(makeBtn(String(i), i, i === activePage));
            }
            if (end < totalPages) {
                if (end < totalPages - 1) container.appendChild(makeEllipsis());
                container.appendChild(makeBtn(String(totalPages), totalPages, activePage === totalPages));
            }
            const nextBtn = makeBtn('Next \u2192', Math.min(totalPages, activePage + 1), false, activePage === totalPages);
            nextBtn.classList.add('nav', 'next');
            container.appendChild(nextBtn);
        }
        // ────────────────────────────────────────────────────────────

        function renderPagination(totalPages) {
            buildPagination('pagination-bottom', currentPage, totalPages, (page) => {
                currentPage = page;
                applyPagination(true);
            });
        }

        function applyPagination(shouldScroll = false) {
            const articles = getFilteredArticles();
            const totalPages = Math.max(1, Math.ceil(articles.length / PAGE_SIZE));
            if (currentPage > totalPages) {
                currentPage = totalPages;
            }

            // Reset pagination visibility
            document.querySelectorAll('.article').forEach(a => a.classList.remove('paged-hidden'));

            const start = (currentPage - 1) * PAGE_SIZE;
            const end = start + PAGE_SIZE;
            articles.forEach((article, idx) => {
                if (idx < start || idx >= end) {
                    article.classList.add('paged-hidden');
                }
            });

            // Hide empty date headers after paging
            const dateHeaders = document.querySelectorAll('.date-header');
            dateHeaders.forEach(header => {
                let next = header.nextElementSibling;
                let hasVisible = false;
                while (next && !next.classList.contains('date-header')) {
                    if (next.classList.contains('article') && !next.classList.contains('hidden') && !next.classList.contains('paged-hidden')) {
                        hasVisible = true;
                        break;
                    }
                    next = next.nextElementSibling;
                }
                header.classList.toggle('hidden', !hasVisible);
            });

            renderPagination(totalPages);
            try { localStorage.setItem('financeradar_page', currentPage); } catch(e) {}
            if (shouldScroll) {
                window.scrollTo(0, 0);
            }
        }

        function setPageToToday() {
            const articles = getFilteredArticles();
            if (!TODAY_ISO) {
                currentPage = 1;
                return;
            }
            const idx = articles.findIndex(a => (a.dataset.date || '') === TODAY_ISO);
            if (idx >= 0) {
                currentPage = Math.floor(idx / PAGE_SIZE) + 1;
            } else {
                currentPage = 1;
            }
        }

        // Scroll to top button
        var scrollTopBtn = document.getElementById('scroll-top');
        if (scrollTopBtn) {
            scrollTopBtn.addEventListener('click', function() {
                window.scrollTo({top: 0, behavior: 'smooth'});
            });
        }
        window.addEventListener('scroll', () => {
            if (scrollTopBtn) scrollTopBtn.classList.toggle('visible', window.scrollY > 400);
        });

        // Keyboard navigation
        let currentArticle = -1;
        const getVisibleArticles = () => [...document.querySelectorAll('.article:not(.hidden):not(.paged-hidden)')];

        document.addEventListener('keydown', (e) => {
            // Don't interfere with typing in search
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') {
                if (e.key === 'Escape') {
                    e.target.blur();
                }
                return;
            }

            const articles = getVisibleArticles();

            if (e.key === 'j' || e.key === 'ArrowDown') {
                e.preventDefault();
                currentArticle = Math.min(currentArticle + 1, articles.length - 1);
                articles[currentArticle]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                articles[currentArticle]?.querySelector('a')?.focus();
            } else if (e.key === 'k' || e.key === 'ArrowUp') {
                e.preventDefault();
                currentArticle = Math.max(currentArticle - 1, 0);
                articles[currentArticle]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                articles[currentArticle]?.querySelector('a')?.focus();
            } else if (e.key === '/') {
                e.preventDefault();
                if (searchWrap) searchWrap.classList.add('open');
                if (globalSearch) globalSearch.focus();
            } else if (e.key === 'Escape') {
                if (globalSearch) { globalSearch.value = ''; globalSearch.dispatchEvent(new Event('input')); }
                if (searchWrap) searchWrap.classList.remove('open');
            } else if (e.key === 'h' || e.key === 'H') {
                switchTab('home');
            } else if (e.key === '1') {
                switchTab('news');
            } else if (e.key === '2') {
                switchTab('reports');
            } else if (e.key === '3') {
                switchTab('research');
            } else if (e.key === '4') {
                switchTab('papers');
            } else if (e.key === '5') {
                switchTab('youtube');
            } else if (e.key === '6') {
                switchTab('twitter');
            }
        });

        // Initial pagination — restore saved page or default to today
        const savedPage = parseInt(safeStorage.get('financeradar_page'), 10);
        if (savedPage && savedPage > 0) {
            currentPage = savedPage;
        } else {
            setPageToToday();
        }
        applyPagination();

        // ==================== BOOKMARKS ====================
        const BOOKMARKS_KEY = 'financeradar_bookmarks';
        const WSW_BOOKMARKS_KEY = 'financeradar_wsw_bookmarks';

        function getBookmarks() {
            try {
                const data = localStorage.getItem(BOOKMARKS_KEY);
                return data ? JSON.parse(data) : [];
            } catch (e) {
                return [];
            }
        }

        function saveBookmarks(bookmarks) {
            try {
                localStorage.setItem(BOOKMARKS_KEY, JSON.stringify(bookmarks));
            } catch (e) { /* no-op */ }
        }

        function toggleBookmark(btn) {
            const article = btn.closest('.article');
            btn.dataset.url = article.dataset.url;
            btn.dataset.title = article.dataset.title;
            btn.dataset.source = article.querySelector('.source-tag')?.textContent || '';
            toggleGenericBookmark(btn);
        }

        function updateBookmarkCount() {
            var storyArticleCount = getStoryBookmarks().reduce(function(sum, s) {
                return sum + (s.articles ? s.articles.length : 0);
            }, 0);
            const count = getBookmarks().length + storyArticleCount;
            var badge = document.getElementById('bk-count');
            if (badge) badge.textContent = count;
        }

        function initBookmarkButtons() {
            document.querySelectorAll('.article').forEach(article => {
                const url = article.dataset.url;
                const btn = article.querySelector('.bookmark-btn');
                if (btn && isBookmarked(url)) {
                    btn.classList.add('bookmarked');
                }
            });
            updateBookmarkCount();
        }

        function toggleGenericBookmark(btn) {
            const url = btn.dataset.url;
            const title = btn.dataset.title;
            const source = btn.dataset.source || '';

            let bookmarks = getBookmarks();
            const idx = bookmarks.findIndex(b => b.url === url);

            if (idx >= 0) {
                bookmarks.splice(idx, 1);
                btn.classList.remove('bookmarked');
            } else {
                bookmarks.unshift({ url, title, source, addedAt: Date.now() });
                btn.classList.add('bookmarked');
            }

            saveBookmarks(bookmarks);
            updateBookmarkCount();
            syncBookmarkState();
            renderSidebarContent();
        }

        function syncBookmarkState() {
            const bookmarks = getBookmarks();
            const urls = new Set(bookmarks.map(b => b.url));
            document.querySelectorAll('.bookmark-btn[data-url]').forEach(btn => {
                btn.classList.toggle('bookmarked', urls.has(btn.dataset.url));
            });
        }

        function openSidebar() {
            var panel = document.getElementById('bk-panel');
            var overlay = document.getElementById('bk-overlay');
            if (!panel) return;
            panel.classList.add('open');
            if (overlay) overlay.classList.add('open');
            lockBodyScroll();
            renderSidebarContent();
        }

        function closeSidebar() {
            var panel = document.getElementById('bk-panel');
            var overlay = document.getElementById('bk-overlay');
            if (panel) panel.classList.remove('open');
            if (overlay) overlay.classList.remove('open');
            unlockBodyScroll();
        }

        function renderSidebarContent() {
            var container = document.getElementById('bk-list');
            if (!container) return;
            var storyBookmarks = getStoryBookmarks();
            var bookmarks = getBookmarks();

            if (storyBookmarks.length === 0 && bookmarks.length === 0) {
                container.innerHTML = '<p class="bk-empty">No bookmarks yet. Click the bookmark icon on any article to save it.</p>';
                return;
            }

            var html = '';

            // Story bookmarks (bundles) first
            if (storyBookmarks.length > 0) {
                html += storyBookmarks.map(function(s) {
                    var articleItems = (s.articles || []).map(function(a) {
                        var dotColor = BUCKET_COLORS[a.source_type] || '#6B645C';
                        return '<div class="bk-story-sub"><span class="cat-dot" style="background:' + dotColor + '"></span>'
                            + '<a href="' + escapeHtml(a.url) + '" target="_blank" rel="noopener">' + escapeHtml(a.title) + '</a>'
                            + '<span class="bk-saved-src">' + escapeHtml(a.source) + '</span></div>';
                    }).join('');
                    return '<div class="bk-story-bundle">'
                        + '<div class="bk-story-header"><span class="bk-story-label">' + escapeHtml(s.storyLabel) + '</span>'
                        + '<button class="bk-remove" onclick="removeStoryBookmark(\'' + escapeForAttr(s.storyId) + '\')" title="Remove">&times;</button></div>'
                        + articleItems + '</div>';
                }).join('');
            }

            // Individual bookmarks
            if (bookmarks.length > 0) {
                html += bookmarks.map(function(b) {
                    return '<div class="bk-saved-item"><div><a href="' + escapeHtml(b.url) + '" target="_blank" rel="noopener">' + escapeHtml(b.title) + '</a><span class="bk-saved-src">' + escapeHtml(b.source) + '</span></div><button class="bk-remove" onclick="removeBookmark(\'' + escapeForAttr(b.url) + '\')" title="Remove">&times;</button></div>';
                }).join('');
            }

            container.innerHTML = html;
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text || '';
            return div.innerHTML;
        }

        function escapeForAttr(text) {
            return escapeHtml(text).replace(/'/g, '&#39;');
        }

        function sanitizeUrl(url) {
            if (!url) return '';
            const trimmed = url.trim().toLowerCase();
            if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) return url;
            return '';
        }

        function copyTextWithFallback(text, onSuccess) {
            if (!text) return;
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(() => {
                    if (typeof onSuccess === 'function') onSuccess();
                }).catch(() => {
                    fallbackCopyText(text);
                    if (typeof onSuccess === 'function') onSuccess();
                });
                return;
            }
            fallbackCopyText(text);
            if (typeof onSuccess === 'function') onSuccess();
        }

        function fallbackCopyText(text) {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }

        function flashCopiedButton(button) {
            if (!button) return;
            const span = button.querySelector('span');
            const originalText = span ? span.textContent : '';
            button.classList.add('copied');
            if (span) span.textContent = 'Copied!';
            setTimeout(() => {
                button.classList.remove('copied');
                if (span) span.textContent = originalText;
            }, 2000);
        }

        function removeBookmark(url) {
            let bookmarks = getBookmarks();
            bookmarks = bookmarks.filter(b => b.url !== url);
            saveBookmarks(bookmarks);
            updateBookmarkCount();
            syncBookmarkState();
            renderSidebarContent();
        }

        function removeStoryBookmark(storyId) {
            var storyBookmarks = getStoryBookmarks().filter(function(s) { return s.storyId !== storyId; });
            saveStoryBookmarks(storyBookmarks);
            updateBookmarkCount();
            syncStoryBookmarkState();
            renderSidebarContent();
        }

        function copyBookmarks() {
            var storyBookmarks = getStoryBookmarks();
            var bookmarks = getBookmarks();
            if (storyBookmarks.length === 0 && bookmarks.length === 0) return;

            var lines = [];
            var hasStories = storyBookmarks.length > 0;
            var hasIndividual = bookmarks.length > 0;

            // Story bundles
            if (hasStories) {
                storyBookmarks.forEach(function(s, si) {
                    lines.push('📌 ' + s.storyLabel);
                    lines.push('');
                    (s.articles || []).forEach(function(a, i) {
                        var entry = '  ' + (i + 1) + '. ' + a.title;
                        if (a.angle) entry += '  —  ' + a.angle;
                        lines.push(entry);
                        lines.push('     ' + a.url);
                        lines.push('');
                    });
                    // Spacer between clusters (but not after the last one if individual follows)
                    if (si < storyBookmarks.length - 1) {
                        lines.push('');
                    }
                });
            }

            // Individual bookmarks
            if (hasIndividual) {
                if (hasStories) {
                    lines.push('');
                    lines.push('━━━━━━━━━━━━━━━━━━━━━');
                    lines.push('');
                }
                lines.push('🔖 Saved Articles');
                lines.push('');
                bookmarks.forEach(function(b, i) {
                    lines.push('  ' + (i + 1) + '. ' + b.title);
                    lines.push('     ' + b.url);
                    lines.push('');
                });
            }

            var text = lines.join('\n').replace(/\n{3,}/g, '\n\n').trim();
            copyTextWithFallback(text, () => flashCopiedButton(document.querySelector('#bk-panel .bk-action-btn')));
        }

        function clearAllBookmarks() {
            if (!confirm('Are you sure you want to clear all bookmarks?')) return;
            saveBookmarks([]);
            saveStoryBookmarks([]);
            document.querySelectorAll('.bookmark-btn.bookmarked').forEach(btn => {
                btn.classList.remove('bookmarked');
            });
            updateBookmarkCount();
            renderSidebarContent();
        }

        // ==================== STORY BOOKMARKS ====================
        function getStoryBookmarks() {
            try {
                var data = localStorage.getItem(STORY_BOOKMARKS_KEY);
                var parsed = data ? JSON.parse(data) : [];
                return Array.isArray(parsed) ? parsed : [];
            } catch (e) { return []; }
        }

        function saveStoryBookmarks(bookmarks) {
            try { localStorage.setItem(STORY_BOOKMARKS_KEY, JSON.stringify(bookmarks)); } catch (e) { /* no-op */ }
        }

        function isStoryBookmarked(storyId) {
            if (!storyId) return false;
            return getStoryBookmarks().some(function(s) { return s.storyId === storyId; });
        }

        function toggleStoryBookmark(btn) {
            var storyId = btn.dataset.storyId;
            if (!storyId) return;

            var storyBookmarks = getStoryBookmarks();
            var idx = storyBookmarks.findIndex(function(s) { return s.storyId === storyId; });

            if (idx >= 0) {
                storyBookmarks.splice(idx, 1);
                btn.classList.remove('bookmarked');
            } else {
                var clusters = getMergedClusters();
                var cluster = clusters.find(function(c) { return c.story_id === storyId; });
                if (!cluster) return;

                storyBookmarks.unshift({
                    storyId: storyId,
                    storyLabel: cluster.story_label || '',
                    articles: getClusterArticles(cluster),
                    addedAt: Date.now()
                });
                btn.classList.add('bookmarked');
            }

            saveStoryBookmarks(storyBookmarks);
            updateBookmarkCount();
            renderSidebarContent();
        }

        function syncStoryBookmarkState() {
            var bookmarks = getStoryBookmarks();
            var ids = new Set(bookmarks.map(function(s) { return s.storyId; }));
            document.querySelectorAll('.btn-bk-story[data-story-id]').forEach(function(btn) {
                btn.classList.toggle('bookmarked', ids.has(btn.dataset.storyId));
            });
        }

        // Bookmark panel toggle
        var bkToggleBtn = document.getElementById('bk-toggle');
        if (bkToggleBtn) bkToggleBtn.addEventListener('click', function() {
            var panel = document.getElementById('bk-panel');
            if (panel && panel.classList.contains('open')) {
                closeSidebar();
            } else {
                openSidebar();
            }
        });
        var bkOverlayEl = document.getElementById('bk-overlay');
        if (bkOverlayEl) bkOverlayEl.addEventListener('click', closeSidebar);

        // Close bookmark panel with Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                var panel = document.getElementById('bk-panel');
                if (panel && panel.classList.contains('open')) {
                    closeSidebar();
                }
            }
        });

        // Initialize bookmarks
        initBookmarkButtons();

        // ==================== AI RANKINGS SIDEBAR ====================
        let aiRankings = null;
        const AI_REFRESH_INTERVAL_MS = 3 * 60 * 60 * 1000;
        const AI_BUCKET_ORDER = ['news', 'telegram', 'reports', 'twitter', 'youtube'];

        function normalizeAiRankingsPayload(payload) {
            if (!payload || typeof payload !== 'object') return { providers: {} };
            if (!payload.providers || typeof payload.providers !== 'object') payload.providers = {};
            Object.values(payload.providers).forEach(provider => {
                if (!provider || typeof provider !== 'object') return;
                if (!provider.buckets || typeof provider.buckets !== 'object') {
                    provider.buckets = {};
                    // Backward compatibility with legacy ai_rankings.json.
                    if (Array.isArray(provider.rankings)) {
                        provider.buckets.news = provider.rankings;
                    }
                }
                provider.available_buckets = AI_BUCKET_ORDER.filter(bucket => {
                    const bucketItems = provider.buckets && Array.isArray(provider.buckets[bucket]) ? provider.buckets[bucket] : [];
                    return bucketItems.length > 0;
                });
            });
            return payload;
        }

        function getProviderBucketRankings(provider, bucket) {
            if (!provider || typeof provider !== 'object') return [];
            if (provider.buckets && Array.isArray(provider.buckets[bucket])) {
                return provider.buckets[bucket];
            }
            if (bucket === 'news' && Array.isArray(provider.rankings)) {
                return provider.rankings;
            }
            return [];
        }

        function getAvailableProvidersForBucket(bucket) {
            if (!aiRankings || !aiRankings.providers) return [];
            return Object.entries(aiRankings.providers).filter(([, provider]) => {
                if (!provider || typeof provider !== 'object') return false;
                const status = provider.status || 'ok';
                if (status !== 'ok' && status !== 'partial') return false;
                return getProviderBucketRankings(provider, bucket).length > 0;
            });
        }

        // (updateAiBucketPillState removed — AI sidebar no longer exists)

        // ==================== AI MERGE (cross-provider consensus) ====================
        function normalizeAiTitle(title) {
            var t = String(title || '').replace(/"/g, "'").replace(/\n/g, ' ').replace(/\r/g, ' ').trim();
            t = t.replace(/\u2014/g, '-').replace(/\u2013/g, '-').replace(/\u2012/g, '-').replace(/\u2212/g, '-');
            t = t.replace(/\u2018/g, "'").replace(/\u2019/g, "'").replace(/\u02bc/g, "'");
            t = t.replace(/\u201c/g, '"').replace(/\u201d/g, '"');
            t = t.replace(/\u2026/g, '...');
            t = t.replace(/\s+/g, ' ').trim();
            return t.toLowerCase();
        }

        function getMergedAiRankings(bucket) {
            if (!aiRankings || !aiRankings.providers) return [];
            var providerEntries = Object.entries(aiRankings.providers).filter(function(entry) {
                var p = entry[1];
                if (!p || typeof p !== 'object') return false;
                var status = p.status || 'ok';
                return (status === 'ok' || status === 'partial') && getProviderBucketRankings(p, bucket).length > 0;
            });
            if (!providerEntries.length) return [];

            // Collect items per provider with rank positions
            var urlMap = {};   // lowercased url → merge entry
            var titleMap = {}; // normalizeAiTitle → merge entry (fallback)

            providerEntries.forEach(function(entry, pIdx) {
                var items = getProviderBucketRankings(entry[1], bucket);
                items.forEach(function(item, rank) {
                    var url = String(item.url || '').toLowerCase().trim();
                    var normTitle = normalizeAiTitle(item.title);
                    var existing = null;

                    // Match by URL first, then by normalized title
                    if (url && urlMap[url]) {
                        existing = urlMap[url];
                    } else if (normTitle && titleMap[normTitle]) {
                        existing = titleMap[normTitle];
                    }

                    if (existing) {
                        existing._ranks.push(rank);
                        existing._providerCount++;
                        // Keep richer metadata (prefer items with why_it_matters)
                        if (item.why_it_matters && !existing.why_it_matters) {
                            existing.why_it_matters = item.why_it_matters;
                        }
                        if (item.signal_type && !existing.signal_type) {
                            existing.signal_type = item.signal_type;
                        }
                    } else {
                        var merged = {
                            title: item.title,
                            url: item.url || '',
                            source: item.source || '',
                            source_type: item.source_type || bucket,
                            why_it_matters: item.why_it_matters || '',
                            signal_type: item.signal_type || '',
                            confidence: item.confidence || '',
                            region: item.region || '',
                            date: item.date || '',
                            _ranks: [rank],
                            _providerCount: 1
                        };
                        if (url) urlMap[url] = merged;
                        if (normTitle) titleMap[normTitle] = merged;
                    }
                });
            });

            // Deduplicate: collect unique entries from urlMap and titleMap
            var seen = new Set();
            var all = [];
            [urlMap, titleMap].forEach(function(map) {
                Object.values(map).forEach(function(entry) {
                    // Use object identity to deduplicate
                    if (seen.has(entry)) return;
                    seen.add(entry);
                    var avgRank = entry._ranks.reduce(function(a, b) { return a + b; }, 0) / entry._ranks.length;
                    var penalty = entry._providerCount >= 2 ? 0 : 50;
                    entry._consensus = entry._providerCount >= 2;
                    entry._mergedRank = avgRank + penalty;
                    all.push(entry);
                });
            });

            all.sort(function(a, b) { return a._mergedRank - b._mergedRank; });
            return all;
        }

        // ==================== CLUSTER MERGE (cross-provider) ====================
        var STORY_BOOKMARKS_KEY = 'financeradar_story_bookmarks';

        function getMergedClusters() {
            if (!aiRankings || !aiRankings.providers) return [];
            var providerClusters = [];
            Object.values(aiRankings.providers).forEach(function(p) {
                if (!p || typeof p !== 'object') return;
                var status = p.status || 'ok';
                if (status !== 'ok' && status !== 'partial') return;
                if (Array.isArray(p.clusters) && p.clusters.length > 0) {
                    providerClusters.push(p.clusters);
                }
            });
            if (!providerClusters.length) return [];

            // If only one provider has clusters, return them directly
            if (providerClusters.length === 1) {
                return providerClusters[0].map(function(c) {
                    c._consensus = false;
                    c._providerCount = 1;
                    return c;
                });
            }

            // Merge clusters across providers by ANY shared URL (not just lead)
            var merged = [];

            var _mergeStopWords = new Set('a an the is are was were be been being have has had do does did will would shall should may might can could of in on at to for with by from as into and or but not no nor so yet if then than that this these those it its says said report reports india indian market markets stock stocks news via rt the new after how'.split(' '));
            function _titleWords(t) {
                var words = new Set();
                String(t || '').toLowerCase().replace(/[^\w\s]/g, ' ').split(/\s+/).forEach(function(w) {
                    if (w.length > 1 && !_mergeStopWords.has(w)) words.add(w);
                });
                return words;
            }
            function _titleSimilar(a, b) {
                var wa = _titleWords(a), wb = _titleWords(b);
                if (!wa.size || !wb.size) return false;
                var inter = 0; wa.forEach(function(w) { if (wb.has(w)) inter++; });
                return inter / Math.min(wa.size, wb.size) >= 0.5;
            }

            function getClusterUrls(cluster) {
                var urls = new Set();
                if (cluster.lead && cluster.lead.url) urls.add(String(cluster.lead.url).toLowerCase().trim());
                (cluster.related || []).forEach(function(r) {
                    if (r.url) urls.add(String(r.url).toLowerCase().trim());
                });
                return urls;
            }

            function findOverlapping(urls) {
                for (var i = 0; i < merged.length; i++) {
                    var existingUrls = getClusterUrls(merged[i]);
                    var overlap = false;
                    urls.forEach(function(u) { if (existingUrls.has(u)) overlap = true; });
                    if (overlap) return i;
                }
                return -1;
            }

            providerClusters.forEach(function(clusters) {
                clusters.forEach(function(cluster) {
                    if (!cluster || !cluster.lead) return;
                    var clusterUrls = getClusterUrls(cluster);
                    if (!clusterUrls.size) return;
                    var idx = findOverlapping(clusterUrls);

                    if (idx >= 0) {
                        // Merge into existing: add new articles, dedup by URL + title similarity
                        var existing = merged[idx];
                        existing._providerCount++;
                        var seenUrls = getClusterUrls(existing);
                        var existingTitles = [existing.lead.title || ''];
                        (existing.related || []).forEach(function(r) { existingTitles.push(r.title || ''); });

                        function isNewArticle(art) {
                            var url = String(art.url || '').toLowerCase().trim();
                            if (url && seenUrls.has(url)) return false;
                            var title = art.title || '';
                            for (var t = 0; t < existingTitles.length; t++) {
                                if (_titleSimilar(title, existingTitles[t])) return false;
                            }
                            return true;
                        }
                        // Add lead as related if it's genuinely new
                        if (cluster.lead && isNewArticle(cluster.lead)) {
                            existing.related.push(cluster.lead);
                            seenUrls.add(String(cluster.lead.url || '').toLowerCase().trim());
                            existingTitles.push(cluster.lead.title || '');
                        }
                        (cluster.related || []).forEach(function(r) {
                            if (isNewArticle(r)) {
                                seenUrls.add(String(r.url || '').toLowerCase().trim());
                                existingTitles.push(r.title || '');
                                existing.related.push(r);
                            }
                        });
                    } else {
                        merged.push({
                            story_id: cluster.story_id || '',
                            story_label: cluster.story_label || '',
                            lead: cluster.lead,
                            related: (cluster.related || []).slice(),
                            _providerCount: 1
                        });
                    }
                });
            });

            // Sort by how many models picked the story (stable, so ties keep model order)
            merged.forEach(function(c) { c._consensus = c._providerCount >= 2; });
            merged.sort(function(a, b) { return b._providerCount - a._providerCount; });
            return merged;
        }

        function getClusteredUrls(clusters) {
            var urls = new Set();
            clusters.forEach(function(c) {
                if (c.lead && c.lead.url) urls.add(String(c.lead.url).toLowerCase().trim());
                (c.related || []).forEach(function(r) {
                    if (r.url) urls.add(String(r.url).toLowerCase().trim());
                });
            });
            return urls;
        }

        function hasAiRankingsBootstrap() {
            return typeof AI_RANKINGS_BOOTSTRAP === 'object'
                && AI_RANKINGS_BOOTSTRAP
                && typeof AI_RANKINGS_BOOTSTRAP.providers === 'object';
        }

        function applyAiRankingsPayload(payload) {
            if (!payload || typeof payload !== 'object') return false;
            const normalized = normalizeAiRankingsPayload(payload);
            if (!normalized.providers || typeof normalized.providers !== 'object') return false;
            aiRankings = normalized;
            renderHomeTab();
            return true;
        }

        async function loadAiRankings() {
            if (!aiRankings && hasAiRankingsBootstrap()) {
                applyAiRankingsPayload(AI_RANKINGS_BOOTSTRAP);
            }
            try {
                const refreshToken = Math.floor(Date.now() / AI_REFRESH_INTERVAL_MS);
                const res = await fetch(`static/ai_rankings.json?v=${refreshToken}`, { cache: 'no-store' });
                if (!res.ok) throw new Error('Rankings not found');
                applyAiRankingsPayload(await res.json());
            } catch (e) {
                if (aiRankings && aiRankings.providers) {
                    return;
                }
                if (hasAiRankingsBootstrap()) {
                    applyAiRankingsPayload(AI_RANKINGS_BOOTSTRAP);
                    return;
                }
                // No AI data available — renderHomeTab will show empty state
                renderHomeTab();
            }
        }

        // (AI sidebar functions removed — homepage now uses merged AI rankings directly)

        function isBookmarked(url) {
            if (!url) return false;
            return getBookmarks().some(b => b.url === url);
        }

        // (toggleAiBookmark removed — AI sidebar no longer exists)

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && document.getElementById('wsw-sidebar-overlay').classList.contains('open')) {
                closeWswSidebar();
            }
        });

        loadAiRankings();
        setInterval(() => {
            loadAiRankings();
        }, AI_REFRESH_INTERVAL_MS);

        // ==================== MANUAL REFRESH BUTTON ====================
        // Shows a "Refresh now" button in the footer only when the site is
        // stale (>2h since last build). Clicking it calls the same-origin
        // /api/trigger-update Pages Function, which re-checks staleness
        // server-side before dispatching the GitHub Action. The token lives
        // only in the Function — never here.
        const REFRESH_STALE_MS = 60 * 60 * 1000; // 60 min — button is clickable only once the feed is this stale
        const REFRESH_MESSAGES = {
            already_running: 'A refresh is already running.',
            cooldown: 'A refresh just ran — try again shortly.',
            fresh: 'Site is already up to date.',
        };

        function initRefreshButton() {
            const btn = document.getElementById('refresh-now');
            const status = document.getElementById('refresh-status');
            if (!btn) return;
            const builtAt = (typeof SITE_GENERATED_AT === 'string') ? Date.parse(SITE_GENERATED_AT) : NaN;
            btn.hidden = false; // always visible; only its clickable state changes

            // Enable only when the feed is stale enough. Re-checked on a timer so
            // the button "wakes up" without a reload if the hourly cycle runs late.
            function refreshEnabledState() {
                if (btn.dataset.busy === '1') return; // a trigger is in flight — leave it disabled
                const stale = isNaN(builtAt) || (Date.now() - builtAt) >= REFRESH_STALE_MS;
                btn.disabled = !stale;
                btn.title = stale ? 'Manually refresh the feed' : 'Available once the feed is over 60 min old';
            }
            refreshEnabledState();
            setInterval(refreshEnabledState, 30 * 1000);

            btn.addEventListener('click', async () => {
                btn.dataset.busy = '1';
                btn.disabled = true;
                if (status) status.textContent = 'Refreshing… new content in ~3 min, reload shortly.';
                try {
                    const res = await fetch('/api/trigger-update', { method: 'POST' });
                    const data = await res.json();
                    if (data && data.ok) {
                        if (status) status.textContent = 'Refresh started — reload in a few minutes.';
                        return; // leave disabled + busy; a run is on its way
                    }
                    const msg = (data && REFRESH_MESSAGES[data.reason]) || 'Could not start a refresh — try again later.';
                    if (status) status.textContent = msg;
                } catch (e) {
                    if (status) status.textContent = 'Could not start a refresh — try again later.';
                }
                btn.dataset.busy = '';
                refreshEnabledState();
            });
        }
        initRefreshButton();

        // ==================== WSW SIDEBAR ====================
        let wswData = null;
        let currentWswProvider = 'gemini-3-flash';
        let currentWswView = safeStorage.get('financeradar_wsw_view') || 'ideas';
        if (currentWswView !== 'ideas' && currentWswView !== 'bookmarks') {
            currentWswView = 'ideas';
        }

        function getWswBookmarks() {
            try {
                const data = localStorage.getItem(WSW_BOOKMARKS_KEY);
                const parsed = data ? JSON.parse(data) : [];
                return Array.isArray(parsed) ? parsed : [];
            } catch (e) {
                return [];
            }
        }

        function saveWswBookmarks(bookmarks) {
            try {
                localStorage.setItem(WSW_BOOKMARKS_KEY, JSON.stringify(bookmarks));
            } catch (e) { /* no-op */ }
        }

        function hashWswKey(text) {
            const input = String(text || '');
            let hash = 0;
            for (let i = 0; i < input.length; i++) {
                hash = ((hash << 5) - hash) + input.charCodeAt(i);
                hash |= 0;
            }
            return Math.abs(hash).toString(36);
        }

        function getWswBookmarkId(cluster, providerKey) {
            const primaryUrl = sanitizeUrl(cluster.source_url_primary);
            if (primaryUrl) return primaryUrl;
            const seed = [
                providerKey || '',
                cluster.rank || '',
                cluster.cluster_title || '',
                cluster.quote_snippet || '',
                cluster.quote_speaker || ''
            ].join('|');
            return 'wsw:' + hashWswKey(seed);
        }

        function buildWswBookmark(cluster, providerKey, providerName) {
            return {
                id: getWswBookmarkId(cluster, providerKey),
                url: sanitizeUrl(cluster.source_url_primary),
                title: cluster.cluster_title || 'Untitled WSW idea',
                quoteSnippet: cluster.quote_snippet || '',
                quoteSpeaker: cluster.quote_speaker || '',
                indiaRelevance: cluster.india_relevance || '',
                confidence: cluster.confidence || '',
                providerKey: providerKey || '',
                providerName: providerName || '',
                addedAt: Date.now()
            };
        }

        function isWswBookmarked(id) {
            if (!id) return false;
            return getWswBookmarks().some(b => b.id === id);
        }

        function updateWswBookmarkCount() {
            const count = getWswBookmarks().length;
            const badge = document.getElementById('wsw-bookmark-count');
            const toggle = document.getElementById('wsw-toggle');
            if (!badge || !toggle) return;
            badge.textContent = count;
            badge.classList.toggle('hidden', count === 0);
            toggle.classList.toggle('has-bookmarks', count > 0);
        }

        function updateWswViewPills() {
            document.querySelectorAll('.wsw-view-pill').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.wswView === currentWswView);
            });
        }

        function updateWswBookmarkActions() {
            const hasBookmarks = getWswBookmarks().length > 0;
            const copyBtn = document.getElementById('wsw-copy-btn');
            const clearBtn = document.getElementById('wsw-clear-btn');
            if (copyBtn) copyBtn.disabled = !hasBookmarks;
            if (clearBtn) clearBtn.disabled = !hasBookmarks;
        }

        function switchWswView(view) {
            if (view !== 'ideas' && view !== 'bookmarks') return;
            currentWswView = view;
            safeStorage.set('financeradar_wsw_view', view);
            renderWswContent();
        }

        async function loadWswClusters() {
            try {
                const res = await fetch('static/wsw_clusters.json');
                if (!res.ok) throw new Error('not found');
                wswData = await res.json();
                // Backward compat: old format has wswData.clusters directly
                if (wswData.clusters && !wswData.providers) {
                    wswData = { ...wswData, providers: { 'gemini-3-flash': { name: 'Gemini 3.0 Flash', status: 'ok', count: wswData.clusters.length, clusters: wswData.clusters } } };
                }
                populateWswProviderDropdown();
                renderWswContent();
                renderHomeTab();
            } catch(e) {
                document.getElementById('wsw-content').innerHTML =
                    '<div class="ai-error"><div class="ai-error-title">WSW Unavailable</div>' +
                    '<div>Run wsw_ranker.py to generate story ideas.</div></div>';
            }
        }

        function populateWswProviderDropdown() {
            const select = document.getElementById('wsw-provider');
            select.innerHTML = '';
            if (!wswData || !wswData.providers) return;
            const providers = Object.entries(wswData.providers);
            providers.forEach(([key, p]) => {
                const opt = document.createElement('option');
                opt.value = key;
                opt.textContent = p.name + (p.status !== 'ok' ? ' (unavailable)' : '');
                if (key === currentWswProvider) opt.selected = true;
                select.appendChild(opt);
            });
            if (!wswData.providers[currentWswProvider]) {
                const firstOk = providers.find(([k, p]) => p.status === 'ok');
                if (firstOk) { currentWswProvider = firstOk[0]; select.value = currentWswProvider; }
            }
        }

        function switchWswProvider() {
            currentWswProvider = document.getElementById('wsw-provider').value;
            renderWswContent();
            renderHomeTab();
        }

        function syncWswClusterBookmarkButtons() {
            const ids = new Set(getWswBookmarks().map(b => b.id));
            document.querySelectorAll('#wsw-content .wsw-bookmark-btn[data-wsw-id]').forEach(btn => {
                btn.classList.toggle('bookmarked', ids.has(btn.dataset.wswId));
            });
        }

        function toggleWswBookmark(payload, btn) {
            if (!payload || !payload.id) return;
            let bookmarks = getWswBookmarks();
            const idx = bookmarks.findIndex(b => b.id === payload.id);

            if (idx >= 0) {
                bookmarks.splice(idx, 1);
                if (btn) btn.classList.remove('bookmarked');
            } else {
                bookmarks.unshift({
                    ...payload,
                    addedAt: payload.addedAt || Date.now()
                });
                if (btn) btn.classList.add('bookmarked');
            }

            saveWswBookmarks(bookmarks);
            updateWswBookmarkCount();
            updateWswBookmarkActions();

            if (currentWswView === 'bookmarks') {
                renderWswBookmarks();
            } else {
                syncWswClusterBookmarkButtons();
            }
        }

        function removeWswBookmark(id) {
            let bookmarks = getWswBookmarks();
            bookmarks = bookmarks.filter(b => b.id !== id);
            saveWswBookmarks(bookmarks);
            updateWswBookmarkCount();
            updateWswBookmarkActions();
            if (currentWswView === 'bookmarks') {
                renderWswBookmarks();
            } else {
                syncWswClusterBookmarkButtons();
            }
        }

        function renderWswBookmarks() {
            const container = document.getElementById('wsw-content');
            const bookmarks = getWswBookmarks();
            if (bookmarks.length === 0) {
                container.innerHTML = '<div class="sidebar-empty">No Who Said What bookmarks yet.<br>Save ideas using the bookmark icon.</div>';
                return;
            }

            container.innerHTML = bookmarks.map(b => {
                const url = sanitizeUrl(b.url);
                const titleHtml = url
                    ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(b.title || 'Untitled WSW idea')}</a>`
                    : `<span class="rank-title-nolink">${escapeHtml(b.title || 'Untitled WSW idea')}</span>`;
                const sourceParts = [];
                if (b.quoteSpeaker) sourceParts.push(escapeHtml(b.quoteSpeaker));
                if (b.providerName) sourceParts.push(escapeHtml(b.providerName));
                if (b.confidence) sourceParts.push(('CONF: ' + escapeHtml(String(b.confidence).toUpperCase())));
                return `
                    <div class="sidebar-article wsw-bookmark-item" data-wsw-id="${escapeHtml(b.id)}">
                        <div class="sidebar-article-title">${titleHtml}</div>
                        ${b.quoteSnippet ? `<div class="wsw-bookmark-quote">"${escapeHtml(b.quoteSnippet)}"</div>` : ''}
                        ${b.indiaRelevance ? `<div class="wsw-bookmark-india">${escapeHtml(b.indiaRelevance)}</div>` : ''}
                        <div class="sidebar-article-meta">
                            <span class="sidebar-article-source">${sourceParts.join(' · ')}</span>
                            <button class="sidebar-remove" onclick="removeWswBookmark('${escapeForAttr(b.id)}')" title="Remove bookmark">✕</button>
                        </div>
                    </div>
                `;
            }).join('');
        }

        function renderWswClusters() {
            const container = document.getElementById('wsw-content');
            if (!wswData || !wswData.providers) {
                container.innerHTML = '<div class="ai-error">No WSW clusters yet.</div>';
                return;
            }
            const provider = wswData.providers[currentWswProvider];
            if (!provider) {
                container.innerHTML = '<div class="ai-error">Provider not available.</div>';
                return;
            }
            if (provider.status !== 'ok') {
                container.innerHTML = '<div class="ai-error"><div class="ai-error-title">WSW Temporarily Unavailable</div><div style="margin-top:8px;font-size:12px;color:var(--text-muted)">Will refresh on next scheduled run.</div></div>';
                return;
            }
            container.innerHTML = provider.clusters.map(c => {
                const bookmark = buildWswBookmark(c, currentWswProvider, provider.name || currentWswProvider);
                const confidenceClass = String(c.confidence || '').toLowerCase();
                return `
                    <div class="ai-rank-item wsw-cluster-item">
                        <span class="rank-num">${c.rank}</span>
                        <div class="rank-content">
                            ${bookmark.url
                                ? `<a href="${escapeHtml(bookmark.url)}" target="_blank" rel="noopener">${escapeHtml(c.cluster_title)}</a>`
                                : `<span class="rank-title-nolink">${escapeHtml(c.cluster_title)}</span>`}
                            <div class="wsw-quote">"${escapeHtml(c.quote_snippet)}"
                                <span class="wsw-speaker">— ${escapeHtml(c.quote_speaker)}</span>
                            </div>
                            <div class="wsw-india">${escapeHtml(c.india_relevance)}</div>
                            <span class="wsw-confidence wsw-conf-${escapeHtml(confidenceClass)}">${escapeHtml(c.confidence)}</span>
                        </div>
                        <button class="ai-bookmark-btn wsw-bookmark-btn ${isWswBookmarked(bookmark.id) ? 'bookmarked' : ''}"
                                data-wsw-id="${escapeForAttr(bookmark.id)}"
                                data-url="${escapeForAttr(bookmark.url)}"
                                data-title="${escapeForAttr(bookmark.title)}"
                                data-quote-snippet="${escapeForAttr(bookmark.quoteSnippet)}"
                                data-quote-speaker="${escapeForAttr(bookmark.quoteSpeaker)}"
                                data-india-relevance="${escapeForAttr(bookmark.indiaRelevance)}"
                                data-confidence="${escapeForAttr(bookmark.confidence)}"
                                data-provider-key="${escapeForAttr(bookmark.providerKey)}"
                                data-provider-name="${escapeForAttr(bookmark.providerName)}"
                                title="Bookmark WSW idea"
                                aria-label="Bookmark WSW idea">
                            <svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                        </button>
                    </div>
                `;
            }).join('');
            const el = document.getElementById('wsw-updated');
            if (wswData.generated_at) {
                const d = Math.floor((new Date() - new Date(wswData.generated_at)) / 60000);
                el.textContent = 'Updated ' + (d < 1 ? 'just now' : d < 60 ? d + ' min ago' : d < 1440 ? Math.floor(d/60) + ' hr ago' : Math.floor(d/1440) + ' day ago');
            } else {
                el.textContent = 'Updated: --';
            }
        }

        function renderWswContent() {
            if (currentWswView === 'bookmarks') {
                renderWswBookmarks();
            } else {
                renderWswClusters();
            }
            updateWswViewPills();
            updateWswBookmarkActions();
        }

        function copyWswBookmarks() {
            const bookmarks = getWswBookmarks();
            if (bookmarks.length === 0) return;

            const text = bookmarks.map(b => {
                const lines = [];
                lines.push(b.title || 'Untitled WSW idea');
                if (b.quoteSnippet) lines.push('Quote: "' + b.quoteSnippet + '"');
                if (b.quoteSpeaker) lines.push('Speaker: ' + b.quoteSpeaker);
                if (b.indiaRelevance) lines.push('India relevance: ' + b.indiaRelevance);
                if (b.confidence) lines.push('Confidence: ' + String(b.confidence).toUpperCase());
                if (b.url) lines.push('URL: ' + b.url);
                return lines.join('\n');
            }).join('\n\n');

            copyTextWithFallback(text, () => flashCopiedButton(document.getElementById('wsw-copy-btn')));
        }

        function clearAllWswBookmarks() {
            if (!confirm('Are you sure you want to clear all Who Said What bookmarks?')) return;
            saveWswBookmarks([]);
            updateWswBookmarkCount();
            updateWswBookmarkActions();
            if (currentWswView === 'bookmarks') {
                renderWswBookmarks();
            } else {
                syncWswClusterBookmarkButtons();
            }
        }

        function openWswSidebar() {
            const overlay = document.getElementById('wsw-sidebar-overlay');
            if (!overlay || overlay.classList.contains('open')) return;
            overlay.classList.add('open');
            lockBodyScroll();
            renderWswContent();
        }

        function closeWswSidebar() {
            const overlay = document.getElementById('wsw-sidebar-overlay');
            if (!overlay || !overlay.classList.contains('open')) return;
            overlay.classList.remove('open');
            unlockBodyScroll();
        }

        document.getElementById('wsw-sidebar-overlay').addEventListener('click', e => {
            if (e.target.id === 'wsw-sidebar-overlay') closeWswSidebar();
        });

        document.getElementById('wsw-content').addEventListener('click', (e) => {
            const btn = e.target.closest('.wsw-bookmark-btn');
            if (!btn) return;
            e.preventDefault();
            e.stopPropagation();

            const payload = {
                id: btn.getAttribute('data-wsw-id') || '',
                url: btn.getAttribute('data-url') || '',
                title: btn.getAttribute('data-title') || '',
                quoteSnippet: btn.getAttribute('data-quote-snippet') || '',
                quoteSpeaker: btn.getAttribute('data-quote-speaker') || '',
                indiaRelevance: btn.getAttribute('data-india-relevance') || '',
                confidence: btn.getAttribute('data-confidence') || '',
                providerKey: btn.getAttribute('data-provider-key') || '',
                providerName: btn.getAttribute('data-provider-name') || '',
                addedAt: Date.now()
            };
            if (!payload.id) return;
            toggleWswBookmark(payload, btn);
        });

        loadWswClusters();
        updateWswBookmarkCount();
        updateWswViewPills();
        updateWswBookmarkActions();

        // ==================== HOME TAB (vars) ====================
        // These vars must be assigned BEFORE the switchTab('home') IIFE below,
        // because renderHomeTab() is called synchronously during initialization.
        var BOOKMARK_SVG = '<svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>';
        var BUCKET_COLORS = {
            news: '#4A8F7A', telegram: '#5E6A96', reports: '#9A8345',
            twitter: '#4A8A9A', youtube: '#A86565', papers: '#7A6B8F'
        };
        var BUCKET_LABELS = {
            news: 'News', telegram: 'Telegram', reports: 'Reports',
            twitter: 'Twitter', youtube: 'YouTube', papers: 'Papers'
        };
        var homeRendered = false;

        // ==================== REPORTS TAB ====================
        let reportsRendered = false;
        let filteredReports = [];
        let reportsViewMode = 'all';
        let reportsNoTargetFilterActive = false;
        let selectedTgChannels = new Set();
        let reportsPage = 1;
        const REPORTS_PAGE_SIZE = 20;
        let reportImageLightboxEl = null;
        let reportImageLightboxImgEl = null;
        let reportImageLightboxErrorEl = null;
        let reportImageLightboxCounterEl = null;
        let reportImageLightboxPrevEl = null;
        let reportImageLightboxNextEl = null;
        let reportImageItems = [];
        let reportImageIndex = 0;
        let reportImageLastTrigger = null;

        // ==================== RESEARCH TAB (vars) ====================
        let researchRendered = false;
        let filteredResearch = [];
        let researchPage = 1;
        const RESEARCH_PAGE_SIZE = 20;
        let selectedResearchPublishers = new Set();
        let researchRegionFilter = 'all'; // 'all' | 'indian' | 'international'

        // ==================== PAPERS TAB (vars) ====================
        let papersRendered = false;
        let paperSessionPool = [];
        let filteredPapers = [];
        let papersPage = 1;
        const PAPERS_PAGE_SIZE = 10;

        // ==================== YOUTUBE TAB (vars) ====================
        let youtubeRendered = false;
        let filteredYoutube = [];
        let youtubePage = 1;
        const YOUTUBE_PAGE_SIZE = 20;
        let selectedYoutubePublishers = new Set();
        let youtubeBucketFilter = 'all';

        // ==================== TWITTER TAB (vars) ====================
        let twitterRendered = false;
        let newsRendered = false;
        let filteredTwitter = [];
        let twitterPage = 1;
        const TWITTER_PAGE_SIZE = 30;
        let selectedTwitterPublishers = new Set();
        let twitterLane = safeStorage.get('financeradar_twitter_lane') || 'high-signal';
        let activeTab = 'home';
        const tabScrollPositions = { home: 0, news: 0 };
        let pendingTabScrollCapture = null;

        function rememberActiveTabScroll() {
            if (!activeTab) return;
            tabScrollPositions[activeTab] = window.scrollY || window.pageYOffset || 0;
        }

        window.addEventListener('scroll', rememberActiveTabScroll, { passive: true });
        document.querySelectorAll('.tab-pill').forEach(btn => {
            const capture = () => {
                pendingTabScrollCapture = window.scrollY || window.pageYOffset || 0;
            };
            btn.addEventListener('pointerdown', capture, { passive: true });
            btn.addEventListener('mousedown', capture, { passive: true });
            btn.addEventListener('touchstart', capture, { passive: true });
        });

        // Tab pill click handlers
        document.querySelectorAll('.tab-pill').forEach(function(pill) {
            pill.addEventListener('click', function() {
                switchTab(pill.dataset.tab);
            });
        });

        // Always open Home on initial load.
        (function() {
            switchTab('home', true);
        })();

        function switchTab(tab, skipScroll) {
            const previousTab = activeTab;
            if (previousTab) {
                if (pendingTabScrollCapture != null) {
                    tabScrollPositions[previousTab] = pendingTabScrollCapture;
                } else if (tabScrollPositions[previousTab] == null) {
                    tabScrollPositions[previousTab] = window.scrollY || window.pageYOffset || 0;
                }
            }
            pendingTabScrollCapture = null;
            document.querySelectorAll('.tab-pill').forEach(btn => {
                const isActive = btn.dataset.tab === tab;
                btn.classList.toggle('tab-active', isActive);
                btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
            });
            document.querySelectorAll('.tab-content').forEach(el => {
                el.classList.toggle('active', el.id === 'tab-' + tab);
            });
            const searchEl = document.getElementById('search-input');
            if (searchEl) searchEl.placeholder = 'Search...';
            var _doRender = function() {
                if (tab === 'home') {
                    renderHomeTab();
                    homeRendered = true;
                } else if (tab === 'reports') {
                    if (!reportsRendered) {
                        renderMainReports();
                        reportsRendered = true;
                    }
                    filterReports();
                } else if (tab === 'research') {
                    if (!researchRendered) {
                        renderMainResearch();
                        researchRendered = true;
                    }
                    filterResearch();
                } else if (tab === 'papers') {
                    if (!papersRendered) {
                        renderMainPapers();
                        papersRendered = true;
                    }
                    if (previousTab !== 'papers') {
                        reshufflePaperSession();
                    }
                    filterPapers();
                } else if (tab === 'youtube') {
                    if (!youtubeRendered) {
                        renderMainYoutube();
                        youtubeRendered = true;
                    }
                    filterYoutube();
                } else if (tab === 'twitter') {
                    if (!twitterRendered) {
                        renderMainTwitter();
                        twitterRendered = true;
                    }
                    filterTwitter();
                } else {
                    if (!newsRendered) {
                        renderNewsFromJSON();
                        newsRendered = true;
                    }
                    filterArticles();
                }
            };
            ensureTabData(tab, _doRender);
            activeTab = tab;
            applyFilterCollapseForTab(tab);
            const activeTabButton = document.querySelector('.tab-pill.tab-active');
            if (isMobileViewport() && activeTabButton) {
                const tabStrip = activeTabButton.closest('.tab-bar');
                if (tabStrip) {
                    const targetLeft = activeTabButton.offsetLeft - ((tabStrip.clientWidth - activeTabButton.offsetWidth) / 2);
                    tabStrip.scrollTo({
                        left: Math.max(0, Math.round(targetLeft)),
                        behavior: skipScroll ? 'auto' : 'smooth'
                    });
                }
            }
            if (!skipScroll) {
                if (isMobileViewport()) {
                    const targetY = Number(tabScrollPositions[tab] || 0);
                    const restore = () => window.scrollTo({ top: targetY, left: 0, behavior: 'auto' });
                    restore();
                    window.requestAnimationFrame(restore);
                    setTimeout(restore, 120);
                } else {
                    window.scrollTo({top: 0, behavior: 'smooth'});
                }
            }
            safeStorage.set('financeradar_active_tab', tab);
        }

        const brandHomeLink = document.getElementById('brand-home-link');
        if (brandHomeLink) {
            brandHomeLink.addEventListener('click', (e) => {
                e.preventDefault();
                switchTab('home');
            });
        }

        function formatRelativeTimeShort(isoStr) {
            if (!isoStr) return '';
            const date = new Date(isoStr);
            if (Number.isNaN(date.getTime())) return '';
            const now = new Date();
            const diffMs = now - date;
            const diffMin = Math.floor(diffMs / 60000);
            const diffHr = Math.floor(diffMs / 3600000);
            const diffDay = Math.floor(diffMs / 86400000);
            if (diffMin < 1) return 'Just now';
            if (diffMin < 60) return diffMin + 'm ago';
            if (diffHr < 24) return diffHr + 'h ago';
            if (diffDay < 7) return diffDay + 'd ago';
            return date.toLocaleDateString();
        }

        // ==================== HEADLINE CLEAN-UP ====================
        // ALL-CAPS headlines (common on Telegram and in SBI notes) → Title Case. Title Case, not
        // sentence case, so company names stay readable ("Karur Vysya Bank"). Acronyms, vowel-less
        // short words (JV, NTPC), months, "Rs" and a leading stock ticker ("CMPDI : ...") keep their form.
        var HEADLINE_ACRONYMS = new Set(('RBI SEBI SBI LIC IPO GDP CPI WPI GST US UK EU IMF FII FPI DII NBFC PSU SC HC AT1 IT AI EV FY '
            + 'Q1 Q2 Q3 Q4 MPC NSE BSE ETF CR BPS OPEC IEA FDI MSME PLI UPI NPCI IRDAI PFRDA EPFO IIP BOM BESS IDBI '
            + 'ICICI ONGC IOC GAIL BHEL SAIL NHPC SJVN IREDA LLP YOY QOQ PAT EPS NII').split(' '));
        var HEADLINE_SMALL_WORDS = new Set('a an the and but or nor for so yet as at by in of off on per to up via vs with from into'.split(' '));
        var HEADLINE_MONTHS = new Set('jan feb mar apr may jun jul aug sep sept oct nov dec january february march april june july august september october november december'.split(' '));

        function deshoutTitle(text) {
            var t = String(text || '');
            var letters = t.replace(/[^A-Za-z]/g, '');
            if (!letters) return t;
            var upper = letters.replace(/[^A-Z]/g, '').length;
            if (upper / letters.length < 0.8) return t;
            var words = t.split(' ');
            var out = words.map(function(w, i) {
                var core = w.replace(/[^A-Za-z0-9]/g, '');
                var coreUp = core.toUpperCase();
                if (HEADLINE_ACRONYMS.has(coreUp)) return w;
                if (coreUp === 'RS') return w.charAt(0) + w.slice(1).toLowerCase();
                if (/[0-9]/.test(core) && /[A-Za-z]/.test(core)) return w;
                if (core.length >= 2 && core.length <= 5 && /^[A-Za-z]+$/.test(core) && !/[AEIOUY]/.test(coreUp)) return w;
                if (i > 0 && HEADLINE_SMALL_WORDS.has(core.toLowerCase())) return w.toLowerCase();
                if (HEADLINE_MONTHS.has(core.toLowerCase())) return w.charAt(0) + w.slice(1).toLowerCase();
                return w.split('-').map(function(p) { return p.charAt(0).toUpperCase() + p.slice(1).toLowerCase(); }).join('-');
            });
            // Telegram posts open with a stock ticker: keep "CMPDI : ..." in capitals
            var ticker = t.match(/^([A-Z0-9&.\-]{2,15})\s?:/);
            if (ticker) out[0] = words[0];
            return out.join(' ');
        }

        // Cluster angle tags often repeat the source name ("Reuters confirmation of ..."). Drop it
        // and the filler words the AI tends to start with, so the tag says only what this source adds.
        var ANGLE_FILLER = /^((telegram|twitter|official|report|reports|analysis|thread|relay|confirmation|details|on|of|the|sebi|circular|video:?)\s+)+/i;
        function tidyAngle(angle, source) {
            var a = String(angle || '').trim();
            var src = String(source || '').trim();
            var names = [src, src.split(' ')[0]];
            for (var i = 0; i < names.length; i++) {
                if (names[i] && a.toLowerCase().indexOf(names[i].toLowerCase()) === 0) {
                    a = a.slice(names[i].length).trim();
                    break;
                }
            }
            return a.replace(ANGLE_FILLER, '').trim();
        }

        // Some Telegram channels are named only with an emoji (e.g. "📈") — say "Telegram" on the homepage.
        function homeSourceName(name, sourceType) {
            var n = String(name || '').trim();
            if (/[A-Za-z0-9]/.test(n)) return n;
            return sourceType === 'telegram' || !sourceType ? 'Telegram' : (BUCKET_LABELS[sourceType] || 'Source');
        }

        function cleanHomeTitle(rawTitle) {
            var t = String(rawTitle || '')
                .replace(/\s+-\s+Press Information Bureau\s*$/i, '')
                .replace(/[*_`~#>\[\]\(\)]/g, ' ')
                .replace(/\s+/g, ' ')
                .trim() || 'Untitled';
            if (/^https?:\/\//.test(t) && t.length > 80) {
                try {
                    var u = new URL(t);
                    t = u.hostname.replace(/^www\./, '') + '/\u2026';
                } catch (e) { /* keep original */ }
            }
            return deshoutTitle(t);
        }

        function getTelegramReportDocuments(report) {
            if (Array.isArray(report.documents) && report.documents.length > 0) return report.documents;
            if (report.document && report.document.title) return [report.document];
            return [];
        }

        // (Old bento-grid home builders removed — replaced by newspaper layout)

        function getHomeAiItems() {
            if (!aiRankings || !aiRankings.providers) return { clusters: [], feed: [], youtube: [], reports: [], twitter: [], isEmpty: true };

            // Get clusters first, then exclude clustered URLs from feeds
            var clusters = getMergedClusters();
            var clusteredUrls = getClusteredUrls(clusters);

            var newsMerged = getMergedAiRankings('news');
            var telegramMerged = getMergedAiRankings('telegram');
            var reportsMerged = getMergedAiRankings('reports');
            var twitterMerged = getMergedAiRankings('twitter');
            var youtubeMerged = getMergedAiRankings('youtube');

            if (!newsMerged.length && !telegramMerged.length && !reportsMerged.length
                && !twitterMerged.length && !youtubeMerged.length && !clusters.length) {
                return { clusters: [], feed: [], youtube: [], reports: [], twitter: [], isEmpty: true };
            }

            // Filter out clustered items from all buckets
            function notClustered(item) {
                var url = String(item.url || '').toLowerCase().trim();
                return !url || !clusteredUrls.has(url);
            }
            newsMerged = newsMerged.filter(notClustered);
            telegramMerged = telegramMerged.filter(notClustered);
            reportsMerged = reportsMerged.filter(notClustered);
            twitterMerged = twitterMerged.filter(notClustered);
            youtubeMerged = youtubeMerged.filter(notClustered);

            // Convert merged AI items to homepage card format
            function toCard(item, bucket) {
                var source = item.source || '';
                if (source.length > 35) source = source.slice(0, 35) + '...';
                return {
                    title: cleanHomeTitle(item.title),
                    url: item.url || '',
                    meta: source,
                    _bucket: bucket,
                    why_it_matters: item.why_it_matters || '',
                    signal_type: item.signal_type || '',
                    confidence: item.confidence || '',
                    _consensus: item._consensus || false,
                    _mergedRank: item._mergedRank || 0,
                    source_tier: item.source_tier || '',
                    high_signal: item.high_signal || false
                };
            }

            // Convert to slider-compatible format (matching what buildYtSlider/buildRpSlider/buildTwSlider expect)
            function toSliderItem(item) {
                return {
                    title: item.title,
                    link: item.url || '',
                    source_url: item.url || '',
                    source: item.source || '',
                    publisher: item.source || '',
                    thumbnail: item.thumbnail || '',
                    region: item.region || '',
                    date: item.date || '',
                    _providerCount: item._providerCount || 1
                };
            }

            var newsCards = newsMerged.map(function(it) { return toCard(it, 'news'); });
            var telegramCards = telegramMerged.map(function(it) { return toCard(it, 'telegram'); });

            // Interleave news + telegram: 3 news, 1 telegram, repeat
            var feed = [];
            var ni = 0, ti = 0;
            while (ni < newsCards.length || ti < telegramCards.length) {
                for (var k = 0; k < 3 && ni < newsCards.length; k++) {
                    feed.push(newsCards[ni++]);
                }
                if (ti < telegramCards.length) {
                    feed.push(telegramCards[ti++]);
                }
            }

            // Keep high-signal official items out of the news feed — they surface in the
            // dedicated "From The Source" slider (sourced separately from NEWS_ARTICLES).
            var regularFeed = feed.filter(function(c) {
                return !(c.source_tier === 'official' && c.high_signal);
            });

            return {
                clusters: clusters,
                feed: regularFeed,
                youtube: youtubeMerged.map(toSliderItem),
                reports: reportsMerged.map(toSliderItem),
                twitter: twitterMerged.map(toSliderItem),
                isEmpty: false
            };
        }

        function getYoutubeVideoIdFromUrl(url) {
            const raw = String(url || '').trim();
            if (!raw) return '';
            const short = raw.match(/youtu\.be\/([a-zA-Z0-9_-]{6,})/);
            if (short && short[1]) return short[1];
            const watch = raw.match(/[?&]v=([a-zA-Z0-9_-]{6,})/);
            if (watch && watch[1]) return watch[1];
            const embed = raw.match(/\/embed\/([a-zA-Z0-9_-]{6,})/);
            if (embed && embed[1]) return embed[1];
            const shorts = raw.match(/\/shorts\/([a-zA-Z0-9_-]{6,})/);
            if (shorts && shorts[1]) return shorts[1];
            return '';
        }

        // (Old spotlight/AI-ranking home functions removed — newspaper layout uses direct data access)

        // ==================== NEWSPAPER CARD BUILDERS ====================

        function npBookmarkBtn(url, title, source) {
            if (!url) return '';
            const cls = 'btn-bk bookmark-btn' + (isBookmarked(url) ? ' bookmarked' : '');
            return '<button class="' + cls + '" type="button"'
                + ' data-url="' + escapeForAttr(url) + '"'
                + ' data-title="' + escapeForAttr(title) + '"'
                + ' data-source="' + escapeForAttr(source || 'Home') + '"'
                + ' onclick="toggleGenericBookmark(this)" aria-label="Bookmark">'
                + BOOKMARK_SVG + '</button>';
        }

        function catMeta(item, bk) {
            var bucket = item._bucket || 'news';
            var color = BUCKET_COLORS[bucket] || '#6B645C';
            var label = BUCKET_LABELS[bucket] || 'News';
            return '<div class="card-meta"><span class="cat-dot" style="background:' + color + '"></span><span class="cat-label">' + label + '</span>' + (bk || '') + '</div>';
        }

        function cardHero(item) {
            const title = escapeHtml(cleanHomeTitle(item.title));
            const url = sanitizeUrl(item.url || '');
            const source = escapeHtml(homeSourceName(item.meta, item._bucket) || 'News');
            const desc = item.description ? '<p class="hero-desc">' + escapeHtml(item.description) + '</p>' : '';
            const why = item.why_it_matters ? '<p class="hero-why">' + escapeHtml(item.why_it_matters) + '</p>' : '';
            const signal = item.signal_type ? '<span class="hero-signal-badge">' + escapeHtml(item.signal_type) + '</span>' : '';
            const consensus = item._consensus ? '<span class="hero-consensus" title="Picked by multiple AI models"></span>' : '';
            const bk = npBookmarkBtn(url, title, item.meta);
            const titleHtml = url
                ? '<a href="' + escapeForAttr(url) + '" target="_blank" rel="noopener">' + title + '</a>'
                : title;
            return '<div class="card-hero">'
                + catMeta(item) + bk
                + '<h2 class="hero-title">' + titleHtml + '</h2>'
                + desc + why
                + '<div class="hero-source">' + source + signal + consensus + '</div></div>';
        }

        function cardCompact(item) {
            const title = escapeHtml(cleanHomeTitle(item.title));
            const url = sanitizeUrl(item.url || '');
            const source = escapeHtml(homeSourceName(item.meta, item._bucket) || 'News');
            const bk = npBookmarkBtn(url, title, item.meta);
            var bucket = item._bucket || 'news';
            var color = BUCKET_COLORS[bucket] || '#6B645C';
            const linkHtml = url
                ? '<a class="compact-link" href="' + escapeForAttr(url) + '" target="_blank" rel="noopener">' + title + '</a>'
                : '<span class="compact-link">' + title + '</span>';
            return '<div class="card-compact"><span class="cat-dot" style="background:' + color + '"></span><div class="compact-body">'
                + linkHtml
                + '<span class="compact-src">' + source + '</span></div>' + bk + '</div>';
        }

        // ==================== NEWSPAPER PATTERN BUILDERS ====================
        // Block 1 of the feed: one lead story, a side list, then two columns of rows.
        function renderPatternA(items) {
            if (!items.length) return '';
            const hero = items[0];
            const sidebar = items.slice(1, 5);
            const rows = items.slice(5);
            return '<section class="feed-section"><div class="pa-lead">'
                + cardHero(hero)
                + '<div class="pa-sidebar">' + sidebar.map(cardCompact).join('') + '</div>'
                + '</div>'
                + (rows.length ? '<div class="feed-rows">' + rows.map(cardCompact).join('') + '</div>' : '')
                + '</section>';
        }

        // Later feed blocks: plain two-column rows under an ink rule (no second hero).
        // Last block of the homepage: every remaining story in a box that scrolls inside
        // itself, so the page ends instead of growing with the feed.
        function renderFeedBucket(items) {
            if (!items.length) return '';
            return renderSectionLabel('More from the feed', items.length + ' more stories, scroll inside the box')
                + '<section class="feed-section"><div class="feed-bucket"><div class="feed-rows feed-rows-ruled">'
                + items.map(cardCompact).join('') + '</div></div></section>';
        }

        function renderFeedRows(items) {
            if (!items.length) return '';
            return '<section class="feed-section"><div class="feed-rows feed-rows-ruled">'
                + items.map(cardCompact).join('') + '</div></section>';
        }

        // ==================== SLIDER BUILDERS ====================
        function sliderArrows(trackId) {
            return '<button class="slider-arrow slider-prev" aria-label="Scroll left" data-track="' + trackId + '">&#8249;</button>'
                + '<button class="slider-arrow slider-next" aria-label="Scroll right" data-track="' + trackId + '">&#8250;</button>';
        }

        function buildYtSlider(items) {
            if (!items.length) return '';
            const cards = items.map(v => {
                const title = escapeHtml(cleanHomeTitle(v.title));
                const url = sanitizeUrl(v.link || v.source_url || '');
                const channel = escapeHtml(v.publisher || v.source || 'YouTube');
                const videoId = getYoutubeVideoIdFromUrl(url);
                const thumb = sanitizeUrl(v.thumbnail || '') || (videoId ? 'https://i.ytimg.com/vi/' + videoId + '/mqdefault.jpg' : '');
                const bk = npBookmarkBtn(url, title, channel);
                return '<div class="slider-card slider-yt">'
                    + (thumb ? '<a href="' + escapeForAttr(url) + '" target="_blank" rel="noopener" class="yt-thumb" style="background-image:url(' + escapeForAttr(thumb) + ')"><span class="yt-play">&#9654;</span></a>' : '')
                    + '<div class="slider-card-body"><div class="slider-card-header">'
                    + '<a class="yt-title" href="' + escapeForAttr(url) + '" target="_blank" rel="noopener">' + title + '</a>'
                    + bk + '</div><div class="yt-channel">' + channel + '</div></div></div>';
            }).join('');
            return '<section class="slider-section">'
                + sliderHead('Watch', items.length + ' videos picked today', 'yt-track')
                + '<div class="slider-track" id="yt-track">' + cards + '</div></section>';
        }

        function buildRpSlider(items) {
            if (!items.length) return '';
            const cards = items.map(r => {
                const title = escapeHtml(cleanHomeTitle(r.title));
                const url = sanitizeUrl(r.link || r.source_url || '');
                const pub = escapeHtml(r.publisher || r.source || 'Research');
                const bk = npBookmarkBtn(url, title, pub);
                const region = String(r.region || '').toLowerCase();
                const regionBadge = region === 'indian' ? '<span class="rp-reg rp-reg-in">India</span>'
                    : region === 'international' ? '<span class="rp-reg rp-reg-intl">International</span>' : '';
                const d = r.date ? new Date(r.date) : null;
                const dateStr = d && !isNaN(d) ? escapeHtml(d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })) : '';
                return '<div class="slider-card slider-rp"><div class="slider-card-body">'
                    + '<div class="slider-card-header"><div><div class="rp-publisher">' + pub + '</div>'
                    + '<a class="rp-title" href="' + escapeForAttr(url) + '" target="_blank" rel="noopener">' + title + '</a>'
                    + '</div>' + bk + '</div>'
                    + (regionBadge || dateStr ? '<div class="card-signals">' + regionBadge + (dateStr ? '<span class="rp-date">' + dateStr + '</span>' : '') + '</div>' : '')
                    + '</div></div>';
            }).join('');
            return '<section class="slider-section">'
                + sliderHead('Research Reports', items.length + ' picked today', 'rp-track')
                + '<div class="slider-track" id="rp-track">' + cards + '</div></section>';
        }

        // "RT The Indian Express: …" → reposted from The Indian Express, text without the prefix.
        function tweetKind(rawTitle) {
            var raw = String(rawTitle || '').trim();
            var m = raw.match(/^RT\s+@?([^:]{1,60}):\s*/);
            var text = m ? raw.slice(m[0].length) : raw;
            var kind = '';
            if (m) kind = '<span class="tw-kind tw-kind-repost">Repost of <b>' + escapeHtml(m[1].trim()) + '</b></span>';
            else if (/^[“”"]/.test(raw)) kind = '<span class="tw-kind tw-kind-quote">Quote post</span>';
            if (raw.indexOf('🧵') !== -1) kind += '<span class="tw-kind tw-kind-thread">Thread</span>';
            return { text: text, kind: kind };
        }

        function buildTwSlider(items) {
            if (!items.length) return '';
            const cards = items.map(t => {
                const k = tweetKind(t.title);
                const title = escapeHtml(cleanHomeTitle(k.text));
                const url = sanitizeUrl(t.link || t.source_url || '');
                const author = escapeHtml(t.publisher || t.source || 'Twitter');
                const bk = npBookmarkBtn(url, title, author);
                return '<div class="slider-card slider-tw"><div class="slider-card-body">'
                    + '<div class="slider-card-header"><div><div class="tw-author">' + author + '</div>'
                    + '<a class="tw-text" href="' + escapeForAttr(url) + '" target="_blank" rel="noopener">' + title + '</a>'
                    + '</div>' + bk + '</div>'
                    + '<div class="card-signals">' + k.kind + '<span class="bs-sigs">' + agreementHtml(t._providerCount) + '</span></div>'
                    + '</div></div>';
            }).join('');
            return '<section class="slider-section">'
                + sliderHead('Voices', items.length + ' posts picked today', 'tw-track')
                + '<div class="slider-track" id="tw-track">' + cards + '</div></section>';
        }

        function getSebiNotices() {
            if (!NEWS_ARTICLES || !NEWS_ARTICLES.length) return [];
            var SEBI_NOTICE_SOURCES = {
                'SEBI — Enforcement Orders': true,
                'SEBI — Adjudication Orders': true
            };
            // Cutoff = start of (today - 10 days), local time — calendar-day window
            var cutoff = new Date();
            cutoff.setHours(0, 0, 0, 0);
            cutoff.setDate(cutoff.getDate() - 10);
            var cutoffMs = cutoff.getTime();
            return NEWS_ARTICLES
                .filter(function(a) {
                    if (SEBI_NOTICE_SOURCES[a.source] !== true) return false;
                    var t = new Date(a.date || 0).getTime();
                    return t >= cutoffMs;
                })
                .slice()
                .sort(function(a, b) {
                    return new Date(b.date || 0).getTime() - new Date(a.date || 0).getTime();
                })
                .slice(0, 15);
        }

        // "From The Source" = every official-channel news item + SEBI notices, merged.
        // Official channels mirror the News tab's "official-channels" desk, matched by
        // publisher (fallback source) substring — see NEWS_DESKS['official-channels'].
        var OFFICIAL_CHANNEL_NAMES = ['RBI', 'SEBI', 'ECB', 'ADB', 'FRED', 'PIB', 'MoSPI'];
        function isOfficialChannelArticle(a) {
            var pub = (a && (a.publisher || a.source)) || '';
            for (var i = 0; i < OFFICIAL_CHANNEL_NAMES.length; i++) {
                if (pub.indexOf(OFFICIAL_CHANNEL_NAMES[i]) !== -1) return true;
            }
            return false;
        }

        function sliderHead(label, note, trackId) {
            return '<div class="slider-header"><h2 class="slider-label">' + escapeHtml(label) + '</h2>'
                + (note ? '<span class="slider-note">' + escapeHtml(note) + '</span>' : '')
                + '<div class="slider-nav">' + sliderArrows(trackId) + '</div></div>';
        }

        function getFromSourceItems() {
            var out = [];
            var seen = {};
            function add(title, url, publisher, date) {
                if (!title) return;
                var key = String(url || '').toLowerCase().trim();
                if (key && seen[key]) return;
                if (key) seen[key] = true;
                out.push({ title: title, url: url || '', publisher: publisher || 'Source', date: date || null });
            }
            // All official-channel news items (RBI/SEBI/PIB/MoSPI/ECB/ADB/FRED etc.)
            (NEWS_ARTICLES || []).forEach(function(a) {
                if (!isOfficialChannelArticle(a)) return;
                add(a.title, a.link || a.source_url || '', a.publisher || a.source, a.date);
            });
            // SEBI enforcement / adjudication notices (deduped against the above)
            getSebiNotices().forEach(function(n) {
                add(n.title, n.link || n.source_url || '', n.source, n.date);
            });
            out.sort(function(a, b) {
                return new Date(b.date || 0).getTime() - new Date(a.date || 0).getTime();
            });
            return out.slice(0, 25);
        }

        // From the Source: a list, not a strip — source (RBI / SEBI / PIB) | headline | date | bookmark.
        // The list sits in a fixed-height box (~8 rows) that scrolls on its own, so the page never jumps.
        // One fixed colour per issuer, so RBI always looks like RBI.
        var ISSUERS = [
            { re: /\bRBI\b|Reserve Bank/i, code: 'RBI', c: '#2F5D8A' },
            { re: /\bSEBI\b/i, code: 'SEBI', c: '#7A4E8C' },
            { re: /\bPIB\b|Press Information Bureau/i, code: 'PIB', c: '#B0602A' },
            { re: /MoSPI|Statistics/i, code: 'MoSPI', c: '#3F7F6A' },
            { re: /\bECB\b|European Central/i, code: 'ECB', c: '#2C6E86' },
            { re: /FRED|Federal Reserve|\bFed\b/i, code: 'Fed', c: '#4F5C93' },
            { re: /\bADB\b|Asian Development/i, code: 'ADB', c: '#2F7C79' },
            { re: /\bIMF\b|Monetary Fund/i, code: 'IMF', c: '#365F9C' },
            { re: /World Bank/i, code: 'WB', c: '#26768E' },
            { re: /\bBIS\b|International Settlements/i, code: 'BIS', c: '#86683A' },
            { re: /\bNSE\b|\bBSE\b/i, code: 'Exch', c: '#6B6F3A' },
            { re: /Ministry|Government|Cabinet/i, code: 'GoI', c: '#9A5B3C' }
        ];
        function issuerOf(publisher) {
            var p = String(publisher || '');
            for (var i = 0; i < ISSUERS.length; i++) if (ISSUERS[i].re.test(p)) return ISSUERS[i];
            return { code: (p.split(/[\s—–-]+/)[0] || 'Src').slice(0, 5), c: '#6B645C' };
        }

        function buildFromSourceSlider(items) {
            if (!items || !items.length) return '';
            var counts = [], byCode = {};
            const rows = items.map(function(n) {
                const title = escapeHtml(cleanHomeTitle(n.title));
                const url = sanitizeUrl(n.url || '');
                const pubRaw = n.publisher || 'Source';
                const src = escapeHtml(pubRaw);
                const iss = issuerOf(pubRaw);
                if (!byCode[iss.code]) { byCode[iss.code] = { iss: iss, n: 0 }; counts.push(byCode[iss.code]); }
                byCode[iss.code].n++;
                const dateStr = n.date ? escapeHtml(new Date(n.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })) : '';
                const link = url
                    ? '<a class="source-row-title" href="' + escapeForAttr(url) + '" target="_blank" rel="noopener">' + title + '</a>'
                    : '<span class="source-row-title">' + title + '</span>';
                return '<li class="source-row">'
                    + '<span class="issuer-badge" style="--c:' + iss.c + '" title="' + escapeForAttr(pubRaw) + '">' + escapeHtml(iss.code) + '</span>'
                    + '<span class="source-row-main">' + link + '<span class="source-row-pub">' + src + '</span></span>'
                    + '<span class="source-row-date">' + dateStr + '</span>'
                    + npBookmarkBtn(url, title, src) + '</li>';
            }).join('');
            counts.sort(function(a, b) { return b.n - a.n; });
            const strip = '<div class="issuer-strip">' + counts.map(function(x) {
                return '<span class="issuer-count"><span class="issuer-dot" style="background:' + x.iss.c + '"></span>' + escapeHtml(x.iss.code) + ' <b>' + x.n + '</b></span>';
            }).join('') + '</div>';
            return '<section class="slider-section source-list">'
                + '<div class="slider-header"><h2 class="slider-label">From the Source</h2>'
                + '<span class="slider-note">' + items.length + ' from official channels</span></div>'
                + strip
                + '<ul class="source-rows">' + rows + '</ul>'
                + '</section>';
        }

        // Slow Reads — SLOW_READS_SOURCES in config.py: every post from the last 7 days, plus
        // quieter sources' newest from 30 days. Chronological, NOT AI-ranked. Mirrors From The Source.
        function buildSlowReadsSlider(items) {
            if (!items || !items.length) return '';
            const cards = items.map(function(n) {
                const title = escapeHtml(cleanHomeTitle(n.title));
                const url = sanitizeUrl(n.link || '');
                const src = escapeHtml(n.publisher || n.source || 'Source');
                const dateStr = n.date ? escapeHtml(new Date(n.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })) : '';
                const bk = npBookmarkBtn(url, title, src);
                return '<div class="slider-card slider-slow"><div class="slider-card-body">'
                    + '<div class="slider-card-header"><div><div class="rp-publisher">' + src + '</div>'
                    + '<a class="rp-title" href="' + escapeForAttr(url) + '" target="_blank" rel="noopener">' + title + '</a>'
                    + (dateStr ? '<span class="rp-region">' + dateStr + '</span>' : '')
                    + '</div>' + bk + '</div></div></div>';
            }).join('');
            return '<section class="slider-section">'
                + sliderHead('Slow Reads', items.length + ' this week', 'slow-track')
                + '<div class="slider-track" id="slow-track">' + cards + '</div></section>';
        }

        function buildPpSlider(items) {
            if (!items.length) return '';
            const cards = items.map(p => {
                const title = escapeHtml(cleanHomeTitle(p.title));
                const url = sanitizeUrl(p.link || p.source_url || '');
                const authors = escapeHtml(p.authors || p.publisher || p.source || 'Paper');
                const bk = npBookmarkBtn(url, title, authors);
                return '<div class="slider-card slider-pp">'
                    + '<div class="slider-card-header">'
                    + '<div class="pp-authors">' + authors + '</div>'
                    + bk + '</div>'
                    + '<a class="pp-title" href="' + escapeForAttr(url) + '" target="_blank" rel="noopener">' + title + '</a>'
                    + '</div>';
            }).join('');
            return '<section class="slider-section">'
                + sliderHead('Papers', items.length + ' picked today', 'pp-track')
                + '<div class="slider-track" id="pp-track">' + cards + '</div></section>';
        }

        // ==================== WSW BREAKER BUILDER ====================
        // "Who Said What" quote between sections: hanging rust quote mark, speaker + role underneath.
        function splitSpeaker(who) {
            var s = String(who || '').trim();
            var m = s.match(/^(.*?)\s*\((.*)\)\s*$/);
            if (m) return { name: m[1], role: m[2] };
            var comma = s.indexOf(',');
            if (comma > 0) return { name: s.slice(0, comma).trim(), role: s.slice(comma + 1).trim() };
            return { name: s, role: '' };
        }

        function stripWrappingQuotes(text) {
            var t = String(text || '').trim();
            // Only drop marks that wrap the whole quote — an inner "phrase" at the start must survive.
            if (/^["“].*["”]$/.test(t)) t = t.slice(1, -1).trim();
            return t;
        }

        function buildWswBreaker(cluster) {
            if (!cluster) return '';
            const quote = escapeHtml(stripWrappingQuotes(cluster.quote_snippet || cluster.headline || ''));
            if (!quote) return '';
            const who = splitSpeaker(cluster.quote_speaker || cluster.source || '');
            const url = sanitizeUrl(cluster.source_url_primary || cluster.url || '');
            const bk = npBookmarkBtn(url, quote.substring(0, 80), who.name);
            const quoteHtml = url
                ? '<a href="' + escapeForAttr(url) + '" target="_blank" rel="noopener">' + quote + '</a>'
                : quote;
            return '<figure class="wsw-breaker">'
                + '<span class="wsw-qm" aria-hidden="true">“</span>'
                + '<div class="wsw-body"><blockquote class="wsw-text">' + quoteHtml + '</blockquote>'
                + '<figcaption class="wsw-cite"><b>' + escapeHtml(who.name) + '</b>'
                + (who.role ? '<span class="wsw-role">' + escapeHtml(who.role) + '</span>' : '')
                + '</figcaption></div>' + bk + '</figure>';
        }

        // ==================== SLIDER NAVIGATION ====================
        function initSliders() {
            document.querySelectorAll('.slider-arrow').forEach(btn => {
                btn.addEventListener('click', () => {
                    const trackId = btn.dataset.track;
                    const track = document.getElementById(trackId);
                    if (!track) return;
                    // Scroll by one card width (+gap) so wider cards (e.g. Big Stories) page cleanly.
                    const first = track.querySelector(':scope > *');
                    const step = first ? Math.round(first.getBoundingClientRect().width + 16) : 320;
                    const dir = btn.classList.contains('slider-prev') ? -step : step;
                    track.scrollBy({ left: dir, behavior: 'smooth' });
                });
            });
        }

        // ==================== CLUSTER RENDERING ====================
        var SOURCE_TYPE_DOTS = {
            news: '#4A8F7A', telegram: '#5E6A96', reports: '#9A8345',
            twitter: '#4A8A9A', youtube: '#A86565'
        };
        // Big Stories (Oct 2026): a front page. The lead shows a short Coverage list; every
        // other story shows no sources until asked. Sources open in a side drawer (a bottom
        // sheet on phones), so the page never moves. Each story carries a signal row:
        // dots for how many models picked it, a colour strip of its source mix, and a count.
        var BIG_STORY_COVERAGE = 4;
        var BS_TYPE_ORDER = ['news', 'telegram', 'reports', 'youtube', 'twitter'];
        var BS_TYPE_LABELS = { news: 'News', telegram: 'Telegram', reports: 'Reports', youtube: 'Videos', twitter: 'X' };
        var BS_GROUP_LABELS = { news: 'News', telegram: 'Telegram notes', reports: 'Research reports', youtube: 'Videos', twitter: 'Posts on X' };
        var BS_ARROW = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.7"/></svg>';
        var BS_CLOSE = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 3.5l9 9M12.5 3.5l-9 9" fill="none" stroke="currentColor" stroke-width="1.7"/></svg>';
        var bigStoriesShown = [];
        var storyDrawerReturnFocus = null;

        function getClusterArticles(cluster) {
            // Flatten lead + related into one list of articles
            var articles = [];
            function push(a) {
                articles.push({
                    title: a.title || '',
                    url: a.url || '',
                    source: a.source || '',
                    source_type: a.source_type || 'news',
                    source_tier: a.source_tier || '',
                    angle: a.angle || ''
                });
            }
            if (cluster.lead) push(cluster.lead);
            (cluster.related || []).forEach(push);
            return articles;
        }

        // One plain line under the story label: the AI's story_summary, else the lead's why_it_matters.
        function clusterSummary(cluster) {
            var s = String(cluster.story_summary || '').trim();
            if (!s && cluster.lead) s = String(cluster.lead.why_it_matters || '').trim();
            return s;
        }

        function bsType(a) {
            return BS_GROUP_LABELS[a.source_type] ? a.source_type : 'news';
        }

        // Models that ran this time vs. how many are configured. A failed model still has
        // an entry in ai_rankings.json (status "error"), so the gap is visible here.
        function bigStoryModels() {
            var providers = (aiRankings && aiRankings.providers) ? Object.values(aiRankings.providers) : [];
            var ran = providers.filter(function(p) {
                return p && (p.status === 'ok' || p.status === 'partial') && Array.isArray(p.clusters) && p.clusters.length;
            }).length;
            return { ran: ran, configured: providers.length };
        }

        // "3 of 4 models" dots. With one model running, agreement means nothing, so they go.
        function agreementHtml(providerCount) {
            var ran = bigStoryModels().ran;
            if (ran < 2) return '';
            var picked = Math.min(providerCount || 1, ran);
            var pips = '';
            for (var i = 0; i < ran; i++) pips += '<i' + (i < picked ? ' class="on"' : '') + '></i>';
            return '<span><span class="bs-pips" aria-hidden="true">' + pips + '</span>'
                + '<span><b>' + picked + '</b> of ' + ran + ' models</span></span>';
        }

        // Signal row: agreement dots + source-mix strip + count.
        function bsSignals(cluster, articles, extra) {
            var html = '<span class="bs-sigs">' + agreementHtml(cluster._providerCount);
            var mix = articles.slice()
                .sort(function(a, b) { return BS_TYPE_ORDER.indexOf(bsType(a)) - BS_TYPE_ORDER.indexOf(bsType(b)); })
                .slice(0, 12)
                .map(function(a) { return '<i style="background:' + SOURCE_TYPE_DOTS[bsType(a)] + '"></i>'; }).join('');
            html += '<span><span class="bs-mix" aria-hidden="true">' + mix + '</span><span><b>' + articles.length + '</b> sources</span></span>';
            return html + (extra || '') + '</span>';
        }

        function bsKick(cluster, articles, idx) {
            return '<div class="bs-kick"><span class="bs-num">' + (idx + 1) + '</span>' + bsSignals(cluster, articles) + '</div>';
        }

        function bsLegend() {
            var models = bigStoryModels();
            return '<span class="bs-legend">'
                + BS_TYPE_ORDER.map(function(t) { return '<span><span class="bs-dot" style="background:' + SOURCE_TYPE_DOTS[t] + '"></span>' + BS_TYPE_LABELS[t] + '</span>'; }).join('')
                + (models.ran > 1 ? '<span><span class="bs-pips" aria-hidden="true"><i class="on"></i><i class="on"></i><i></i></span>models that picked it</span>' : '')
                + '</span>';
        }

        function bsSource(a) {
            var aTitle = escapeHtml(cleanHomeTitle(a.title));
            var aUrl = sanitizeUrl(a.url || '');
            var angle = tidyAngle(a.angle, a.source);
            var link = aUrl
                ? '<a class="bs-src-t" href="' + escapeForAttr(aUrl) + '" target="_blank" rel="noopener">' + aTitle + '</a>'
                : '<span class="bs-src-t">' + aTitle + '</span>';
            return '<li class="bs-src"><div class="bs-src-body">' + link
                + '<div class="bs-src-m"><span class="bs-dot" style="background:' + SOURCE_TYPE_DOTS[bsType(a)] + '"></span>'
                + '<b>' + escapeHtml(homeSourceName(a.source, a.source_type)) + '</b>'
                + (a.source_tier === 'official' ? '<span class="official-badge">Primary source</span>' : '')
                + (angle ? '<span>· ' + escapeHtml(angle) + '</span>' : '')
                + '</div></div>'
                + (aUrl ? npBookmarkBtn(aUrl, aTitle, a.source || 'Home') : '')
                + '</li>';
        }

        function bsTitle(cluster, idx, tag) {
            return '<' + tag + ' class="bs-title"><button class="bs-tb" type="button" onclick="openStoryDrawer(' + idx + ')">'
                + escapeHtml(cluster.story_label || '') + '</button></' + tag + '>';
        }

        function bsShow(idx, text) {
            return '<button class="bs-see" type="button" onclick="openStoryDrawer(' + idx + ')">' + text + ' ' + BS_ARROW + '</button>';
        }

        function renderBigStories(clusters) {
            if (!clusters || !clusters.length) return '';
            bigStoriesShown = clusters;
            var lead = clusters[0], two = clusters.slice(1, 3), rest = clusters.slice(3);
            var leadArts = getClusterArticles(lead);
            var leadSummary = clusterSummary(lead);

            var models = bigStoryModels();
            var total = aiRankings && aiRankings.article_count ? Number(aiRankings.article_count) : 0;
            var when = aiRankings && aiRankings.generated_at ? new Date(aiRankings.generated_at) : null;
            var whenStr = when && !isNaN(when) ? when.toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' }) : '';
            var who = models.ran === 1 ? 'one Gemini model' : models.ran + ' Gemini models';
            var caption = 'Grouped and ranked by ' + who
                + (total ? ' from ' + total.toLocaleString('en-IN') + ' stories' : '')
                + (whenStr ? ' · ' + whenStr : '')
                + (models.configured > models.ran ? ' · ' + (models.configured - models.ran) + ' of ' + models.configured + ' models didn’t run this time' : '');

            var html = '<section class="big-stories-section">'
                + '<div class="section-divider"><span class="section-label">The Big Stories</span>' + bsLegend() + '</div>'
                + '<article class="bs-lead"><div class="bs-lead-main">' + bsKick(lead, leadArts, 0) + bsTitle(lead, 0, 'h2')
                + (leadSummary ? '<p class="bs-sum">' + escapeHtml(leadSummary) + '</p>' : '') + '</div>'
                + '<div class="bs-cover"><h3>Coverage</h3><ul class="bs-srcs">'
                + leadArts.slice(0, BIG_STORY_COVERAGE).map(bsSource).join('') + '</ul>'
                + bsShow(0, leadArts.length > BIG_STORY_COVERAGE ? 'See all ' + leadArts.length + ' sources' : 'Open in the panel')
                + '</div></article>';

            if (two.length) {
                html += '<div class="bs-two">' + two.map(function(c, i) {
                    var arts = getClusterArticles(c);
                    var sum = clusterSummary(c);
                    return '<article>' + bsKick(c, arts, i + 1) + bsTitle(c, i + 1, 'h3')
                        + (sum ? '<p class="bs-sum bs-clamp3">' + escapeHtml(sum) + '</p>' : '')
                        + bsShow(i + 1, 'Show sources') + '</article>';
                }).join('') + '</div>';
            }

            if (rest.length) {
                html += '<div class="bs-briefs"><h3 class="bs-briefs-head">Also developing<span>' + rest.length + ' more ' + (rest.length === 1 ? 'story' : 'stories') + '</span></h3><ol class="bs-list">'
                    + rest.map(function(c, i) {
                        var idx = i + 3;
                        var arts = getClusterArticles(c);
                        var sum = clusterSummary(c);
                        return '<li><button class="bs-row" type="button" onclick="openStoryDrawer(' + idx + ')">'
                            + '<span class="bs-num">' + (idx + 1) + '</span><span class="bs-row-body">'
                            + '<span class="bs-row-title">' + escapeHtml(c.story_label || '') + '</span>'
                            + (sum ? '<span class="bs-row-sum">' + escapeHtml(sum) + '</span>' : '')
                            + bsSignals(c, arts, '<span class="bs-cta">Show sources ' + BS_ARROW + '</span>')
                            + '</span></button></li>';
                    }).join('') + '</ol></div>';
            }

            return html + '<p class="cluster-caption">' + escapeHtml(caption) + '</p></section>';
        }

        function openStoryDrawer(idx) {
            var cluster = bigStoriesShown[idx];
            if (!cluster) return;
            var returnTo = document.activeElement;
            closeStoryDrawer(true);
            storyDrawerReturnFocus = returnTo;
            var arts = getClusterArticles(cluster);
            var sum = clusterSummary(cluster);
            var groups = BS_TYPE_ORDER.map(function(t) {
                var g = arts.filter(function(a) { return bsType(a) === t; });
                if (!g.length) return '';
                return '<section class="bs-group"><h4><span class="bs-dot" style="background:' + SOURCE_TYPE_DOTS[t] + '"></span>'
                    + BS_GROUP_LABELS[t] + ' <span>' + g.length + '</span></h4><ul class="bs-srcs">' + g.map(bsSource).join('') + '</ul></section>';
            }).join('');
            var wrap = document.createElement('div');
            wrap.id = 'story-drawer';
            wrap.innerHTML = '<div class="bs-scrim" onclick="closeStoryDrawer()"></div>'
                + '<aside class="bs-drawer" role="dialog" aria-modal="true" aria-labelledby="bs-drawer-title">'
                + '<div class="bs-dr-head"><button class="bs-x" type="button" onclick="closeStoryDrawer()" aria-label="Close">' + BS_CLOSE + '</button>'
                + bsKick(cluster, arts, idx)
                + '<h2 class="bs-title" id="bs-drawer-title">' + escapeHtml(cluster.story_label || '') + '</h2>'
                + (sum ? '<p class="bs-sum">' + escapeHtml(sum) + '</p>' : '') + '</div>'
                + '<div class="bs-dr-body">' + groups + '</div></aside>';
            document.body.appendChild(wrap);
            lockBodyScroll();
            wrap.querySelector('.bs-x').focus({ preventScroll: true });
        }

        function closeStoryDrawer(silent) {
            var el = document.getElementById('story-drawer');
            if (!el) return;
            el.remove();
            unlockBodyScroll();
            if (!silent && storyDrawerReturnFocus && document.contains(storyDrawerReturnFocus)) {
                storyDrawerReturnFocus.focus({ preventScroll: true });
            }
        }

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && document.getElementById('story-drawer')) closeStoryDrawer();
        });

        function renderSectionLabel(text, note) {
            return '<div class="section-divider"><span class="section-label">' + escapeHtml(text) + '</span>'
                + (note ? '<span class="section-note">' + escapeHtml(note) + '</span>' : '') + '</div>';
        }


        // ==================== RENDER HOME TAB (Newspaper — AI-curated) ====================
        function renderHomeTab() {
            const container = document.getElementById('home-newspaper');
            if (!container) return;

            const result = getHomeAiItems();
            if (result.isEmpty) {
                container.innerHTML = '<div class="home-ai-empty">'
                    + '<h3>AI-curated picks are being generated</h3>'
                    + '<p>Check individual tabs for the latest content.</p></div>';
                var homeLoading = document.getElementById('home-loading');
                if (homeLoading) homeLoading.remove();
                if (window.__reveal) window.__reveal();
                return;
            }

            var feed = result.feed;
            var clusters = result.clusters || [];

            // Split feed across 4 pattern sections
            const s1 = feed.slice(0, 15);
            const s3 = feed.slice(15, 27);
            const s5 = feed.slice(27, 37);
            const s7 = feed.slice(37);

            // Get WSW breakers
            const wswClusters = getWswBreakers();
            const breakers = [];
            for (let i = 0; i < 6; i++) {
                breakers.push(wswClusters[i] ? buildWswBreaker(wswClusters[i]) : '');
            }

            // Build the full newspaper layout with AI-curated sliders.
            // Order: Big Stories → quote → Reports → (feed label) → news → quote → Slow Reads →
            // news → quote → Watch → news → quote → From the Source → Voices → quote → news.
            // Voices sits directly under From the Source (user request, Oct 2026).
            const parts = [];

            // Big Stories at the very top
            if (clusters.length > 0) {
                parts.push(renderBigStories(clusters));
            }

            // Research Reports leads the sliders, then the feed label
            parts.push(
                breakers[0],
                buildRpSlider(result.reports)
            );
            if (clusters.length > 0 || result.reports.length > 0) {
                parts.push(renderSectionLabel('From the Feed', 'news and Telegram, ranked by AI'));
            }

            parts.push(
                renderPatternA(s1),
                breakers[1],
                buildSlowReadsSlider(SLOW_READS),
                renderFeedRows(s3),
                breakers[2],
                buildYtSlider(result.youtube),
                renderFeedRows(s5),
                breakers[3],
                buildFromSourceSlider(getFromSourceItems()),
                buildTwSlider(result.twitter),
                breakers[4],
                renderFeedBucket(s7)
            );
            const html = parts.filter(Boolean).join('');

            container.innerHTML = html || '<div class="home-no-results">No content available yet.</div>';
            var homeLoading = document.getElementById('home-loading');
            if (homeLoading) homeLoading.remove();

            // Initialize slider navigation
            initSliders();

            // Reveal page — all content is now rendered
            if (window.__reveal) window.__reveal();
        }

        function getWswBreakers() {
            if (!wswData || !wswData.providers) return [];
            // Pick the provider with the most clusters for homepage breakers
            var best = null;
            Object.values(wswData.providers).forEach(function(p) {
                if (!p || p.status !== 'ok' || !Array.isArray(p.clusters)) return;
                if (!best || p.clusters.length > best.clusters.length) best = p;
            });
            if (!best) return [];
            return best.clusters.slice(0, 6);
        }

        function filterHomeCards() {
            const query = (document.getElementById('search-input').value || '').toLowerCase().trim();
            const container = document.getElementById('home-newspaper');
            const empty = document.getElementById('home-no-results');
            if (!container) return;

            if (!query) {
                container.querySelectorAll('.feed-section, .slider-section, .wsw-breaker, .big-stories-section, .section-divider').forEach(el => {
                    el.classList.remove('hidden');
                });
                if (empty) empty.classList.add('hidden');
                return;
            }

            let visible = 0;
            container.querySelectorAll('.feed-section, .slider-section, .wsw-breaker, .big-stories-section').forEach(el => {
                const match = el.textContent.toLowerCase().includes(query);
                el.classList.toggle('hidden', !match);
                if (match) visible++;
            });
            // Hide section labels when their section is hidden
            container.querySelectorAll('.section-divider').forEach(el => {
                const next = el.nextElementSibling;
                if (next && next.classList.contains('hidden')) {
                    el.classList.add('hidden');
                } else {
                    el.classList.remove('hidden');
                }
            });
            if (empty) empty.classList.toggle('hidden', visible > 0);
        }

        function resetNewsTabState() {
            selectedPublishers.clear();
            syncCheckboxes();
            syncPresetButtons();
            syncDeskButtons();
            updatePublisherSummary();
            if (inFocusOnly) {
                inFocusOnly = false;
                const inFocusBtn = document.getElementById('in-focus-toggle');
                if (inFocusBtn) inFocusBtn.classList.remove('active');
            }
            currentPage = 1;
            setPageToToday();
            applyPagination();
        }

        function resetReportsTabState() {
            reportsViewMode = 'all';
            reportsNoTargetFilterActive = false;
            selectedTgChannels.clear();
            reportsPage = 1;
            const allBtn = document.getElementById('reports-view-all');
            const pdfBtn = document.getElementById('reports-view-pdf');
            const noPdfBtn = document.getElementById('reports-view-nopdf');
            const noTargetBtn = document.getElementById('reports-notarget-filter');
            if (allBtn) allBtn.classList.add('active');
            if (pdfBtn) pdfBtn.classList.remove('active');
            if (noPdfBtn) noPdfBtn.classList.remove('active');
            if (noTargetBtn) noTargetBtn.classList.remove('active');
            updateTgChannelSummary();
            syncTgCheckboxes();
        }

        function resetResearchTabState() {
            selectedResearchPublishers.clear();
            researchRegionFilter = 'all';
            researchPage = 1;
            syncResearchCheckboxes();
            syncResearchPublisherSummary();
            const allBtn = document.getElementById('research-region-all');
            const indianBtn = document.getElementById('research-region-indian');
            const intlBtn = document.getElementById('research-region-international');
            if (allBtn) allBtn.classList.add('active');
            if (indianBtn) indianBtn.classList.remove('active');
            if (intlBtn) intlBtn.classList.remove('active');
        }

        function resetPapersTabState() {
            papersPage = 1;
            if (papersRendered || paperSessionPool.length > 0) {
                reshufflePaperSession();
            }
        }

        function resetYoutubeTabState() {
            selectedYoutubePublishers.clear();
            youtubeBucketFilter = 'all';
            youtubePage = 1;
            syncYoutubeCheckboxes();
            syncYoutubeBucketButtons();
            updateYoutubePublisherSummary();
        }

        function resetTwitterTabState() {
            selectedTwitterPublishers.clear();
            twitterLane = 'high-signal';
            safeStorage.set('financeradar_twitter_lane', 'high-signal');
            twitterPage = 1;
            syncTwitterCheckboxes();
            syncTwitterLaneButtons();
            syncTwitterPresetButtons();
            updateTwitterPublisherSummary();
            updateTwitterLaneSummary();
        }

        function formatReportDate(isoStr) {
            if (!isoStr) return '';
            const date = new Date(isoStr);
            const now = new Date();
            const diffMs = now - date;
            const diffMin = Math.floor(diffMs / 60000);
            const diffHr = Math.floor(diffMs / 3600000);
            const diffDay = Math.floor(diffMs / 86400000);
            if (diffMin < 1) return 'Just now';
            if (diffMin < 60) return diffMin + 'm ago';
            if (diffHr < 24) return diffHr + 'h ago';
            if (diffDay === 1) return 'Yesterday';
            if (diffDay < 7) return diffDay + 'd ago';
            return date.toLocaleDateString();
        }

        // Day header: bold label, plus a grey date for Today / Yesterday ("Today Fri 16 Oct").
        function dateHeaderHtml(label, iso) {
            var sub = '';
            if ((label === 'Today' || label === 'Yesterday') && iso) {
                var d = new Date(iso);
                if (!isNaN(d)) sub = d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }).replace(',', '');
            }
            return '<h2 class="date-header">' + escapeHtml(label)
                + (sub ? '<span class="date-header-sub">' + escapeHtml(sub) + '</span>' : '') + '</h2>';
        }

        // Telegram posts: keep the author's structure. Real bullet lines stay bullets, short label
        // lines ("Key Highlights") become small sub-heads, **bold** lines stay bold.
        // A label line: short, no sentence punctuation or numbers, and every longer word capitalised
        // ("Key Highlights", "IPO HIGHLIGHTS") — not a short sentence like "Here is the response".
        function isTelegramSubhead(line) {
            var t = line.replace(/^[^A-Za-z]+/, '');
            if (!t || t.length > 40 || /[.:!?,]$/.test(t) || /\d/.test(t)) return false;
            return t.split(/\s+/).every(function(w) { return w.length < 4 || /^[A-Z]/.test(w); });
        }
        var TG_BULLET = /^\s*([\u2022\-\u2013*]|\d+[.)])\s+/;
        function telegramBodyHtml(lines) {
            var html = '';
            var inList = false;
            lines.forEach(function(raw) {
                var bold = /^\*\*.*\*\*$/.test(raw);
                var plain = raw.replace(/\*\*/g, '').trim();
                if (!plain) return;
                if (TG_BULLET.test(plain)) {
                    if (!inList) { html += '<ul class="tg-bullets">'; inList = true; }
                    html += '<li>' + escapeHtml(deshoutTitle(plain.replace(TG_BULLET, ''))) + '</li>';
                    return;
                }
                if (inList) { html += '</ul>'; inList = false; }
                html += '<p class="' + (isTelegramSubhead(plain) ? 'tg-sub' : (bold ? 'tg-line tg-strong' : 'tg-line'))
                    + '">' + escapeHtml(deshoutTitle(plain)) + '</p>';
            });
            if (inList) html += '</ul>';
            return html;
        }

        function formatReportDateHeader(isoStr) {
            if (!isoStr) return 'Unknown Date';
            const date = new Date(isoStr);
            const now = new Date();
            const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            const articleDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
            const diffDays = Math.floor((today - articleDay) / 86400000);
            if (diffDays === 0) return 'Today';
            if (diffDays === 1) return 'Yesterday';
            return date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
        }

        function renderNewsFromJSON() {
            if (!NEWS_ARTICLES) return;
            var container = document.getElementById('news-list');
            if (!container) return;
            var html = '';
            var lastDateLabel = '';
            var now = new Date();
            var todayStr = now.toISOString().slice(0, 10);
            var yest = new Date(now);
            yest.setDate(yest.getDate() - 1);
            var yesterdayStr = yest.toISOString().slice(0, 10);

            NEWS_ARTICLES.forEach(function(a) {
                var dateStr = a.date ? a.date.slice(0, 10) : '';
                var dateLabel = '';
                if (dateStr === todayStr) dateLabel = 'Today';
                else if (dateStr === yesterdayStr) dateLabel = 'Yesterday';
                else if (a.date) {
                    var d = new Date(a.date);
                    var days = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
                    var months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
                    dateLabel = days[d.getDay()] + ', ' + months[d.getMonth()] + ' ' + String(d.getDate()).padStart(2, '0');
                }
                if (dateLabel && dateLabel !== lastDateLabel) {
                    html += dateHeaderHtml(dateLabel, a.date) + '\n';
                    lastDateLabel = dateLabel;
                }

                var sourceBadge = '';
                var alsoCovered = '';
                if (a.in_focus && a.related_sources && a.related_sources.length) {
                    var total = a.related_sources.length + 1;
                    sourceBadge = '<span class="source-badge">' + total + ' sources</span>';
                    var links = a.related_sources.map(function(rs) {
                        var name = escapeHtml(rs.name);
                        var display = name.length > 25 ? name.slice(0, 25) + '...' : name;
                        return '<a href="' + escapeForAttr(rs.link) + '" target="_blank" rel="noopener" title="' + name + '">' + display + '</a>';
                    });
                    alsoCovered = '<div class="also-covered">Also covered by: ' + links.join(', ') + '</div>';
                }

                var sourceDisplay = a.source.length > 35 ? escapeHtml(a.source.slice(0, 35)) + '...' : escapeHtml(a.source);
                var hhmm = '';
                if (a.date) {
                    var when = new Date(a.date);
                    if (!isNaN(when)) hhmm = when.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
                }
                var focusDot = a.in_focus ? '<span class="focus-dot" title="Covered by several sources"></span>' : '';

                html += '<article class="article" data-source="' + escapeForAttr(a.source.toLowerCase()) + '" data-date="' + escapeForAttr(dateStr) + '" data-url="' + escapeForAttr(a.link) + '" data-title="' + escapeForAttr(a.title) + '" data-in-focus="' + (a.in_focus ? 'true' : 'false') + '" data-publisher="' + escapeForAttr(a.publisher) + '">'
                    + '<span class="article-time">' + escapeHtml(hhmm) + '</span>'
                    + '<h3 class="article-title">' + focusDot + '<a href="' + escapeForAttr(a.link) + '" target="_blank" rel="noopener">' + escapeHtml(deshoutTitle(a.title)) + '</a>' + sourceBadge + '</h3>'
                    + '<div class="article-meta">'
                    + '<a href="' + escapeForAttr(a.source_url) + '" target="_blank" class="source-tag" title="' + escapeForAttr(a.source) + '">' + sourceDisplay + '</a>'
                    + '<button class="bookmark-btn" onclick="toggleBookmark(this)" aria-label="Bookmark article" title="Bookmark">'
                    + '<svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>'
                    + '</button>'
                    + '</div>'
                    + alsoCovered
                    + '</article>\n';
            });

            container.innerHTML = html;
            syncBookmarkState();
            var newsLoading = document.getElementById('news-loading');
            if (newsLoading) newsLoading.remove();
        }

        function renderMainReports() {
            if (!reportsRendered) {
                initTgChannelDropdown();
                reportsRendered = true;
            }
            filteredReports = [...TELEGRAM_REPORTS];
            reportsPage = 1;
            applyReportsPagination();
            var warnEl = document.getElementById('reports-warning');
            if (warnEl && TELEGRAM_WARNINGS && TELEGRAM_WARNINGS.length > 0) {
                warnEl.innerHTML = '<strong>⚠ Fetch issue:</strong> ' + TELEGRAM_WARNINGS.map(w => escapeHtml(w)).join(' · ') + ' — some reports may be missing.';
                warnEl.style.display = 'block';
            }
        }
        function initTgChannelDropdown() {
            const channels = [...new Set(TELEGRAM_REPORTS.map(r => r.channel || '').filter(Boolean))].sort();
            const list = document.getElementById('tg-dropdown-list');
            if (!list || channels.length === 0) return;
            list.innerHTML = '';
            channels.forEach(ch => {
                const item = document.createElement('div');
                item.className = 'dropdown-item';
                item.dataset.publisher = ch;
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.id = 'tgch-' + ch.replace(/\s+/g, '-');
                cb.dataset.publisher = ch;
                cb.addEventListener('change', () => onTgChannelChange(ch, cb.checked));
                const lbl = document.createElement('label');
                lbl.htmlFor = cb.id;
                lbl.textContent = ch;
                item.appendChild(cb);
                item.appendChild(lbl);
                item.addEventListener('click', (e) => {
                    if (e.target !== cb) { cb.checked = !cb.checked; onTgChannelChange(ch, cb.checked); }
                });
                list.appendChild(item);
            });
        }
        function toggleTgDropdown() {
            const dd = document.getElementById('tg-channel-dropdown');
            dd.classList.toggle('open');
            if (dd.classList.contains('open')) {
                document.getElementById('tg-dropdown-search').focus();
            }
        }
        function filterTgChannelList() { filterDropdownList('tg-dropdown-search', 'tg-dropdown-list'); }
        function selectAllTgChannels() {
            selectedTgChannels.clear();
            syncTgCheckboxes();
            updateTgChannelSummary();
            filterReports();
        }
        function clearAllTgChannels() {
            selectedTgChannels.clear();
            syncTgCheckboxes();
            updateTgChannelSummary();
            filterReports();
        }
        function onTgChannelChange(ch, checked) {
            if (checked) { selectedTgChannels.add(ch); } else { selectedTgChannels.delete(ch); }
            updateTgChannelSummary();
            filterReports();
        }
        function syncTgCheckboxes() {
            document.querySelectorAll('#tg-dropdown-list input[type="checkbox"]').forEach(cb => {
                cb.checked = selectedTgChannels.has(cb.dataset.publisher);
            });
        }
        function updateTgChannelSummary() {
            const el = document.getElementById('tg-channel-summary');
            if (!el) return;
            const n = selectedTgChannels.size;
            if (n === 0) { el.textContent = 'All channels'; }
            else if (n === 1) { el.textContent = [...selectedTgChannels][0]; }
            else { el.textContent = n + ' channels'; }
        }
        function closeTgDropdown() { closeDropdownById('tg-channel-dropdown', 'tg-dropdown-search', 'tg-dropdown-list'); }

        function parseReportImageList(raw) {
            if (!raw) return [];
            try {
                const parsed = JSON.parse(raw);
                if (!Array.isArray(parsed)) return [];
                return parsed
                    .map(url => sanitizeUrl(String(url || '')))
                    .filter(Boolean);
            } catch (e) {
                return [];
            }
        }

        function isReportImageLightboxOpen() {
            return !!(reportImageLightboxEl && reportImageLightboxEl.classList.contains('open'));
        }

        function ensureReportImageLightbox() {
            if (reportImageLightboxEl) return;

            const root = document.createElement('div');
            root.id = 'report-image-lightbox';
            root.className = 'report-image-lightbox';
            root.setAttribute('aria-hidden', 'true');
            root.innerHTML = `
                <div class="report-image-lightbox-backdrop"></div>
                <div class="report-image-lightbox-dialog" role="dialog" aria-modal="true" aria-label="Telegram image viewer">
                    <button type="button" class="report-image-lightbox-close" aria-label="Close image viewer">×</button>
                    <button type="button" class="report-image-lightbox-nav report-image-lightbox-prev" aria-label="Previous image">‹</button>
                    <img class="report-image-lightbox-img" alt="Report image" loading="eager">
                    <div class="report-image-lightbox-error">Image unavailable</div>
                    <button type="button" class="report-image-lightbox-nav report-image-lightbox-next" aria-label="Next image">›</button>
                    <div class="report-image-lightbox-counter">1 / 1</div>
                </div>
            `;

            document.body.appendChild(root);
            reportImageLightboxEl = root;
            reportImageLightboxImgEl = root.querySelector('.report-image-lightbox-img');
            reportImageLightboxErrorEl = root.querySelector('.report-image-lightbox-error');
            reportImageLightboxCounterEl = root.querySelector('.report-image-lightbox-counter');
            reportImageLightboxPrevEl = root.querySelector('.report-image-lightbox-prev');
            reportImageLightboxNextEl = root.querySelector('.report-image-lightbox-next');

            const closeBtn = root.querySelector('.report-image-lightbox-close');
            closeBtn.addEventListener('click', closeReportImageLightbox);
            reportImageLightboxPrevEl.addEventListener('click', showPrevReportImage);
            reportImageLightboxNextEl.addEventListener('click', showNextReportImage);

            root.addEventListener('click', (e) => {
                if (
                    e.target === root ||
                    e.target.classList.contains('report-image-lightbox-backdrop')
                ) {
                    closeReportImageLightbox();
                }
            });

            reportImageLightboxImgEl.addEventListener('load', () => {
                reportImageLightboxImgEl.style.display = 'block';
                if (reportImageLightboxErrorEl) reportImageLightboxErrorEl.style.display = 'none';
            });
            reportImageLightboxImgEl.addEventListener('error', () => {
                reportImageLightboxImgEl.style.display = 'none';
                if (reportImageLightboxErrorEl) reportImageLightboxErrorEl.style.display = 'flex';
            });
        }

        function renderReportImageLightboxFrame() {
            if (!reportImageLightboxImgEl) return;
            if (!Array.isArray(reportImageItems) || reportImageItems.length === 0) {
                closeReportImageLightbox();
                return;
            }

            reportImageIndex = Math.max(0, Math.min(reportImageIndex, reportImageItems.length - 1));
            const current = reportImageItems[reportImageIndex] || '';

            if (reportImageLightboxCounterEl) {
                reportImageLightboxCounterEl.textContent = (reportImageIndex + 1) + ' / ' + reportImageItems.length;
            }
            if (reportImageLightboxPrevEl) {
                reportImageLightboxPrevEl.disabled = reportImageIndex === 0;
            }
            if (reportImageLightboxNextEl) {
                reportImageLightboxNextEl.disabled = reportImageIndex >= reportImageItems.length - 1;
            }
            if (reportImageLightboxErrorEl) reportImageLightboxErrorEl.style.display = 'none';
            reportImageLightboxImgEl.style.display = 'block';
            reportImageLightboxImgEl.src = current;
            reportImageLightboxImgEl.alt = 'Report image ' + (reportImageIndex + 1) + ' of ' + reportImageItems.length;
        }

        function openReportImageLightbox(images, startIndex, triggerEl) {
            const list = Array.isArray(images)
                ? images.map(url => sanitizeUrl(String(url || ''))).filter(Boolean)
                : [];
            if (list.length === 0) return;

            ensureReportImageLightbox();
            reportImageItems = list;
            reportImageIndex = Number.isInteger(startIndex) ? startIndex : 0;
            reportImageLastTrigger = triggerEl || document.activeElement;

            reportImageLightboxEl.classList.add('open');
            reportImageLightboxEl.setAttribute('aria-hidden', 'false');
            lockBodyScroll();
            renderReportImageLightboxFrame();
        }

        function closeReportImageLightbox() {
            if (!isReportImageLightboxOpen()) return;
            reportImageLightboxEl.classList.remove('open');
            reportImageLightboxEl.setAttribute('aria-hidden', 'true');
            if (reportImageLightboxImgEl) {
                reportImageLightboxImgEl.removeAttribute('src');
            }
            reportImageItems = [];
            reportImageIndex = 0;
            unlockBodyScroll();
            if (reportImageLastTrigger && typeof reportImageLastTrigger.focus === 'function') {
                reportImageLastTrigger.focus();
            }
            reportImageLastTrigger = null;
        }

        function openReportImageLightboxFromButton(buttonEl) {
            if (!buttonEl) return;
            const imagesRaw = buttonEl.getAttribute('data-report-images') || '[]';
            const images = parseReportImageList(imagesRaw);
            const startRaw = parseInt(buttonEl.getAttribute('data-start-index') || '0', 10);
            const startIndex = Number.isFinite(startRaw) ? startRaw : 0;
            openReportImageLightbox(images, startIndex, buttonEl);
        }

        function showPrevReportImage() {
            if (!isReportImageLightboxOpen()) return;
            if (reportImageIndex <= 0) return;
            reportImageIndex -= 1;
            renderReportImageLightboxFrame();
        }

        function showNextReportImage() {
            if (!isReportImageLightboxOpen()) return;
            if (reportImageIndex >= reportImageItems.length - 1) return;
            reportImageIndex += 1;
            renderReportImageLightboxFrame();
        }

        document.addEventListener('keydown', (e) => {
            if (!isReportImageLightboxOpen()) return;

            if (e.key === 'Escape') {
                e.preventDefault();
                e.stopImmediatePropagation();
                closeReportImageLightbox();
                return;
            }
            if (e.key === 'ArrowLeft') {
                e.preventDefault();
                e.stopImmediatePropagation();
                showPrevReportImage();
                return;
            }
            if (e.key === 'ArrowRight') {
                e.preventDefault();
                e.stopImmediatePropagation();
                showNextReportImage();
            }
        }, true);

        function setReportsView(mode) {
            reportsViewMode = mode;
            document.getElementById('reports-view-all').classList.toggle('active', mode === 'all');
            document.getElementById('reports-view-pdf').classList.toggle('active', mode === 'pdf');
            document.getElementById('reports-view-nopdf').classList.toggle('active', mode === 'nopdf');
            filterReports();
        }

        function toggleNoTargetFilter() {
            reportsNoTargetFilterActive = !reportsNoTargetFilterActive;
            document.getElementById('reports-notarget-filter').classList.toggle('active', reportsNoTargetFilterActive);
            filterReports();
        }

        function reportHasStockTarget(r) {
            const RE = /upside|downside|TP\s+\d|target\s+price/i;
            if (RE.test(r.text || '')) return true;
            const docs = (r.documents && r.documents.length > 0) ? r.documents
                : (r.document && r.document.title) ? [r.document] : [];
            return docs.some(d => RE.test(d.title || ''));
        }

        function reportHasPdf(r) {
            if (r.documents && r.documents.length > 0) return true;
            if (r.document && r.document.title) return true;
            if (/https?:\/\/\S+\.pdf(\b|\?)/i.test(r.text || '')) return true;
            return false;
        }

        function reportHasContent(r) {
            // Keep posts that have text, documents, or at least one image
            const hasText = !!(r.text || '').trim();
            const hasDocs = (r.documents && r.documents.length > 0) || !!(r.document && r.document.title);
            const hasImages = Array.isArray(r.images) && r.images.length > 0;
            return hasText || hasDocs || hasImages;
        }

        function filterReports() {
            const query = document.getElementById('search-input').value.toLowerCase().trim();
            filteredReports = query
                ? TELEGRAM_REPORTS.filter(r => {
                    const text = (r.text || '').toLowerCase();
                    const channel = (r.channel || '').toLowerCase();
                    const docTitle = (r.documents && r.documents.length > 0
                        ? r.documents.map(d => d.title || '').join(' ')
                        : (r.document && r.document.title || '')).toLowerCase();
                    return text.includes(query) || channel.includes(query) || docTitle.includes(query);
                })
                : [...TELEGRAM_REPORTS];
            // Exclude fully empty posts only (no text, docs, or images)
            filteredReports = filteredReports.filter(reportHasContent);
            // View mode filter
            if (reportsViewMode === 'pdf') {
                filteredReports = filteredReports.filter(reportHasPdf);
            } else if (reportsViewMode === 'nopdf') {
                filteredReports = filteredReports.filter(r => !reportHasPdf(r));
            }
            // Channel filter
            if (selectedTgChannels.size > 0) {
                filteredReports = filteredReports.filter(r => selectedTgChannels.has(r.channel || ''));
            }
            // No price targets
            if (reportsNoTargetFilterActive) {
                filteredReports = filteredReports.filter(r => !reportHasStockTarget(r));
            }
            document.getElementById('reports-visible-count').textContent = filteredReports.length;
            reportsPage = 1;
            applyReportsPagination();
        }

        function applyReportsPagination() {
            const totalPages = Math.max(1, Math.ceil(filteredReports.length / REPORTS_PAGE_SIZE));
            if (reportsPage > totalPages) reportsPage = totalPages;

            const start = (reportsPage - 1) * REPORTS_PAGE_SIZE;
            const end = start + REPORTS_PAGE_SIZE;
            const pageReports = filteredReports.slice(start, end);

            const container = document.getElementById('reports-container');
            if (pageReports.length === 0) {
                container.innerHTML = '<div style="padding:40px 20px;text-align:center;color:var(--text-muted);font-size:14px;">No reports found.</div>';
                renderReportsPagination(totalPages);
                return;
            }

            let html = '';
            let currentDateHeader = '';
            const bookmarks = getBookmarks();

            pageReports.forEach(r => {
                const dateHeader = formatReportDateHeader(r.date);
                if (dateHeader !== currentDateHeader) {
                    currentDateHeader = dateHeader;
                    html += dateHeaderHtml(dateHeader, r.date);
                }

                const rawText = r.text || '';
                const lines = rawText.split('\n').map(line => line.trim()).filter(Boolean);
                const reportTitleRaw = lines[0] || '';
                const reportBodyRaw = lines.length > 1 ? lines.slice(1).join('\n') : '';
                const hasReportTitle = !!reportTitleRaw.trim();
                const reportTitle = escapeHtml(deshoutTitle(reportTitleRaw.replace(/\*\*/g, '').trim()));
                const text = telegramBodyHtml(lines.slice(1));
                const reportUrl = sanitizeUrl(r.url || '');
                const isBookmarkedReport = bookmarks.some(b => b.url === reportUrl);
                const titleHtml = hasReportTitle
                    ? (reportUrl
                        ? `<a href="${escapeForAttr(reportUrl)}" target="_blank" rel="noopener" class="report-title-link">${reportTitle}</a>`
                        : `<span class="report-title-link">${reportTitle}</span>`)
                    : '';
                const channel = escapeHtml(r.channel || 'Telegram');
                const sourceHtml = reportUrl
                    ? `<a href="${escapeForAttr(reportUrl)}" target="_blank" rel="noopener" class="report-channel card-source-link">${channel}</a>`
                    : `<span class="report-channel">${channel}</span>`;
                let docHtml = '';
                const docs = (r.documents && r.documents.length > 0) ? r.documents
                    : (r.document && r.document.title) ? [r.document] : [];
                if (docs.length > 0) {
                    const docItems = docs.map(d => {
                        const name = escapeHtml(d.title || 'Document');
                        const size = d.size ? `<span class="report-doc-size">${escapeHtml(d.size)}</span>` : '';
                        return `<div class="report-doc-item"><span class="report-doc-icon">📄</span><span class="report-doc-name">${name}</span>${size}</div>`;
                    }).join('');
                    docHtml = `<div class="report-doc-list">${docItems}</div>`;
                }

                let imgHtml = '';
                const images = Array.isArray(r.images)
                    ? r.images.map(url => sanitizeUrl(String(url || ''))).filter(Boolean)
                    : [];
                if (images.length > 0) {
                    const badge = images.length > 1
                        ? `<span class="report-images-badge">+${images.length - 1} more</span>` : '';
                    const encodedImages = escapeForAttr(JSON.stringify(images));
                    imgHtml = `<button type="button" class="report-images" onclick="openReportImageLightboxFromButton(this)"
                        data-report-images='${encodedImages}' data-start-index="0" aria-label="Open report image in fullscreen">
                        <img src="${escapeForAttr(images[0])}" alt="Report image" loading="lazy"
                             onerror="this.onerror=null;this.style.display='none';this.parentElement.classList.add('report-images-fallback')">
                        ${badge}</button>`;
                }

                const hasPdfLink = /https?:\/\/\S+\.pdf(\b|\?)/i.test(r.text || '');
                const bookmarkTitleRaw = hasReportTitle
                    ? reportTitleRaw
                    : (docs[0] && docs[0].title ? docs[0].title : '');

                // Content-type badge
                let typeBadge = '';
                if (docs.length > 0 || hasPdfLink) {
                    typeBadge = '<span class="report-type-badge report-type-doc">Report</span>';
                } else if (images.length > 0) {
                    typeBadge = '<span class="report-type-badge report-type-photo">Photo</span>';
                }

                html += `
                    <div class="report-card" data-url="${escapeForAttr(reportUrl)}" data-title="${escapeForAttr((bookmarkTitleRaw || '').substring(0, 100))}" data-channel="${escapeForAttr(r.channel || '')}">
                        <div class="report-card-header">
                            <div class="report-card-left">
                                ${sourceHtml}
                                ${typeBadge}
                            </div>
                            <div class="report-card-right">
                                <span class="report-card-date">${formatReportDate(r.date)}</span>
                                <button class="bookmark-btn${isBookmarkedReport ? ' bookmarked' : ''}" onclick="toggleReportBookmark(this)" aria-label="Bookmark">
                                    <svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                                </button>
                            </div>
                        </div>
                        ${imgHtml}
                        ${docHtml}
                        ${hasReportTitle ? `<div class="report-title">${titleHtml}</div>` : ''}
                        ${reportBodyRaw ? `<div class="report-text">${text}</div><button class="report-expand-btn" style="display:none" onclick="toggleReportExpand(this)">Show more</button>` : ''}
                        ${r.views ? `<div class="report-meta"><span>${escapeHtml(r.views)} views</span></div>` : ''}
                    </div>
                `;
            });

            container.innerHTML = html;
            requestAnimationFrame(() => checkOverflow(container, '.report-text', '.report-expand-btn'));
            renderReportsPagination(totalPages);
        }

        function renderReportsPagination(totalPages) {
            buildPagination('reports-pagination-bottom', reportsPage, totalPages, (page) => {
                reportsPage = page;
                applyReportsPagination();
                window.scrollTo({top: 0, behavior: 'smooth'});
            });
        }

        function toggleReportExpand(btn) {
            const textEl = btn.previousElementSibling;
            const isExpanded = textEl.classList.toggle('expanded');
            btn.textContent = isExpanded ? 'Show less' : 'Show more';
        }

        function toggleReportBookmark(btn) {
            const card = btn.closest('.report-card');
            const url = card.dataset.url;
            const title = card.dataset.title;
            const source = card.dataset.channel;

            let bookmarks = getBookmarks();
            const idx = bookmarks.findIndex(b => b.url === url);

            if (idx >= 0) {
                bookmarks.splice(idx, 1);
                btn.classList.remove('bookmarked');
            } else {
                bookmarks.unshift({ url, title, source: source + ' (Telegram)', addedAt: Date.now() });
                btn.classList.add('bookmarked');
            }

            saveBookmarks(bookmarks);
            updateBookmarkCount();
            renderSidebarContent();
        }

        // ==================== RESEARCH TAB (functions) ====================
        function renderMainResearch() {
            initResearchPublisherDropdown();
            filteredResearch = [...RESEARCH_REPORTS];
            researchPage = 1;
            applyResearchPagination();
        }

        function filterResearch() {
            const query = document.getElementById('search-input').value.toLowerCase().trim();
            filteredResearch = RESEARCH_REPORTS.filter(r => {
                const matchesSearch = !query || (r.title + ' ' + r.source + ' ' + (r.publisher || '') + ' ' + (r.description || '')).toLowerCase().includes(query);
                const pub = r.publisher || r.source;
                const matchesPublisher = selectedResearchPublishers.size === 0 || selectedResearchPublishers.has(pub);
                const region = (r.region || 'Indian').toLowerCase();
                const matchesRegion = researchRegionFilter === 'all' || region === researchRegionFilter;
                return matchesSearch && matchesPublisher && matchesRegion;
            });
            researchPage = 1;
            applyResearchPagination();
        }

        function setResearchRegion(mode) {
            researchRegionFilter = mode;
            document.getElementById('research-region-all').classList.toggle('active', mode === 'all');
            document.getElementById('research-region-indian').classList.toggle('active', mode === 'indian');
            document.getElementById('research-region-international').classList.toggle('active', mode === 'international');
            filterResearch();
        }

        function formatResearchDate(isoStr) {
            if (!isoStr) return '';
            const date = new Date(isoStr);
            const now = new Date();
            const diffMs = now - date;
            const diffMin = Math.floor(diffMs / 60000);
            const diffHr = Math.floor(diffMs / 3600000);
            const diffDay = Math.floor(diffMs / 86400000);
            if (diffMin < 1) return 'Just now';
            if (diffMin < 60) return diffMin + 'm ago';
            if (diffHr < 24) return diffHr + 'h ago';
            if (diffDay === 1) return 'Yesterday';
            if (diffDay < 7) return diffDay + 'd ago';
            return date.toLocaleDateString();
        }

        function formatResearchDateHeader(isoStr) {
            if (!isoStr) return 'Unknown Date';
            const date = new Date(isoStr);
            const now = new Date();
            const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            const rDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
            const diffDays = Math.floor((today - rDay) / 86400000);
            if (diffDays === 0) return 'Today';
            if (diffDays === 1) return 'Yesterday';
            return date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
        }

        function applyResearchPagination() {
            const totalPages = Math.max(1, Math.ceil(filteredResearch.length / RESEARCH_PAGE_SIZE));
            if (researchPage > totalPages) researchPage = totalPages;

            document.getElementById('research-visible-count').textContent = filteredResearch.length;

            const start = (researchPage - 1) * RESEARCH_PAGE_SIZE;
            const end = start + RESEARCH_PAGE_SIZE;
            const pageReports = filteredResearch.slice(start, end);

            const container = document.getElementById('research-container');
            if (pageReports.length === 0) {
                container.innerHTML = '<div style="padding:40px 20px;text-align:center;color:var(--text-muted);font-size:14px;">No reports found.</div>';
                renderResearchPagination(totalPages);
                return;
            }

            let html = '';
            let currentDateHeader = '';

            pageReports.forEach(r => {
                const dateHeader = formatResearchDateHeader(r.date);
                if (dateHeader !== currentDateHeader) {
                    currentDateHeader = dateHeader;
                    html += dateHeaderHtml(dateHeader, r.date);
                }

                const title = escapeHtml(r.title);
                const publisher = escapeHtml(r.publisher || r.source);
                const reportUrl = sanitizeUrl(r.link || '');
                const sourceUrl = sanitizeUrl(r.source_url || '') || reportUrl;
                const cardUrl = reportUrl || sourceUrl;
                const description = escapeHtml(r.description || '');
                const region = (r.region || 'Indian').toLowerCase();
                const sourceHtml = sourceUrl
                    ? `<a href="${escapeForAttr(sourceUrl)}" target="_blank" rel="noopener" class="report-channel card-source-link">${publisher}</a>`
                    : `<span class="report-channel">${publisher}</span>`;
                const titleHtml = cardUrl
                    ? `<a href="${escapeForAttr(cardUrl)}" target="_blank" rel="noopener" class="report-title-link">${title}</a>`
                    : `<span class="report-title-link">${title}</span>`;

                html += `
                    <div class="report-card" data-publisher="${publisher}" data-url="${escapeForAttr(cardUrl)}" data-region="${region}">
                        <div class="report-card-header">
                            <div class="report-card-left">
                                ${sourceHtml}
                                <span class="region-tag">${region === 'international' ? 'International' : 'Indian'}</span>
                            </div>
                            <div class="report-card-right">
                                ${r.date ? `<span class="report-card-date">${formatResearchDate(r.date)}</span>` : ''}
                                <button class="bookmark-btn" data-url="${escapeForAttr(cardUrl)}" data-title="${escapeForAttr(r.title)}" data-source="${publisher}" onclick="toggleGenericBookmark(this)" aria-label="Bookmark report" title="Bookmark">
                                    <svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                                </button>
                            </div>
                        </div>
                        <div class="report-title">${titleHtml}</div>
                        ${description ? `<div class="research-card-description">${description}</div>` : ''}
                    </div>
                `;
            });

            container.innerHTML = html;
            syncBookmarkState();
            renderResearchPagination(totalPages);
        }

        function renderResearchPagination(totalPages) {
            buildPagination('research-pagination-bottom', researchPage, totalPages, (page) => {
                researchPage = page;
                applyResearchPagination();
                window.scrollTo({top: 0, behavior: 'smooth'});
            });
        }

        // Research publisher dropdown
        function initResearchPublisherDropdown() {
            const list = document.getElementById('research-dropdown-list');
            if (!list) return;
            list.innerHTML = '';
            RESEARCH_PUBLISHERS.forEach(pub => {
                const item = document.createElement('div');
                item.className = 'dropdown-item';
                item.dataset.publisher = pub;
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.id = 'research-pub-' + pub.replace(/\s+/g, '-');
                cb.dataset.publisher = pub;
                cb.addEventListener('change', () => onResearchPublisherChange(pub, cb.checked));
                const lbl = document.createElement('label');
                lbl.htmlFor = cb.id;
                lbl.textContent = pub;
                item.appendChild(cb);
                item.appendChild(lbl);
                item.addEventListener('click', (e) => {
                    if (e.target !== cb) {
                        cb.checked = !cb.checked;
                        onResearchPublisherChange(pub, cb.checked);
                    }
                });
                list.appendChild(item);
            });
        }

        function onResearchPublisherChange(pub, checked) {
            if (checked) {
                selectedResearchPublishers.add(pub);
            } else {
                selectedResearchPublishers.delete(pub);
            }
            syncResearchPublisherSummary();
            filterResearch();
        }

        function syncResearchPublisherSummary() {
            const trigger = document.getElementById('research-publisher-trigger');
            const summary = document.getElementById('research-publisher-summary');
            if (!trigger || !summary) return;
            if (selectedResearchPublishers.size === 0) {
                summary.textContent = 'All publishers';
                trigger.classList.remove('has-selection');
            } else if (selectedResearchPublishers.size === 1) {
                summary.textContent = [...selectedResearchPublishers][0];
                trigger.classList.add('has-selection');
            } else {
                summary.textContent = selectedResearchPublishers.size + ' of ' + RESEARCH_PUBLISHERS.length + ' publishers';
                trigger.classList.add('has-selection');
            }
        }

        function toggleResearchDropdown() {
            const dd = document.getElementById('research-publisher-dropdown');
            dd.classList.toggle('open');
            if (dd.classList.contains('open')) {
                document.getElementById('research-dropdown-search').focus();
            }
        }

        function closeResearchDropdown() { closeDropdownById('research-publisher-dropdown', 'research-dropdown-search', 'research-dropdown-list'); }
        function filterResearchPublisherList() { filterDropdownList('research-dropdown-search', 'research-dropdown-list'); }

        function syncResearchCheckboxes() {
            document.querySelectorAll('#research-dropdown-list input[type="checkbox"]').forEach(cb => {
                cb.checked = selectedResearchPublishers.has(cb.dataset.publisher);
            });
        }

        function selectAllResearchPublishers() {
            RESEARCH_PUBLISHERS.forEach(pub => selectedResearchPublishers.add(pub));
            syncResearchCheckboxes();
            syncResearchPublisherSummary();
            filterResearch();
        }

        function clearAllResearchPublishers() {
            selectedResearchPublishers.clear();
            syncResearchCheckboxes();
            syncResearchPublisherSummary();
            filterResearch();
        }

        // ==================== PAPERS TAB (functions) ====================
        function reshufflePaperSession() {
            paperSessionPool = [...PAPER_ARTICLES];
            for (let i = paperSessionPool.length - 1; i > 0; i--) {
                const j = Math.floor(Math.random() * (i + 1));
                [paperSessionPool[i], paperSessionPool[j]] = [paperSessionPool[j], paperSessionPool[i]];
            }
        }

        function renderMainPapers() {
            // Reserved for future Paper-tab initialization hooks.
        }

        function filterPapers() {
            const query = document.getElementById('search-input').value.toLowerCase().trim();
            const sourcePool = paperSessionPool.length > 0 ? paperSessionPool : PAPER_ARTICLES;
            filteredPapers = sourcePool.filter(p => {
                const haystack = (
                    (p.title || '') + ' ' +
                    (p.source || '') + ' ' +
                    (p.publisher || '') + ' ' +
                    (p.description || '') + ' ' +
                    (p.authors || '')
                ).toLowerCase();
                return !query || haystack.includes(query);
            });
            papersPage = 1;
            applyPapersPagination();
        }

        function formatPaperDate(isoStr) {
            if (!isoStr) return '';
            const date = new Date(isoStr);
            const now = new Date();
            const diffMs = now - date;
            const diffMin = Math.floor(diffMs / 60000);
            const diffHr = Math.floor(diffMs / 3600000);
            const diffDay = Math.floor(diffMs / 86400000);
            if (diffMin < 1) return 'Just now';
            if (diffMin < 60) return diffMin + 'm ago';
            if (diffHr < 24) return diffHr + 'h ago';
            if (diffDay === 1) return 'Yesterday';
            if (diffDay < 7) return diffDay + 'd ago';
            return date.toLocaleDateString();
        }

        function formatPaperDateHeader(isoStr) {
            if (!isoStr) return 'Unknown Date';
            const date = new Date(isoStr);
            const now = new Date();
            const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            const paperDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
            const diffDays = Math.floor((today - paperDay) / 86400000);
            if (diffDays === 0) return 'Today';
            if (diffDays === 1) return 'Yesterday';
            return date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
        }

        function applyPapersPagination() {
            const totalPages = Math.max(1, Math.ceil(filteredPapers.length / PAPERS_PAGE_SIZE));
            if (papersPage > totalPages) papersPage = totalPages;

            const countEl = document.getElementById('papers-visible-count');
            if (countEl) countEl.textContent = filteredPapers.length;

            const start = (papersPage - 1) * PAPERS_PAGE_SIZE;
            const end = start + PAPERS_PAGE_SIZE;
            const pagePapers = filteredPapers.slice(start, end);

            const container = document.getElementById('papers-container');
            if (pagePapers.length === 0) {
                container.innerHTML = '<div style="padding:40px 20px;text-align:center;color:var(--text-muted);font-size:14px;">No papers found.</div>';
                renderPapersPagination(totalPages);
                return;
            }

            let html = '';

            pagePapers.forEach(p => {
                const title = escapeHtml(p.title || 'Untitled paper');
                const publisher = escapeHtml(p.publisher || p.source || 'Unknown source');
                const paperUrl = sanitizeUrl(p.link || '');
                const sourceUrl = sanitizeUrl(p.source_url || '');
                const cardUrl = paperUrl || sourceUrl;
                const titleHtml = paperUrl
                    ? `<a href="${escapeForAttr(paperUrl)}" target="_blank" rel="noopener" class="report-title-link">${title}</a>`
                    : `<span class="report-title-link">${title}</span>`;
                const sourceHtml = sourceUrl
                    ? `<a href="${escapeForAttr(sourceUrl)}" target="_blank" rel="noopener" class="report-channel card-source-link">${publisher}</a>`
                    : `<span class="report-channel">${publisher}</span>`;
                const authors = escapeHtml(p.authors || '');
                // Many sources only give "Click title to read full paper →" (or the title again) — skip those.
                const rawSummary = String(p.description || '').trim();
                const summary = (/^click title/i.test(rawSummary) || rawSummary === (p.title || '').trim()) ? '' : escapeHtml(rawSummary);
                const bookmarkHtml = cardUrl
                    ? `<button class="bookmark-btn" data-url="${escapeForAttr(cardUrl)}" data-title="${escapeForAttr(p.title || '')}" data-source="${publisher}" onclick="toggleGenericBookmark(this)" aria-label="Bookmark paper" title="Bookmark">
                            <svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                       </button>`
                    : '';

                html += `
                    <div class="report-card paper-card" data-publisher="${publisher}" data-url="${escapeForAttr(cardUrl)}">
                        <div class="report-card-header">
                            <div class="report-card-left">
                                ${sourceHtml}
                            </div>
                            <div class="report-card-right">
                                ${(p.date && !p.date_is_fallback) ? `<span class="report-card-date">${formatPaperDate(p.date)}</span>` : ''}
                                ${bookmarkHtml}
                            </div>
                        </div>
                        <div class="report-title">${titleHtml}</div>
                        ${authors ? `<div class="paper-card-authors">${authors}</div>` : ''}
                        ${summary ? `<div class="paper-card-summary">${summary}</div>` : ''}
                    </div>
                `;
            });

            container.innerHTML = html;
            syncBookmarkState();
            renderPapersPagination(totalPages);
        }

        function renderPapersPagination(totalPages) {
            buildPagination('papers-pagination-bottom', papersPage, totalPages, (page) => {
                papersPage = page;
                applyPapersPagination();
                window.scrollTo({top: 0, behavior: 'smooth'});
            });
        }

        // ==================== YOUTUBE TAB (functions) ====================
        function renderMainYoutube() {
            initYoutubePublisherDropdown();
            syncYoutubeBucketButtons();
            filteredYoutube = [...YOUTUBE_VIDEOS];
            youtubePage = 1;
            applyYoutubePagination();
        }

        function filterYoutube() {
            const query = document.getElementById('search-input').value.toLowerCase().trim();
            filteredYoutube = YOUTUBE_VIDEOS.filter(v => {
                const matchesSearch = !query || (v.title + ' ' + v.source + ' ' + v.publisher).toLowerCase().includes(query);
                const pub = v.publisher || v.source;
                const matchesPublisher = selectedYoutubePublishers.size === 0 || selectedYoutubePublishers.has(pub);
                const bucket = v.youtube_bucket || 'Educational/Explainers';
                const matchesBucket = youtubeBucketFilter === 'all' || bucket === youtubeBucketFilter;
                return matchesSearch && matchesPublisher && matchesBucket;
            });
            youtubePage = 1;
            applyYoutubePagination();
            updateYoutubePublisherSummary();
        }

        function setYoutubeBucketFilter(bucket) {
            if (bucket !== 'all' && !YOUTUBE_BUCKETS.includes(bucket)) {
                youtubeBucketFilter = 'all';
            } else {
                youtubeBucketFilter = bucket;
            }
            syncYoutubeBucketButtons();
            filterYoutube();
        }

        function syncYoutubeBucketButtons() {
            document.querySelectorAll('[data-youtube-bucket]').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.youtubeBucket === youtubeBucketFilter);
            });
        }

        function initYoutubePublisherDropdown() {
            const list = document.getElementById('youtube-dropdown-list');
            if (!list) return;
            list.innerHTML = '';
            YOUTUBE_PUBLISHERS.forEach(pub => {
                const item = document.createElement('div');
                item.className = 'dropdown-item';
                item.dataset.publisher = pub;
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.id = 'ytpub-' + pub.replace(/\s+/g, '-');
                cb.dataset.publisher = pub;
                cb.addEventListener('change', () => onYoutubePublisherChange(pub, cb.checked));
                const lbl = document.createElement('label');
                lbl.htmlFor = cb.id;
                lbl.textContent = pub;
                item.appendChild(cb);
                item.appendChild(lbl);
                item.addEventListener('click', (e) => {
                    if (e.target !== cb) {
                        cb.checked = !cb.checked;
                        onYoutubePublisherChange(pub, cb.checked);
                    }
                });
                list.appendChild(item);
            });
        }

        function toggleYoutubeDropdown() {
            const dd = document.getElementById('youtube-publisher-dropdown');
            dd.classList.toggle('open');
            if (dd.classList.contains('open')) {
                document.getElementById('youtube-dropdown-search').focus();
            }
        }

        function filterYoutubePublisherList() { filterDropdownList('youtube-dropdown-search', 'youtube-dropdown-list'); }

        function selectAllYoutubePublishers() {
            selectedYoutubePublishers.clear();
            syncYoutubeCheckboxes();
            updateYoutubePublisherSummary();
            filterYoutube();
        }

        function clearAllYoutubePublishers() {
            selectedYoutubePublishers.clear();
            syncYoutubeCheckboxes();
            updateYoutubePublisherSummary();
            filterYoutube();
        }

        function onYoutubePublisherChange(pub, checked) {
            if (checked) {
                selectedYoutubePublishers.add(pub);
            } else {
                selectedYoutubePublishers.delete(pub);
            }
            updateYoutubePublisherSummary();
            filterYoutube();
        }

        function syncYoutubeCheckboxes() {
            document.querySelectorAll('#youtube-dropdown-list input[type="checkbox"]').forEach(cb => {
                cb.checked = selectedYoutubePublishers.has(cb.dataset.publisher);
            });
        }

        function updateYoutubePublisherSummary() {
            const el = document.getElementById('youtube-publisher-summary');
            const countLabel = document.getElementById('youtube-publisher-count-label');
            if (!el) return;
            const inBucket = YOUTUBE_VIDEOS
                .filter(v => youtubeBucketFilter === 'all' || (v.youtube_bucket || 'Educational/Explainers') === youtubeBucketFilter)
                .map(v => v.publisher || v.source)
                .filter(Boolean);
            const inBucketSet = new Set(inBucket);
            const total = inBucketSet.size;
            const selectedVisible = [...selectedYoutubePublishers].filter(pub => inBucketSet.has(pub));
            const n = selectedVisible.length;
            if (selectedYoutubePublishers.size === 0) {
                el.textContent = 'All channels';
                if (countLabel) countLabel.innerHTML = '<strong>' + total + '</strong> channels';
            } else if (n === 1) {
                el.textContent = selectedVisible[0];
                if (countLabel) countLabel.textContent = '· 1 of ' + total + ' channels';
            } else {
                el.textContent = n + ' channels';
                if (countLabel) countLabel.textContent = '· ' + n + ' of ' + total + ' channels';
            }
        }

        function closeYoutubeDropdown() { closeDropdownById('youtube-publisher-dropdown', 'youtube-dropdown-search', 'youtube-dropdown-list'); }

        function formatYoutubeDate(isoStr) {
            if (!isoStr) return '';
            const date = new Date(isoStr);
            const now = new Date();
            const diffMs = now - date;
            const diffMin = Math.floor(diffMs / 60000);
            const diffHr = Math.floor(diffMs / 3600000);
            const diffDay = Math.floor(diffMs / 86400000);
            if (diffMin < 1) return 'Just now';
            if (diffMin < 60) return diffMin + 'm ago';
            if (diffHr < 24) return diffHr + 'h ago';
            if (diffDay === 1) return 'Yesterday';
            if (diffDay < 7) return diffDay + 'd ago';
            return date.toLocaleDateString();
        }

        function formatYoutubeDateHeader(isoStr) {
            if (!isoStr) return 'Unknown Date';
            const date = new Date(isoStr);
            const now = new Date();
            const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            const videoDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
            const diffDays = Math.floor((today - videoDay) / 86400000);
            if (diffDays === 0) return 'Today';
            if (diffDays === 1) return 'Yesterday';
            return date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
        }

        function applyYoutubePagination() {
            const totalPages = Math.max(1, Math.ceil(filteredYoutube.length / YOUTUBE_PAGE_SIZE));
            if (youtubePage > totalPages) youtubePage = totalPages;

            document.getElementById('youtube-visible-count').textContent = filteredYoutube.length;

            const start = (youtubePage - 1) * YOUTUBE_PAGE_SIZE;
            const end = start + YOUTUBE_PAGE_SIZE;
            const pageVideos = filteredYoutube.slice(start, end);

            const container = document.getElementById('youtube-container');
            if (pageVideos.length === 0) {
                container.innerHTML = '<div style="padding:40px 20px;text-align:center;color:var(--text-muted);font-size:14px;">No videos found.</div>';
                renderYoutubePagination(totalPages);
                return;
            }

            let html = '';
            let currentDateHeader = '';

            pageVideos.forEach(v => {
                const dateHeader = formatYoutubeDateHeader(v.date);
                if (dateHeader !== currentDateHeader) {
                    currentDateHeader = dateHeader;
                    html += dateHeaderHtml(dateHeader, v.date);
                }

                const title = escapeHtml(v.title);
                const channel = escapeHtml(v.publisher || v.source);
                const videoUrl = sanitizeUrl(v.link || '');
                const sourceUrl = sanitizeUrl(v.source_url || '') || videoUrl;
                const bookmarkUrl = videoUrl || sourceUrl;
                const thumbnail = v.thumbnail || (v.video_id ? `https://i.ytimg.com/vi/${v.video_id}/mqdefault.jpg` : '');
                const sourceHtml = sourceUrl
                    ? `<a href="${escapeForAttr(sourceUrl)}" target="_blank" rel="noopener" class="video-channel card-source-link">${channel}</a>`
                    : `<span class="video-channel">${channel}</span>`;
                const titleHtml = videoUrl
                    ? `<a href="${escapeForAttr(videoUrl)}" target="_blank" rel="noopener">${title}</a>`
                    : `<span>${title}</span>`;
                const thumbInner = `
                            ${thumbnail ? `<img src="${escapeForAttr(thumbnail)}" alt="${escapeForAttr(v.title)}" loading="lazy" onerror="this.style.display='none'">` : ''}
                            ${/\/shorts\//.test(v.link || '') ? '<span class="video-short">Short</span>' : ''}
                            <div class="video-thumb-play">
                                <svg viewBox="0 0 24 24"><polygon points="5,3 19,12 5,21"/></svg>
                            </div>`;
                const thumbHtml = videoUrl
                    ? `<a href="${escapeForAttr(videoUrl)}" target="_blank" rel="noopener" class="video-thumb">${thumbInner}</a>`
                    : `<div class="video-thumb">${thumbInner}</div>`;

                html += `
                    <div class="video-card">
                        ${thumbHtml}
                        <div class="video-info">
                            ${sourceHtml}
                            <div class="video-title">${titleHtml}</div>
                            <div class="video-meta">
                                <span>${formatYoutubeDate(v.date)}</span>
                            </div>
                        </div>
                        <button class="bookmark-btn video-bookmark" data-url="${escapeForAttr(bookmarkUrl)}" data-title="${escapeForAttr(v.title)}" data-source="${channel}" onclick="toggleGenericBookmark(this)" aria-label="Bookmark video" title="Bookmark">
                            <svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                        </button>
                    </div>
                `;
            });

            container.innerHTML = html;
            syncBookmarkState();
            renderYoutubePagination(totalPages);
        }

        function renderYoutubePagination(totalPages) {
            buildPagination('youtube-pagination-bottom', youtubePage, totalPages, (page) => {
                youtubePage = page;
                applyYoutubePagination();
                window.scrollTo({top: 0, behavior: 'smooth'});
            });
        }

        // ==================== TWITTER TAB (helpers) ====================
        function getTweetBadges(title, tweet) {
            const badges = [];
            const isRt = (tweet && tweet.is_retweet) || title.startsWith('RT @') || title.startsWith('RT ');
            const isQuote = (tweet && tweet.is_quote) || title.startsWith('”') || title.startsWith('\u201c');
            if (isQuote) badges.push({label: 'Quote', cls: 'tweet-badge-quote'});
            else if (isRt) badges.push({label: 'Retweet', cls: 'tweet-badge-retweet'});
            if (title.includes('\ud83e\uddf5')) badges.push({label: 'Thread', cls: 'tweet-badge-thread'});
            return badges;
        }
        function toggleTweetExpand(btn) {
            const textEl = btn.previousElementSibling;
            const expanded = textEl.classList.toggle('expanded');
            btn.textContent = expanded ? 'Show less' : 'Show more';
        }
        function checkOverflow(container, textSelector, btnSelector) {
            if (!container) return;
            container.querySelectorAll(textSelector).forEach(el => {
                const btn = el.parentElement.querySelector(btnSelector);
                if (!btn) return;
                const clampedH = el.clientHeight;
                const clone = el.cloneNode(true);
                clone.classList.add('expanded');
                clone.style.position = 'absolute';
                clone.style.visibility = 'hidden';
                clone.style.width = el.offsetWidth + 'px';
                el.parentNode.appendChild(clone);
                const naturalH = clone.scrollHeight;
                clone.remove();
                const clamped = naturalH > clampedH + 2;
                btn.style.display = clamped ? '' : 'none';
                el.classList.toggle('is-clamped', clamped);
            });
        }

        // ==================== TWITTER TAB (functions) ====================
        function getActiveTwitterPool() {
            return twitterLane === 'full-stream' ? TWITTER_ARTICLES : TWITTER_HIGH_SIGNAL;
        }

        function renderMainTwitter() {
            if (twitterLane !== 'high-signal' && twitterLane !== 'full-stream') {
                twitterLane = 'high-signal';
            }
            initTwitterPublisherDropdown();
            syncTwitterLaneButtons();
            syncTwitterPresetButtons();
            filteredTwitter = [...getActiveTwitterPool()];
            twitterPage = 1;
            applyTwitterPagination();
            updateTwitterLaneSummary();
        }

        function setTwitterLane(lane) {
            if (lane !== 'high-signal' && lane !== 'full-stream') return;
            twitterLane = lane;
            safeStorage.set('financeradar_twitter_lane', lane);
            syncTwitterLaneButtons();
            filterTwitter();
        }

        function syncTwitterLaneButtons() {
            document.querySelectorAll('[data-twitter-lane]').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.twitterLane === twitterLane);
            });
        }

        function updateTwitterLaneSummary() {
            const laneEl = document.getElementById('twitter-lane-summary');
            if (!laneEl) return;
            const fullCount = TWITTER_ARTICLES.length;
            const highCount = TWITTER_HIGH_SIGNAL.length;
            if (twitterLane === 'high-signal') {
                const mode = (TWITTER_LANE_META && TWITTER_LANE_META.ranking_mode) || 'fallback';
                const modeLabel = mode === 'ai' ? 'AI ranked' : 'Rule fallback';
                laneEl.textContent = 'High Signal · ' + highCount + ' of ' + fullCount + ' · ' + modeLabel;
            } else {
                laneEl.textContent = 'Full Stream · ' + fullCount;
            }
        }

        function filterTwitter() {
            const query = document.getElementById('search-input').value.toLowerCase().trim();
            const pool = getActiveTwitterPool();
            filteredTwitter = pool.filter(t => {
                const matchesSearch = !query || (t.title + ' ' + t.source + ' ' + (t.publisher || '')).toLowerCase().includes(query);
                const pub = t.publisher || t.source;
                const matchesPublisher = selectedTwitterPublishers.size === 0 || selectedTwitterPublishers.size === TWITTER_PUBLISHERS.length || selectedTwitterPublishers.has(pub);
                return matchesSearch && matchesPublisher;
            });
            twitterPage = 1;
            applyTwitterPagination();
            updateTwitterPublisherSummary();
            updateTwitterLaneSummary();
        }

        function initTwitterPublisherDropdown() {
            const list = document.getElementById('twitter-dropdown-list');
            if (!list) return;
            list.innerHTML = '';
            TWITTER_PUBLISHERS.forEach(pub => {
                const item = document.createElement('div');
                item.className = 'dropdown-item';
                item.dataset.publisher = pub;
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.id = 'twpub-' + pub.replace(/\s+/g, '-');
                cb.dataset.publisher = pub;
                cb.addEventListener('change', () => onTwitterPublisherChange(pub, cb.checked));
                const lbl = document.createElement('label');
                lbl.htmlFor = cb.id;
                lbl.textContent = pub;
                item.appendChild(cb);
                item.appendChild(lbl);
                item.addEventListener('click', (e) => {
                    if (e.target !== cb) {
                        cb.checked = !cb.checked;
                        onTwitterPublisherChange(pub, cb.checked);
                    }
                });
                list.appendChild(item);
            });
        }

        function toggleTwitterDropdown() {
            const dd = document.getElementById('twitter-publisher-dropdown');
            dd.classList.toggle('open');
            if (dd.classList.contains('open')) {
                document.getElementById('twitter-dropdown-search').focus();
            }
        }

        function filterTwitterPublisherList() { filterDropdownList('twitter-dropdown-search', 'twitter-dropdown-list'); }

        function selectAllTwitterPublishers() {
            TWITTER_PUBLISHERS.forEach(pub => selectedTwitterPublishers.add(pub));
            syncTwitterCheckboxes();
            syncTwitterPresetButtons();
            updateTwitterPublisherSummary();
            filterTwitter();
        }

        function clearAllTwitterPublishers() {
            selectedTwitterPublishers.clear();
            syncTwitterCheckboxes();
            syncTwitterPresetButtons();
            updateTwitterPublisherSummary();
            filterTwitter();
        }

        function onTwitterPublisherChange(pub, checked) {
            if (checked) {
                selectedTwitterPublishers.add(pub);
            } else {
                selectedTwitterPublishers.delete(pub);
            }
            syncTwitterPresetButtons();
            updateTwitterPublisherSummary();
            filterTwitter();
        }

        function syncTwitterCheckboxes() {
            document.querySelectorAll('#twitter-dropdown-list input[type="checkbox"]').forEach(cb => {
                cb.checked = selectedTwitterPublishers.has(cb.dataset.publisher);
            });
        }

        function toggleTwitterPreset(name) {
            const pubs = TWITTER_PRESETS[name];
            if (!pubs) return;
            const allSelected = pubs.every(p => selectedTwitterPublishers.has(p));
            if (allSelected) {
                pubs.forEach(p => selectedTwitterPublishers.delete(p));
            } else {
                pubs.forEach(p => selectedTwitterPublishers.add(p));
            }
            syncTwitterCheckboxes();
            syncTwitterPresetButtons();
            updateTwitterPublisherSummary();
            filterTwitter();
        }

        function syncTwitterPresetButtons() {
            document.querySelectorAll('[data-twitter-preset]').forEach(btn => {
                const name = btn.dataset.twitterPreset;
                const pubs = TWITTER_PRESETS[name];
                if (!pubs) return;
                const selected = pubs.filter(p => selectedTwitterPublishers.has(p));
                if (selectedTwitterPublishers.size === 0) {
                    btn.classList.remove('active', 'partial');
                } else if (selected.length === pubs.length) {
                    btn.classList.add('active');
                    btn.classList.remove('partial');
                } else if (selected.length > 0) {
                    btn.classList.remove('active');
                    btn.classList.add('partial');
                } else {
                    btn.classList.remove('active', 'partial');
                }
            });
        }

        function updateTwitterPublisherSummary() {
            const el = document.getElementById('twitter-publisher-summary');
            const countLabel = document.getElementById('twitter-publisher-count-label');
            if (!el) return;
            const pubsInLane = [...new Set(getActiveTwitterPool().map(t => t.publisher || t.source).filter(Boolean))];
            const pubSet = new Set(pubsInLane);
            const selectedVisible = [...selectedTwitterPublishers].filter(p => pubSet.has(p));
            const n = selectedVisible.length;
            const total = pubsInLane.length;
            if (n === 0) {
                el.textContent = 'All publishers';
                if (countLabel) countLabel.textContent = '';
            } else if (n === 1) {
                el.textContent = selectedVisible[0];
                if (countLabel) countLabel.textContent = '· 1 of ' + total + ' publishers';
            } else {
                el.textContent = n + ' publishers';
                if (countLabel) countLabel.textContent = '· ' + n + ' of ' + total + ' publishers';
            }
        }

        function closeTwitterDropdown() { closeDropdownById('twitter-publisher-dropdown', 'twitter-dropdown-search', 'twitter-dropdown-list'); }

        function formatTwitterDate(isoStr) {
            if (!isoStr) return '';
            const date = new Date(isoStr);
            const now = new Date();
            const diffMs = now - date;
            const diffMin = Math.floor(diffMs / 60000);
            const diffHr = Math.floor(diffMs / 3600000);
            const diffDay = Math.floor(diffMs / 86400000);
            if (diffMin < 1) return 'Just now';
            if (diffMin < 60) return diffMin + 'm ago';
            if (diffHr < 24) return diffHr + 'h ago';
            if (diffDay === 1) return 'Yesterday';
            if (diffDay < 7) return diffDay + 'd ago';
            return date.toLocaleDateString();
        }

        function formatTwitterDateHeader(isoStr) {
            if (!isoStr) return 'Unknown Date';
            const date = new Date(isoStr);
            const now = new Date();
            const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
            const tweetDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
            const diffDays = Math.floor((today - tweetDay) / 86400000);
            if (diffDays === 0) return 'Today';
            if (diffDays === 1) return 'Yesterday';
            return date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
        }

        function applyTwitterPagination() {
            const totalPages = Math.max(1, Math.ceil(filteredTwitter.length / TWITTER_PAGE_SIZE));
            if (twitterPage > totalPages) twitterPage = totalPages;

            document.getElementById('twitter-visible-count').textContent = filteredTwitter.length;

            const start = (twitterPage - 1) * TWITTER_PAGE_SIZE;
            const end = start + TWITTER_PAGE_SIZE;
            const pageTweets = filteredTwitter.slice(start, end);

            const container = document.getElementById('twitter-container');
            if (pageTweets.length === 0) {
                container.innerHTML = '<div style="padding:40px 20px;text-align:center;color:var(--text-muted);font-size:14px;">No tweets found.</div>';
                renderTwitterPagination(totalPages);
                return;
            }

            let html = '';
            let currentDateHeader = '';

            pageTweets.forEach(t => {
                const dateHeader = formatTwitterDateHeader(t.date);
                if (dateHeader !== currentDateHeader) {
                    currentDateHeader = dateHeader;
                    html += dateHeaderHtml(dateHeader, t.date);
                }

                const title = escapeHtml(t.title);
                const source = escapeHtml(t.source);
                const tweetUrl = sanitizeUrl(t.link || '');
                const sourceUrl = sanitizeUrl(t.source_url || '') || tweetUrl;
                const bookmarkUrl = tweetUrl || sourceUrl;
                const titleHtml = tweetUrl
                    ? `<a href="${escapeForAttr(tweetUrl)}" target="_blank" rel="noopener">${title}</a>`
                    : `<span>${title}</span>`;
                const publisher = escapeHtml(t.publisher || t.source);
                const publisherHtml = sourceUrl
                    ? `<a href="${escapeForAttr(sourceUrl)}" target="_blank" rel="noopener" class="tweet-card-publisher card-source-link">${publisher}</a>`
                    : `<span class="tweet-card-publisher">${publisher}</span>`;
                const badges = getTweetBadges(t.title, t);
                const threadCollapsed = Number(t.thread_collapsed_count || 0);
                if (threadCollapsed > 0) {
                    badges.push({ label: '+' + threadCollapsed + ' merged', cls: 'tweet-badge-thread' });
                }
                const badgeHtml = badges.map(b => `<span class="tweet-badge ${b.cls}">${b.label}</span>`).join('');
                const threadHtml = threadCollapsed > 0
                    ? `<div class="tweet-card-thread-note">${threadCollapsed} similar thread posts collapsed</div>`
                    : '';
                html += `
                    <div class="tweet-card" data-publisher="${publisher}" data-url="${escapeForAttr(bookmarkUrl)}">
                        <div class="tweet-card-header">
                            <div class="tweet-card-left">
                                ${publisherHtml}
                                ${badgeHtml}
                            </div>
                            <div class="tweet-card-right">
                                ${t.date ? `<span class="tweet-card-date">${formatTwitterDate(t.date)}</span>` : ''}
                                <button class="bookmark-btn" data-url="${escapeForAttr(bookmarkUrl)}" data-title="${escapeForAttr(t.title)}" data-source="${source}" onclick="toggleGenericBookmark(this)" aria-label="Bookmark tweet" title="Bookmark">
                                    <svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                                </button>
                            </div>
                        </div>
                        <div class="tweet-card-body">${titleHtml}</div>
                        ${threadHtml}
                        <button class="tweet-expand-btn" onclick="toggleTweetExpand(this)">Show more</button>
                        ${t.image ? `<div class="tweet-card-image"><img src="${escapeForAttr(t.image)}" alt="" loading="lazy" onerror="this.parentElement.style.display='none'"></div>` : ''}
                    </div>
                `;
            });

            container.innerHTML = html;
            requestAnimationFrame(() => checkOverflow(container, '.tweet-card-body', '.tweet-expand-btn'));
            syncBookmarkState();
            renderTwitterPagination(totalPages);
        }

        function renderTwitterPagination(totalPages) {
            buildPagination('twitter-pagination-bottom', twitterPage, totalPages, (page) => {
                twitterPage = page;
                applyTwitterPagination();
                window.scrollTo({top: 0, behavior: 'smooth'});
            });
        }

        // Update relative time for all timestamped elements
        function formatTimeAgo(el) {
            if (!el || !el.dataset.time) return;
            var diff = Math.floor((new Date() - new Date(el.dataset.time)) / 1000);
            var prefix = el.id === 'twitter-update-time' ? 'Latest tweet' : 'Updated';
            var text;
            if (diff < 60) text = prefix + ' just now';
            else if (diff < 3600) text = prefix + ' ' + Math.floor(diff / 60) + ' min ago';
            else if (diff < 86400) text = prefix + ' ' + Math.floor(diff / 3600) + ' hr ago';
            else text = prefix + ' ' + Math.floor(diff / 86400) + ' day ago';
            el.textContent = text;
        }
        function updateRelativeTime() {
            formatTimeAgo(document.getElementById('update-time'));
            formatTimeAgo(document.getElementById('reports-update-time'));
            formatTimeAgo(document.getElementById('papers-update-time'));
            formatTimeAgo(document.getElementById('youtube-update-time'));
            formatTimeAgo(document.getElementById('twitter-update-time'));
            formatTimeAgo(document.getElementById('ai-updated'));
        }
        updateRelativeTime();
        setInterval(updateRelativeTime, 60000);

        // Ensure page starts at top on load
        window.addEventListener('load', () => {
            window.scrollTo(0, 0);
        });
