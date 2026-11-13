        // Stock notes globals are declared by index.html (aggregator.py). The script
        // deploys before the hourly run regenerates index.html, so default them here
        // rather than throw on a page that predates them.
        if (!('STOCK_NOTES' in window)) window.STOCK_NOTES = null;
        if (!('STOCK_NOTES_HOME' in window)) window.STOCK_NOTES_HOME = null;
        if (!('STOCK_NOTE_PUBLISHERS' in window)) window.STOCK_NOTE_PUBLISHERS = [];
        if (!('PAID_PUBLISHERS' in window)) window.PAID_PUBLISHERS = [];
        // ICRA, India Ratings: the card opens a free summary; the full report is paid (user, Nov 2026).
        function paidTagHtml(publisher) {
            return PAID_PUBLISHERS.indexOf(publisher) !== -1 ? '<span class="paid-tag" title="Full report needs a login or payment; the link opens a free summary">Paid</span>' : '';
        }

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
            if (tab === 'home' && !SLOW_READS) {
                loads.push(_safeLoad('slow_reads', 'static/tab_slow_reads.json', function(d) { SLOW_READS = d; }));
            }
            if (tab === 'home' && !CALENDAR) {
                loads.push(_safeLoad('calendar', 'static/calendar.json', function(d) { CALENDAR = d; }));
            }
            if (tab === 'home' && !STOCK_NOTES_HOME) {
                loads.push(_safeLoad('stock_notes_home', 'static/tab_stock_notes_home.json', function(d) { STOCK_NOTES_HOME = d; }));
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
                switchTab('research');   // Reports
            } else if (e.key === '3') {
                switchTab('reports');    // Telegram
            } else if (e.key === '4') {
                switchTab('youtube');
            } else if (e.key === '5') {
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

        // ==================== SHARE + "VIA FINANCE RADAR" ====================
        // Outbound article links get utm_source=financeradar.news at click time, so
        // publishers see where readers came from in their analytics. Nothing about the
        // reader is recorded. Hrefs, bookmarks and right-click "copy link" stay clean.
        // Skipped where a tag can break the link or nobody reads it: files (PDFs etc.),
        // Google News redirects, social platforms, links that already carry a tag or a
        // signature.
        var REF_SOURCE = 'financeradar.news';
        var REF_SKIP_HOSTS = /(^|\.)(google\.com|x\.com|twitter\.com|t\.me|telegram\.me|youtube\.com|youtu\.be|linkedin\.com|instagram\.com|facebook\.com|financeradar\.news)$/i;
        var REF_SKIP_PATH = /\.(pdf|xlsx?|csv|zip|pptx?|docx?)$/i;
        var REF_SKIP_QUERY = /(^|&)(utm_[a-z]+|x-amz-[a-z-]+|signature|sig|token|expires)=/i;
        function referralUrl(url, medium) {
            var u;
            try { u = new URL(url); } catch (e) { return url; }
            if (u.protocol !== 'https:' && u.protocol !== 'http:') return url;
            if (u.hostname === location.hostname || REF_SKIP_HOSTS.test(u.hostname)) return url;
            if (REF_SKIP_PATH.test(u.pathname) || REF_SKIP_QUERY.test(u.search.slice(1))) return url;
            // Append by hand: rebuilding via searchParams would re-encode the publisher's own query.
            var hash = url.indexOf('#');
            var base = hash === -1 ? url : url.slice(0, hash);
            var frag = hash === -1 ? '' : url.slice(hash);
            return base + (base.indexOf('?') === -1 ? '?' : (/[?&]$/.test(base) ? '' : '&'))
                + 'utm_source=' + REF_SOURCE + '&utm_medium=' + (medium || 'referral') + frag;
        }

        function tagOutboundLink(e) {
            if (e.button === 2) return;
            var a = e.target.closest && e.target.closest('a[href]');
            if (!a) return;
            var href = a.getAttribute('href');
            if (!/^https?:/i.test(href)) return;
            var tagged = referralUrl(href, 'referral');
            if (tagged === href) return;
            a.setAttribute('href', tagged);
            setTimeout(function() { a.setAttribute('href', href); }, 0);  // navigation already has the tagged URL
        }
        document.addEventListener('click', tagOutboundLink, true);
        document.addEventListener('auxclick', tagOutboundLink, true);

        // "Share" sits at the end of each item's source line; "Share story" on Big Stories.
        // The words come from CSS (::after), so homepage/tab search never matches "share".
        // Phones (coarse pointer + Web Share) open the phone's share menu; laptops copy.
        var SHARE_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>';

        function shareLinkHtml(url, title, source) {
            if (!sanitizeUrl(url || '')) return '';
            return '<button type="button" class="share-link" aria-label="Share"'
                + ' data-share-url="' + escapeForAttr(url) + '"'
                + ' data-share-title="' + escapeForAttr(title || '') + '"'
                + ' data-share-source="' + escapeForAttr(source || '') + '">' + SHARE_SVG + '</button>';
        }

        function bsShareStoryHtml(idx) {
            return '<button type="button" class="bs-see bs-share" aria-label="Share story" data-story="' + idx + '">' + SHARE_SVG + '</button>';
        }

        // Titles reach the buttons already HTML-escaped in some templates; undo that for plain text.
        function decodeEntities(s) {
            var t = document.createElement('textarea');
            t.innerHTML = s || '';
            return t.value;
        }

        function shareOrCopy(btn, text, title) {
            var touch = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
            if (touch && navigator.share) {
                navigator.share({ title: title, text: text }).catch(function() {});
                return;
            }
            copyTextWithFallback(text, function() {
                btn.classList.add('copied');
                setTimeout(function() { btn.classList.remove('copied'); }, 2000);
            });
        }

        function shareItemText(title, source, url) {
            return title + (source ? ' — ' + source : '') + '\n' + referralUrl(url, 'share') + '\n\nvia financeradar.news';
        }

        function shareStoryText(cluster) {
            var arts = getClusterArticles(cluster).filter(function(a) { return sanitizeUrl(a.url || ''); });
            var lines = [cluster.story_label || '', ''];
            arts.slice(0, 3).forEach(function(a) {
                lines.push('• ' + cleanHomeTitle(a.title) + ' — ' + homeSourceName(a.source, a.source_type));
                lines.push(referralUrl(a.url, 'share'));
            });
            lines.push('', (arts.length > 3 ? 'All ' + arts.length + ' sources' : 'More') + ' on financeradar.news');
            return lines.join('\n');
        }

        document.addEventListener('click', function(e) {
            var btn = e.target.closest && e.target.closest('.share-link, .bs-share');
            if (!btn) return;
            e.preventDefault();
            if (btn.classList.contains('bs-share')) {
                var cluster = bigStoriesShown[Number(btn.dataset.story)];
                if (cluster) shareOrCopy(btn, shareStoryText(cluster), cluster.story_label || 'Finance Radar');
                return;
            }
            var d = btn.dataset;
            var title = decodeEntities(d.shareTitle).trim();
            shareOrCopy(btn, shareItemText(title, decodeEntities(d.shareSource).trim(), d.shareUrl), title);
        });

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
            twitter: '#4A8A9A', youtube: '#A86565'
        };
        var BUCKET_LABELS = {
            news: 'News', telegram: 'Telegram', reports: 'Reports',
            twitter: 'Twitter', youtube: 'YouTube'
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
        let researchRegionFilter = 'all'; // 'all' | 'indian' | 'international' | 'stocknotes'
        // Broker stock notes live in their own files (static/stock_notes/), fetched in
        // pieces only when the Stock notes view is opened — see loadStockNotes().
        const RESEARCH_VIEW_IDS = { all: 'research-region-all', indian: 'research-region-indian', international: 'research-region-international', stocknotes: 'research-region-stocknotes' };


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
                    renderWeekCal();
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
                + '<div class="hero-source">' + source + signal + consensus + shareLinkHtml(url, title, source) + '</div></div>';
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
                + '<span class="compact-src">' + source + shareLinkHtml(url, title, source) + '</span></div>' + bk + '</div>';
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
                    + bk + '</div><div class="yt-channel">' + channel + shareLinkHtml(url, title, channel) + '</div></div></div>';
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
                    + '<div class="slider-card-header"><div><div class="rp-publisher">' + pub + shareLinkHtml(url, title, pub) + '</div>'
                    + '<a class="rp-title" href="' + escapeForAttr(url) + '" target="_blank" rel="noopener">' + title + '</a>'
                    + '</div>' + bk + '</div>'
                    + (regionBadge || dateStr ? '<div class="card-signals">' + regionBadge + paidTagHtml(r.publisher || r.source) + (dateStr ? '<span class="rp-date">' + dateStr + '</span>' : '') + '</div>' : '')
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
                    + '<div class="slider-card-header"><div><div class="tw-author">' + author + shareLinkHtml(url, title, author) + '</div>'
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
        var OFFICIAL_CHANNEL_NAMES = ['RBI', 'SEBI', 'DGFT', 'DGTR', 'CBIC', 'IRDAI', 'PFRDA', 'IFSCA', 'CCI', 'MCA', 'DPIIT', 'ECB', 'ADB', 'FRED', 'PIB', 'MoSPI'];
        function isOfficialChannelArticle(a) {
            var pub = (a && (a.publisher || a.source)) || '';
            for (var i = 0; i < OFFICIAL_CHANNEL_NAMES.length; i++) {
                if (pub.indexOf(OFFICIAL_CHANNEL_NAMES[i]) !== -1) return true;
            }
            return false;
        }

        // One or two plain lines per homepage section, shown from the small (i) next to its title.
        // Windows match SOURCE_WINDOWS in ai_ranker.py: news 48h, X 96h, the rest 7 days.
        var SECTION_INFO = {
            'The Big Stories': 'The day’s biggest stories, each built from several sources. AI models group the coverage; the dots show how many of them picked each story.',
            'Research Reports': 'Notes from research houses, rating agencies and think tanks, picked by AI from the past week.',
            'From the Feed': 'News from the last two days and Telegram notes from the past week, ranked by AI for what matters to Indian readers.',
            'Stock Notes': 'The newest notes from Indian brokers on single companies, with the headline from each PDF. Newest first, not ranked by AI. All of them sit in Reports → Stock notes.',
            'Slow Reads': 'Essays and long reads from independent writers. Every post from the past week, newest first. Not ranked by AI.',
            'Watch': 'Explainers and interviews from finance video channels, picked by AI from the past week.',
            'From the Source': 'Straight from RBI, SEBI, PIB and other official bodies: releases, orders and data, newest first. Not ranked by AI.',
            'Voices': 'Posts on X from economists, journalists and market watchers, picked by AI from the past four days.',
            'This Week': 'India’s data releases, policy dates, market dates and results from Nifty 200 companies, plus the main global events. Dates come from NSE and the agencies’ own calendars; companies can move theirs. Times IST.',
            'More from the feed': 'The rest of the AI-ranked news and Telegram notes. Scroll inside the box.'
        };
        var INFO_ICON = '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8.2" cy="4.2" r="1.15" stroke="none"/><path d="M6.6 7.3h1.9v4.9M6.4 12.2h3.6" fill="none" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';
        function infoTip(label) {
            var text = SECTION_INFO[label];
            if (!text) return '';
            return '<button class="info-btn" type="button" data-info="' + escapeForAttr(text) + '"'
                + ' aria-label="About ' + escapeForAttr(label) + ': ' + escapeForAttr(text) + '" aria-expanded="false">' + INFO_ICON + '</button>';
        }

        // The explanation floats in one fixed element placed under the (i) and kept inside the
        // screen, so it never pushes the page or makes it scroll sideways. Hover or focus shows
        // it; a tap pins it until the next tap anywhere.
        var infoPop = null, infoFor = null, infoPinned = false;
        function showInfo(btn, pin) {
            if (!infoPop) {
                infoPop = document.createElement('div');
                infoPop.className = 'info-pop';
                infoPop.setAttribute('role', 'tooltip');
                document.body.appendChild(infoPop);
            }
            if (infoFor && infoFor !== btn) infoFor.setAttribute('aria-expanded', 'false');
            infoFor = btn;
            infoPinned = !!pin;
            infoPop.textContent = btn.dataset.info || '';
            infoPop.hidden = false;
            btn.setAttribute('aria-expanded', 'true');
            var r = btn.getBoundingClientRect();
            var vw = document.documentElement.clientWidth;
            var w = infoPop.offsetWidth;
            var left = Math.min(Math.max(12, r.left - 12), vw - w - 12);
            infoPop.style.left = left + 'px';
            infoPop.style.top = (r.bottom + 8) + 'px';
            infoPop.style.setProperty('--arrow', Math.round(r.left + r.width / 2 - left) + 'px');
        }
        function hideInfo() {
            if (infoPop) infoPop.hidden = true;
            if (infoFor) infoFor.setAttribute('aria-expanded', 'false');
            infoFor = null;
            infoPinned = false;
        }
        document.addEventListener('mouseover', function(e) {
            var b = e.target.closest && e.target.closest('.info-btn');
            if (b && !infoPinned && window.matchMedia('(hover: hover)').matches) showInfo(b, false);
        });
        document.addEventListener('mouseout', function(e) {
            var b = e.target.closest && e.target.closest('.info-btn');
            if (b && b === infoFor && !infoPinned && !b.contains(e.relatedTarget)) hideInfo();
        });
        document.addEventListener('focusin', function(e) {
            if (e.target.classList && e.target.classList.contains('info-btn')) showInfo(e.target, false);
        });
        document.addEventListener('focusout', function(e) {
            if (e.target === infoFor && !infoPinned) hideInfo();
        });
        document.addEventListener('click', function(e) {
            var b = e.target.closest && e.target.closest('.info-btn');
            if (b) {
                if (b === infoFor && infoPinned) hideInfo(); else showInfo(b, true);
                return;
            }
            if (infoFor) hideInfo();
        });
        document.addEventListener('keydown', function(e) { if (e.key === 'Escape' && infoFor) hideInfo(); });
        window.addEventListener('scroll', function() { if (infoFor) hideInfo(); }, { passive: true });

        function sliderHead(label, note, trackId) {
            return '<div class="slider-header"><h2 class="slider-label">' + escapeHtml(label) + '</h2>' + infoTip(label)
                + (note ? '<span class="slider-note">' + escapeHtml(note) + '</span>' : '')
                + '<div class="slider-nav">' + sliderArrows(trackId) + '</div></div>';
        }

        var RBI_ALWAYS_SOURCES = { 'RBI — Bulletin': true, 'RBI — Speeches': true };
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
            out = out.slice(0, 25);
            seen = {};
            out.forEach(function(o) { var k = String(o.url || '').toLowerCase().trim(); if (k) seen[k] = true; });
            // RBI's monthly Bulletin (incl. State of the Economy) and its speeches land a
            // few times a month, so the busy daily feeds would push them out of the newest
            // 25 within a day. Always list the last 35 days of them, in date order.
            (NEWS_ARTICLES || []).forEach(function(a) {
                if (RBI_ALWAYS_SOURCES[a.source] !== true) return;
                if (new Date(a.date || 0).getTime() < Date.now() - 35 * 86400000) return;
                add(a.title, a.link || a.source_url || '', a.publisher || a.source, a.date);
            });
            out.sort(function(a, b) {
                return new Date(b.date || 0).getTime() - new Date(a.date || 0).getTime();
            });
            return out;
        }

        // From the Source: a list, not a strip — source (RBI / SEBI / PIB) | headline | date | bookmark.
        // The list sits in a fixed-height box (~8 rows) that scrolls on its own, so the page never jumps.
        // One fixed colour per issuer, so RBI always looks like RBI.
        var ISSUERS = [
            { re: /\bRBI\b|Reserve Bank/i, code: 'RBI', c: '#2F5D8A' },
            { re: /\bSEBI\b/i, code: 'SEBI', c: '#7A4E8C' },
            { re: /\bDGFT\b|Foreign Trade/i, code: 'DGFT', c: '#8C3F55' },
            { re: /\bDGTR\b|Trade Remedies/i, code: 'DGTR', c: '#A14A3B' },
            { re: /\bCBIC\b|Customs/i, code: 'CBIC', c: '#5C6E2E' },
            { re: /\bIRDAI\b/i, code: 'IRDAI', c: '#3A6F9A' },
            { re: /\bPFRDA\b/i, code: 'PFRDA', c: '#6A5A9C' },
            { re: /\bIFSCA\b/i, code: 'IFSCA', c: '#2E7A8C' },
            { re: /\bCCI\b|Competition Commission/i, code: 'CCI', c: '#8A4F7D' },
            { re: /\bMCA\b|Corporate Affairs/i, code: 'MCA', c: '#7A6A3A' },
            { re: /\bDPIIT\b/i, code: 'DPIIT', c: '#9C5B2E' },
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
                    + '<span class="source-row-main">' + link + '<span class="source-row-pub">' + src + shareLinkHtml(url, title, src) + '</span></span>'
                    + '<span class="source-row-date">' + dateStr + '</span>'
                    + npBookmarkBtn(url, title, src) + '</li>';
            }).join('');
            counts.sort(function(a, b) { return b.n - a.n; });
            const strip = '<div class="issuer-strip">' + counts.map(function(x) {
                return '<span class="issuer-count"><span class="issuer-dot" style="background:' + x.iss.c + '"></span>' + escapeHtml(x.iss.code) + ' <b>' + x.n + '</b></span>';
            }).join('') + '</div>';
            return '<section class="slider-section source-list">'
                + '<div class="slider-header"><h2 class="slider-label">From the Source</h2>' + infoTip('From the Source')
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
                    + '<div class="slider-card-header"><div><div class="rp-publisher">' + src + shareLinkHtml(url, title, src) + '</div>'
                    + '<a class="rp-title" href="' + escapeForAttr(url) + '" target="_blank" rel="noopener">' + title + '</a>'
                    + (dateStr ? '<span class="rp-region">' + dateStr + '</span>' : '')
                    + '</div>' + bk + '</div></div></div>';
            }).join('');
            return '<section class="slider-section">'
                + sliderHead('Slow Reads', items.length + ' this week', 'slow-track')
                + '<div class="slider-track" id="slow-track">' + cards + '</div></section>';
        }

        // Stock Notes — newest single-company broker notes (static/tab_stock_notes_home.json,
        // ~30 items). Chronological, NOT AI-ranked. Sits just above the quote before From the Source.
        function buildStockNotesSlider(items) {
            if (!items || !items.length) return '';
            const cards = items.map(function(n) {
                const title = escapeHtml(n.title || '');
                const url = sanitizeUrl(n.link || '');
                const broker = escapeHtml(n.publisher || 'Broker');
                const dateStr = n.date ? escapeHtml(new Date(n.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })) : '';
                const bk = npBookmarkBtn(url, title, broker);
                return '<div class="slider-card slider-rp"><div class="slider-card-body">'
                    + '<div class="slider-card-header"><div><div class="rp-publisher">' + broker + shareLinkHtml(url, title, broker) + '</div>'
                    + '<a class="rp-title" href="' + escapeForAttr(url) + '" target="_blank" rel="noopener">' + title + '</a>'
                    + '</div>' + bk + '</div>'
                    + (dateStr ? '<div class="card-signals"><span class="rp-date">' + dateStr + '</span></div>' : '')
                    + '</div></div>';
            }).join('');
            return '<section class="slider-section">'
                + sliderHead('Stock Notes', 'from Indian brokers, newest first', 'sn-track')
                + '<div class="slider-track" id="sn-track">' + cards + '</div></section>';
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
                + shareLinkHtml(url, '“' + quote + '”', who.name)
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
                + (angle ? '<span class="bs-angle">· ' + escapeHtml(angle) + '</span>' : '')
                + shareLinkHtml(aUrl, aTitle, homeSourceName(a.source, a.source_type))
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
                + '<div class="section-divider"><span class="head-title"><span class="section-label">The Big Stories</span>' + infoTip('The Big Stories') + '</span>' + bsLegend() + '</div>'
                + '<article class="bs-lead"><div class="bs-lead-main">' + bsKick(lead, leadArts, 0) + bsTitle(lead, 0, 'h2')
                + (leadSummary ? '<p class="bs-sum">' + escapeHtml(leadSummary) + '</p>' : '') + '</div>'
                + '<div class="bs-cover"><h3>Coverage</h3><ul class="bs-srcs">'
                + leadArts.slice(0, BIG_STORY_COVERAGE).map(bsSource).join('') + '</ul>'
                + bsShow(0, leadArts.length > BIG_STORY_COVERAGE ? 'See all ' + leadArts.length + ' sources' : 'Open in the panel') + bsShareStoryHtml(0)
                + '</div></article>';

            if (two.length) {
                html += '<div class="bs-two">' + two.map(function(c, i) {
                    var arts = getClusterArticles(c);
                    var sum = clusterSummary(c);
                    return '<article>' + bsKick(c, arts, i + 1) + bsTitle(c, i + 1, 'h3')
                        + (sum ? '<p class="bs-sum bs-clamp3">' + escapeHtml(sum) + '</p>' : '')
                        + bsShow(i + 1, 'Show sources') + bsShareStoryHtml(i + 1) + '</article>';
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
                + (sum ? '<p class="bs-sum">' + escapeHtml(sum) + '</p>' : '') + bsShareStoryHtml(idx) + '</div>'
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
            return '<div class="section-divider"><span class="section-label">' + escapeHtml(text) + '</span>' + infoTip(text)
                + (note ? '<span class="section-note">' + escapeHtml(note) + '</span>' : '') + '</div>';
        }


        // ==================== THIS WEEK (homepage calendar) ====================
        // static/calendar.json, written every hour by calendar_events.py: India data
        // releases, policy dates, market dates, the main global events and Nifty 200
        // results. One list of days, shown three ways by screen width (style.css):
        //   ≥1600px  a rail in the right margin that stays in view (.wk-wide)
        //   769–1599 a folded column of day chips on the right edge (.wk-fold + popover)
        //   ≤768px   a strip of day chips under the tabs (.wk-strip), and once it has
        //            scrolled away a "next" chip in the top bar (.wk-chip)
        // The full calendar and a phone's single day open in the story drawer's frame.
        var CALENDAR = null;
        var WK_KIND_ORDER = ['big', 'india', 'policy', 'market', 'global', 'results'];
        var WK_FILTERS = [['all', 'All'], ['india', 'India data'], ['policy', 'Policy'], ['results', 'Results'], ['market', 'Market'], ['global', 'Global']];
        var WK_DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
        var WK_DOW_LONG = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
        var WK_MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        var WK_AHEAD_DAYS = 9;      // the rail/strip look this far ahead...
        var WK_MAX_DAYS = 6;        // ...and show today plus up to five days with something on
        var WK_DRAWER_DAYS = 28;    // the full calendar: four weeks
        var WK_CAL_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4.5" width="18" height="16.5" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M8 2.5v4M16 2.5v4M3 10h18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
        var WK_ARROW_L = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3.5L5.5 8l4.5 4.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
        var WK_ARROW_R = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3.5L10.5 8 6 12.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
        var wkFilter = 'all';
        var wkDrawerState = null;
        var wkDrawerReturnFocus = null;

        // Dates are IST calendar days ("2026-11-12"), whatever the reader's own time zone.
        function wkIstNow() { return new Date(Date.now() + 330 * 60000); }
        function wkTodayIST() { return wkIstNow().toISOString().slice(0, 10); }
        function wkDate(ds) { var p = ds.split('-'); return new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])); }
        function wkAddDays(ds, n) { var d = wkDate(ds); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); }
        function wkDow(ds, today) { return ds === today ? 'Today' : WK_DOW[wkDate(ds).getUTCDay()]; }
        function wkShortLabel(ds, today) {
            var d = wkDate(ds);
            return (ds === today ? 'Today · ' : '') + WK_DOW[d.getUTCDay()] + ' ' + d.getUTCDate();
        }
        function wkLongLabel(ds, today) {
            var d = wkDate(ds);
            var s = WK_DOW_LONG[d.getUTCDay()] + ' ' + d.getUTCDate() + ' ' + WK_MON[d.getUTCMonth()];
            return ds === today ? 'Today · ' + s : s;
        }
        function wkTime(t) {
            if (!t) return '';
            var p = t.split(':'), h = +p[0];
            var ap = h >= 12 ? 'pm' : 'am';
            h = h % 12 || 12;
            return h + (p[1] !== '00' ? ':' + p[1] : '') + ' ' + ap;
        }
        function wkMeta(e, long) {
            var parts = [];
            if (e.time) parts.push(wkTime(e.time));
            if (long && e.source) parts.push(e.source);
            if (e.expected) parts.push('expected');
            return parts.join(' · ');
        }
        function wkAllDays() {
            if (!CALENDAR || !Array.isArray(CALENDAR.days)) return [];
            var today = wkTodayIST();
            return CALENDAR.days.filter(function(d) { return d && d.date >= today; }).map(function(d) {
                return { date: d.date, events: d.events || [], results: d.results || [] };
            });
        }
        function wkUpcoming(today) {
            var last = wkAddDays(today, WK_AHEAD_DAYS);
            var days = wkAllDays();
            var first = days.filter(function(d) { return d.date === today; })[0] || { date: today, events: [], results: [] };
            var out = [first];
            days.forEach(function(d) {
                if (d.date !== today && d.date <= last && out.length < WK_MAX_DAYS) out.push(d);
            });
            return out;
        }
        function wkMarks(day) {
            var seen = {};
            day.events.forEach(function(e) { seen[e.big ? 'big' : e.kind] = 1; });
            if (day.results.length) seen.results = 1;
            return WK_KIND_ORDER.filter(function(k) { return seen[k]; }).slice(0, 3);
        }
        function wkMk(kind) { return '<span class="wk-mk wk-mk-' + kind + '" aria-hidden="true"></span>'; }
        function wkEventRow(e, long) {
            var meta = wkMeta(e, long);
            return '<li class="wk-ev">' + wkMk(e.big ? 'big' : e.kind) + '<span><b>' + escapeHtml(e.name) + '</b>'
                + (meta ? ' <span class="wk-meta">' + escapeHtml(meta) + '</span>' : '') + '</span></li>';
        }
        // Results: the first n names (Nifty 50 first), then "+N more" opening the full list.
        function wkResultsRow(day, n) {
            if (!day.results.length) return '';
            var names = n ? day.results.slice(0, n) : day.results;
            var more = day.results.length - names.length;
            return '<li class="wk-ev wk-res">' + wkMk('results') + '<span><b>Results</b> '
                + escapeHtml(names.join(', '))
                + (more > 0 ? ' <button type="button" class="wk-more" data-wk-day="' + day.date + '">+' + more + ' more</button>' : '')
                + '</span></li>';
        }
        function wkDayList(day, n, long) {
            if (!day.events.length && !day.results.length) return '<p class="wk-none">Nothing scheduled</p>';
            return '<ul class="wk-evs">' + day.events.map(function(e) { return wkEventRow(e, long); }).join('')
                + wkResultsRow(day, n) + '</ul>';
        }
        function wkAria(day, today) {
            var bits = day.events.map(function(e) { return e.name; });
            if (day.results.length) bits.push('results from ' + day.results.length + ' Nifty 200 companies');
            return wkLongLabel(day.date, today) + ': ' + (bits.length ? bits.join(', ') : 'nothing scheduled');
        }
        function wkChipBtn(day, today, cls) {
            var d = wkDate(day.date);
            return '<button type="button" class="' + cls + (day.date === today ? ' is-today' : '') + '" data-wk-day="' + day.date + '"'
                + ' aria-label="' + escapeForAttr(wkAria(day, today)) + '">'
                + '<span class="wk-c-dow">' + wkDow(day.date, today) + '</span>'
                + '<span class="wk-c-num">' + d.getUTCDate() + '</span>'
                + '<span class="wk-c-mks">' + wkMarks(day).map(wkMk).join('') + '</span></button>';
        }
        function wkFootHtml() {
            return '<div class="wk-foot"><button type="button" class="wk-full wk-link">Full calendar →</button>'
                + '<a class="wk-ics" href="static/calendar.ics" download="financeradar-this-week.ics">Add to my calendar</a></div>';
        }

        function wkWideHtml(days, today) {
            return '<aside class="wk-wide" aria-labelledby="wk-title"><div class="wk-wide-in">'
                + '<div class="wk-head"><h2 class="wk-title" id="wk-title">This Week</h2>' + infoTip('This Week') + '</div>'
                + '<ol class="wk-days">' + days.map(function(d) {
                    return '<li class="wk-day' + (d.date === today ? ' is-today' : '') + '"><span class="wk-dl">'
                        + wkShortLabel(d.date, today) + '</span>' + wkDayList(d, 3, false) + '</li>';
                }).join('') + '</ol>' + wkFootHtml() + '</div></aside>';
        }
        function wkFoldHtml(days, today) {
            return '<nav class="wk-fold" aria-label="This week">'
                + days.map(function(d) { return wkChipBtn(d, today, 'wk-c wk-fd'); }).join('')
                + '<button type="button" class="wk-fold-all wk-full" aria-label="Open the full calendar">' + WK_CAL_ICON + '</button></nav>';
        }
        function wkStripHtml(days, today) {
            return '<section class="wk-strip" aria-label="This week"><div class="wk-strip-head"><span class="wk-strip-title">This week</span>'
                + '<button type="button" class="wk-full wk-link">Full calendar →</button></div>'
                + '<div class="wk-strip-days">' + days.map(function(d) { return wkChipBtn(d, today, 'wk-c wk-sd'); }).join('') + '</div></section>';
        }

        // The top bar's "next" chip (phones, once the strip has scrolled away): the next
        // market-moving release in the coming week, else the next event in three days.
        function wkNext(today) {
            var now = wkIstNow(), mins = now.getUTCHours() * 60 + now.getUTCMinutes();
            var cands = [];
            wkAllDays().forEach(function(d) {
                d.events.forEach(function(e) {
                    if (d.date === today && e.time) {
                        var p = e.time.split(':');
                        if (+p[0] * 60 + +p[1] < mins) return;  // already out
                    }
                    cands.push({ day: d.date, e: e });
                });
            });
            var big = cands.filter(function(c) { return c.e.big && c.day <= wkAddDays(today, 7); })[0];
            return big || cands.filter(function(c) { return c.day <= wkAddDays(today, 3); })[0] || null;
        }
        function wkChipUpdate(next, today) {
            var nav = document.querySelector('.utility-nav');
            var chip = document.getElementById('wk-chip');
            if (!next) { if (chip) chip.remove(); return; }
            if (!chip && nav) {
                chip = document.createElement('button');
                chip.type = 'button';
                chip.id = 'wk-chip';
                chip.className = 'wk-chip wk-full';
                nav.insertBefore(chip, nav.firstChild);
            }
            if (!chip) return;
            var label = next.e.short || String(next.e.name).split(',')[0];
            var when = next.day === today ? (next.e.time ? wkTime(next.e.time) : 'today') : WK_DOW[wkDate(next.day).getUTCDay()];
            chip.innerHTML = wkMk(next.e.big ? 'big' : next.e.kind) + '<span><b>' + escapeHtml(label) + '</b> ' + escapeHtml(when) + '</span>';
            chip.setAttribute('aria-label', 'Next: ' + next.e.name + ', ' + wkLongLabel(next.day, today) + (next.e.time ? ' ' + wkTime(next.e.time) : '') + '. Open the calendar');
        }
        var wkStripObserver = null;
        function wkObserveStrip(strip) {
            if (wkStripObserver) wkStripObserver.disconnect();
            document.body.classList.remove('wk-strip-off');
            if (!strip || !window.IntersectionObserver) return;
            var head = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--head-h'), 10) || 0;
            wkStripObserver = new IntersectionObserver(function(entries) {
                var en = entries[0];
                // Off = scrolled up past the top bar (not merely hidden by another tab).
                var off = !en.isIntersecting && en.boundingClientRect.top < head && en.boundingClientRect.height > 0;
                document.body.classList.toggle('wk-strip-off', off);
            }, { rootMargin: '-' + head + 'px 0px 0px 0px' });
            wkStripObserver.observe(strip);
        }

        // Two hosts. The phone strip scrolls with the page, so it lives in the Home tab.
        // The margin rail and the folded column are position: fixed, so they live in
        // <body>: the tab's fade-in animates `transform`, and a transformed ancestor
        // pins fixed children to itself — the rail sat over the text for half a second
        // after every switch back to Home. CSS shows #week-cal-side only on Home.
        function renderWeekCal() {
            var host = document.getElementById('week-cal');
            if (!host) {
                var tabHome = document.getElementById('tab-home');
                var paper = document.getElementById('home-newspaper');
                if (!tabHome || !paper) return;
                host = document.createElement('div');
                host.id = 'week-cal';
                host.className = 'wk';
                tabHome.insertBefore(host, paper);
            }
            var side = document.getElementById('week-cal-side');
            if (!side) {
                side = document.createElement('div');
                side.id = 'week-cal-side';
                document.body.appendChild(side);
            }
            hideWkPop();
            if (!CALENDAR) {
                host.classList.remove('wk-ready'); host.innerHTML = '';
                side.classList.remove('wk-ready'); side.innerHTML = '';
                wkChipUpdate(null);
                return;
            }
            var today = wkTodayIST();
            var days = wkUpcoming(today);
            host.innerHTML = wkStripHtml(days, today);
            side.innerHTML = wkWideHtml(days, today) + wkFoldHtml(days, today);
            host.classList.add('wk-ready');
            side.classList.add('wk-ready');
            wkChipUpdate(wkNext(today), today);
            wkObserveStrip(host.querySelector('.wk-strip'));
        }

        // Popover for the folded rail: hover or focus shows a day, a click pins it.
        var wkPop = null, wkPopFor = null, wkPopPinned = false, wkPopTimer = null;
        function showWkPop(btn, pin) {
            var day = wkAllDays().filter(function(d) { return d.date === btn.dataset.wkDay; })[0]
                || { date: btn.dataset.wkDay, events: [], results: [] };
            var today = wkTodayIST();
            if (!wkPop) {
                wkPop = document.createElement('div');
                wkPop.className = 'wk-pop';
                wkPop.addEventListener('mouseenter', function() { clearTimeout(wkPopTimer); });
                wkPop.addEventListener('mouseleave', function() { if (!wkPopPinned) wkPopTimer = setTimeout(hideWkPop, 160); });
                document.body.appendChild(wkPop);
            }
            clearTimeout(wkPopTimer);
            if (wkPopFor && wkPopFor !== btn) wkPopFor.classList.remove('is-open');
            wkPopFor = btn;
            wkPopPinned = !!pin;
            btn.classList.add('is-open');
            wkPop.innerHTML = '<p class="wk-pop-day">' + wkLongLabel(day.date, today) + '</p>' + wkDayList(day, 3, true)
                + '<button type="button" class="wk-full wk-link">Full calendar →</button>';
            wkPop.style.display = 'block';
            var r = btn.getBoundingClientRect();
            var top = Math.max(8, Math.min(r.top - 8, window.innerHeight - wkPop.offsetHeight - 8));
            wkPop.style.top = top + 'px';
            wkPop.style.right = (window.innerWidth - r.left + 10) + 'px';
        }
        function hideWkPop() {
            clearTimeout(wkPopTimer);
            if (wkPop) wkPop.style.display = 'none';
            if (wkPopFor) wkPopFor.classList.remove('is-open');
            wkPopFor = null;
            wkPopPinned = false;
        }
        document.addEventListener('mouseover', function(e) {
            var fd = e.target.closest && e.target.closest('.wk-fd');
            if (fd && !wkPopPinned) showWkPop(fd, false);
        });
        document.addEventListener('mouseout', function(e) {
            var fd = e.target.closest && e.target.closest('.wk-fd');
            if (fd && !wkPopPinned && !(e.relatedTarget && wkPop && wkPop.contains(e.relatedTarget))) {
                wkPopTimer = setTimeout(hideWkPop, 160);
            }
        });
        document.addEventListener('focusin', function(e) {
            var fd = e.target.closest && e.target.closest('.wk-fd');
            if (fd) showWkPop(fd, false);
        });

        // Full calendar ('all') or one day ('day', phones). Same frame as the story drawer.
        function wkWeekLabel(monday, today) {
            var sun = wkAddDays(monday, 6), a = wkDate(monday), b = wkDate(sun);
            var range = a.getUTCMonth() === b.getUTCMonth()
                ? a.getUTCDate() + '–' + b.getUTCDate() + ' ' + WK_MON[b.getUTCMonth()]
                : a.getUTCDate() + ' ' + WK_MON[a.getUTCMonth()] + ' – ' + b.getUTCDate() + ' ' + WK_MON[b.getUTCMonth()];
            var thisMon = wkMonday(today);
            if (monday === thisMon) return 'This week · ' + range;
            if (monday === wkAddDays(thisMon, 7)) return 'Next week · ' + range;
            return range;
        }
        function wkMonday(ds) { var dow = (wkDate(ds).getUTCDay() + 6) % 7; return wkAddDays(ds, -dow); }
        function wkFiltered(day) {
            if (wkFilter === 'all') return day;
            if (wkFilter === 'results') return { date: day.date, events: [], results: day.results };
            return { date: day.date, events: day.events.filter(function(e) { return e.kind === wkFilter; }), results: [] };
        }
        function renderCalDrawer() {
            var wrap = document.getElementById('cal-drawer');
            if (!wrap || !wkDrawerState) return;
            var today = wkTodayIST();
            var head = wrap.querySelector('.wk-dr-headin'), body = wrap.querySelector('.wk-dr-body'), foot = wrap.querySelector('.wk-dr-foot');
            if (wkDrawerState.mode === 'day') {
                var ds = wkDrawerState.day;
                var day = wkAllDays().filter(function(d) { return d.date === ds; })[0] || { date: ds, events: [], results: [] };
                head.innerHTML = '<div class="wk-dr-step"><button type="button" class="wk-step" data-wk-step="-1" aria-label="Previous day"' + (ds <= today ? ' disabled' : '') + '>' + WK_ARROW_L + '</button>'
                    + '<h2 class="bs-title" id="wk-dr-title">' + wkLongLabel(ds, today) + '</h2>'
                    + '<button type="button" class="wk-step" data-wk-step="1" aria-label="Next day"' + (ds >= wkAddDays(today, WK_DRAWER_DAYS) ? ' disabled' : '') + '>' + WK_ARROW_R + '</button></div>';
                body.innerHTML = wkDayList(day, 0, true);
                foot.innerHTML = '<button type="button" class="wk-full wk-link">See the whole calendar →</button>';
                return;
            }
            head.innerHTML = '<h2 class="bs-title" id="wk-dr-title">Calendar</h2>'
                + '<p class="bs-sum">Next four weeks: India data, policy dates, Nifty 200 results and the main global events. Times IST.</p>'
                + '<div class="wk-filters" role="group" aria-label="Show">' + WK_FILTERS.map(function(f) {
                    return '<button type="button" class="wk-filter' + (wkFilter === f[0] ? ' is-on' : '') + '" data-wk-filter="' + f[0] + '" aria-pressed="' + (wkFilter === f[0]) + '">' + f[1] + '</button>';
                }).join('') + '</div>';
            var last = wkAddDays(today, WK_DRAWER_DAYS);
            var weeks = [], cur = null;
            wkAllDays().forEach(function(d) {
                if (d.date > last) return;
                var f = wkFiltered(d);
                if (!f.events.length && !f.results.length) return;
                var mon = wkMonday(d.date);
                if (!cur || cur.mon !== mon) { cur = { mon: mon, days: [] }; weeks.push(cur); }
                cur.days.push(f);
            });
            body.innerHTML = weeks.length ? weeks.map(function(w) {
                return '<section class="wk-dr-week"><h3>' + wkWeekLabel(w.mon, today) + '</h3>' + w.days.map(function(d) {
                    return '<div class="wk-dr-day' + (d.date === today ? ' is-today' : '') + '" data-wk-anchor="' + d.date + '"><span class="wk-dl">'
                        + wkShortLabel(d.date, today) + '</span>' + wkDayList(d, 0, true) + '</div>';
                }).join('') + '</section>';
            }).join('') : '<p class="wk-none">Nothing in the next four weeks.</p>';
            foot.innerHTML = '<a class="wk-ics" href="static/calendar.ics" download="financeradar-this-week.ics">' + WK_CAL_ICON + 'Add to my calendar</a>'
                + '<span class="wk-note">Companies can move their dates. “expected” = not confirmed yet.</span>';
            if (wkDrawerState.day) {
                var target = body.querySelector('[data-wk-anchor="' + wkDrawerState.day + '"]');
                if (target) body.scrollTop = target.offsetTop - body.offsetTop - 8;
                wkDrawerState.day = null;
            }
        }
        function openCalDrawer(mode, ds) {
            hideWkPop();
            var existing = document.getElementById('cal-drawer');
            if (existing) { wkDrawerState = { mode: mode, day: ds || null }; renderCalDrawer(); return; }
            if (document.getElementById('story-drawer')) closeStoryDrawer(true);
            wkDrawerReturnFocus = document.activeElement;
            wkDrawerState = { mode: mode, day: ds || null };
            var wrap = document.createElement('div');
            wrap.id = 'cal-drawer';
            wrap.innerHTML = '<div class="bs-scrim" data-wk-close></div>'
                + '<aside class="bs-drawer wk-drawer" role="dialog" aria-modal="true" aria-labelledby="wk-dr-title">'
                + '<div class="bs-dr-head"><button class="bs-x" type="button" data-wk-close aria-label="Close">' + BS_CLOSE + '</button><div class="wk-dr-headin"></div></div>'
                + '<div class="bs-dr-body wk-dr-body"></div><div class="wk-dr-foot"></div></aside>';
            document.body.appendChild(wrap);
            lockBodyScroll();
            renderCalDrawer();
            wrap.querySelector('.bs-x').focus({ preventScroll: true });
        }
        function closeCalDrawer() {
            var el = document.getElementById('cal-drawer');
            if (!el) return;
            el.remove();
            unlockBodyScroll();
            wkDrawerState = null;
            if (wkDrawerReturnFocus && document.contains(wkDrawerReturnFocus)) wkDrawerReturnFocus.focus({ preventScroll: true });
        }

        document.addEventListener('click', function(e) {
            var t = e.target.closest ? e.target : null;
            if (!t) return;
            var el;
            if ((el = t.closest('[data-wk-close]'))) { closeCalDrawer(); return; }
            if ((el = t.closest('[data-wk-filter]'))) { wkFilter = el.dataset.wkFilter; renderCalDrawer(); return; }
            if ((el = t.closest('[data-wk-step]')) && wkDrawerState) {
                wkDrawerState.day = wkAddDays(wkDrawerState.day, +el.dataset.wkStep);
                renderCalDrawer();
                return;
            }
            if ((el = t.closest('.wk-more'))) { openCalDrawer('all', el.dataset.wkDay); return; }
            if ((el = t.closest('.wk-sd'))) { openCalDrawer('day', el.dataset.wkDay); return; }
            if ((el = t.closest('.wk-fd'))) {
                if (wkPopFor === el && wkPopPinned) hideWkPop(); else showWkPop(el, true);
                return;
            }
            if ((el = t.closest('.wk-full'))) {
                // In the phone's day view, "See the whole calendar" switches the open drawer.
                if (wkDrawerState && wkDrawerState.mode === 'day') { wkDrawerState = { mode: 'all', day: wkDrawerState.day }; renderCalDrawer(); return; }
                openCalDrawer('all');
                return;
            }
            if (wkPop && wkPop.style.display === 'block' && !wkPop.contains(t)) hideWkPop();
        });
        document.addEventListener('keydown', function(e) {
            if (e.key !== 'Escape') return;
            if (document.getElementById('cal-drawer')) closeCalDrawer();
            else if (wkPop && wkPop.style.display === 'block') hideWkPop();
        });
        window.addEventListener('resize', hideWkPop);

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
            // news → quote → Watch → news → Stock Notes → quote → From the Source → Voices → quote → news.
            // Voices sits directly under From the Source (user request, Oct 2026).
            const parts = [];

            // Big Stories at the very top
            if (clusters.length > 0) {
                parts.push(renderBigStories(clusters));
            }

            // Research Reports leads the sliders, then the feed label
            parts.push(
                breakers[0],
                // Broker notes have their own slider; keep any older picks from those feeds out of here.
                buildRpSlider(result.reports.filter(r => STOCK_NOTE_PUBLISHERS.indexOf(r.publisher || r.source) === -1))
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
                buildStockNotesSlider(STOCK_NOTES_HOME),
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
            const wasNotes = researchRegionFilter === 'stocknotes';
            researchRegionFilter = 'all';
            researchPage = 1;
            if (wasNotes && RESEARCH_REPORTS) initResearchPublisherDropdown();
            syncResearchCheckboxes();
            syncResearchPublisherSummary();
            syncResearchViewButtons();
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
                    + shareLinkHtml(a.link, deshoutTitle(a.title), a.source)
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
                                ${shareLinkHtml(reportUrl, bookmarkTitleRaw || (r.text || '').slice(0, 120), r.channel || '')}
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
            filterResearch();
        }

        const isStockNote = r => r.kind === 'stock_note';

        // Archive rows → the research-card shape. Title = company — the PDF's own
        // headline; either alone when that's all there is (company until the
        // headline is read; a multi-stock daily like "First Light | …" has no company).
        function toStockNoteCard(n) {
            return {
                title: [n.company, n.headline].filter(Boolean).join(' — '),
                company: n.company || '',
                headline: n.headline || '',
                link: n.link,
                date: n.date ? n.date + 'T00:00:00+05:30' : null,
                publisher: n.broker,
                source: n.via || '',
                source_url: '',
                description: '',
                region: 'Indian',
                kind: 'stock_note',
            };
        }

        // Stock notes load in pieces so the first page shows at once (user, 11 Nov
        // 2026): static/stock_notes/recent.json holds the newest ~10 pages plus the
        // broker list; a year file (static/stock_notes/<year>.json) is fetched only
        // when someone pages near the end of what's loaded, searches, or picks brokers.
        let stockNoteYearsLeft = null;   // years not fetched yet, newest first
        let stockNoteBrokers = [];
        const stockNoteLinks = new Set();
        let stockNoteYearLoad = null;

        function addStockNotes(list) {
            (Array.isArray(list) ? list : []).forEach(function(n) {
                if (!n || !n.link || stockNoteLinks.has(n.link)) return;
                stockNoteLinks.add(n.link);
                STOCK_NOTES.push(toStockNoteCard(n));
            });
        }

        function loadStockNotes() {
            if (STOCK_NOTES) return Promise.resolve();
            return _safeLoad('stock_notes_recent', 'static/stock_notes/recent.json', function(d) {
                STOCK_NOTES = [];
                stockNoteBrokers = d.brokers || [];
                stockNoteYearsLeft = (d.years || []).slice();
                addStockNotes(d.notes);
            }).then(function() {
                if (!STOCK_NOTES) { STOCK_NOTES = []; stockNoteYearsLeft = []; }
            });
        }

        // Next year's notes (or every remaining year). Year files arrive newest
        // first and each is sorted, so appending keeps the list in date order.
        function loadMoreStockNotes(all) {
            if (stockNoteYearLoad) return stockNoteYearLoad;
            if (!stockNoteYearsLeft || !stockNoteYearsLeft.length) return Promise.resolve(false);
            const years = all ? stockNoteYearsLeft.splice(0) : stockNoteYearsLeft.splice(0, 1);
            stockNoteYearLoad = Promise.all(years.map(function(y) {
                return loadTabData('stock_notes_' + y, 'static/stock_notes/' + y + '.json');
            })).then(function(lists) {
                lists.forEach(addStockNotes);
                stockNoteYearLoad = null;
                return true;
            });
            return stockNoteYearLoad;
        }

        function refreshStockNotes() {
            if (researchRegionFilter === 'stocknotes') filterResearch(true);
        }

        // "By company" (user, 11 Nov 2026): every company with a note in the last
        // 3 months, A–Z, each with all of its notes from that window, newest first.
        // No counts (Stock notes stays count-free).
        let stockNotesArrange = 'date';   // 'date' | 'company'
        const STOCK_NOTES_COMPANY_DAYS = 91;

        function stockNotesCompanyCutoff() {
            return new Date(Date.now() - STOCK_NOTES_COMPANY_DAYS * 86400000).toISOString().slice(0, 10);
        }

        // Same idea as _company_sort_key() in stock_notes.py: "Mahindra & Mahindra Ltd" = "Mahindra and Mahindra".
        function stockNoteCompanyKey(name) {
            const words = (name || '').toLowerCase().replace(/\([^)]*\)/g, ' ').replace(/&/g, ' and ')
                .match(/[a-z0-9]+/g) || [];
            const kept = words.filter(w => !['ltd', 'limited', 'the', 'pvt', 'private'].includes(w));
            const tail = ['company', 'co', 'corporation', 'corp', 'india', 'industries', 'inds', 'enterprises', 'enterprise'];
            while (kept.length > 1 && tail.includes(kept[kept.length - 1])) kept.pop();  // "Titan Company" = "Titan"
            return kept.join(' ');
        }

        function stockNotesNeedYearsFor(cutoff) {
            return !!(stockNoteYearsLeft && stockNoteYearsLeft.length && stockNoteYearsLeft[0] >= cutoff.slice(0, 4));
        }

        function loadStockNotesSince(cutoff) {
            if (!stockNotesNeedYearsFor(cutoff)) return Promise.resolve();
            return loadMoreStockNotes(false).then(function() { return loadStockNotesSince(cutoff); });
        }

        function setStockNotesArrange(mode) {
            stockNotesArrange = mode === 'company' ? 'company' : 'date';
            researchPage = 1;
            filterResearch(true);
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        function syncStockNotesArrange() {
            const notesView = researchRegionFilter === 'stocknotes';
            const bar = document.getElementById('sn-arrange');
            if (bar) bar.style.display = notesView ? '' : 'none';
            const byCompany = notesView && stockNotesArrange === 'company';
            const d = document.getElementById('sn-by-date'), c = document.getElementById('sn-by-company');
            if (d) d.classList.toggle('active', !byCompany);
            if (c) c.classList.toggle('active', byCompany);
            const hint = document.getElementById('sn-arrange-hint');
            if (hint) hint.textContent = byCompany ? 'A–Z · companies with notes in the last 3 months' : '';
            const az = document.getElementById('sn-az');
            if (az && !byCompany) az.style.display = 'none';
        }

        function stockNotesByCompany() {
            const cutoff = stockNotesCompanyCutoff();
            const groups = new Map();
            filteredResearch.forEach(function(r) {
                if (!r.company || !r.date || r.date.slice(0, 10) < cutoff) return;
                const key = stockNoteCompanyKey(r.company);
                if (!key) return;
                if (!groups.has(key)) groups.set(key, { key: key, name: r.company, notes: [] });
                groups.get(key).notes.push(r);  // filteredResearch is newest first
            });
            return [...groups.values()].sort((a, b) => a.key.localeCompare(b.key));
        }

        function stockNoteShortDate(iso) {
            const d = new Date(iso);
            return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
        }

        function renderStockNotesByCompany() {
            const all = stockNotesByCompany();
            const totalPages = Math.max(1, Math.ceil(all.length / RESEARCH_PAGE_SIZE));
            if (researchPage > totalPages) researchPage = totalPages;
            const start = (researchPage - 1) * RESEARCH_PAGE_SIZE;
            const container = document.getElementById('research-container');
            const page = all.slice(start, start + RESEARCH_PAGE_SIZE);
            container.innerHTML = page.length ? page.map(function(g, i) {
                return `<section class="sn-co" id="sn-co-${start + i}"><h3 class="sn-co-name">${escapeHtml(g.name)}</h3>` +
                    g.notes.map(function(r) {
                        const url = sanitizeUrl(r.link || '');
                        const publisher = escapeHtml(r.publisher || '');
                        const head = r.headline ? escapeHtml(r.headline) : '<span class="sn-co-plain">Report</span>';
                        return `<div class="sn-co-row">
                            <span class="report-channel sn-co-broker">${publisher}</span>
                            <span class="sn-co-head"><a href="${escapeForAttr(url)}" target="_blank" rel="noopener" class="sn-co-title">${head}</a>${shareLinkHtml(url, r.title, r.publisher)}</span>
                            <span class="sn-co-date">${stockNoteShortDate(r.date)}</span>
                            <button class="bookmark-btn" data-url="${escapeForAttr(url)}" data-title="${escapeForAttr(r.title)}" data-source="${publisher}" onclick="toggleGenericBookmark(this)" aria-label="Bookmark report" title="Bookmark">
                                <svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                            </button>
                        </div>`;
                    }).join('') + '</section>';
            }).join('') : '<div style="padding:40px 20px;text-align:center;color:var(--text-muted);font-size:14px;">No company notes in the last 3 months match.</div>';
            renderStockNotesAZ(all);
            syncBookmarkState();
            renderResearchPagination(totalPages);
        }

        function renderStockNotesAZ(all) {
            const az = document.getElementById('sn-az');
            if (!az) return;
            const query = document.getElementById('search-input').value.trim();
            if (query || all.length <= RESEARCH_PAGE_SIZE) { az.style.display = 'none'; return; }
            const first = {};
            all.forEach(function(g, i) {
                const ch = g.key.charAt(0).toUpperCase();
                const letter = /[A-Z]/.test(ch) ? ch : '#';
                if (!(letter in first)) first[letter] = i;
            });
            az.innerHTML = ['#', ...'ABCDEFGHIJKLMNOPQRSTUVWXYZ'].map(L => L in first
                ? `<button type="button" onclick="jumpToStockNotesLetter(${first[L]})">${L}</button>`
                : `<span>${L}</span>`).join('');
            az.style.display = '';
        }

        function jumpToStockNotesLetter(index) {
            researchPage = Math.floor(index / RESEARCH_PAGE_SIZE) + 1;
            renderStockNotesByCompany();
            const el = document.getElementById('sn-co-' + index);
            if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

        // Publishers for the dropdown: brokers in Stock notes, research houses elsewhere.
        function currentResearchPublishers() {
            if (researchRegionFilter !== 'stocknotes') return RESEARCH_PUBLISHERS;
            if (stockNoteBrokers.length) return stockNoteBrokers;  // every broker, not just the loaded pages
            return [...new Set((STOCK_NOTES || []).map(r => r.publisher).filter(Boolean))].sort();
        }

        function syncResearchViewButtons() {
            Object.entries(RESEARCH_VIEW_IDS).forEach(([mode, id]) => {
                const btn = document.getElementById(id);
                if (btn) btn.classList.toggle('active', mode === researchRegionFilter);
            });
        }

        function filterResearch(keepPage) {
            const query = document.getElementById('search-input').value.toLowerCase().trim();
            const notesView = researchRegionFilter === 'stocknotes';
            if (notesView && !STOCK_NOTES) {
                document.getElementById('research-container').innerHTML = '<div style="padding:40px 20px;text-align:center;color:var(--text-muted);font-size:14px;">Loading stock notes…</div>';
                loadStockNotes().then(function() {
                    if (researchRegionFilter !== 'stocknotes') return;
                    initResearchPublisherDropdown();
                    syncResearchPublisherSummary();
                    filterResearch();
                });
                return;
            }
            // A search or a broker pick has to see every note: fetch the remaining
            // years, show what's loaded meanwhile, then filter again.
            // (By company only covers 3 months, so it never needs the older years.)
            if (notesView && stockNotesArrange !== 'company' && (query || selectedResearchPublishers.size)
                    && stockNoteYearsLeft && stockNoteYearsLeft.length) {
                loadMoreStockNotes(true).then(refreshStockNotes);
            } else if (notesView && stockNotesArrange === 'company' && stockNotesNeedYearsFor(stockNotesCompanyCutoff())) {
                loadStockNotesSince(stockNotesCompanyCutoff()).then(refreshStockNotes);
            }
            filteredResearch = (notesView ? STOCK_NOTES : RESEARCH_REPORTS).filter(r => {
                const matchesSearch = !query || (r.title + ' ' + r.source + ' ' + (r.publisher || '') + ' ' + (r.description || '')).toLowerCase().includes(query);
                const pub = r.publisher || r.source;
                const matchesPublisher = selectedResearchPublishers.size === 0 || selectedResearchPublishers.has(pub);
                const region = (r.region || 'Indian').toLowerCase();
                const matchesRegion = notesView || researchRegionFilter === 'all' || region === researchRegionFilter;
                return matchesSearch && matchesPublisher && matchesRegion;
            });
            if (!keepPage) researchPage = 1;
            applyResearchPagination();
        }

        function setResearchRegion(mode) {
            const crossesNotes = (mode === 'stocknotes') !== (researchRegionFilter === 'stocknotes');
            researchRegionFilter = mode;
            syncResearchViewButtons();
            if (crossesNotes) {
                // Brokers and research houses are different lists; a selection can't carry over.
                selectedResearchPublishers.clear();
                initResearchPublisherDropdown();
                syncResearchPublisherSummary();
            }
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
            syncStockNotesArrange();
            if (researchRegionFilter === 'stocknotes' && stockNotesArrange === 'company') {
                const stats = document.getElementById('research-stats');
                if (stats) stats.style.visibility = 'hidden';
                renderStockNotesByCompany();
                return;
            }
            const totalPages = Math.max(1, Math.ceil(filteredResearch.length / RESEARCH_PAGE_SIZE));
            if (researchPage > totalPages) researchPage = totalPages;
            // Two pages from the end of the loaded notes: fetch the next year.
            if (researchRegionFilter === 'stocknotes' && researchPage >= totalPages - 1
                    && stockNoteYearsLeft && stockNoteYearsLeft.length) {
                loadMoreStockNotes(false).then(function(added) { if (added) refreshStockNotes(); });
            }

            document.getElementById('research-visible-count').textContent = filteredResearch.length;
            // Stock notes show no counts (user's call); research views keep them.
            const stats = document.getElementById('research-stats');
            if (stats) stats.style.visibility = researchRegionFilter === 'stocknotes' ? 'hidden' : '';
            const pubCount = document.getElementById('research-publisher-count');
            if (pubCount) pubCount.textContent = currentResearchPublishers().length;
            const pubLabel = document.getElementById('research-publisher-label');
            if (pubLabel) pubLabel.textContent = researchRegionFilter === 'stocknotes' ? 'brokers' : 'publishers';

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
                                ${paidTagHtml(r.publisher || r.source)}
                                ${shareLinkHtml(cardUrl, r.title, r.publisher || r.source)}
                            </div>
                            <div class="report-card-right">
                                ${r.date && !isStockNote(r) ? `<span class="report-card-date">${formatResearchDate(r.date)}</span>` : ''}
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
            currentResearchPublishers().forEach(pub => {
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
                summary.textContent = researchRegionFilter === 'stocknotes' ? 'All brokers' : 'All publishers';
                trigger.classList.remove('has-selection');
            } else if (selectedResearchPublishers.size === 1) {
                summary.textContent = [...selectedResearchPublishers][0];
                trigger.classList.add('has-selection');
            } else {
                summary.textContent = selectedResearchPublishers.size + ' of ' + currentResearchPublishers().length + (researchRegionFilter === 'stocknotes' ? ' brokers' : ' publishers');
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
            currentResearchPublishers().forEach(pub => selectedResearchPublishers.add(pub));
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
                                <span>${formatYoutubeDate(v.date)}</span>${shareLinkHtml(bookmarkUrl, v.title, v.publisher || v.source || '')}
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
                                ${shareLinkHtml(bookmarkUrl, t.title, t.publisher || t.source || '')}
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
