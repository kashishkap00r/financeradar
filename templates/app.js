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
        let bodyScrollLockDepth = 0;
        let bodyScrollLockY = 0;
        let inFocusOnly = false;

        function isMobileViewport() {
            return window.matchMedia('(max-width: ' + MOBILE_BREAKPOINT + 'px)').matches;
        }

        function updateTopBarHeightVar() {
            const topBar = document.querySelector('.top-bar');
            if (!topBar) return;
            document.documentElement.style.setProperty('--top-bar-height', topBar.offsetHeight + 'px');
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

        const setTheme = (theme) => {
            document.documentElement.setAttribute('data-theme', theme);
            document.body.setAttribute('data-theme', theme);
            safeStorage.set('theme', theme);
            const btn = document.getElementById('theme-toggle');
            if (btn) {
                btn.setAttribute('data-theme', theme);
                btn.setAttribute('aria-pressed', theme === 'light' ? 'false' : 'true');
            }
            syncMobileMenuState();
        };
        function toggleTheme() {
            const current = document.documentElement.getAttribute('data-theme') || 'dark';
            setTheme(current === 'light' ? 'dark' : 'light');
        }
        const initTheme = () => {
            const saved = safeStorage.get('theme');
            const theme = saved || 'light';
            setTheme(theme);
        };
        initTheme();
        const themeToggleBtn = document.getElementById('theme-toggle');
        if (themeToggleBtn) {
            themeToggleBtn.addEventListener('click', toggleTheme);
        }
        updateTopBarHeightVar();
        window.addEventListener('load', updateTopBarHeightVar);
        window.addEventListener('resize', () => {
            updateTopBarHeightVar();
            if (!isMobileViewport() && isMobileMenuOpen()) {
                closeMobileMenu();
            }
        });

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
            var dd = document.getElementById('publisher-dropdown');
            if (dd && dd.classList.contains('open')) closeDropdown();
            var tdd = document.getElementById('twitter-publisher-dropdown');
            if (tdd && tdd.classList.contains('open')) closeTwitterDropdown();
            var ydd = document.getElementById('youtube-publisher-dropdown');
            if (ydd && ydd.classList.contains('open')) closeYoutubeDropdown();
            var rgdd = document.getElementById('tg-channel-dropdown');
            if (rgdd && rgdd.classList.contains('open')) closeTgDropdown();
            var rsdd = document.getElementById('research-publisher-dropdown');
            if (rsdd && rsdd.classList.contains('open')) closeResearchDropdown();
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

        function closeDropdown() {
            const dd = document.getElementById('publisher-dropdown');
            if (dd) dd.classList.remove('open');
            const search = document.getElementById('dropdown-search');
            if (search) { search.value = ''; filterPublisherList(); }
        }

        function filterPublisherList() {
            const query = document.getElementById('dropdown-search').value.toLowerCase();
            document.querySelectorAll('#dropdown-list .dropdown-item').forEach(item => {
                const pub = item.dataset.publisher.toLowerCase();
                item.classList.toggle('hidden', query && !pub.includes(query));
            });
        }

        function selectAllPublishers() {
            selectedPublishers.clear();
            syncCheckboxes();
            syncPresetButtons();
            updatePublisherSummary();
            filterArticles();
        }

        function clearAllPublishers() {
            selectedPublishers.clear();
            syncCheckboxes();
            syncPresetButtons();
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
            return document.querySelector('.content-tab.active')?.dataset.tab || 'home';
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
            const query = document.getElementById('search').value.toLowerCase();
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
            const dd = document.getElementById('publisher-dropdown');
            if (dd.classList.contains('open') && !dd.contains(e.target)) {
                closeDropdown();
            }
            const tdd = document.getElementById('twitter-publisher-dropdown');
            if (tdd && tdd.classList.contains('open') && !tdd.contains(e.target)) {
                closeTwitterDropdown();
            }
            const ydd = document.getElementById('youtube-publisher-dropdown');
            if (ydd && ydd.classList.contains('open') && !ydd.contains(e.target)) {
                closeYoutubeDropdown();
            }
            const rgdd = document.getElementById('tg-channel-dropdown');
            if (rgdd && rgdd.classList.contains('open') && !rgdd.contains(e.target)) {
                closeTgDropdown();
            }
            const rsdd = document.getElementById('research-publisher-dropdown');
            if (rsdd && rsdd.classList.contains('open') && !rsdd.contains(e.target)) {
                closeResearchDropdown();
            }
        });

        // Close dropdown on Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                const dd = document.getElementById('publisher-dropdown');
                if (dd.classList.contains('open')) {
                    closeDropdown();
                    e.stopImmediatePropagation();
                    return;
                }
                const tdd = document.getElementById('twitter-publisher-dropdown');
                if (tdd && tdd.classList.contains('open')) {
                    closeTwitterDropdown();
                    e.stopImmediatePropagation();
                    return;
                }
                const ydd = document.getElementById('youtube-publisher-dropdown');
                if (ydd && ydd.classList.contains('open')) {
                    closeYoutubeDropdown();
                    e.stopImmediatePropagation();
                    return;
                }
                const rgdd = document.getElementById('tg-channel-dropdown');
                if (rgdd && rgdd.classList.contains('open')) {
                    closeTgDropdown();
                    e.stopImmediatePropagation();
                    return;
                }
                const rsdd = document.getElementById('research-publisher-dropdown');
                if (rsdd && rsdd.classList.contains('open')) {
                    closeResearchDropdown();
                    e.stopImmediatePropagation();
                    return;
                }
            }
        });

        // Initialize publisher dropdown
        initPublisherDropdown();

        // Pagination
        const PAGE_SIZE = 20;
        let currentPage = 1;
        const TODAY_ISO = "{today_iso}";

        function getFilteredArticles() {
            return [...document.querySelectorAll('.article:not(.hidden)')];
        }

        function renderPagination(totalPages) {
            const bottom = document.getElementById('pagination-bottom');
            bottom.innerHTML = '';

            if (totalPages <= 1) {
                return;
            }
            const makeBtn = (label, page, isActive = false, isDisabled = false) => {
                const btn = document.createElement('button');
                btn.className = 'page-btn' + (isActive ? ' active' : '');
                btn.textContent = label;
                if (isDisabled) {
                    btn.disabled = true;
                } else {
                    btn.addEventListener('click', () => {
                        currentPage = page;
                        applyPagination(true);
                    });
                }
                return btn;
            };
            const makeEllipsis = () => {
                const span = document.createElement('span');
                span.className = 'page-ellipsis';
                span.textContent = '…';
                return span;
            };
            const windowSize = 7;
            const half = Math.floor(windowSize / 2);
            let start = Math.max(1, currentPage - half);
            let end = Math.min(totalPages, currentPage + half);

            if (end - start + 1 < windowSize) {
                if (start === 1) {
                    end = Math.min(totalPages, start + windowSize - 1);
                } else if (end === totalPages) {
                    start = Math.max(1, end - windowSize + 1);
                }
            }

            const build = (container) => {
                const prevBtn = makeBtn('← Prev', Math.max(1, currentPage - 1), false, currentPage === 1);
                prevBtn.classList.add('nav', 'prev');
                container.appendChild(prevBtn);

                if (start > 1) {
                    container.appendChild(makeBtn('1', 1, currentPage === 1));
                    if (start > 2) {
                        container.appendChild(makeEllipsis());
                    }
                }

                for (let i = start; i <= end; i++) {
                    container.appendChild(makeBtn(String(i), i, i === currentPage));
                }

                if (end < totalPages) {
                    if (end < totalPages - 1) {
                        container.appendChild(makeEllipsis());
                    }
                    container.appendChild(makeBtn(String(totalPages), totalPages, currentPage === totalPages));
                }

                const nextBtn = makeBtn('Next →', Math.min(totalPages, currentPage + 1), false, currentPage === totalPages);
                nextBtn.classList.add('nav', 'next');
                container.appendChild(nextBtn);
            };

            build(bottom);
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

        // Back to top button
        window.addEventListener('scroll', () => {
            const btn = document.querySelector('.back-to-top');
            btn.classList.toggle('visible', window.scrollY > 500);
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
                document.getElementById('search').focus();
            } else if (e.key === 'Escape') {
                document.getElementById('search').value = '';
                onSearchInput();
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
            const count = getBookmarks().length;
            const badge = document.getElementById('bookmark-count');
            const toggle = document.getElementById('bookmarks-toggle');

            badge.textContent = count;
            badge.classList.toggle('hidden', count === 0);
            toggle.classList.toggle('has-bookmarks', count > 0);
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

        function syncMobileMenuState() {
            const themeAction = document.querySelector('[data-mobile-action="theme"]');
            const themeState = document.getElementById('mobile-theme-state');
            const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
            if (themeAction) {
                themeAction.classList.toggle('active', currentTheme === 'dark');
                themeAction.setAttribute('data-theme', currentTheme);
            }
            if (themeState) themeState.textContent = currentTheme === 'dark' ? 'Dark' : 'Light';
        }

        function isMobileMenuOpen() {
            const overlay = document.getElementById('mobile-menu-overlay');
            return Boolean(overlay && overlay.classList.contains('open'));
        }

        function openMobileMenu() {
            const overlay = document.getElementById('mobile-menu-overlay');
            if (!overlay || overlay.classList.contains('open')) return;
            syncMobileMenuState();
            overlay.classList.add('open');
            lockBodyScroll();
        }

        function closeMobileMenu() {
            const overlay = document.getElementById('mobile-menu-overlay');
            if (!overlay || !overlay.classList.contains('open')) return;
            overlay.classList.remove('open');
            unlockBodyScroll();
        }

        function toggleMobileMenu() {
            if (isMobileMenuOpen()) closeMobileMenu();
            else openMobileMenu();
        }

        function openMobileAiSidebar() {
            closeMobileMenu();
            openAiSidebar();
        }

        function openMobileWswSidebar() {
            closeMobileMenu();
            openWswSidebar();
        }

        function toggleMobileTheme() {
            toggleTheme();
        }

        function openSidebar() {
            const overlay = document.getElementById('sidebar-overlay');
            if (!overlay || overlay.classList.contains('open')) return;
            overlay.classList.add('open');
            lockBodyScroll();
            renderSidebarContent();
        }

        function closeSidebar() {
            const overlay = document.getElementById('sidebar-overlay');
            if (!overlay || !overlay.classList.contains('open')) return;
            overlay.classList.remove('open');
            unlockBodyScroll();
        }

        function renderSidebarContent() {
            const container = document.getElementById('sidebar-content');
            const bookmarks = getBookmarks();

            if (bookmarks.length === 0) {
                container.innerHTML = '<div class="sidebar-empty">No bookmarks yet.<br>Click the bookmark icon on articles to save them.</div>';
                return;
            }

            container.innerHTML = bookmarks.map(b => `
                <div class="sidebar-article" data-url="${escapeHtml(b.url)}">
                    <div class="sidebar-article-title">
                        <a href="${escapeHtml(b.url)}" target="_blank" rel="noopener">${escapeHtml(b.title)}</a>
                    </div>
                    <div class="sidebar-article-meta">
                        <span class="sidebar-article-source">${escapeHtml(b.source)}</span>
                        <button class="sidebar-remove" onclick="removeBookmark('${escapeForAttr(b.url)}')" title="Remove bookmark">✕</button>
                    </div>
                </div>
            `).join('');
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

        function copyBookmarks() {
            const bookmarks = getBookmarks();
            if (bookmarks.length === 0) {
                return;
            }

            const text = bookmarks.map(b => b.title + '\n' + b.url).join('\n\n');
            copyTextWithFallback(text, () => flashCopiedButton(document.querySelector('#sidebar-overlay .copy-btn')));
        }

        function clearAllBookmarks() {
            if (!confirm('Are you sure you want to clear all bookmarks?')) return;
            saveBookmarks([]);
            document.querySelectorAll('.bookmark-btn.bookmarked').forEach(btn => {
                btn.classList.remove('bookmarked');
            });
            updateBookmarkCount();
            renderSidebarContent();
        }

        // Sidebar toggle
        const bookmarksToggleBtn = document.getElementById('bookmarks-toggle');
        if (bookmarksToggleBtn) bookmarksToggleBtn.addEventListener('click', openSidebar);
        document.getElementById('sidebar-overlay').addEventListener('click', (e) => {
            if (e.target.id === 'sidebar-overlay') closeSidebar();
        });
        document.getElementById('mobile-menu-overlay').addEventListener('click', (e) => {
            if (e.target.id === 'mobile-menu-overlay') closeMobileMenu();
        });

        // Close sidebar with Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && isMobileMenuOpen()) {
                closeMobileMenu();
                return;
            }
            if (e.key === 'Escape' && document.getElementById('sidebar-overlay').classList.contains('open')) {
                closeSidebar();
            }
        });

        // Initialize bookmarks
        initBookmarkButtons();

        // ==================== AI RANKINGS SIDEBAR ====================
        let aiRankings = null;
        let currentAiProvider = 'deepseek-v3';
        let currentAiBucket = safeStorage.get('financeradar_ai_bucket') || 'news';
        const AI_REFRESH_INTERVAL_MS = 3 * 60 * 60 * 1000;
        const AI_BUCKET_ORDER = ['news', 'telegram', 'reports', 'twitter', 'youtube'];
        const AI_BUCKET_LABELS = {
            news: 'News',
            telegram: 'Telegram',
            reports: 'Reports',
            twitter: 'Twitter',
            youtube: 'YouTube'
        };

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

        function updateAiBucketPillState() {
            document.querySelectorAll('.ai-source-pill').forEach(btn => {
                const bucket = btn.dataset.aiBucket;
                const hasProviders = getAvailableProvidersForBucket(bucket).length > 0;
                btn.classList.toggle('active', bucket === currentAiBucket);
                btn.classList.toggle('disabled', !hasProviders);
            });
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
            if (!AI_BUCKET_ORDER.includes(currentAiBucket)) {
                currentAiBucket = 'news';
            }
            populateProviderDropdown();
            renderAiRankings();
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
                document.getElementById('ai-rankings-content').innerHTML =
                    '<div class="ai-error"><div class="ai-error-title">AI Rankings Unavailable</div><div>Run ai_ranker.py to generate rankings</div></div>';
                renderHomeTab();
            }
        }

        function populateProviderDropdown() {
            const select = document.getElementById('ai-provider');
            select.innerHTML = '';
            if (!aiRankings || !aiRankings.providers) {
                updateAiBucketPillState();
                return;
            }

            const providers = getAvailableProvidersForBucket(currentAiBucket);
            if (!providers.length) {
                const opt = document.createElement('option');
                opt.value = '';
                opt.textContent = 'No model available';
                select.appendChild(opt);
                currentAiProvider = '';
                updateAiBucketPillState();
                return;
            }

            const providerKeys = providers.map(([key]) => key);
            if (!providerKeys.includes(currentAiProvider)) {
                currentAiProvider = providers[0][0];
            }

            providers.forEach(([key, p]) => {
                const opt = document.createElement('option');
                opt.value = key;
                const rankingsCount = getProviderBucketRankings(p, currentAiBucket).length;
                opt.textContent = `${p.name} (${rankingsCount})`;
                if (key === currentAiProvider) opt.selected = true;
                select.appendChild(opt);
            });
            select.value = currentAiProvider;
            updateAiBucketPillState();
        }

        function switchAiProvider() {
            currentAiProvider = document.getElementById('ai-provider').value;
            renderAiRankings();
            if (homeRendered) renderHomeTab();
        }

        function switchAiBucket(bucket) {
            if (!AI_BUCKET_ORDER.includes(bucket)) return;
            currentAiBucket = bucket;
            safeStorage.set('financeradar_ai_bucket', bucket);
            populateProviderDropdown();
            renderAiRankings();
            if (homeRendered) renderHomeTab();
        }

        function renderAiRankings() {
            if (!aiRankings || !aiRankings.providers) return;
            const container = document.getElementById('ai-rankings-content');
            const available = getAvailableProvidersForBucket(currentAiBucket);

            if (!available.length) {
                container.innerHTML = `<div class="ai-error"><div class="ai-error-title">${AI_BUCKET_LABELS[currentAiBucket]} Rankings Unavailable</div><div style="margin-top:8px;font-size:12px;color:var(--text-muted)">No provider returned valid ${AI_BUCKET_LABELS[currentAiBucket].toLowerCase()} picks yet.</div></div>`;
                return;
            }

            if (!currentAiProvider || !available.some(([key]) => key === currentAiProvider)) {
                currentAiProvider = available[0][0];
                const select = document.getElementById('ai-provider');
                if (select) select.value = currentAiProvider;
            }

            const provider = aiRankings.providers[currentAiProvider];
            const rankings = getProviderBucketRankings(provider, currentAiBucket);

            container.innerHTML = rankings.map((r, i) => `
                <div class="ai-rank-item">
                    <span class="rank-num">${r.rank || i + 1}</span>
                    <div class="rank-content">
                        ${sanitizeUrl(r.url)
                            ? `<a href="${escapeHtml(sanitizeUrl(r.url))}" target="_blank" rel="noopener">${escapeHtml(r.title)}</a>`
                            : `<span class="rank-title-nolink">${escapeHtml(r.title)}</span>`
                        }
                        <div class="rank-meta">
                            <span class="rank-source">${escapeHtml(r.source)}</span>
                            ${(r.source_type || currentAiBucket)
                                ? `<span class="rank-source-type">${escapeHtml(String(r.source_type || currentAiBucket).toUpperCase())}</span>`
                                : ''
                            }
                        </div>
                    </div>
                    <button class="ai-bookmark-btn ${isBookmarked(r.url) ? 'bookmarked' : ''}"
                            data-url="${escapeForAttr(r.url)}" data-title="${escapeForAttr(r.title)}" data-source="${escapeForAttr(r.source)}" title="Bookmark">
                        <svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                    </button>
                </div>
            `).join('');
            const aiEl = document.getElementById('ai-updated');
            aiEl.setAttribute('data-time', aiRankings.generated_at);
            const aiD = Math.floor((new Date() - new Date(aiRankings.generated_at)) / 60000);
            aiEl.textContent = 'Updated ' + (aiD < 1 ? 'just now' : aiD < 60 ? aiD + ' min ago' : aiD < 1440 ? Math.floor(aiD / 60) + ' hr ago' : Math.floor(aiD / 1440) + ' day ago');
        }

        function isBookmarked(url) {
            if (!url) return false;
            return getBookmarks().some(b => b.url === url);
        }

        function toggleAiBookmark(btn, url, title, source) {
            if (!url) return;
            let bookmarks = getBookmarks();
            const exists = bookmarks.some(b => b.url === url);
            if (exists) {
                bookmarks = bookmarks.filter(b => b.url !== url);
                btn.classList.remove('bookmarked');
            } else {
                bookmarks.push({ url, title, source, date: new Date().toISOString() });
                btn.classList.add('bookmarked');
            }
            saveBookmarks(bookmarks);
            updateBookmarkCount();
            syncBookmarkState();
        }

        function openAiSidebar() {
            const overlay = document.getElementById('ai-sidebar-overlay');
            if (!overlay || overlay.classList.contains('open')) return;
            overlay.classList.add('open');
            lockBodyScroll();
            updateAiBucketPillState();
        }

        function closeAiSidebar() {
            const overlay = document.getElementById('ai-sidebar-overlay');
            if (!overlay || !overlay.classList.contains('open')) return;
            overlay.classList.remove('open');
            unlockBodyScroll();
        }

        document.getElementById('ai-sidebar-overlay').addEventListener('click', (e) => {
            if (e.target.id === 'ai-sidebar-overlay') closeAiSidebar();
        });

        // Event delegation for AI sidebar bookmark buttons (mobile fix)
        document.getElementById('ai-rankings-content').addEventListener('click', (e) => {
            const btn = e.target.closest('.ai-bookmark-btn');
            if (btn) {
                e.preventDefault();
                e.stopPropagation();
                const url = btn.getAttribute('data-url');
                const title = btn.getAttribute('data-title');
                const source = btn.getAttribute('data-source');
                if (url) toggleAiBookmark(btn, url, title, source);
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && document.getElementById('ai-sidebar-overlay').classList.contains('open')) {
                closeAiSidebar();
            }
            if (e.key === 'Escape' && document.getElementById('wsw-sidebar-overlay').classList.contains('open')) {
                closeWswSidebar();
            }
        });

        loadAiRankings();
        setInterval(() => {
            loadAiRankings();
        }, AI_REFRESH_INTERVAL_MS);

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
        let homeRendered = false;
        const HOME_LIMITS = {
            hero: 7,
            news: 12,
            telegram: 12,
            research: 12,
            youtube: 9,
            twitter: 9
        };
        const HOME_PAIR_MAX = {
            topRow: 18,
            bottomRow: 14
        };
        const SPOTLIGHT_PLAN = [
            { bucket: 'news', count: 3 },
            { bucket: 'telegram', count: 2 },
            { bucket: 'youtube', count: 1 },
            { bucket: 'twitter', count: 1 }
        ];
        const HOME_FALLBACK_TABS = new Set(['news', 'reports', 'research', 'youtube', 'twitter']);

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
        document.querySelectorAll('.content-tab').forEach(btn => {
            const capture = () => {
                pendingTabScrollCapture = window.scrollY || window.pageYOffset || 0;
            };
            btn.addEventListener('pointerdown', capture, { passive: true });
            btn.addEventListener('mousedown', capture, { passive: true });
            btn.addEventListener('touchstart', capture, { passive: true });
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
            document.querySelectorAll('.content-tab').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.tab === tab);
            });
            document.querySelectorAll('.tab-content').forEach(el => {
                el.classList.toggle('active', el.id === 'tab-' + tab);
            });
            const searchEl = document.getElementById('search');
            searchEl.placeholder = tab === 'home' ? 'Search home highlights...' : tab === 'reports' ? 'Search Telegram...' : tab === 'research' ? 'Search reports...' : tab === 'papers' ? 'Search papers...' : tab === 'youtube' ? 'Search YouTube...' : tab === 'twitter' ? 'Search tweets...' : 'Search articles...';
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
                filterArticles();
            }
            activeTab = tab;
            applyFilterCollapseForTab(tab);
            const activeTabButton = document.querySelector('.content-tab.active');
            if (isMobileViewport() && activeTabButton) {
                const tabStrip = activeTabButton.closest('.content-tabs');
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

        function cleanHomeTitle(rawTitle) {
            return String(rawTitle || '')
                .replace(/[*_`~#>\[\]\(\)]/g, ' ')
                .replace(/\s+/g, ' ')
                .trim() || 'Untitled';
        }

        function getTelegramReportDocuments(report) {
            if (Array.isArray(report.documents) && report.documents.length > 0) return report.documents;
            if (report.document && report.document.title) return [report.document];
            return [];
        }

        function normalizeHomeFallbackTab(tab) {
            return HOME_FALLBACK_TABS.has(tab) ? tab : 'news';
        }

        function buildHomeBookmarkButton(url, title, source) {
            if (!url) {
                return `<button class="bookmark-btn home-bookmark-btn home-bookmark-btn-disabled" type="button" aria-label="Bookmark unavailable" title="Bookmark unavailable" disabled>
                    <svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                </button>`;
            }

            return `<button class="bookmark-btn home-bookmark-btn${isBookmarked(url) ? ' bookmarked' : ''}" type="button"
                    data-url="${escapeForAttr(url)}"
                    data-title="${escapeForAttr(title)}"
                    data-source="${escapeForAttr(source || 'Home')}"
                    onclick="toggleGenericBookmark(this)"
                    aria-label="Bookmark"
                    title="Bookmark">
                <svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
            </button>`;
        }

        function buildHomeItemHtml(item) {
            const cleanTitle = cleanHomeTitle(item.title || '');
            const title = escapeHtml(cleanTitle);
            const url = sanitizeUrl(item.url || '');
            const fallbackTab = normalizeHomeFallbackTab(String(item.fallbackTab || 'news'));
            const sourceLabel = String(item.meta || '').trim() || 'Home';
            const meta = item.meta ? `<div class="home-item-meta">${escapeHtml(item.meta)}</div>` : '';
            const thumbnail = sanitizeUrl(item.thumbnail || '');
            const media = thumbnail
                ? `<div class="home-item-thumb"><img src="${escapeForAttr(thumbnail)}" alt="${escapeForAttr(cleanTitle)}" loading="lazy" onerror="this.parentElement.style.display='none'"></div>`
                : '';
            const content = `${media}
                <div class="home-item-body">
                    <div class="home-item-title">${title}</div>
                    ${meta}
                </div>`;
            const linkClass = `home-item-link${thumbnail ? ' home-item-link-with-thumb' : ''}`;
            const bookmarkHtml = buildHomeBookmarkButton(url, cleanTitle, sourceLabel);

            if (url) {
                return `<article class="home-item${thumbnail ? ' home-item-with-thumb' : ''}">
                    <a class="${linkClass}" href="${escapeForAttr(url)}" target="_blank" rel="noopener">
                        ${content}
                    </a>
                    ${bookmarkHtml}
                </article>`;
            }

            return `<article class="home-item${thumbnail ? ' home-item-with-thumb' : ''}">
                <button class="${linkClass} home-item-link-button" type="button" onclick="openTabFromHome('${fallbackTab}')">
                    ${content}
                </button>
                ${bookmarkHtml}
            </article>`;
        }

        function renderHomeList(containerId, items, emptyText) {
            const container = document.getElementById(containerId);
            if (!container) return;
            if (!Array.isArray(items) || items.length === 0) {
                container.innerHTML = `<div class="home-item-empty">${escapeHtml(emptyText)}</div>`;
                return;
            }
            container.innerHTML = items.map(buildHomeItemHtml).join('');
        }

        function getHomeNewsItems(limit) {
            const items = [];
            const seen = new Set();
            document.querySelectorAll('#articles .article').forEach(article => {
                if (items.length >= limit) return;
                const url = sanitizeUrl(article.dataset.url || '');
                const title = article.dataset.title || '';
                if (!title || (url && seen.has(url))) return;
                if (url) seen.add(url);
                const source = article.querySelector('.source-tag')?.textContent?.trim() || 'News';
                items.push({ title: cleanHomeTitle(title), url, meta: source, fallbackTab: 'news' });
            });
            return items;
        }

        function getHomeTelegramItems(limit) {
            const items = [];
            TELEGRAM_REPORTS.forEach(report => {
                if (items.length >= limit) return;
                const lines = String(report.text || '').split('\n').map(line => line.trim()).filter(Boolean);
                const docs = getTelegramReportDocuments(report);
                const firstDocWithUrl = docs.find(doc => sanitizeUrl(doc && doc.url ? doc.url : ''));
                const hasText = lines.length > 0;
                const hasDocs = docs.length > 0;
                if (!hasText && !hasDocs) return;

                const title = cleanHomeTitle(lines[0] || (firstDocWithUrl && firstDocWithUrl.title) || (docs[0] && docs[0].title) || 'Telegram update');
                const channel = report.channel || 'Telegram';
                items.push({
                    title,
                    url: sanitizeUrl(report.url || (firstDocWithUrl && firstDocWithUrl.url) || ''),
                    meta: channel,
                    fallbackTab: 'reports'
                });
            });
            return items;
        }

        function getHomeResearchItems(limit) {
            return RESEARCH_REPORTS.slice(0, limit).map(report => {
                const source = report.publisher || report.source || 'Research';
                return {
                    title: cleanHomeTitle(report.title || 'Research report'),
                    url: sanitizeUrl(report.link || report.source_url || ''),
                    meta: source,
                    fallbackTab: 'research'
                };
            });
        }

        function getHomeYoutubeItems(limit) {
            return YOUTUBE_VIDEOS.slice(0, limit).map(video => {
                const channel = video.publisher || video.source || 'YouTube';
                return {
                    title: cleanHomeTitle(video.title || 'Untitled video'),
                    url: sanitizeUrl(video.link || video.source_url || ''),
                    thumbnail: sanitizeUrl(video.thumbnail || '') || (video.video_id ? `https://i.ytimg.com/vi/${video.video_id}/mqdefault.jpg` : ''),
                    meta: channel,
                    fallbackTab: 'youtube'
                };
            });
        }

        function getHomeTwitterItems(limit) {
            return TWITTER_HIGH_SIGNAL.slice(0, limit).map(tweet => {
                const publisher = tweet.publisher || tweet.source || 'Twitter';
                return {
                    title: cleanHomeTitle(tweet.title || 'Tweet'),
                    url: sanitizeUrl(tweet.link || tweet.source_url || ''),
                    meta: publisher,
                    fallbackTab: 'twitter'
                };
            });
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
            return '';
        }

        function getSpotlightYoutubeThumbnail(url, title) {
            const videoId = getYoutubeVideoIdFromUrl(url);
            if (videoId) return `https://i.ytimg.com/vi/${videoId}/mqdefault.jpg`;

            const safeUrl = sanitizeUrl(url);
            const normalizedTitle = cleanHomeTitle(title || '').toLowerCase();
            const matched = YOUTUBE_VIDEOS.find(video => {
                const videoUrl = sanitizeUrl(video.link || video.source_url || '');
                if (safeUrl && videoUrl && videoUrl === safeUrl) return true;
                const videoTitle = cleanHomeTitle(video.title || '').toLowerCase();
                return normalizedTitle && videoTitle && normalizedTitle === videoTitle;
            });
            if (!matched) return '';
            return sanitizeUrl(matched.thumbnail || '')
                || (matched.video_id ? `https://i.ytimg.com/vi/${matched.video_id}/mqdefault.jpg` : '');
        }

        function getAiProviderOrderForBucket(bucket) {
            const providers = getAvailableProvidersForBucket(bucket);
            if (!providers.length) return [];
            const order = [];
            if (providers.some(([key]) => key === currentAiProvider)) {
                order.push(currentAiProvider);
            }
            providers.forEach(([key]) => {
                if (!order.includes(key)) order.push(key);
            });
            return order;
        }

        function buildSpotlightItemFromRanking(item, bucket) {
            const bucketToTab = {
                news: 'news',
                telegram: 'reports',
                reports: 'research',
                youtube: 'youtube',
                twitter: 'twitter'
            };
            const title = cleanHomeTitle(item.title || 'Untitled');
            const url = sanitizeUrl(item.url || '');
            const spotlight = {
                title,
                url,
                meta: item.source || AI_BUCKET_LABELS[bucket] || 'AI pick',
                fallbackTab: bucketToTab[bucket] || 'news',
                bucket
            };
            if (bucket === 'youtube') {
                spotlight.thumbnail = getSpotlightYoutubeThumbnail(url, title);
            }
            return spotlight;
        }

        function getHomeSpotlightItems(limit) {
            if (!aiRankings || !aiRankings.providers) return getHomeNewsItems(limit);

            const items = [];
            const globalSeen = new Set();

            SPOTLIGHT_PLAN.forEach(plan => {
                const { bucket, count } = plan;
                let added = 0;
                const providerOrder = getAiProviderOrderForBucket(bucket);
                providerOrder.forEach(providerKey => {
                    if (added >= count) return;
                    const provider = aiRankings.providers[providerKey];
                    const rankings = getProviderBucketRankings(provider, bucket);
                    rankings.forEach(rankingItem => {
                        if (added >= count) return;
                        const candidate = buildSpotlightItemFromRanking(rankingItem, bucket);
                        const uniqueKey = candidate.url || `${bucket}|${candidate.title}|${candidate.meta}`;
                        if (!candidate.title || globalSeen.has(uniqueKey)) return;
                        globalSeen.add(uniqueKey);
                        items.push(candidate);
                        added += 1;
                    });
                });
            });

            if (!items.length) return getHomeNewsItems(limit);

            if (items.length < limit) {
                const fillSeen = new Set(items.map(item => item.url || `${item.bucket || 'news'}|${item.title}|${item.meta}`));
                const newsFill = getHomeNewsItems(limit * 2);
                newsFill.forEach(newsItem => {
                    if (items.length >= limit) return;
                    const key = newsItem.url || `news|${newsItem.title}|${newsItem.meta}`;
                    if (fillSeen.has(key)) return;
                    fillSeen.add(key);
                    items.push({
                        ...newsItem,
                        bucket: 'news'
                    });
                });
            }

            return items.slice(0, limit);
        }

        function buildSpotlightItemHtml(item, index) {
            const cleanTitle = cleanHomeTitle(item.title || 'Untitled');
            const title = escapeHtml(cleanTitle);
            const url = sanitizeUrl(item.url || '');
            const bucket = String(item.bucket || 'news');
            const laneLabel = bucket === 'news'
                ? 'News'
                : bucket === 'telegram'
                    ? 'Telegram'
                    : bucket === 'youtube'
                        ? 'YouTube'
                        : bucket === 'twitter'
                            ? 'Tweet'
                            : 'AI Pick';
            const source = escapeHtml(String(item.meta || 'AI Pick'));
            const fallbackTab = normalizeHomeFallbackTab(String(item.fallbackTab || 'news'));
            const thumb = sanitizeUrl(item.thumbnail || '');
            const bookmarkHtml = buildHomeBookmarkButton(url, cleanTitle, String(item.meta || laneLabel));
            const media = thumb
                ? `<div class="spotlight-thumb"><img src="${escapeForAttr(thumb)}" alt="${escapeForAttr(cleanTitle)}" loading="lazy" onerror="this.parentElement.style.display='none'"></div>`
                : '';

            const content = `${media}
                <div class="spotlight-content">
                    <div class="spotlight-meta">
                        <span class="spotlight-lane spotlight-lane-${escapeForAttr(bucket)}">${escapeHtml(laneLabel)}</span>
                        <span class="spotlight-source">${source}</span>
                    </div>
                    <div class="spotlight-title">${title}</div>
                </div>`;

            const cls = `spotlight-item spotlight-item-${escapeForAttr(bucket)}${index === 0 ? ' spotlight-item-featured' : ''}${thumb ? ' spotlight-item-media' : ''}`;
            if (url) {
                return `<article class="${cls}">
                    ${bookmarkHtml}
                    <a class="spotlight-link" href="${escapeForAttr(url)}" target="_blank" rel="noopener">${content}</a>
                </article>`;
            }

            return `<article class="${cls}">
                ${bookmarkHtml}
                <button class="spotlight-link spotlight-link-btn" type="button" onclick="openTabFromHome('${fallbackTab}')">${content}</button>
            </article>`;
        }

        function getHomeHeroPayload() {
            return {
                title: 'Spotlight',
                subtitle: 'Top highlights of the day.',
                items: getHomeSpotlightItems(HOME_LIMITS.hero)
            };
        }

        function renderHomeHero() {
            const titleEl = document.getElementById('home-hero-title');
            const subtitleEl = document.getElementById('home-hero-subtitle');
            const listEl = document.getElementById('home-hero-list');
            if (!titleEl || !subtitleEl || !listEl) return;

            const payload = getHomeHeroPayload();
            titleEl.textContent = payload.title;
            subtitleEl.textContent = payload.subtitle;
            if (!payload.items.length) {
                listEl.innerHTML = '<div class="home-item-empty">No highlights available yet.</div>';
                return;
            }
            listEl.innerHTML = payload.items.map((item, idx) => buildSpotlightItemHtml(item, idx)).join('');
        }

        function renderHomeTab() {
            renderHomeHero();
            const newsPool = getHomeNewsItems(HOME_PAIR_MAX.topRow);
            const telegramPool = getHomeTelegramItems(HOME_PAIR_MAX.topRow);
            const researchPool = getHomeResearchItems(HOME_PAIR_MAX.topRow);
            const youtubePool = getHomeYoutubeItems(HOME_PAIR_MAX.bottomRow);
            const twitterPool = getHomeTwitterItems(HOME_PAIR_MAX.bottomRow);

            const topRowTarget = Math.min(
                HOME_PAIR_MAX.topRow,
                Math.max(
                    HOME_LIMITS.news,
                    HOME_LIMITS.telegram,
                    HOME_LIMITS.research,
                    newsPool.length,
                    telegramPool.length,
                    researchPool.length
                )
            );
            const bottomRowTarget = Math.min(
                HOME_PAIR_MAX.bottomRow,
                Math.max(
                    HOME_LIMITS.youtube,
                    HOME_LIMITS.twitter,
                    youtubePool.length,
                    twitterPool.length
                )
            );

            renderHomeList('home-news-list', newsPool.slice(0, topRowTarget), 'No news highlights available.');
            renderHomeList('home-telegram-list', telegramPool.slice(0, topRowTarget), 'No Telegram highlights available.');
            renderHomeList('home-research-list', researchPool.slice(0, topRowTarget), 'No report highlights available.');
            renderHomeList('home-youtube-list', youtubePool.slice(0, bottomRowTarget), 'No YouTube highlights available.');
            renderHomeList('home-twitter-list', twitterPool.slice(0, bottomRowTarget), 'No Twitter highlights available.');
            bindHomeListScrollStates();
            filterHomeCards();
        }

        function syncHomeListScrollState(listEl) {
            if (!listEl) return;
            const wrap = listEl.closest('.home-card-list-scroll');
            if (!wrap) return;
            const canScroll = listEl.scrollHeight > listEl.clientHeight + 2;
            const atBottom = listEl.scrollTop + listEl.clientHeight >= listEl.scrollHeight - 2;
            wrap.classList.toggle('has-overflow', canScroll);
            wrap.classList.toggle('at-bottom', !canScroll || atBottom);
        }

        function bindHomeListScrollStates() {
            document.querySelectorAll('.home-card-list').forEach((listEl) => {
                if (listEl.dataset.scrollBound !== '1') {
                    listEl.dataset.scrollBound = '1';
                    listEl.addEventListener('scroll', () => syncHomeListScrollState(listEl), { passive: true });
                }
                syncHomeListScrollState(listEl);
            });
        }

        function filterHomeCards() {
            const query = (document.getElementById('search').value || '').toLowerCase().trim();
            const cards = document.querySelectorAll('#home-bento-grid .home-card');
            const heroCard = document.getElementById('home-hero-card');
            const empty = document.getElementById('home-no-results');
            let visibleCards = 0;

            cards.forEach(card => {
                const match = !query || card.textContent.toLowerCase().includes(query);
                card.classList.toggle('hidden', !match);
                if (match) visibleCards += 1;
            });

            const heroVisible = !query || (heroCard && heroCard.textContent.toLowerCase().includes(query));
            if (heroCard) heroCard.classList.toggle('hidden', !heroVisible);

            if (empty) {
                const hasAnyVisible = visibleCards > 0 || !!heroVisible;
                empty.classList.toggle('hidden', hasAnyVisible);
            }
        }

        function resetNewsTabState() {
            selectedPublishers.clear();
            syncCheckboxes();
            syncPresetButtons();
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

        function resetTabStateForCleanView(tab) {
            switch (tab) {
                case 'news':
                    resetNewsTabState();
                    break;
                case 'reports':
                    resetReportsTabState();
                    break;
                case 'research':
                    resetResearchTabState();
                    break;
                case 'papers':
                    resetPapersTabState();
                    break;
                case 'youtube':
                    resetYoutubeTabState();
                    break;
                case 'twitter':
                    resetTwitterTabState();
                    break;
                default:
                    break;
            }
        }

        function openTabFromHome(tab) {
            if (!['news', 'reports', 'research', 'papers', 'youtube', 'twitter'].includes(tab)) return;
            const search = document.getElementById('search');
            if (search) search.value = '';

            closeDropdown();
            closeTwitterDropdown();
            closeYoutubeDropdown();
            closeTgDropdown();
            closeResearchDropdown();

            resetTabStateForCleanView(tab);
            switchTab(tab);
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
        function filterTgChannelList() {
            const query = document.getElementById('tg-dropdown-search').value.toLowerCase();
            document.querySelectorAll('#tg-dropdown-list .dropdown-item').forEach(item => {
                item.classList.toggle('hidden', query && !item.dataset.publisher.toLowerCase().includes(query));
            });
        }
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
        function closeTgDropdown() {
            const dd = document.getElementById('tg-channel-dropdown');
            if (dd) dd.classList.remove('open');
            const search = document.getElementById('tg-dropdown-search');
            if (search) { search.value = ''; filterTgChannelList(); }
        }

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
            const query = document.getElementById('search').value.toLowerCase().trim();
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
                    html += `<h2 class="date-header">${dateHeader}</h2>`;
                }

                const rawText = r.text || '';
                const lines = rawText.split('\n').map(line => line.trim()).filter(Boolean);
                const reportTitleRaw = lines[0] || '';
                const reportBodyRaw = lines.length > 1 ? lines.slice(1).join('\n') : '';
                const hasReportTitle = !!reportTitleRaw.trim();
                const reportTitle = escapeHtml(reportTitleRaw);
                const text = escapeHtml(reportBodyRaw).replace(/\n/g, '<br>');
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
                             onerror="this.closest('.report-images').style.display='none'">
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
            container.querySelectorAll('.report-text').forEach(el => {
                if (el.scrollHeight > el.clientHeight) {
                    const btn = el.nextElementSibling;
                    if (btn && btn.classList.contains('report-expand-btn')) {
                        btn.style.display = 'block';
                    }
                }
            });
            renderReportsPagination(totalPages);
        }

        function renderReportsPagination(totalPages) {
            const bottom = document.getElementById('reports-pagination-bottom');
            bottom.innerHTML = '';

            if (totalPages <= 1) return;

            const makeBtn = (label, page, isActive = false, isDisabled = false) => {
                const btn = document.createElement('button');
                btn.className = 'page-btn' + (isActive ? ' active' : '');
                btn.textContent = label;
                if (isDisabled) {
                    btn.disabled = true;
                } else {
                    btn.addEventListener('click', () => {
                        reportsPage = page;
                        applyReportsPagination();
                        window.scrollTo({top: 0, behavior: 'smooth'});
                    });
                }
                return btn;
            };
            const makeEllipsis = () => {
                const span = document.createElement('span');
                span.className = 'page-ellipsis';
                span.textContent = '…';
                return span;
            };
            const windowSize = 7;
            const half = Math.floor(windowSize / 2);
            let startP = Math.max(1, reportsPage - half);
            let endP = Math.min(totalPages, reportsPage + half);
            if (endP - startP + 1 < windowSize) {
                if (startP === 1) endP = Math.min(totalPages, startP + windowSize - 1);
                else if (endP === totalPages) startP = Math.max(1, endP - windowSize + 1);
            }

            const build = (container) => {
                const prevBtn = makeBtn('← Prev', Math.max(1, reportsPage - 1), false, reportsPage === 1);
                prevBtn.classList.add('nav', 'prev');
                container.appendChild(prevBtn);
                if (startP > 1) {
                    container.appendChild(makeBtn('1', 1, reportsPage === 1));
                    if (startP > 2) container.appendChild(makeEllipsis());
                }
                for (let i = startP; i <= endP; i++) {
                    container.appendChild(makeBtn(String(i), i, i === reportsPage));
                }
                if (endP < totalPages) {
                    if (endP < totalPages - 1) container.appendChild(makeEllipsis());
                    container.appendChild(makeBtn(String(totalPages), totalPages, reportsPage === totalPages));
                }
                const nextBtn = makeBtn('Next →', Math.min(totalPages, reportsPage + 1), false, reportsPage === totalPages);
                nextBtn.classList.add('nav', 'next');
                container.appendChild(nextBtn);
            };

            build(bottom);
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
            const query = document.getElementById('search').value.toLowerCase().trim();
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
                    html += `<h2 class="date-header">${dateHeader}</h2>`;
                }

                const title = escapeHtml(r.title);
                const publisher = escapeHtml(r.publisher || r.source);
                const reportUrl = sanitizeUrl(r.link || '');
                const sourceUrl = sanitizeUrl(r.source_url || '') || reportUrl;
                const cardUrl = reportUrl || sourceUrl;
                const description = escapeHtml(r.description || '');
                const region = (r.region || 'Indian').toLowerCase();
                const regionLabel = region === 'international' ? 'Intl' : 'Indian';
                const regionCls = region === 'international' ? 'international' : 'indian';
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
                                <span class="research-region-badge ${regionCls}">${regionLabel}</span>
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
            const bottom = document.getElementById('research-pagination-bottom');
            if (!bottom || totalPages <= 1) {
                if (bottom) bottom.innerHTML = '';
                return;
            }

            const build = (container) => {
                container.innerHTML = '';
                const makeBtn = (text, page, isActive, isDisabled) => {
                    const btn = document.createElement('button');
                    btn.className = 'page-btn' + (isActive ? ' active' : '');
                    btn.textContent = text;
                    btn.disabled = isDisabled;
                    if (!isDisabled && !isActive) btn.onclick = () => { researchPage = page; applyResearchPagination(); window.scrollTo({top: 0, behavior: 'smooth'}); };
                    return btn;
                };

                const prevBtn = makeBtn('← Prev', researchPage - 1, false, researchPage === 1);
                prevBtn.classList.add('nav', 'prev');
                container.appendChild(prevBtn);

                const nums = document.createElement('span');
                nums.className = 'page-numbers';
                const addPage = (p) => nums.appendChild(makeBtn(String(p), p, p === researchPage, false));
                const addEllipsis = () => { const s = document.createElement('span'); s.className = 'page-ellipsis'; s.textContent = '…'; nums.appendChild(s); };

                if (totalPages <= 7) {
                    for (let i = 1; i <= totalPages; i++) addPage(i);
                } else {
                    addPage(1);
                    if (researchPage > 3) addEllipsis();
                    for (let i = Math.max(2, researchPage - 1); i <= Math.min(totalPages - 1, researchPage + 1); i++) addPage(i);
                    if (researchPage < totalPages - 2) addEllipsis();
                    addPage(totalPages);
                }
                container.appendChild(nums);

                const nextBtn = makeBtn('Next →', researchPage + 1, false, researchPage === totalPages);
                nextBtn.classList.add('nav', 'next');
                container.appendChild(nextBtn);
            };

            build(bottom);
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

        function closeResearchDropdown() {
            const dd = document.getElementById('research-publisher-dropdown');
            if (dd) dd.classList.remove('open');
            const search = document.getElementById('research-dropdown-search');
            if (search) { search.value = ''; filterResearchPublisherList(); }
        }

        function filterResearchPublisherList() {
            const query = document.getElementById('research-dropdown-search').value.toLowerCase();
            document.querySelectorAll('#research-dropdown-list .dropdown-item').forEach(item => {
                const pub = item.dataset.publisher.toLowerCase();
                item.classList.toggle('hidden', query && !pub.includes(query));
            });
        }

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
            const query = document.getElementById('search').value.toLowerCase().trim();
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
                const summary = escapeHtml(p.description || '');
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
                                ${(p.date && !p.date_is_fallback) ? `<span class="report-card-date">${formatPaperDate(p.date)}</span>` : '<span class="report-card-date">Date unavailable</span>'}
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
            const bottom = document.getElementById('papers-pagination-bottom');
            if (!bottom || totalPages <= 1) {
                if (bottom) bottom.innerHTML = '';
                return;
            }

            const build = (container) => {
                container.innerHTML = '';
                const makeBtn = (text, page, isActive, isDisabled) => {
                    const btn = document.createElement('button');
                    btn.className = 'page-btn' + (isActive ? ' active' : '');
                    btn.textContent = text;
                    btn.disabled = isDisabled;
                    if (!isDisabled && !isActive) btn.onclick = () => { papersPage = page; applyPapersPagination(); window.scrollTo({top: 0, behavior: 'smooth'}); };
                    return btn;
                };

                const prevBtn = makeBtn('← Prev', papersPage - 1, false, papersPage === 1);
                prevBtn.classList.add('nav', 'prev');
                container.appendChild(prevBtn);

                const nums = document.createElement('span');
                nums.className = 'page-numbers';
                const addPage = (p) => nums.appendChild(makeBtn(String(p), p, p === papersPage, false));
                const addEllipsis = () => { const s = document.createElement('span'); s.className = 'page-ellipsis'; s.textContent = '…'; nums.appendChild(s); };

                if (totalPages <= 7) {
                    for (let i = 1; i <= totalPages; i++) addPage(i);
                } else {
                    addPage(1);
                    if (papersPage > 3) addEllipsis();
                    for (let i = Math.max(2, papersPage - 1); i <= Math.min(totalPages - 1, papersPage + 1); i++) addPage(i);
                    if (papersPage < totalPages - 2) addEllipsis();
                    addPage(totalPages);
                }
                container.appendChild(nums);

                const nextBtn = makeBtn('Next →', papersPage + 1, false, papersPage === totalPages);
                nextBtn.classList.add('nav', 'next');
                container.appendChild(nextBtn);
            };

            build(bottom);
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
            const query = document.getElementById('search').value.toLowerCase().trim();
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

        function filterYoutubePublisherList() {
            const query = document.getElementById('youtube-dropdown-search').value.toLowerCase();
            document.querySelectorAll('#youtube-dropdown-list .dropdown-item').forEach(item => {
                const pub = item.dataset.publisher.toLowerCase();
                item.classList.toggle('hidden', query && !pub.includes(query));
            });
        }

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

        function closeYoutubeDropdown() {
            const dd = document.getElementById('youtube-publisher-dropdown');
            if (dd) dd.classList.remove('open');
            const search = document.getElementById('youtube-dropdown-search');
            if (search) { search.value = ''; filterYoutubePublisherList(); }
        }

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
                    html += `<h2 class="date-header">${dateHeader}</h2>`;
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
                                <button class="bookmark-btn" data-url="${escapeForAttr(bookmarkUrl)}" data-title="${escapeForAttr(v.title)}" data-source="${channel}" onclick="toggleGenericBookmark(this)" aria-label="Bookmark video" title="Bookmark">
                                    <svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            });

            container.innerHTML = html;
            syncBookmarkState();
            renderYoutubePagination(totalPages);
        }

        function renderYoutubePagination(totalPages) {
            const bottom = document.getElementById('youtube-pagination-bottom');
            if (!bottom || totalPages <= 1) {
                if (bottom) bottom.innerHTML = '';
                return;
            }

            const build = (container) => {
                container.innerHTML = '';
                const makeBtn = (text, page, isActive, isDisabled) => {
                    const btn = document.createElement('button');
                    btn.className = 'page-btn' + (isActive ? ' active' : '');
                    btn.textContent = text;
                    btn.disabled = isDisabled;
                    if (!isDisabled && !isActive) btn.onclick = () => { youtubePage = page; applyYoutubePagination(); window.scrollTo({top: 0, behavior: 'smooth'}); };
                    return btn;
                };
                const prevBtn = makeBtn('← Prev', Math.max(1, youtubePage - 1), false, youtubePage === 1);
                prevBtn.classList.add('nav', 'prev');
                container.appendChild(prevBtn);

                const nums = document.createElement('div');
                nums.className = 'page-numbers';
                const addPage = (p) => nums.appendChild(makeBtn(String(p), p, p === youtubePage, false));
                const addEllipsis = () => { const el = document.createElement('span'); el.className = 'page-ellipsis'; el.textContent = '...'; nums.appendChild(el); };

                if (totalPages <= 7) {
                    for (let i = 1; i <= totalPages; i++) addPage(i);
                } else {
                    addPage(1);
                    if (youtubePage > 3) addEllipsis();
                    for (let i = Math.max(2, youtubePage - 1); i <= Math.min(totalPages - 1, youtubePage + 1); i++) addPage(i);
                    if (youtubePage < totalPages - 2) addEllipsis();
                    addPage(totalPages);
                }
                container.appendChild(nums);

                const nextBtn = makeBtn('Next →', Math.min(totalPages, youtubePage + 1), false, youtubePage === totalPages);
                nextBtn.classList.add('nav', 'next');
                container.appendChild(nextBtn);
            };

            build(bottom);
        }

        // ==================== TWITTER TAB (helpers) ====================
        function getTweetBadges(title) {
            const badges = [];
            if (title.startsWith('”') || title.startsWith('\u201c')) badges.push({label: 'Quote', cls: 'tweet-badge-quote'});
            else if (title.startsWith('RT @')) badges.push({label: 'Retweet', cls: 'tweet-badge-retweet'});
            if (title.includes('\ud83e\uddf5')) badges.push({label: 'Thread', cls: 'tweet-badge-thread'});
            return badges;
        }
        function toggleTweetExpand(btn) {
            const textEl = btn.previousElementSibling;
            const expanded = textEl.classList.toggle('expanded');
            btn.textContent = expanded ? 'Show less' : 'Show more';
        }
        function checkTweetOverflow(container) {
            container.querySelectorAll('.tweet-card-body').forEach(el => {
                const btn = el.nextElementSibling;
                if (btn && btn.classList.contains('tweet-expand-btn')) {
                    // Temporarily remove line-clamp to measure true content height
                    el.style.webkitLineClamp = 'unset';
                    el.style.display = 'block';
                    const fullHeight = el.scrollHeight;
                    el.style.webkitLineClamp = '';
                    el.style.display = '';
                    btn.style.display = fullHeight > el.clientHeight ? 'block' : 'none';
                }
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
            const query = document.getElementById('search').value.toLowerCase().trim();
            const pool = getActiveTwitterPool();
            filteredTwitter = pool.filter(t => {
                const matchesSearch = !query || (t.title + ' ' + t.source + ' ' + (t.publisher || '')).toLowerCase().includes(query);
                const pub = t.publisher || t.source;
                const matchesPublisher = selectedTwitterPublishers.size === 0 || selectedTwitterPublishers.has(pub);
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

        function filterTwitterPublisherList() {
            const query = document.getElementById('twitter-dropdown-search').value.toLowerCase();
            document.querySelectorAll('#twitter-dropdown-list .dropdown-item').forEach(item => {
                const pub = item.dataset.publisher.toLowerCase();
                item.classList.toggle('hidden', query && !pub.includes(query));
            });
        }

        function selectAllTwitterPublishers() {
            selectedTwitterPublishers.clear();
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

        function closeTwitterDropdown() {
            const dd = document.getElementById('twitter-publisher-dropdown');
            if (dd) dd.classList.remove('open');
            const search = document.getElementById('twitter-dropdown-search');
            if (search) { search.value = ''; filterTwitterPublisherList(); }
        }

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
                    html += `<h2 class="date-header">${dateHeader}</h2>`;
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
                const badges = getTweetBadges(t.title);
                const threadCollapsed = Number(t.thread_collapsed_count || 0);
                if (twitterLane === 'high-signal') {
                    badges.push({
                        label: (TWITTER_LANE_META && TWITTER_LANE_META.ranking_mode) === 'ai' ? 'AI Signal' : 'Signal',
                        cls: 'tweet-badge-thread'
                    });
                }
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
            checkTweetOverflow(container);
            syncBookmarkState();
            renderTwitterPagination(totalPages);
        }

        function renderTwitterPagination(totalPages) {
            const bottom = document.getElementById('twitter-pagination-bottom');
            if (!bottom || totalPages <= 1) {
                if (bottom) bottom.innerHTML = '';
                return;
            }

            const build = (container) => {
                container.innerHTML = '';
                const makeBtn = (text, page, isActive, isDisabled) => {
                    const btn = document.createElement('button');
                    btn.className = 'page-btn' + (isActive ? ' active' : '');
                    btn.textContent = text;
                    btn.disabled = isDisabled;
                    if (!isDisabled && !isActive) btn.onclick = () => { twitterPage = page; applyTwitterPagination(); window.scrollTo({top: 0, behavior: 'smooth'}); };
                    return btn;
                };
                const prevBtn = makeBtn('← Prev', Math.max(1, twitterPage - 1), false, twitterPage === 1);
                prevBtn.classList.add('nav', 'prev');
                container.appendChild(prevBtn);

                const nums = document.createElement('div');
                nums.className = 'page-numbers';
                const addPage = (p) => nums.appendChild(makeBtn(String(p), p, p === twitterPage, false));
                const addEllipsis = () => { const el = document.createElement('span'); el.className = 'page-ellipsis'; el.textContent = '...'; nums.appendChild(el); };

                if (totalPages <= 7) {
                    for (let i = 1; i <= totalPages; i++) addPage(i);
                } else {
                    addPage(1);
                    if (twitterPage > 3) addEllipsis();
                    for (let i = Math.max(2, twitterPage - 1); i <= Math.min(totalPages - 1, twitterPage + 1); i++) addPage(i);
                    if (twitterPage < totalPages - 2) addEllipsis();
                    addPage(totalPages);
                }
                container.appendChild(nums);

                const nextBtn = makeBtn('Next →', Math.min(totalPages, twitterPage + 1), false, twitterPage === totalPages);
                nextBtn.classList.add('nav', 'next');
                container.appendChild(nextBtn);
            };

            build(bottom);
        }

        // Update relative time for all timestamped elements
        function formatTimeAgo(el) {
            if (!el || !el.dataset.time) return;
            const diff = Math.floor((new Date() - new Date(el.dataset.time)) / 1000);
            let text;
            if (diff < 60) text = 'Updated just now';
            else if (diff < 3600) text = `Updated ${Math.floor(diff / 60)} min ago`;
            else if (diff < 86400) text = `Updated ${Math.floor(diff / 3600)} hr ago`;
            else text = `Updated ${Math.floor(diff / 86400)} day ago`;
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
