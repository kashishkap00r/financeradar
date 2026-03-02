        // Theme toggle (persisted)
        const safeStorage = {
            get(key) {
                try { return localStorage.getItem(key); } catch (e) { return null; }
            },
            set(key, value) {
                try { localStorage.setItem(key, value); } catch (e) { /* no-op */ }
            }
        };
        const setTheme = (theme) => {
            document.documentElement.setAttribute('data-theme', theme);
            document.body.setAttribute('data-theme', theme);
            safeStorage.set('theme', theme);
            const btn = document.getElementById('theme-toggle');
            btn.setAttribute('data-theme', theme);
            btn.setAttribute('aria-pressed', theme === 'light' ? 'false' : 'true');
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
        document.getElementById('theme-toggle').addEventListener('click', toggleTheme);

        // Filter collapse toggle (mobile)
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
            var isCollapsed = document.documentElement.classList.toggle('filters-collapsed');
            safeStorage.set('financeradar_filters_collapsed', isCollapsed ? 'true' : 'false');
        }

        // Multi-select publisher filter
        let selectedPublishers = new Set();
        let inFocusOnly = false;

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
            return document.querySelector('.content-tab.active')?.dataset.tab || 'news';
        }

        function onSearchInput() {
            const tab = getActiveTab();
            if (tab === 'reports') {
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
            document.getElementById('in-focus-toggle').classList.toggle('active', inFocusOnly);
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
            document.getElementById('sidebar-overlay').classList.add('open');
            document.body.style.overflow = 'hidden';
            renderSidebarContent();
        }

        function closeSidebar() {
            document.getElementById('sidebar-overlay').classList.remove('open');
            document.body.style.overflow = '';
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

            // Update main list button
            const article = document.querySelector(`.article[data-url="${CSS.escape(url)}"], .tweet-card[data-url="${CSS.escape(url)}"]`);
            if (article) {
                const btn = article.querySelector('.bookmark-btn');
                if (btn) btn.classList.remove('bookmarked');
            }

            updateBookmarkCount();
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
        document.getElementById('bookmarks-toggle').addEventListener('click', openSidebar);
        document.getElementById('sidebar-overlay').addEventListener('click', (e) => {
            if (e.target.id === 'sidebar-overlay') closeSidebar();
        });

        // Close sidebar with Escape
        document.addEventListener('keydown', (e) => {
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

        async function loadAiRankings() {
            try {
                const res = await fetch('static/ai_rankings.json');
                if (!res.ok) throw new Error('Rankings not found');
                aiRankings = normalizeAiRankingsPayload(await res.json());
                if (!AI_BUCKET_ORDER.includes(currentAiBucket)) {
                    currentAiBucket = 'news';
                }
                populateProviderDropdown();
                renderAiRankings();
            } catch (e) {
                document.getElementById('ai-rankings-content').innerHTML =
                    '<div class="ai-error"><div class="ai-error-title">AI Rankings Unavailable</div><div>Run ai_ranker.py to generate rankings</div></div>';
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
        }

        function switchAiBucket(bucket) {
            if (!AI_BUCKET_ORDER.includes(bucket)) return;
            currentAiBucket = bucket;
            safeStorage.set('financeradar_ai_bucket', bucket);
            populateProviderDropdown();
            renderAiRankings();
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
            const article = document.querySelector(`.article[data-url="${CSS.escape(url)}"], .tweet-card[data-url="${CSS.escape(url)}"]`);
            if (article) {
                const mainBtn = article.querySelector('.bookmark-btn');
                if (mainBtn) mainBtn.classList.toggle('bookmarked', !exists);
            }
        }

        function openAiSidebar() {
            document.getElementById('ai-sidebar-overlay').classList.add('open');
            document.body.style.overflow = 'hidden';
            updateAiBucketPillState();
        }

        function closeAiSidebar() {
            document.getElementById('ai-sidebar-overlay').classList.remove('open');
            document.body.style.overflow = '';
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
            document.getElementById('wsw-sidebar-overlay').classList.add('open');
            document.body.style.overflow = 'hidden';
            renderWswContent();
        }

        function closeWswSidebar() {
            document.getElementById('wsw-sidebar-overlay').classList.remove('open');
            document.body.style.overflow = '';
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

        // ==================== REPORTS TAB ====================
        let reportsRendered = false;
        let filteredReports = [];
        let reportsViewMode = 'all';
        let reportsNoTargetFilterActive = false;
        let selectedTgChannels = new Set();
        let reportsPage = 1;
        const REPORTS_PAGE_SIZE = 20;

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
        let activeTab = 'news';

        // Restore last active tab
        (function() {
            var saved = safeStorage.get('financeradar_active_tab');
            if (saved && saved !== 'news') switchTab(saved, true);
        })();

        function switchTab(tab, skipScroll) {
            const previousTab = activeTab;
            document.querySelectorAll('.content-tab').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.tab === tab);
            });
            document.querySelectorAll('.tab-content').forEach(el => {
                el.classList.toggle('active', el.id === 'tab-' + tab);
            });
            const searchEl = document.getElementById('search');
            searchEl.placeholder = tab === 'reports' ? 'Search Telegram...' : tab === 'research' ? 'Search reports...' : tab === 'papers' ? 'Search papers...' : tab === 'youtube' ? 'Search YouTube...' : tab === 'twitter' ? 'Search tweets...' : 'Search articles...';
            if (tab === 'reports') {
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
            if (!skipScroll) window.scrollTo({top: 0, behavior: 'smooth'});
            safeStorage.set('financeradar_active_tab', tab);
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
            // Exclude image-only posts: must have text or at least one document
            const hasText = !!(r.text || '').trim();
            const hasDocs = (r.documents && r.documents.length > 0) || !!(r.document && r.document.title);
            return hasText || hasDocs;
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
            // Always exclude image-only posts
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
                const reportTitleRaw = lines[0] || rawText.trim() || 'Untitled';
                const reportBodyRaw = lines.length > 1 ? lines.slice(1).join('\n') : '';
                const reportTitle = escapeHtml(reportTitleRaw);
                const text = escapeHtml(reportBodyRaw).replace(/\n/g, '<br>');
                const reportUrl = sanitizeUrl(r.url || '');
                const isBookmarkedReport = bookmarks.some(b => b.url === reportUrl);
                const titleHtml = reportUrl
                    ? `<a href="${escapeForAttr(reportUrl)}" target="_blank" rel="noopener" class="report-title-link">${reportTitle}</a>`
                    : `<span class="report-title-link">${reportTitle}</span>`;
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
                const images = r.images || [];
                if (images.length > 0) {
                    const badge = images.length > 1
                        ? `<span class="report-images-badge">+${images.length - 1} more</span>` : '';
                    imgHtml = `<div class="report-images">
                        <img src="${escapeForAttr(images[0])}" alt="Report image" loading="lazy"
                             onerror="this.parentElement.style.display='none'">
                        ${badge}</div>`;
                }

                const hasPdfLink = /https?:\/\/\S+\.pdf(\b|\?)/i.test(r.text || '');

                // Content-type badge
                let typeBadge = '';
                if (docs.length > 0 || hasPdfLink) {
                    typeBadge = '<span class="report-type-badge report-type-doc">Report</span>';
                } else if (images.length > 0) {
                    typeBadge = '<span class="report-type-badge report-type-photo">Photo</span>';
                }

                html += `
                    <div class="report-card" data-url="${escapeForAttr(reportUrl)}" data-title="${escapeForAttr(reportTitleRaw.substring(0, 100))}" data-channel="${escapeForAttr(r.channel || '')}">
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
                        <div class="report-title">${titleHtml}</div>
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
