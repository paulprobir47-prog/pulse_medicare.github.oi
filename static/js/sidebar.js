(function () {
    const storageKey = 'pulseSidebarExpanded';

    function setExpanded(expanded) {
        document.body.classList.toggle('sidebar-expanded', expanded);

        const toggle = document.getElementById('sidebarToggle');
        if (!toggle) {
            return;
        }

        toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        toggle.setAttribute('aria-label', expanded ? 'Collapse sidebar' : 'Expand sidebar');

        const icon = toggle.querySelector('i');
        if (icon) {
            icon.className = expanded ? 'fa fa-angles-left' : 'fa fa-angles-right';
        }
    }

    function getStoredExpanded() {
        return localStorage.getItem(storageKey) === 'true';
    }

    document.addEventListener('DOMContentLoaded', function () {
        setExpanded(getStoredExpanded());

        const toggle = document.getElementById('sidebarToggle');
        if (toggle) {
            toggle.addEventListener('click', function () {
                const expanded = !document.body.classList.contains('sidebar-expanded');
                localStorage.setItem(storageKey, expanded ? 'true' : 'false');
                setExpanded(expanded);
            });
        }

        document.querySelectorAll('.app-sidebar__submenu-toggle').forEach(function (button) {
            button.addEventListener('click', function () {
                if (!document.body.classList.contains('sidebar-expanded')) {
                    localStorage.setItem(storageKey, 'true');
                    setExpanded(true);
                }

                const item = button.closest('.app-sidebar__item');
                if (!item) {
                    return;
                }

                item.classList.toggle('open');
                button.setAttribute('aria-expanded', item.classList.contains('open') ? 'true' : 'false');
            });
        });

        const searchWrap = document.querySelector('.app-sidebar__search');
        const searchInput = document.getElementById('sidebarSearchInput');
        const searchResults = document.getElementById('sidebarSearchResults');
        const searchHint = document.getElementById('sidebarSearchHint');
        const searchableLinks = Array.from(document.querySelectorAll('.app-sidebar .sidebar-link[href]'));

        function expandForSearch() {
            if (!document.body.classList.contains('sidebar-expanded')) {
                localStorage.setItem(storageKey, 'true');
                setExpanded(true);
            }
        }

        function clearSearchResults() {
            if (!searchResults || !searchHint) {
                return;
            }

            searchResults.replaceChildren();
            searchResults.classList.remove('show');
            searchHint.textContent = 'Type to filter menu items';
        }

        function createSearchResult(link) {
            const result = document.createElement('a');
            result.className = 'app-sidebar__search-result sidebar-search-result';
            result.href = link.href;

            const sourceIcon = link.querySelector('i:first-child');
            const icon = document.createElement('i');
            icon.className = sourceIcon ? sourceIcon.className : 'fa fa-arrow-right';
            result.appendChild(icon);

            const label = document.createElement('span');
            label.textContent = (link.querySelector('span') || link).textContent.trim();
            result.appendChild(label);

            return result;
        }

        function renderSearchResults(query) {
            if (!searchResults || !searchHint) {
                return;
            }

            const term = query.trim().toLowerCase();
            if (!term) {
                clearSearchResults();
                return;
            }

            const matches = searchableLinks.filter(function (link) {
                const text = (link.getAttribute('data-search-text') || link.textContent).toLowerCase();
                return text.includes(term);
            });

            searchResults.replaceChildren();

            if (!matches.length) {
                const empty = document.createElement('div');
                empty.className = 'app-sidebar__search-result sidebar-search-result';
                empty.textContent = 'No matching menu items';
                searchResults.appendChild(empty);
                searchResults.classList.add('show');
                searchHint.textContent = 'No matching menu items';
                return;
            }

            matches.forEach(function (link) {
                searchResults.appendChild(createSearchResult(link));
            });
            searchResults.classList.add('show');
            searchHint.textContent = matches.length + ' menu item' + (matches.length === 1 ? '' : 's') + ' found';
        }

        if (searchWrap && searchInput) {
            searchWrap.addEventListener('click', function () {
                expandForSearch();
                searchInput.focus();
            });
        }

        if (searchInput) {
            searchInput.addEventListener('focus', expandForSearch);
            searchInput.addEventListener('input', function (event) {
                renderSearchResults(event.target.value);
            });
            searchInput.addEventListener('keydown', function (event) {
                if (event.key === 'Escape') {
                    searchInput.value = '';
                    clearSearchResults();
                    searchInput.blur();
                }
            });
        }

            const profileToggle = document.getElementById('profileToggle');
            const profileMenu = document.getElementById('profileMenu');

            if (profileToggle && profileMenu) {
                profileToggle.addEventListener('click', function (event) {
                    event.stopPropagation();
                    const isOpen = profileMenu.classList.toggle('show');
                    profileToggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
                });

                document.addEventListener('click', function (event) {
                    if (!profileToggle.contains(event.target) && !profileMenu.contains(event.target)) {
                        profileMenu.classList.remove('show');
                        profileToggle.setAttribute('aria-expanded', 'false');
                    }
                });
            }
        });
    }());

