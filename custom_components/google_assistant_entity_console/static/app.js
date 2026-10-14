// Global state
let entities = [];
let filteredEntities = [];
let rooms = [];
let currentAliases = [];
const collapsedGroups = new Set();
let activeFilters = {
    exposure: 'all',
    area: null,
    domain: null
};
let sidebarCollapsed = localStorage.getItem('gaec_sidebar_collapsed') === 'true';

// DOM Elements
const totalEntitiesEl = document.getElementById('totalEntities');
const exposedEntitiesEl = document.getElementById('exposedEntities');
const searchInput = document.getElementById('searchInput');
const roomFilter = document.getElementById('roomFilter');
const exposedOnlyCheckbox = document.getElementById('exposedOnlyCheckbox');

// Slicing & Sidebar DOM Elements
const appSidebar = document.getElementById('appSidebar');
const sidebarToggleBtn = document.getElementById('sidebarToggleBtn');
const sidebarCollapseBtn = document.getElementById('sidebarCollapseBtn');
const sidebarBackdrop = document.getElementById('sidebarBackdrop');
const sidebarFilterInput = document.getElementById('sidebarFilterInput');
const exposureNav = document.getElementById('exposureNav');
const areasNav = document.getElementById('areasNav');
const domainsNav = document.getElementById('domainsNav');
const countAllEl = document.getElementById('countAll');
const countExposedEl = document.getElementById('countExposed');
const countUnexposedEl = document.getElementById('countUnexposed');
const countOverridesEl = document.getElementById('countOverrides');
const areasCountBadge = document.getElementById('areasCountBadge');
const domainsCountBadge = document.getElementById('domainsCountBadge');
const breadcrumbSliceText = document.getElementById('breadcrumbSliceText');
const breadcrumbChips = document.getElementById('breadcrumbChips');
const clearSliceBtn = document.getElementById('clearSliceBtn');
const sliceBulkActionBtn = document.getElementById('sliceBulkActionBtn');
const sliceBulkActionText = document.getElementById('sliceBulkActionText');
const regexIndicator = document.getElementById('regexIndicator');

// Advanced Filters DOM & State
const toggleAdvancedFiltersBtn = document.getElementById('toggleAdvancedFiltersBtn');
const advancedFiltersDrawer = document.getElementById('advancedFiltersDrawer');
const hideGroupedLightsCheckbox = document.getElementById('hideGroupedLightsCheckbox');
const hideUnavailableCheckbox = document.getElementById('hideUnavailableCheckbox');
const domainChipsContainer = document.getElementById('domainChipsContainer');
const selectedDomains = new Set();
const entityTableBody = document.getElementById('entityTableBody');
const rebuildBtn = document.getElementById('rebuildBtn');
const groupingType = document.getElementById('groupingType');



// Restart Modal Elements
const restartModal = document.getElementById('restartModal');
const cancelRestartBtn = document.getElementById('cancelRestartBtn');
const confirmRestartBtn = document.getElementById('confirmRestartBtn');

// Blocklist Modal Elements
const blocklistModal = document.getElementById('blocklistModal');
const manageBlocklistBtn = document.getElementById('manageBlocklistBtn');
const newBlocklistPattern = document.getElementById('newBlocklistPattern');
const addBlocklistPatternBtn = document.getElementById('addBlocklistPatternBtn');
const blocklistContainer = document.getElementById('blocklistContainer');
const closeBlocklistModal = document.getElementById('closeBlocklistModal');
const closeBlocklistModalBtn = document.getElementById('closeBlocklistModalBtn');

// Listen for token updates from parent panel
window.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'HA_TOKEN_UPDATE' && event.data.token) {
        sessionStorage.setItem('ha_token', event.data.token);
    }
});

function requestParentToken() {
    try {
        if (window.parent && window.parent !== window) {
            window.parent.postMessage({ type: 'REQUEST_HA_TOKEN' }, '*');
        }
    } catch (e) {
        console.debug('Failed to request token from parent window:', e);
    }
}

// Get auth headers from URL token parameter or session storage
function getAuthHeaders() {
    const params = new URLSearchParams(window.location.search);
    let token = params.get('token');
    if (token) {
        sessionStorage.setItem('ha_token', token);
    } else {
        token = sessionStorage.getItem('ha_token');
    }
    
    if (token) {
        return {
            'Authorization': `Bearer ${token}`
        };
    }
    return {};
}

// Authenticated fetch wrapper that handles token injection and 401 refresh retry
async function authFetch(url, options = {}) {
    const headers = {
        ...getAuthHeaders(),
        ...(options.headers || {})
    };
    let response = await fetch(url, { ...options, headers });
    if (response.status === 401) {
        requestParentToken();
        // Wait briefly for token update from parent
        await new Promise(resolve => setTimeout(resolve, 300));
        const retryHeaders = {
            ...getAuthHeaders(),
            ...(options.headers || {})
        };
        response = await fetch(url, { ...options, headers: retryHeaders });
    }
    return response;
}

// Init
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        fetchEntities();
        setupEventListeners();
    });
} else {
    fetchEntities();
    setupEventListeners();
}

// Fetch all entities from backend
async function fetchEntities() {
    showTableLoading();
    try {
        const response = await authFetch('/api/google_assistant_entity_console/entities', {
            headers: getAuthHeaders()
        });
        if (!response.ok) throw new Error('Failed to fetch entities');
        
        const data = await response.json();
        entities = Array.isArray(data) ? data : (data.entities || []);
        
        // Update Active YAML Config display name
        const configFileEl = document.getElementById('configFile');
        if (configFileEl) {
            configFileEl.textContent = Array.isArray(data) ? 'gaGen_112225.yaml' : (data.yaml_filename || 'None (Not Configured)');
        }

        // Update app version label
        const appVersionEl = document.getElementById('appVersion');
        if (appVersionEl && data.version) {
            appVersionEl.textContent = `Entity Console v${data.version}`;
        }
        
        // Extract unique rooms/areas
        const uniqueRooms = [...new Set(entities.map(e => e.area))].filter(r => r && r !== "TBA").sort();
        populateRoomFilter(uniqueRooms);
        
        // Extract unique domains and initialize selected domains set
        const uniqueDomains = [...new Set(entities.map(e => e.domain))].sort();
        selectedDomains.clear();
        uniqueDomains.forEach(d => selectedDomains.add(d));
        renderDomainChips(uniqueDomains);
        
        updateStats();
        applyFilters();
    } catch (error) {
        showToast('Error loading entities: ' + error.message, 'error');
        entityTableBody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--danger); padding: 3rem 0;">
            <i class="fa-solid fa-triangle-exclamation" style="font-size: 2rem; margin-bottom: 0.5rem; display: block;"></i>
            Error loading entity registry. Ensure Home Assistant integration is active.
        </td></tr>`;
    }
}

// Event listeners setup
function setupEventListeners() {
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            const clearBtn = document.getElementById('clearSearchBtn');
            if (clearBtn) {
                clearBtn.style.display = searchInput.value ? 'flex' : 'none';
            }
            applyFilters();
        });
    }

    const clearSearchBtn = document.getElementById('clearSearchBtn');
    if (clearSearchBtn) {
        clearSearchBtn.addEventListener('click', () => {
            if (searchInput) {
                searchInput.value = '';
                clearSearchBtn.style.display = 'none';
                searchInput.focus();
                applyFilters();
            }
        });
    }

    if (roomFilter) roomFilter.addEventListener('change', applyFilters);
    if (exposedOnlyCheckbox) exposedOnlyCheckbox.addEventListener('change', applyFilters);
    if (groupingType) groupingType.addEventListener('change', applyFilters);
    
    // Sidebar & Slicing Event Listeners
    if (sidebarToggleBtn) {
        sidebarToggleBtn.addEventListener('click', () => toggleSidebar());
    }
    if (sidebarCollapseBtn) {
        sidebarCollapseBtn.addEventListener('click', () => toggleSidebar(true));
    }
    if (sidebarBackdrop) {
        sidebarBackdrop.addEventListener('click', () => toggleSidebar(true));
    }
    if (sidebarFilterInput) {
        sidebarFilterInput.addEventListener('input', () => renderSidebar());
    }
    if (clearSliceBtn) {
        clearSliceBtn.addEventListener('click', clearAllFilters);
    }
    if (sliceBulkActionBtn) {
        sliceBulkActionBtn.addEventListener('click', handleSliceBulkAction);
    }
    if (sidebarCollapsed && appSidebar) {
        appSidebar.classList.add('collapsed');
    }

    // Advanced Filters Event Listeners
    if (toggleAdvancedFiltersBtn && advancedFiltersDrawer) {
        toggleAdvancedFiltersBtn.addEventListener('click', () => {
            const isHidden = advancedFiltersDrawer.style.display === 'none';
            advancedFiltersDrawer.style.display = isHidden ? 'flex' : 'none';
            toggleAdvancedFiltersBtn.classList.toggle('active', isHidden);
        });
    }
    if (hideGroupedLightsCheckbox) {
        hideGroupedLightsCheckbox.addEventListener('change', applyFilters);
    }
    if (hideUnavailableCheckbox) {
        hideUnavailableCheckbox.addEventListener('change', applyFilters);
    }
    
    // Rebuild Button
    if (rebuildBtn) rebuildBtn.addEventListener('click', handleRebuild);

    // Copy Include Snippet Button
    const copyIncludeBtn = document.getElementById('copyIncludeBtn');
    if (copyIncludeBtn) {
        copyIncludeBtn.addEventListener('click', () => {
            const input = document.getElementById('missingIncludeInput');
            if (input && input.value) {
                navigator.clipboard.writeText(input.value).then(() => {
                    showToast('Include snippet copied to clipboard!', 'success');
                }).catch(() => {
                    input.select();
                    document.execCommand('copy');
                    showToast('Include snippet copied to clipboard!', 'success');
                });
            }
        });
    }
    
    // Restart Modal controls
    if (cancelRestartBtn && restartModal) {
        cancelRestartBtn.addEventListener('click', () => {
            restartModal.style.display = 'none';
        });
    }
    if (confirmRestartBtn) confirmRestartBtn.addEventListener('click', handleRestart);

    // Blocklist Modal controls
    if (manageBlocklistBtn && blocklistModal) {
        manageBlocklistBtn.addEventListener('click', () => {
            fetchBlocklist();
            blocklistModal.style.display = 'block';
        });
    }
    const hideBlocklist = () => {
        if (blocklistModal) blocklistModal.style.display = 'none';
    };
    if (closeBlocklistModal) closeBlocklistModal.addEventListener('click', hideBlocklist);
    if (closeBlocklistModalBtn) closeBlocklistModalBtn.addEventListener('click', hideBlocklist);
    
    if (addBlocklistPatternBtn && newBlocklistPattern) {
        addBlocklistPatternBtn.addEventListener('click', () => {
            const val = newBlocklistPattern.value.trim();
            if (val) addBlocklistPattern(val);
        });
    }
    if (newBlocklistPattern) {
        newBlocklistPattern.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const val = newBlocklistPattern.value.trim();
                if (val) addBlocklistPattern(val);
            }
        });
    }
    setupAiEventListeners();
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function updateStats() {
    if (totalEntitiesEl) totalEntitiesEl.textContent = entities.length;
    if (exposedEntitiesEl) exposedEntitiesEl.textContent = entities.filter(e => e.should_expose).length;

    const pendingAdd = entities.filter(e => e.should_expose && !e.yaml_exposed).length;
    const pendingRemove = entities.filter(e => !e.should_expose && e.yaml_exposed).length;
    const pendingTotal = pendingAdd + pendingRemove;

    const pendingEntitiesStat = document.getElementById('pendingEntitiesStat');
    if (pendingEntitiesStat) pendingEntitiesStat.textContent = pendingTotal;

    const pendingChangesBadge = document.getElementById('pendingChangesBadge');
    if (pendingChangesBadge) {
        if (pendingTotal > 0) {
            pendingChangesBadge.style.display = 'inline-block';
            pendingChangesBadge.textContent = `${pendingTotal} Pending`;
        } else {
            pendingChangesBadge.style.display = 'none';
        }
    }

    if (rebuildBtn) {
        if (pendingTotal > 0) {
            rebuildBtn.classList.add('pulse-highlight');
        } else {
            rebuildBtn.classList.remove('pulse-highlight');
        }
    }

    renderSidebar();
}

function parseSearchQuery(query) {
    const specifiers = {
        exposure: null,
        area: null,
        domain: null,
        floor: null
    };
    
    let text = (query || '').trim();

    // Match is:exposed, is:unexposed, not:exposed, is:override, has:alias
    text = text.replace(/\b(?:is|status):(exposed|unexposed|override|overrides|alias|aliases)\b/gi, (match, val) => {
        const v = val.toLowerCase();
        if (v === 'exposed') specifiers.exposure = 'exposed';
        else if (v === 'unexposed') specifiers.exposure = 'unexposed';
        else if (v.startsWith('override') || v.startsWith('alias')) specifiers.exposure = 'overrides';
        return '';
    });

    text = text.replace(/\bnot:exposed\b/gi, () => {
        specifiers.exposure = 'unexposed';
        return '';
    });

    text = text.replace(/\bhas:(?:alias|aliases|override|overrides)\b/gi, () => {
        specifiers.exposure = 'overrides';
        return '';
    });

    // Match area:"Living Room" or area:basement
    text = text.replace(/\barea:(?:"([^"]+)"|(\S+))/gi, (match, p1, p2) => {
        specifiers.area = (p1 || p2).toLowerCase();
        return '';
    });

    // Match domain:light
    text = text.replace(/\bdomain:(?:"([^"]+)"|(\S+))/gi, (match, p1, p2) => {
        specifiers.domain = (p1 || p2).toLowerCase();
        return '';
    });

    // Match floor:"Main Floor" or floor:basement
    text = text.replace(/\bfloor:(?:"([^"]+)"|(\S+))/gi, (match, p1, p2) => {
        specifiers.floor = (p1 || p2).toLowerCase();
        return '';
    });

    return {
        specifiers,
        remainingQuery: text.replace(/\s+/g, ' ').trim()
    };
}

function renderSidebar() {
    if (!exposureNav || !areasNav || !domainsNav) return;

    // Filter term for sidebar categories search
    const filterTerm = sidebarFilterInput ? sidebarFilterInput.value.toLowerCase().trim() : '';

    // 1. Exposure counts
    const totalCount = entities.length;
    const exposedCount = entities.filter(e => e.should_expose || e.yaml_exposed).length;
    const unexposedCount = totalCount - exposedCount;
    const overridesCount = entities.filter(e => (e.aliases && e.aliases.length > 0) || (e.display_name && e.display_name !== e.original_name)).length;

    if (countAllEl) countAllEl.textContent = totalCount;
    if (countExposedEl) countExposedEl.textContent = exposedCount;
    if (countUnexposedEl) countUnexposedEl.textContent = unexposedCount;
    if (countOverridesEl) countOverridesEl.textContent = overridesCount;

    // 2. Areas section
    const areaMap = new Map();
    let unassignedAreaCount = 0;
    entities.forEach(e => {
        const a = (e.area || '').trim();
        if (!a || a === 'TBA' || a === 'No Room') {
            unassignedAreaCount++;
        } else {
            areaMap.set(a, (areaMap.get(a) || 0) + 1);
        }
    });

    const sortedAreas = [...areaMap.keys()].sort((a, b) => a.localeCompare(b));
    if (areasCountBadge) areasCountBadge.textContent = sortedAreas.length + (unassignedAreaCount > 0 ? 1 : 0);

    areasNav.innerHTML = '';
    sortedAreas.forEach(areaName => {
        if (filterTerm && !areaName.toLowerCase().includes(filterTerm)) return;
        const count = areaMap.get(areaName);
        const item = document.createElement('div');
        const isActive = activeFilters.area && activeFilters.area.toLowerCase() === areaName.toLowerCase();
        item.className = `sidebar-item ${isActive ? 'active' : ''}`;
        item.dataset.filterType = 'area';
        item.dataset.filterValue = areaName;
        item.innerHTML = `
            <span class="sidebar-item-label"><i class="fa-solid fa-door-open"></i> ${escapeHtml(areaName)}</span>
            <span class="sidebar-item-count">${count}</span>
        `;
        item.addEventListener('click', () => setFilter('area', areaName));
        areasNav.appendChild(item);
    });

    if (unassignedAreaCount > 0 && (!filterTerm || 'unassigned area'.includes(filterTerm) || 'no room'.includes(filterTerm))) {
        const item = document.createElement('div');
        const isActive = activeFilters.area === '__unassigned__';
        item.className = `sidebar-item ${isActive ? 'active' : ''}`;
        item.dataset.filterType = 'area';
        item.dataset.filterValue = '__unassigned__';
        item.innerHTML = `
            <span class="sidebar-item-label"><i class="fa-solid fa-question text-muted"></i> <em>Unassigned Area</em></span>
            <span class="sidebar-item-count">${unassignedAreaCount}</span>
        `;
        item.addEventListener('click', () => setFilter('area', '__unassigned__'));
        areasNav.appendChild(item);
    }

    // 3. Domains section
    const domainMap = new Map();
    entities.forEach(e => {
        const d = (e.domain || 'other').trim();
        domainMap.set(d, (domainMap.get(d) || 0) + 1);
    });

    const sortedDomains = [...domainMap.keys()].sort((a, b) => domainMap.get(b) - domainMap.get(a));
    if (domainsCountBadge) domainsCountBadge.textContent = sortedDomains.length;

    domainsNav.innerHTML = '';
    sortedDomains.forEach(domain => {
        const domainFriendly = getDomainName(domain);
        if (filterTerm && !domain.toLowerCase().includes(filterTerm) && !domainFriendly.toLowerCase().includes(filterTerm)) return;
        const count = domainMap.get(domain);
        const item = document.createElement('div');
        const isActive = activeFilters.domain && activeFilters.domain.toLowerCase() === domain.toLowerCase();
        item.className = `sidebar-item ${isActive ? 'active' : ''}`;
        item.dataset.filterType = 'domain';
        item.dataset.filterValue = domain;
        item.innerHTML = `
            <span class="sidebar-item-label"><i class="fa-solid ${getEntityIcon(domain)}"></i> ${escapeHtml(domainFriendly)}</span>
            <span class="sidebar-item-count">${count}</span>
        `;
        item.addEventListener('click', () => setFilter('domain', domain));
        domainsNav.appendChild(item);
    });

    // 4. Sync active classes on exposureNav items
    if (exposureNav) {
        const items = exposureNav.querySelectorAll('.sidebar-item');
        items.forEach(el => {
            const val = el.dataset.sliceValue;
            if (activeFilters.exposure === val) {
                el.classList.add('active');
            } else {
                el.classList.remove('active');
            }
            if (!el.onclick) {
                el.onclick = () => {
                    setFilter('exposure', val);
                };
            }
        });
    }

    updateBreadcrumbs();
}

function setFilter(type, value) {
    if (type === 'exposure') {
        activeFilters.exposure = (activeFilters.exposure === value) ? 'all' : value;
    } else if (type === 'area') {
        activeFilters.area = (activeFilters.area === value) ? null : value;
    } else if (type === 'domain') {
        activeFilters.domain = (activeFilters.domain === value) ? null : value;
    }

    updateBreadcrumbs();
    renderSidebar();

    // On mobile, close sidebar drawer upon selecting
    if (window.innerWidth <= 768 && appSidebar && !appSidebar.classList.contains('collapsed')) {
        toggleSidebar(true);
    }

    applyFilters();
}

window.setFilter = setFilter;

function clearAllFilters() {
    activeFilters = {
        exposure: 'all',
        area: null,
        domain: null
    };
    if (searchInput) searchInput.value = '';
    const clearSearchBtn = document.getElementById('clearSearchBtn');
    if (clearSearchBtn) clearSearchBtn.style.display = 'none';

    updateBreadcrumbs();
    renderSidebar();
    applyFilters();
}

function updateBreadcrumbs() {
    if (!breadcrumbContainer || !breadcrumbSliceText || !breadcrumbChips) return;
    
    const chips = [];
    if (activeFilters.exposure !== 'all') {
        let label = 'Exposed';
        if (activeFilters.exposure === 'unexposed') label = 'Not Exposed';
        else if (activeFilters.exposure === 'overrides') label = 'Custom Overrides';
        chips.push({
            type: 'exposure',
            html: `<strong>Exposure:</strong> ${escapeHtml(label)}`
        });
    }
    if (activeFilters.area) {
        const areaLabel = activeFilters.area === '__unassigned__' ? 'Unassigned' : activeFilters.area;
        chips.push({
            type: 'area',
            html: `<strong>Area:</strong> ${escapeHtml(areaLabel)}`
        });
    }
    if (activeFilters.domain) {
        chips.push({
            type: 'domain',
            html: `<strong>Domain:</strong> ${escapeHtml(getDomainName(activeFilters.domain))}`
        });
    }

    if (chips.length === 0) {
        breadcrumbSliceText.style.display = 'inline';
        breadcrumbSliceText.textContent = `All Entities (${entities.length} items)`;
        breadcrumbChips.style.display = 'none';
        breadcrumbChips.innerHTML = '';
        if (clearSliceBtn) clearSliceBtn.style.display = 'none';
        if (sliceBulkActionBtn) sliceBulkActionBtn.style.display = 'none';
    } else {
        breadcrumbSliceText.style.display = 'none';
        breadcrumbChips.style.display = 'flex';
        breadcrumbChips.innerHTML = '';
        chips.forEach(c => {
            const chipEl = document.createElement('div');
            chipEl.className = 'filter-chip';
            chipEl.innerHTML = `${c.html} <span class="chip-remove" title="Remove filter">&times;</span>`;
            chipEl.querySelector('.chip-remove').addEventListener('click', (e) => {
                e.stopPropagation();
                setFilter(c.type, c.type === 'exposure' ? 'all' : null);
            });
            breadcrumbChips.appendChild(chipEl);
        });
        if (clearSliceBtn) clearSliceBtn.style.display = 'inline-flex';
        if (sliceBulkActionBtn) sliceBulkActionBtn.style.display = 'inline-flex';
    }
}

function toggleSidebar(forceCollapse) {
    if (!appSidebar) return;
    const shouldCollapse = forceCollapse !== undefined ? forceCollapse : !appSidebar.classList.contains('collapsed');
    appSidebar.classList.toggle('collapsed', shouldCollapse);
    if (sidebarBackdrop) {
        sidebarBackdrop.classList.toggle('active', !shouldCollapse && window.innerWidth <= 768);
    }
    localStorage.setItem('gaec_sidebar_collapsed', shouldCollapse);
}

async function handleSliceBulkAction() {
    if (filteredEntities.length === 0) return;
    
    const exposedInView = filteredEntities.filter(e => e.should_expose || e.yaml_exposed).length;
    const willExpose = exposedInView < filteredEntities.length / 2;
    const actionWord = willExpose ? 'Expose' : 'Unexpose';
    
    if (!confirm(`${actionWord} all ${filteredEntities.length} entities in the active filter?`)) {
        return;
    }

    showToast(`${actionWord}ing ${filteredEntities.length} entities...`, 'info');
    let updated = 0;
    for (const entity of filteredEntities) {
        try {
            const currentExposed = !!(entity.should_expose || entity.yaml_exposed);
            if (currentExposed !== willExpose) {
                entity.should_expose = willExpose;
                await authFetch(`/api/google_assistant_entity_console/entities/${encodeURIComponent(entity.entity_id)}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ expose: willExpose })
                });
                updated++;
            }
        } catch (err) {
            console.error('Failed to update entity in filter:', entity.entity_id, err);
        }
    }

    showToast(`Successfully updated ${updated} entities`, 'success');
    updateStats();
    applyFilters();
}

function populateRoomFilter(uniqueRooms) {
    // Keep the "All Rooms" option and append the rest
    roomFilter.innerHTML = '<option value="all">All Rooms</option>';
    uniqueRooms.forEach(room => {
        const opt = document.createElement('option');
        opt.value = room.toLowerCase();
        opt.textContent = room;
        roomFilter.appendChild(opt);
    });
}

function renderDomainChips(uniqueDomains) {
    if (!domainChipsContainer) return;
    domainChipsContainer.innerHTML = '';
    
    uniqueDomains.forEach(domain => {
        const chip = document.createElement('div');
        chip.className = `domain-chip ${selectedDomains.has(domain) ? 'active' : ''}`;
        chip.innerHTML = `
            <i class="fa-solid ${getEntityIcon(domain)}"></i>
            <span>${getDomainName(domain)}</span>
        `;
        chip.addEventListener('click', () => {
            if (selectedDomains.has(domain)) {
                selectedDomains.delete(domain);
                chip.classList.remove('active');
            } else {
                selectedDomains.add(domain);
                chip.classList.add('active');
            }
            applyFilters();
        });
        domainChipsContainer.appendChild(chip);
    });
}

function showTableLoading() {
    entityTableBody.innerHTML = `
        <tr>
            <td colspan="4" class="loading-state">
                <div class="spinner"></div>
                <span>Loading entity registry...</span>
            </td>
        </tr>
    `;
}

// Filter and render table
function applyFilters() {
    const rawSearchText = searchInput ? searchInput.value : '';
    const { specifiers, remainingQuery } = parseSearchQuery(rawSearchText);

    let regex = null;
    let isRegexActive = false;
    
    if (remainingQuery) {
        try {
            regex = new RegExp(remainingQuery, 'i');
            isRegexActive = true;
        } catch (e) {
            // Graceful fallback to substring search if invalid regex
            regex = null;
            isRegexActive = false;
        }
    }

    if (regexIndicator) {
        if (remainingQuery && isRegexActive) {
            regexIndicator.style.display = 'inline-flex';
            regexIndicator.title = 'Regex pattern active';
        } else {
            regexIndicator.style.display = 'none';
        }
    }

    const room = roomFilter ? roomFilter.value : 'all';
    const exposedOnly = exposedOnlyCheckbox ? exposedOnlyCheckbox.checked : false;
    const hideGroupedLights = hideGroupedLightsCheckbox ? hideGroupedLightsCheckbox.checked : false;
    const hideUnavailable = hideUnavailableCheckbox ? hideUnavailableCheckbox.checked : false;

    // Combined effective exposure filter
    const effectiveExposure = specifiers.exposure || (activeFilters.exposure !== 'all' ? activeFilters.exposure : null);

    // Combined effective area filter
    const effectiveArea = specifiers.area || (activeFilters.area ? activeFilters.area.toLowerCase() : null);

    // Combined effective domain filter
    const effectiveDomain = specifiers.domain || (activeFilters.domain ? activeFilters.domain.toLowerCase() : null);

    filteredEntities = entities.filter(e => {
        // 1. Exposure filter (from sidebar OR search specifier is:exposed / not:exposed / is:override)
        if (effectiveExposure) {
            if (effectiveExposure === 'exposed' && !(e.should_expose || e.yaml_exposed)) return false;
            if (effectiveExposure === 'unexposed' && (e.should_expose || e.yaml_exposed)) return false;
            if (effectiveExposure === 'overrides') {
                const hasOverrides = (e.aliases && e.aliases.length > 0) || (e.display_name && e.display_name !== e.original_name);
                if (!hasOverrides) return false;
            }
        }

        // 2. Area filter (from sidebar OR search specifier area:basement)
        if (effectiveArea) {
            if (effectiveArea === '__unassigned__') {
                const isUnassigned = !e.area || e.area === 'TBA' || e.area === 'No Room';
                if (!isUnassigned) return false;
            } else {
                const entityArea = (e.area || '').toLowerCase();
                if (!entityArea.includes(effectiveArea)) return false;
            }
        }

        // 3. Domain filter (from sidebar OR search specifier domain:light)
        if (effectiveDomain) {
            const entityDomain = (e.domain || '').toLowerCase();
            if (entityDomain !== effectiveDomain) return false;
        }

        // 4. Floor filter (from search specifier floor:main)
        if (specifiers.floor) {
            const entityFloor = (e.floor || '').toLowerCase();
            if (!entityFloor.includes(specifiers.floor)) return false;
        }

        // 5. Remaining text or regex match across friendly name, entity_id, google name, aliases, area
        if (remainingQuery) {
            const targets = [
                e.entity_id || '',
                e.display_name || '',
                e.original_name || e.name || '',
                e.area || '',
                ...(e.aliases || []).filter(a => typeof a === 'string')
            ];
            const matchesQuery = regex 
                ? targets.some(t => regex.test(t))
                : targets.some(t => t.toLowerCase().includes(remainingQuery.toLowerCase()));
            if (!matchesQuery) return false;
        }

        // 6. Domain chip filter (Multi-select)
        const matchesDomainChips = selectedDomains.size === 0 || selectedDomains.has(e.domain);
        if (!matchesDomainChips) return false;

        // 7. Room dropdown filter
        const matchesRoom = room === 'all' || (e.area || '').toLowerCase() === room;
        if (!matchesRoom) return false;

        // 8. Exposed Only toggle
        const matchesExposedOnly = !exposedOnly || e.should_expose || e.yaml_exposed;
        if (!matchesExposedOnly) return false;

        // 9. Grouped lights filter
        const matchesGroupedLights = !hideGroupedLights || e.domain !== 'light' || !e.in_group;
        if (!matchesGroupedLights) return false;

        // 10. Unavailable filter
        const matchesUnavailable = !hideUnavailable || !e.unavailable;
        if (!matchesUnavailable) return false;

        return true;
    });

    // Update match count badge
    const matchCountEl = document.getElementById('filterMatchCount');
    if (matchCountEl) {
        const isDefaultState = !rawSearchText && room === 'all' && !exposedOnly && selectedDomains.size === 0 
            && activeFilters.exposure === 'all' && !activeFilters.area && !activeFilters.domain;
        if (isDefaultState) {
            matchCountEl.textContent = `${entities.length} items`;
        } else {
            matchCountEl.textContent = `${filteredEntities.length} of ${entities.length}`;
        }
    }

    // Update bulk action text
    const hasActiveFilters = activeFilters.exposure !== 'all' || !!activeFilters.area || !!activeFilters.domain || !!specifiers.exposure || !!specifiers.area;
    if (sliceBulkActionBtn) {
        if (hasActiveFilters && filteredEntities.length > 0) {
            const exposedInView = filteredEntities.filter(e => e.should_expose || e.yaml_exposed).length;
            const willExpose = exposedInView < filteredEntities.length / 2;
            if (sliceBulkActionText) {
                sliceBulkActionText.textContent = `${willExpose ? 'Expose' : 'Unexpose'} All in Filter (${filteredEntities.length})`;
            }
        }
    }
    
    renderTable();
}

window.toggleGroup = function(groupKey, event) {
    if (event) event.stopPropagation();
    if (collapsedGroups.has(groupKey)) {
        collapsedGroups.delete(groupKey);
    } else {
        collapsedGroups.add(groupKey);
    }
    renderTable();
};

window.toggleSubGroups = function(parentType, parentId, collapse, event) {
    if (event) event.stopPropagation();
    
    if (parentType === 'floor') {
        const floorName = parentId;
        // Find all rooms under this floor in the filtered entities list
        const rooms = [...new Set(filteredEntities
            .filter(e => (e.floor || 'No Floor') === floorName)
            .map(e => e.area || 'No Room'))];
            
        rooms.forEach(r => {
            const roomKey = `room:${floorName}:${r}`;
            if (collapse) {
                collapsedGroups.add(roomKey);
            } else {
                collapsedGroups.delete(roomKey);
            }
            
            // Toggle domains under this room as well
            const domains = [...new Set(filteredEntities
                .filter(e => (e.floor || 'No Floor') === floorName && (e.area || 'No Room') === r)
                .map(e => e.domain || 'No Domain'))];
                
            domains.forEach(d => {
                const domainKey = `domain:${floorName}:${r}:${d}`;
                if (collapse) {
                    collapsedGroups.add(domainKey);
                } else {
                    collapsedGroups.delete(domainKey);
                }
            });
        });
    } else if (parentType === 'room') {
        const parts = parentId.split(':');
        const floorName = parts[0];
        const roomName = parts[1];
        
        // Find all domains under this room
        const domains = [...new Set(filteredEntities
            .filter(e => (e.floor || 'No Floor') === floorName && (e.area || 'No Room') === roomName)
            .map(e => e.domain || 'No Domain'))];
            
        domains.forEach(d => {
            const domainKey = `domain:${floorName}:${roomName}:${d}`;
            if (collapse) {
                collapsedGroups.add(domainKey);
            } else {
                collapsedGroups.delete(domainKey);
            }
        });
    } else if (parentType === 'domain') {
        const domainName = parentId;
        // Find all floors under this domain
        const floors = [...new Set(filteredEntities
            .filter(e => (e.domain || 'No Domain') === domainName)
            .map(e => e.floor || 'No Floor'))];
            
        floors.forEach(f => {
            const floorKey = `floor:${domainName}:${f}`;
            if (collapse) {
                collapsedGroups.add(floorKey);
            } else {
                collapsedGroups.delete(floorKey);
            }
            
            // Toggle rooms under this floor + domain combination
            const rooms = [...new Set(filteredEntities
                .filter(e => (e.domain || 'No Domain') === domainName && (e.floor || 'No Floor') === f)
                .map(e => e.area || 'No Room'))];
                
            rooms.forEach(r => {
                const roomKey = `room:${domainName}:${f}:${r}`;
                if (collapse) {
                    collapsedGroups.add(roomKey);
                } else {
                    collapsedGroups.delete(roomKey);
                }
            });
        });
    } else if (parentType === 'domain-floor') {
        const parts = parentId.split(':');
        const domainName = parts[0];
        const floorName = parts[1];
        
        // Find all rooms under this domain and floor combination
        const rooms = [...new Set(filteredEntities
            .filter(e => (e.domain || 'No Domain') === domainName && (e.floor || 'No Floor') === floorName)
            .map(e => e.area || 'No Room'))];
            
        rooms.forEach(r => {
            const roomKey = `room:${domainName}:${floorName}:${r}`;
            if (collapse) {
                collapsedGroups.add(roomKey);
            } else {
                collapsedGroups.delete(roomKey);
            }
        });
    }
    
    renderTable();
};

const domainNames = {
    light: 'Lights',
    switch: 'Switches',
    media_player: 'Media Players',
    fan: 'Fans',
    sensor: 'Sensors',
    binary_sensor: 'Binary Sensors',
    cover: 'Covers',
    climate: 'Climate Devices',
    lock: 'Locks',
    vacuum: 'Vacuums',
    scene: 'Scenes',
    script: 'Scripts',
    camera: 'Cameras',
    valve: 'Valves'
};

const entityIcons = {
    light: 'fa-lightbulb',
    switch: 'fa-toggle-on',
    media_player: 'fa-tv',
    fan: 'fa-fan',
    sensor: 'fa-gauge-simple-high',
    binary_sensor: 'fa-circle-dot',
    cover: 'fa-window-maximize',
    climate: 'fa-temperature-three-quarters',
    lock: 'fa-lock',
    vacuum: 'fa-robot',
    camera: 'fa-video',
    scene: 'fa-palette',
    script: 'fa-scroll',
    valve: 'fa-faucet',
    alarm_control_panel: 'fa-shield-halved',
    button: 'fa-hand-pointer',
    group: 'fa-users',
    humidifier: 'fa-droplet',
    lawn_mower: 'fa-tractor',
    select: 'fa-list',
    water_heater: 'fa-fire'
};

function getDomainName(domain) {
    return domainNames[domain] || (domain.charAt(0).toUpperCase() + domain.slice(1).replace('_', ' ') + 's');
}

function getEntityIcon(domain) {
    return entityIcons[domain] || 'fa-gear';
}

function renderTable() {
    if (filteredEntities.length === 0) {
        entityTableBody.innerHTML = `
            <tr>
                <td colspan="4" style="text-align: center; color: var(--on-surface-variant); padding: 3rem 0;">
                    <i class="fa-solid fa-magnifying-glass" style="font-size: 1.5rem; opacity: 0.5; margin-bottom: 0.5rem; display: block;"></i>
                    No entities match the active filters.
                </td>
            </tr>
        `;
        return;
    }
    
    entityTableBody.innerHTML = '';
    
    const isDomainGrouping = (groupingType && groupingType.value === 'domain');
    const isFlatGrouping = (groupingType && groupingType.value === 'flat');
    
    if (isFlatGrouping) {
        const ents = [...filteredEntities].sort((a, b) => a.entity_id.localeCompare(b.entity_id));
        ents.forEach(e => renderEntityRow(e));
        return;
    }
    
    if (isDomainGrouping) {
        // Group by Domain -> Floor & Room
        const groups = {};
        filteredEntities.forEach(e => {
            const domain = e.domain || 'No Domain';
            const floor = e.floor || 'No Floor';
            const room = e.area || 'No Room';
            const floorAndRoom = (floor !== 'No Floor' && floor !== 'TBA') ? `${floor} › ${room}` : room;
            
            if (!groups[domain]) {
                groups[domain] = {};
            }
            if (!groups[domain][floorAndRoom]) {
                groups[domain][floorAndRoom] = [];
            }
            groups[domain][floorAndRoom].push(e);
        });
        
        const sortedDomains = Object.keys(groups).sort();
        
        sortedDomains.forEach(domain => {
            const domainKey = `domain:${domain}`;
            const isDomainCollapsed = collapsedGroups.has(domainKey);
            
            // Domain Header
            const domainTr = document.createElement('tr');
            domainTr.className = 'domain-header-row';
            domainTr.style.cursor = 'pointer';
            domainTr.setAttribute('onclick', `toggleGroup('${domainKey}', event)`);
            
            const domainChevron = isDomainCollapsed ? 'fa-chevron-right' : 'fa-chevron-down';
            
            domainTr.innerHTML = `
                <td colspan="4" class="domain-header-cell">
                    <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                        <div>
                            <i class="fa-solid ${domainChevron}" style="margin-right: 0.5rem; width: 12px;"></i>
                            <i class="fa-solid ${getEntityIcon(domain)}" style="margin-right: 0.25rem;"></i> ${getDomainName(domain)}
                        </div>
                        <div style="display: flex; gap: 0.75rem; font-size: 0.75rem; font-weight: normal; text-transform: none; letter-spacing: normal;">
                            <button class="header-action-link" onclick="openAiAssist('domain', '${domain.replace(/'/g, "\\'")}', event)" title="AI Assist for this Domain" style="background: none; border: none; color: var(--primary); cursor: pointer; display: flex; align-items: center; gap: 0.25rem;">
                                <i class="fa-solid fa-wand-magic-sparkles"></i> AI Assist
                            </button>
                        </div>
                    </div>
                </td>
            `;
            entityTableBody.appendChild(domainTr);
            
            if (isDomainCollapsed) return;
            
            const roomsInDomain = groups[domain];
            const sortedRooms = Object.keys(roomsInDomain).sort();
            
            sortedRooms.forEach(room => {
                const roomKey = `room:${domain}:${room}`;
                const isRoomCollapsed = collapsedGroups.has(roomKey);
                
                // Room Subheader (Floor › Room)
                const roomTr = document.createElement('tr');
                roomTr.className = 'room-header-row';
                roomTr.style.cursor = 'pointer';
                roomTr.setAttribute('onclick', `toggleGroup('${roomKey}', event)`);
                
                const roomChevron = isRoomCollapsed ? 'fa-chevron-right' : 'fa-chevron-down';
                
                roomTr.innerHTML = `
                    <td colspan="4" class="room-header-cell" style="padding-left: 2rem !important; font-size: 0.85rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                            <div>
                                <i class="fa-solid ${roomChevron}" style="margin-right: 0.5rem; width: 12px;"></i>
                                <i class="fa-solid fa-door-open"></i> ${room}
                            </div>
                        </div>
                    </td>
                `;
                entityTableBody.appendChild(roomTr);
                
                if (isRoomCollapsed) return;
                
                const ents = roomsInDomain[room];
                ents.sort((a, b) => a.entity_id.localeCompare(b.entity_id));
                
                ents.forEach(e => {
                    renderEntityRow(e);
                });
            });
        });
    } else {
        // Group entities by floor, then by room (Default Floor-first grouping)
        const groups = {};
        filteredEntities.forEach(e => {
            const floor = e.floor || 'No Floor';
            const room = e.area || 'No Room';
            if (!groups[floor]) {
                groups[floor] = {};
            }
            if (!groups[floor][room]) {
                groups[floor][room] = [];
            }
            groups[floor][room].push(e);
        });
        
        // Sort floor names (put "No Floor" or "TBA" at the end)
        const floorNames = Object.keys(groups).sort((a, b) => {
            if (a === 'No Floor' || a === 'TBA') return 1;
            if (b === 'No Floor' || b === 'TBA') return -1;
            return a.localeCompare(b);
        });
        
        floorNames.forEach(floor => {
            const floorKey = `floor:${floor}`;
            const isFloorCollapsed = collapsedGroups.has(floorKey);
            
            // Render Floor Header row
            const floorTr = document.createElement('tr');
            floorTr.className = 'floor-header-row';
            floorTr.style.cursor = 'pointer';
            floorTr.setAttribute('onclick', `toggleGroup('${floorKey}', event)`);
            
            const floorChevron = isFloorCollapsed ? 'fa-chevron-right' : 'fa-chevron-down';
            
            floorTr.innerHTML = `
                <td colspan="4" class="floor-header-cell">
                    <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                        <div>
                            <i class="fa-solid ${floorChevron}" style="margin-right: 0.5rem; width: 12px;"></i>
                            <i class="fa-solid fa-layer-group"></i> Floor: ${floor}
                        </div>
                         <div style="display: flex; gap: 0.75rem; font-size: 0.75rem; font-weight: normal; text-transform: none; letter-spacing: normal;">
                            <button class="header-action-link" onclick="openAiAssist('floor', '${floor.replace(/'/g, "\\'")}', event)" title="AI Assist for this Floor" style="background: none; border: none; color: var(--primary); cursor: pointer; display: flex; align-items: center; gap: 0.25rem;">
                                <i class="fa-solid fa-wand-magic-sparkles"></i> AI Assist
                            </button>
                            <button class="header-action-link" onclick="toggleSubGroups('floor', '${floor.replace(/'/g, "\\'")}', true, event)" title="Collapse all rooms under this floor" style="background: none; border: none; color: var(--primary); cursor: pointer; display: flex; align-items: center; gap: 0.25rem;">
                                <i class="fa-solid fa-angles-up"></i> Collapse Rooms
                            </button>
                            <button class="header-action-link" onclick="toggleSubGroups('floor', '${floor.replace(/'/g, "\\'")}', false, event)" title="Expand all rooms under this floor" style="background: none; border: none; color: var(--primary); cursor: pointer; display: flex; align-items: center; gap: 0.25rem;">
                                <i class="fa-solid fa-angles-down"></i> Expand Rooms
                            </button>
                        </div>
                    </div>
                </td>
            `;
            entityTableBody.appendChild(floorTr);
            
            if (isFloorCollapsed) {
                return;
            }
            
            const roomsInFloor = groups[floor];
            // Sort room names (put "No Room" or "TBA" at the end)
            const roomNames = Object.keys(roomsInFloor).sort((a, b) => {
                if (a === 'No Room' || a === 'TBA') return 1;
                if (b === 'No Room' || b === 'TBA') return -1;
                return a.localeCompare(b);
            });
            
            roomNames.forEach(room => {
                const roomKey = `room:${floor}:${room}`;
                const isRoomCollapsed = collapsedGroups.has(roomKey);
                
                // Render Room Header row
                const roomTr = document.createElement('tr');
                roomTr.className = 'room-header-row';
                roomTr.style.cursor = 'pointer';
                roomTr.setAttribute('onclick', `toggleGroup('${roomKey}', event)`);
                
                const roomChevron = isRoomCollapsed ? 'fa-chevron-right' : 'fa-chevron-down';
                
                roomTr.innerHTML = `
                    <td colspan="4" class="room-header-cell" style="padding-left: 2rem !important;">
                        <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                            <div>
                                <i class="fa-solid ${roomChevron}" style="margin-right: 0.5rem; width: 12px;"></i>
                                <i class="fa-solid fa-door-open"></i> ${room}
                            </div>
                            <div style="display: flex; gap: 0.75rem; font-size: 0.75rem; font-weight: normal; text-transform: none; letter-spacing: normal;">
                                <button class="header-action-link" onclick="openAiAssist('room', '${floor.replace(/'/g, "\\'")}:${room.replace(/'/g, "\\'")}', event)" title="AI Assist for this Room" style="background: none; border: none; color: var(--primary); cursor: pointer; display: flex; align-items: center; gap: 0.25rem;">
                                    <i class="fa-solid fa-wand-magic-sparkles"></i> AI Assist
                                </button>
                            </div>
                        </div>
                    </td>
                `;
                entityTableBody.appendChild(roomTr);
                
                if (isRoomCollapsed) {
                    return;
                }
                
                const ents = roomsInFloor[room];
                // Sort entities by domain first, then by entity_id
                ents.sort((a, b) => {
                    const domainComp = (a.domain || '').localeCompare(b.domain || '');
                    if (domainComp !== 0) return domainComp;
                    return a.entity_id.localeCompare(b.entity_id);
                });
                
                ents.forEach(e => {
                    renderEntityRow(e);
                });
            });
        });
    }
}

window.copyEntityId = function(entityId, event) {
    if (event) event.stopPropagation();
    navigator.clipboard.writeText(entityId).then(() => {
        showToast(`Copied ${entityId}`, 'success');
    }).catch(() => {
        showToast(`Copied ${entityId}`, 'success');
    });
};

function renderEntityRow(e) {
    const tr = document.createElement('tr');
    tr.className = 'entity-row';
    
    // Filter out invalid/empty/0 nicknames
    const validAliases = (e.aliases || []).filter(a => a && a !== '0' && a !== 0);
    
    // Aliases rendering with direct click-to-remove and inline "Add" button
    const aliasBadges = validAliases.map(a => `
        <span class="alias-badge">
            ${a}
            <i class="fa-solid fa-xmark alias-delete-btn" onclick="removeAliasDirectly('${e.entity_id}', '${a.replace(/'/g, "\\'")}', event)" title="Remove nickname"></i>
        </span>
    `).join(' ');
    
    if (e.unavailable) {
        tr.style.opacity = '0.75';
    }
    
    // Expose status badge (directly togglable on click)
    let exposeBadge = '';
    if (e.yaml_exposed && e.should_expose) {
        exposeBadge = `<span class="badge badge-exposed" onclick="toggleExposeDirectly('${e.entity_id}', event)" title="Click to toggle exposure" style="cursor: pointer;"><i class="fa-solid fa-circle-check" style="margin-right: 0.3rem;"></i>Exposed</span>`;
    } else if (e.should_expose && !e.yaml_exposed) {
        exposeBadge = `<span class="badge badge-pending-expose" onclick="toggleExposeDirectly('${e.entity_id}', event)" title="Click to toggle exposure" style="cursor: pointer;"><i class="fa-solid fa-circle-pause" style="margin-right: 0.3rem;"></i>Pending Add</span>`;
    } else if (!e.should_expose && e.yaml_exposed) {
        exposeBadge = `<span class="badge badge-pending-remove" onclick="toggleExposeDirectly('${e.entity_id}', event)" title="Click to toggle exposure" style="cursor: pointer;"><i class="fa-solid fa-circle-minus" style="margin-right: 0.3rem;"></i>Pending Remove</span>`;
    } else {
        exposeBadge = `<span class="badge badge-not-exposed" onclick="toggleExposeDirectly('${e.entity_id}', event)" title="Click to toggle exposure" style="cursor: pointer;">No</span>`;
    }
    
    tr.innerHTML = `
        <td>
            <div class="entity-info-wrapper">
                <div class="entity-icon-badge">
                    <i class="fa-solid ${getEntityIcon(e.domain)}" style="color: ${e.unavailable ? 'var(--on-surface-variant)' : 'var(--primary)'};"></i>
                </div>
                <div class="entity-text-block">
                    <div class="entity-name-row">
                        <span class="entity-name" title="${e.display_name}">${e.display_name}</span>
                        ${e.unavailable ? '<span class="badge-unavailable" title="Offline / Unavailable in Home Assistant">Unavailable</span>' : ''}
                        <button class="inline-edit-name-btn" onclick="openEditNameInline('${e.entity_id}', event)" title="Rename Entity" style="background: none; border: none; cursor: pointer; font-size: 0.75rem; padding: 0.15rem; color: var(--on-surface-variant);">
                            <i class="fa-solid fa-pencil"></i>
                        </button>
                    </div>
                    <div class="entity-id-row">
                        <span class="entity-id-badge" onclick="copyEntityId('${e.entity_id}', event)" title="Click to copy entity ID">${e.entity_id}</span>
                        ${e.area ? `<span style="font-size: 0.72rem; color: var(--on-surface-variant);"><i class="fa-solid fa-door-open" style="font-size: 0.65rem; margin-right: 0.2rem;"></i>${e.area}</span>` : ''}
                    </div>
                </div>
            </div>
        </td>
        <td class="inline-aliases-cell">
            <div class="aliases-wrapper">
                <div class="aliases-badges-list">${aliasBadges || '<span class="no-aliases">None</span>'}</div>
                <button class="inline-add-alias-btn" onclick="openQuickAliasModal('${e.entity_id}', event)" title="Add nickname">
                    <i class="fa-solid fa-plus"></i> Add
                </button>
                <button class="ai-suggest-single-btn" onclick="generateSingleEntityNickname('${e.entity_id}', event)" title="AI Suggest Nicknames (Room-Aware)">
                    <i class="fa-solid fa-wand-magic-sparkles"></i>
                </button>
            </div>
        </td>
        <td style="text-align: center;">${exposeBadge}</td>
        <td class="action-cell">
            <button class="action-btn" onclick="addToBlocklistDirectly('${e.entity_id}', event)" title="Block / Permanently Hide">
                <i class="fa-solid fa-eye-slash"></i>
            </button>
        </td>
    `;
    entityTableBody.appendChild(tr);
}

// Inline Quick Nickname Input Handler
window.openQuickAliasModal = function(entityId, event) {
    event.stopPropagation();
    const btn = event.currentTarget;
    const wrapper = btn.closest('.aliases-wrapper');
    if (!wrapper) return;
    
    // Hide list and button
    const list = wrapper.querySelector('.aliases-badges-list');
    btn.style.display = 'none';
    if (list) list.style.display = 'none';
    
    // Create inline input
    const container = document.createElement('div');
    container.className = 'inline-alias-input-container';
    container.innerHTML = `
        <input type="text" class="inline-alias-input" placeholder="Nickname..." autofocus>
        <button class="inline-alias-submit-btn" title="Save"><i class="fa-solid fa-check"></i></button>
        <button class="inline-alias-cancel-btn" title="Cancel"><i class="fa-solid fa-xmark"></i></button>
    `;
    
    wrapper.appendChild(container);
    
    const input = container.querySelector('.inline-alias-input');
    const submitBtn = container.querySelector('.inline-alias-submit-btn');
    const cancelBtn = container.querySelector('.inline-alias-cancel-btn');
    
    input.focus();
    
    const cleanup = () => {
        container.remove();
        btn.style.display = '';
        if (list) list.style.display = '';
    };
    
    cancelBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        cleanup();
    });
    
    const submit = async () => {
        const val = input.value.trim();
        if (!val || val === '0') {
            cleanup();
            return;
        }
        
        const entity = entities.find(e => e.entity_id === entityId);
        if (!entity) {
            cleanup();
            return;
        }
        
        if (entity.aliases.includes(val)) {
            showToast('Nickname already exists', 'error');
            cleanup();
            return;
        }
        
        const updatedAliases = [...entity.aliases, val];
        
        try {
            const response = await authFetch('/api/google_assistant_entity_console/entities/update', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...getAuthHeaders()
                },
                body: JSON.stringify({
                    entity_id: entityId,
                    name: entity.name,
                    aliases: updatedAliases,
                    should_expose: entity.should_expose
                })
            });
            
            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.error || 'Failed to add nickname');
            }
            
            entity.aliases = updatedAliases;
            showToast('Nickname added successfully', 'success');
            applyFilters();
        } catch (error) {
            showToast('Error adding nickname: ' + error.message, 'error');
            cleanup();
        }
    };
    
    submitBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        submit();
    });
    
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            submit();
        } else if (e.key === 'Escape') {
            e.preventDefault();
            cleanup();
        }
    });
};

// Open Edit Modal


// Trigger YAML generation & rebuild
async function handleRebuild() {
    rebuildBtn.disabled = true;
    const icon = rebuildBtn.querySelector('i');
    icon.className = 'fa-solid fa-spinner fa-spin';
    
    try {
        const result = await authFetch('/api/google_assistant_entity_console/rebuild', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({})
        });
        
        if (!result.ok) {
            const err = await result.json();
            throw new Error(err.error || 'Rebuild failed');
        }
        
        const data = await result.json();
        showToast(`Configuration generated successfully. (${data.exposed_count} entities exposed)`, 'success');

        const missingIncludeContainer = document.getElementById('missingIncludeContainer');
        const missingIncludeInput = document.getElementById('missingIncludeInput');
        if (missingIncludeContainer && missingIncludeInput) {
            if (data.has_include_directive === false && data.required_include) {
                missingIncludeInput.value = data.required_include;
                missingIncludeContainer.style.display = 'block';
            } else {
                missingIncludeContainer.style.display = 'none';
            }
        }

        // Open restart confirmation modal
        restartModal.style.display = 'block';
    } catch (error) {
        showToast('Error rebuilding configs: ' + error.message, 'error');
    } finally {
        rebuildBtn.disabled = false;
        icon.className = 'fa-solid fa-file-code';
    }
}

// Trigger Home Assistant restart
async function handleRestart() {
    confirmRestartBtn.disabled = true;
    cancelRestartBtn.disabled = true;
    confirmRestartBtn.textContent = 'Restarting...';
    
    try {
        const response = await authFetch('/api/google_assistant_entity_console/restart', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
            body: JSON.stringify({})
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Restart failed');
        }
        
        showToast('Home Assistant is restarting...', 'success');
        restartModal.style.display = 'none';
        
        // Wait and check back
        setTimeout(() => {
            window.location.reload();
        }, 12000);
    } catch (error) {
        showToast('Error restarting Home Assistant: ' + error.message, 'error');
        confirmRestartBtn.disabled = false;
        cancelRestartBtn.disabled = false;
        confirmRestartBtn.textContent = 'Yes, Restart';
    }
}

// Click to toggle exposure status directly
window.toggleExposeDirectly = async function(entityId, event) {
    if (event) event.stopPropagation();
    const entity = entities.find(e => e.entity_id === entityId);
    if (!entity) return;
    
    const newExposeStatus = !entity.should_expose;
    
    try {
        const response = await authFetch('/api/google_assistant_entity_console/entities/update', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
            body: JSON.stringify({
                entity_id: entityId,
                should_expose: newExposeStatus
            })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to toggle status');
        }
        
        entity.should_expose = newExposeStatus;
        showToast(`Exposure updated for ${entity.display_name}`, 'success');
        updateStats();
        applyFilters();
    } catch (error) {
        showToast('Error toggling exposure: ' + error.message, 'error');
    }
};

// Remove nickname badge directly from table row
window.removeAliasDirectly = async function(entityId, alias, event) {
    if (event) event.stopPropagation();
    const entity = entities.find(e => e.entity_id === entityId);
    if (!entity) return;
    
    const updatedAliases = (entity.aliases || []).filter(a => a !== alias);
    
    try {
        const response = await authFetch('/api/google_assistant_entity_console/entities/update', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
            body: JSON.stringify({
                entity_id: entityId,
                aliases: updatedAliases
            })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to remove nickname');
        }
        
        entity.aliases = updatedAliases;
        showToast(`Removed nickname "${alias}"`, 'success');
        applyFilters();
    } catch (error) {
        showToast('Error removing nickname: ' + error.message, 'error');
    }
};

// Inline friendly name editing
window.openEditNameInline = function(entityId, event) {
    if (event) event.stopPropagation();
    const cell = event.currentTarget.closest('.entity-info-wrapper');
    if (!cell) return;
    
    const nameWrapper = cell.querySelector('.entity-name-wrapper');
    let inputContainer = cell.querySelector('.inline-name-input-container');
    
    if (!inputContainer) {
        const entity = entities.find(e => e.entity_id === entityId);
        if (!entity) return;
        
        inputContainer = document.createElement('div');
        inputContainer.className = 'inline-name-input-container';
        inputContainer.style.display = 'flex';
        inputContainer.style.alignItems = 'center';
        inputContainer.style.gap = '0.25rem';
        inputContainer.innerHTML = `
            <input type="text" class="inline-name-input" value="${entity.display_name}" style="background-color: var(--surface-variant); border: 1px solid var(--border); color: var(--on-surface); font-size: 0.9rem; padding: 0.15rem 0.4rem; border-radius: 6px; width: 160px;" autofocus>
            <button class="inline-name-submit-btn" title="Save" style="color: var(--success); background: none; border: none; cursor: pointer; padding: 0.2rem;"><i class="fa-solid fa-check"></i></button>
            <button class="inline-name-cancel-btn" title="Cancel" style="color: var(--danger); background: none; border: none; cursor: pointer; padding: 0.2rem;"><i class="fa-solid fa-xmark"></i></button>
        `;
        cell.insertBefore(inputContainer, nameWrapper);
        
        const input = inputContainer.querySelector('.inline-name-input');
        const submitBtn = inputContainer.querySelector('.inline-name-submit-btn');
        const cancelBtn = inputContainer.querySelector('.inline-name-cancel-btn');
        
        input.focus();
        
        cancelBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            inputContainer.remove();
            nameWrapper.style.display = 'inline-flex';
        });
        
        const submit = async () => {
            const newName = input.value.trim();
            if (newName === entity.display_name) {
                inputContainer.remove();
                nameWrapper.style.display = 'inline-flex';
                return;
            }
            
            try {
                const response = await authFetch('/api/google_assistant_entity_console/entities/update', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        ...getAuthHeaders()
                    },
                    body: JSON.stringify({
                        entity_id: entityId,
                        name: newName || null
                    })
                });
                
                if (!response.ok) {
                    const err = await response.json();
                    throw new Error(err.error || 'Failed to update name');
                }
                
                entity.name = newName || null;
                entity.display_name = newName || entity.original_name || entityId.split('.').pop()?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) || '';
                showToast('Name updated successfully', 'success');
                applyFilters();
            } catch (error) {
                showToast('Error updating name: ' + error.message, 'error');
                inputContainer.remove();
                nameWrapper.style.display = 'inline-flex';
            }
        };
        
        submitBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            submit();
        });
        
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                submit();
            } else if (e.key === 'Escape') {
                e.preventDefault();
                inputContainer.remove();
                nameWrapper.style.display = 'inline-flex';
            }
        });
    }
    
    nameWrapper.style.display = 'none';
};

// Toast notification helper
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    toast.className = `toast show ${type}`;
    toast.innerHTML = `
        <i class="fa-solid ${type === 'success' ? 'fa-circle-check' : 'fa-circle-exclamation'}"></i>
        <span>${message}</span>
    `;
    
    setTimeout(() => {
        toast.className = 'toast';
    }, 4000);
}

// Fetch blocklist patterns from backend
async function fetchBlocklist() {
    blocklistContainer.innerHTML = '<span style="color: var(--on-surface-variant); font-size: 0.9rem; font-style: italic;">Loading blocklist...</span>';
    try {
        const response = await authFetch('/api/google_assistant_entity_console/blocklist', {
            headers: getAuthHeaders()
        });
        if (!response.ok) throw new Error('Failed to fetch blocklist');
        const data = await response.json();
        renderBlocklist(data.blocklist || []);
    } catch (error) {
        showToast('Error loading blocklist: ' + error.message, 'error');
        blocklistContainer.innerHTML = '<span style="color: var(--danger); font-size: 0.9rem;">Error loading blocklist patterns.</span>';
    }
}

// Render blocklist in the container
function renderBlocklist(patterns) {
    blocklistContainer.innerHTML = '';
    if (patterns.length === 0) {
        blocklistContainer.innerHTML = '<span style="color: var(--on-surface-variant); font-size: 0.9rem; font-style: italic; padding: 0.5rem 0;">No blocked patterns defined yet.</span>';
        return;
    }
    
    patterns.forEach(pattern => {
        const row = document.createElement('div');
        row.style.display = 'flex';
        row.style.justify = 'space-between';
        row.style.alignItems = 'center';
        row.style.padding = '0.4rem 0.6rem';
        row.style.backgroundColor = 'rgba(255,255,255,0.03)';
        row.style.borderRadius = '6px';
        row.style.border = '1px solid var(--border)';
        
        row.innerHTML = `
            <code style="font-family: monospace; font-size: 0.9rem; color: var(--primary);">${pattern}</code>
            <button class="action-btn" onclick="removeBlocklistPattern('${pattern.replace(/'/g, "\\'")}')" title="Remove Pattern" style="color: var(--danger); width: 1.8rem; height: 1.8rem; font-size: 0.95rem;">
                <i class="fa-solid fa-trash-can"></i>
            </button>
        `;
        blocklistContainer.appendChild(row);
    });
}

// Add a regex pattern to blocklist
async function addBlocklistPattern(pattern) {
    try {
        const response = await authFetch('/api/google_assistant_entity_console/blocklist/add', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
            body: JSON.stringify({ pattern })
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to add pattern');
        }
        newBlocklistPattern.value = '';
        showToast('Pattern added to blocklist', 'success');
        
        // Refresh local view and fetch blocklist details
        await fetchBlocklist();
        await fetchEntities();
    } catch (error) {
        showToast('Error adding pattern: ' + error.message, 'error');
    }
}

// Remove a regex pattern from blocklist
async function removeBlocklistPattern(pattern) {
    try {
        // Fetch current list first
        const getRes = await authFetch('/api/google_assistant_entity_console/blocklist', {
            headers: getAuthHeaders()
        });
        if (!getRes.ok) throw new Error('Failed to load current list');
        const getData = await getRes.json();
        
        const updatedList = (getData.blocklist || []).filter(p => p !== pattern);
        
        const response = await authFetch('/api/google_assistant_entity_console/blocklist', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
            body: JSON.stringify({ blocklist: updatedList })
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to update blocklist');
        }
        
        showToast('Pattern removed from blocklist', 'success');
        renderBlocklist(updatedList);
        
        // Refresh entities table
        await fetchEntities();
    } catch (error) {
        showToast('Error removing pattern: ' + error.message, 'error');
    }
}

// Hide an entity directly by adding exact regex pattern to blocklist
window.addToBlocklistDirectly = async function(entityId, event) {
    if (event) event.stopPropagation();
    if (!confirm(`Are you sure you want to block and permanently hide ${entityId}?`)) {
        return;
    }
    
    // Create an exact match pattern
    const pattern = `^${entityId.replace(/\./g, '\\.')}$`;
    
    try {
        const response = await authFetch('/api/google_assistant_entity_console/blocklist/add', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
            body: JSON.stringify({ pattern })
        });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to block entity');
        }
        
        showToast(`${entityId} blocked and hidden`, 'success');
        
        // Remove locally from the array to immediately update UI
        entities = entities.filter(e => e.entity_id !== entityId);
        updateStats();
        applyFilters();
        showToast(`${entityId} blocked and hidden`, 'success');
        
        // Remove locally from the array to immediately update UI
        entities = entities.filter(e => e.entity_id !== entityId);
        updateStats();
        applyFilters();
    } catch (error) {
        showToast('Error blocking entity: ' + error.message, 'error');
    }
};

// AI Features: Settings, Modal, and Assistant Logic
let aiSettings = {};

async function loadAiSettings() {
    try {
        const response = await authFetch('/api/google_assistant_entity_console/ai/settings', {
            headers: getAuthHeaders()
        });
        if (response.ok) {
            const data = await response.json();
            aiSettings = data.settings || {};
            
            // Populate fields
            const aiSourceEl = document.getElementById('aiSource');
            const baseUrlEl = document.getElementById('aiBaseUrl');
            const apiKeyEl = document.getElementById('aiApiKey');
            const nicknameEl = document.getElementById('nicknamePrompt');
            const singleNicknameEl = document.getElementById('singleNicknamePrompt');
            const exposureEl = document.getElementById('exposurePrompt');
            const modelEl = document.getElementById('aiModel');
            const haAgentIdEl = document.getElementById('haAgentId');
            
            if (aiSourceEl) {
                aiSourceEl.value = aiSettings.ai_source || 'openai';
                updateConnectionFieldsDisplay(aiSourceEl.value);
            }
            if (baseUrlEl) baseUrlEl.value = aiSettings.base_url || '';
            if (apiKeyEl) apiKeyEl.value = aiSettings.api_key || '';
            if (nicknameEl) nicknameEl.value = aiSettings.nickname_prompt || '';
            if (singleNicknameEl) singleNicknameEl.value = aiSettings.single_nickname_prompt || '';
            if (exposureEl) exposureEl.value = aiSettings.exposure_prompt || '';
            
            if (modelEl && aiSettings.model) {
                modelEl.innerHTML = `<option value="${aiSettings.model}">${aiSettings.model}</option>`;
                modelEl.value = aiSettings.model;
            }
            
            if (haAgentIdEl && aiSettings.ha_agent_id) {
                haAgentIdEl.innerHTML = `<option value="${aiSettings.ha_agent_id}">${aiSettings.ha_agent_id}</option>`;
                haAgentIdEl.value = aiSettings.ha_agent_id;
            }
        }
    } catch (e) {
        console.error("Failed to load AI settings", e);
    }
}

function updateConnectionFieldsDisplay(source) {
    const openaiFields = document.getElementById('connection-openai-fields');
    const haFields = document.getElementById('connection-ha-fields');
    if (source === 'home_assistant') {
        if (openaiFields) openaiFields.style.display = 'none';
        if (haFields) haFields.style.display = 'flex';
    } else {
        if (openaiFields) openaiFields.style.display = 'flex';
        if (haFields) haFields.style.display = 'none';
    }
}

// Bind AI Events
function setupAiEventListeners() {
    loadAiSettings();
    
    const openAiSettingsBtn = document.getElementById('openAiSettingsBtn');
    const aiSettingsModal = document.getElementById('aiSettingsModal');
    const closeAiSettingsModal = document.getElementById('closeAiSettingsModal');
    const closeAiSettingsModalBtn = document.getElementById('closeAiSettingsModalBtn');
    const saveAiSettingsBtn = document.getElementById('saveAiSettingsBtn');
    const queryModelsBtn = document.getElementById('queryModelsBtn');
    
    if (openAiSettingsBtn && aiSettingsModal) {
        openAiSettingsBtn.addEventListener('click', () => {
            aiSettingsModal.style.display = 'block';
            switchSettingsTab('connection');
        });
    }
    
    const closeSettings = () => {
        if (aiSettingsModal) aiSettingsModal.style.display = 'none';
    };
    if (closeAiSettingsModal) closeAiSettingsModal.addEventListener('click', closeSettings);
    if (closeAiSettingsModalBtn) closeAiSettingsModalBtn.addEventListener('click', closeSettings);
    
    if (queryModelsBtn) {
        queryModelsBtn.addEventListener('click', async () => {
            const baseUrl = document.getElementById('aiBaseUrl').value.trim();
            const apiKey = document.getElementById('aiApiKey').value.trim();
            if (!baseUrl) {
                showToast('Please enter a Base URL first', 'error');
                return;
            }
            queryModelsBtn.disabled = true;
            queryModelsBtn.textContent = 'Fetching...';
            try {
                const response = await authFetch('/api/google_assistant_entity_console/ai/models', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        ...getAuthHeaders()
                    },
                    body: JSON.stringify({ base_url: baseUrl, api_key: apiKey })
                });
                if (!response.ok) {
                    const err = await response.json();
                    throw new Error(err.error || 'Failed to fetch models');
                }
                const data = await response.json();
                const modelSelect = document.getElementById('aiModel');
                if (modelSelect) {
                    modelSelect.innerHTML = '<option value="">Select a model...</option>';
                    data.models.forEach(m => {
                        const opt = document.createElement('option');
                        opt.value = m.id;
                        
                        // Parse pricing details if they exist (formatted per 1M tokens)
                        let pricingText = '';
                        if (m.pricing && m.pricing.prompt !== undefined) {
                            const promptM = (parseFloat(m.pricing.prompt) * 1000000).toFixed(2);
                            const completionM = (parseFloat(m.pricing.completion) * 1000000).toFixed(2);
                            pricingText = ` ($${promptM}/M in, $${completionM}/M out)`;
                        }
                        
                        opt.textContent = `${m.name}${pricingText}`;
                        modelSelect.appendChild(opt);
                    });
                    if (aiSettings.model) {
                        modelSelect.value = aiSettings.model;
                    }
                    showToast('Models fetched successfully!', 'success');
                }
            } catch (error) {
                showToast('Error querying models: ' + error.message, 'error');
            } finally {
                queryModelsBtn.disabled = false;
                queryModelsBtn.textContent = 'Fetch Models';
            }
        });
    }
    
    if (saveAiSettingsBtn) {
        saveAiSettingsBtn.addEventListener('click', async () => {
            const aiSource = document.getElementById('aiSource').value;
            const baseUrl = document.getElementById('aiBaseUrl').value.trim();
            const apiKey = document.getElementById('aiApiKey').value.trim();
            const model = document.getElementById('aiModel').value.trim();
            const haAgentId = document.getElementById('haAgentId').value.trim();
            const nicknamePrompt = document.getElementById('nicknamePrompt').value;
            const singleNicknamePrompt = document.getElementById('singleNicknamePrompt').value;
            const exposurePrompt = document.getElementById('exposurePrompt').value;
            
            saveAiSettingsBtn.disabled = true;
            saveAiSettingsBtn.textContent = 'Saving...';
            try {
                const response = await authFetch('/api/google_assistant_entity_console/ai/settings', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        ...getAuthHeaders()
                    },
                    body: JSON.stringify({
                        settings: {
                            ai_source: aiSource,
                            base_url: baseUrl,
                            api_key: apiKey,
                            model: model,
                            ha_agent_id: haAgentId,
                            nickname_prompt: nicknamePrompt,
                            single_nickname_prompt: singleNicknamePrompt,
                            exposure_prompt: exposurePrompt
                        }
                    })
                });
                if (!response.ok) {
                    const err = await response.json();
                    throw new Error(err.error || 'Failed to save settings');
                }
                aiSettings = {
                    ai_source: aiSource,
                    base_url: baseUrl,
                    api_key: apiKey,
                    model: model,
                    ha_agent_id: haAgentId,
                    nickname_prompt: nicknamePrompt,
                    single_nickname_prompt: singleNicknamePrompt,
                    exposure_prompt: exposurePrompt
                };
                showToast('AI Settings saved successfully', 'success');
                closeSettings();
            } catch (error) {
                showToast('Error saving settings: ' + error.message, 'error');
            } finally {
                saveAiSettingsBtn.disabled = false;
                saveAiSettingsBtn.textContent = 'Save Settings';
            }
        });
    }

    // Toggle fields based on selected source
    const aiSource = document.getElementById('aiSource');
    if (aiSource) {
        aiSource.addEventListener('change', (e) => {
            updateConnectionFieldsDisplay(e.target.value);
        });
    }

    // Fetch HA Agents
    const queryHaAgentsBtn = document.getElementById('queryHaAgentsBtn');
    if (queryHaAgentsBtn) {
        queryHaAgentsBtn.addEventListener('click', async () => {
            queryHaAgentsBtn.disabled = true;
            queryHaAgentsBtn.textContent = 'Fetching...';
            try {
                const response = await authFetch('/api/google_assistant_entity_console/ai/ha_agents', {
                    headers: getAuthHeaders()
                });
                if (!response.ok) {
                    const err = await response.json();
                    throw new Error(err.error || 'Failed to fetch agents');
                }
                const data = await response.json();
                const haAgentSelect = document.getElementById('haAgentId');
                if (haAgentSelect) {
                    haAgentSelect.innerHTML = '<option value="">Select an agent...</option>';
                    data.agents.forEach(agent => {
                        const opt = document.createElement('option');
                        opt.value = agent.id;
                        opt.textContent = agent.name;
                        haAgentSelect.appendChild(opt);
                    });
                    if (aiSettings.ha_agent_id) {
                        haAgentSelect.value = aiSettings.ha_agent_id;
                    }
                    showToast('Home Assistant Agents fetched successfully!', 'success');
                }
            } catch (error) {
                showToast('Error querying HA Agents: ' + error.message, 'error');
            } finally {
                queryHaAgentsBtn.disabled = false;
                queryHaAgentsBtn.textContent = 'Fetch Agents';
            }
        });
    }
    
    // AI Assist Dialog controls
    const aiAssistModal = document.getElementById('aiAssistModal');
    const closeAiAssistModal = document.getElementById('closeAiAssistModal');
    const closeAiAssistModalBtn = document.getElementById('closeAiAssistModalBtn');
    
    const closeAssist = () => {
        if (aiAssistModal) aiAssistModal.style.display = 'none';
    };
    if (closeAiAssistModal) closeAiAssistModal.addEventListener('click', closeAssist);
    if (closeAiAssistModalBtn) closeAiAssistModalBtn.addEventListener('click', closeAssist);
    
    // AI Nicknames button click handler
    const aiGenNicknamesBtn = document.getElementById('aiGenNicknamesBtn');
    if (aiGenNicknamesBtn) {
        aiGenNicknamesBtn.addEventListener('click', async () => {
            const targetType = document.getElementById('aiAssistTargetType').value;
            const targetId = document.getElementById('aiAssistTargetId').value;
            const ents = getEntitiesInGroup(targetType, targetId);
            
            if (ents.length === 0) {
                showToast('No entities in this group to generate nicknames for.', 'error');
                return;
            }
            
            aiGenNicknamesBtn.disabled = true;
            const oldText = aiGenNicknamesBtn.innerHTML;
            aiGenNicknamesBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin" style="margin-right: 0.5rem;"></i> Generating...';
            
            try {
                const response = await authFetch('/api/google_assistant_entity_console/ai/generate_nicknames', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        ...getAuthHeaders()
                    },
                    body: JSON.stringify({ entities: ents })
                });
                if (!response.ok) {
                    const err = await response.json();
                    throw new Error(err.error || 'Request failed');
                }
                const data = await response.json();
                const results = data.results || {};
                
                // Save nicknames to HA registry concurrently
                const promises = [];
                for (const [entityId, aliases] of Object.entries(results)) {
                    if (aliases && aliases.length > 0) {
                        promises.push(setAliasesDirectly(entityId, aliases));
                    }
                }
                await Promise.all(promises);
                
                showToast(`AI successfully generated nicknames for ${promises.length} entities!`, 'success');
                closeAssist();
                applyFilters();
            } catch (error) {
                showToast('AI Nickname generation failed: ' + error.message, 'error');
            } finally {
                aiGenNicknamesBtn.disabled = false;
                aiGenNicknamesBtn.innerHTML = oldText;
            }
        });
    }
    
    // AI Suggest Exposure button click handler (now renders a review checklist first)
    const aiSuggestExposureBtn = document.getElementById('aiSuggestExposureBtn');
    const aiExposureResultsContainer = document.getElementById('aiExposureResultsContainer');
    const aiExposureResultsList = document.getElementById('aiExposureResultsList');
    const aiApplyExposureBtn = document.getElementById('aiApplyExposureBtn');
    
    if (aiSuggestExposureBtn) {
        aiSuggestExposureBtn.addEventListener('click', async () => {
            const targetType = document.getElementById('aiAssistTargetType').value;
            const targetId = document.getElementById('aiAssistTargetId').value;
            const intent = document.getElementById('aiExposureIntent').value.trim();
            
            if (!intent) {
                showToast('Please enter your criteria intent (e.g. Expose only switches)', 'error');
                return;
            }
            
            const ents = getEntitiesInGroup(targetType, targetId);
            if (ents.length === 0) {
                showToast('No entities in this group to analyze.', 'error');
                return;
            }
            
            // Clear old results
            if (aiExposureResultsContainer) aiExposureResultsContainer.style.display = 'none';
            if (aiExposureResultsList) aiExposureResultsList.innerHTML = '';
            
            aiSuggestExposureBtn.disabled = true;
            const oldText = aiSuggestExposureBtn.innerHTML;
            aiSuggestExposureBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin" style="margin-right: 0.5rem;"></i> Analyzing...';
            
            try {
                const response = await authFetch('/api/google_assistant_entity_console/ai/suggest_exposure', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        ...getAuthHeaders()
                    },
                    body: JSON.stringify({ entities: ents, user_intent: intent })
                });
                if (!response.ok) {
                    const err = await response.json();
                    throw new Error(err.error || 'Request failed');
                }
                const data = await response.json();
                const exposedIds = data.exposed_ids || [];
                
                // Filter ents to find the ones suggested
                const suggestedEnts = ents.filter(e => exposedIds.includes(e.entity_id));
                
                if (suggestedEnts.length === 0) {
                    showToast('AI did not suggest exposing any new entities matching this criteria.', 'info');
                    return;
                }
                
                // Render checklist
                suggestedEnts.forEach(e => {
                    const div = document.createElement('div');
                    div.style.display = 'flex';
                    div.style.alignItems = 'center';
                    div.style.gap = '0.5rem';
                    div.style.padding = '0.2rem 0';
                    div.innerHTML = `
                        <input type="checkbox" id="aiExposeCheck_${e.entity_id.replace(/\./g, '_')}" value="${e.entity_id}" checked style="cursor: pointer; width: 15px; height: 15px;">
                        <label for="aiExposeCheck_${e.entity_id.replace(/\./g, '_')}" style="cursor: pointer; font-size: 0.8rem; display: flex; align-items: center; gap: 0.35rem; color: var(--on-surface);">
                            <i class="fa-solid ${getEntityIcon(e.domain)}" style="color: var(--primary); font-size: 0.8rem; width: 12px; text-align: center;"></i>
                            <span style="font-weight: 500;">${e.display_name}</span>
                            <span style="color: var(--on-surface-variant); font-size: 0.7rem; font-family: monospace;">(${e.entity_id})</span>
                        </label>
                    `;
                    aiExposureResultsList.appendChild(div);
                });
                
                if (aiExposureResultsContainer) aiExposureResultsContainer.style.display = 'flex';
                showToast(`AI generated suggestions for ${suggestedEnts.length} entities. Check list below.`, 'success');
            } catch (error) {
                showToast('AI Smart exposure analysis failed: ' + error.message, 'error');
            } finally {
                aiSuggestExposureBtn.disabled = false;
                aiSuggestExposureBtn.innerHTML = oldText;
            }
        });
    }
    
    if (aiApplyExposureBtn) {
        aiApplyExposureBtn.addEventListener('click', async () => {
            const checkboxes = aiExposureResultsList.querySelectorAll('input[type="checkbox"]:checked');
            if (checkboxes.length === 0) {
                showToast('No entities selected to expose.', 'error');
                return;
            }
            
            aiApplyExposureBtn.disabled = true;
            const oldBtnText = aiApplyExposureBtn.innerHTML;
            aiApplyExposureBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin" style="margin-right: 0.5rem;"></i> Exposing...';
            
            const promises = [];
            checkboxes.forEach(cb => {
                promises.push(setExposureDirectly(cb.value, true));
            });
            
            try {
                await Promise.all(promises);
                showToast(`Successfully exposed ${promises.length} entities!`, 'success');
                closeAssist();
                updateStats();
                applyFilters();
            } catch (error) {
                showToast('Error applying AI exposure: ' + error.message, 'error');
            } finally {
                aiApplyExposureBtn.disabled = false;
                aiApplyExposureBtn.innerHTML = oldBtnText;
            }
        });
    }
}

// AI Assist Pop Up Launcher
window.openAiAssist = function(targetType, targetId, event) {
    if (event) event.stopPropagation();
    
    const modal = document.getElementById('aiAssistModal');
    const targetTypeEl = document.getElementById('aiAssistTargetType');
    const targetIdEl = document.getElementById('aiAssistTargetId');
    const targetDisplayEl = document.getElementById('aiAssistTargetDisplay');
    
    if (modal && targetTypeEl && targetIdEl && targetDisplayEl) {
        targetTypeEl.value = targetType;
        targetIdEl.value = targetId;
        
        let label = '';
        if (targetType === 'floor') {
            label = `Floor: ${targetId}`;
        } else if (targetType === 'room') {
            const parts = targetId.split(':');
            label = `Room: ${parts[parts.length - 1]} (${parts[0]})`;
        } else {
            const parts = targetId.split(':');
            label = `Domain: ${getDomainName(parts[parts.length - 1])}`;
        }
        
        targetDisplayEl.textContent = `Applying AI Assist to: ${label}`;
        
        // Clear old intent and results
        const intentEl = document.getElementById('aiExposureIntent');
        if (intentEl) intentEl.value = '';
        const resultsContainer = document.getElementById('aiExposureResultsContainer');
        if (resultsContainer) resultsContainer.style.display = 'none';
        const resultsList = document.getElementById('aiExposureResultsList');
        if (resultsList) resultsList.innerHTML = '';
        
        modal.style.display = 'block';
    }
};

// Help gather entities in a specific group floor/room/domain
function getEntitiesInGroup(targetType, targetId) {
    if (targetType === 'floor') {
        return entities.filter(e => e.floor === targetId);
    } else if (targetType === 'room') {
        // targetId format: 'floor:room' or 'domain:floor:room'
        const parts = targetId.split(':');
        const roomName = parts[parts.length - 1];
        const floorName = parts[parts.length - 2];
        return entities.filter(e => e.floor === floorName && e.area === roomName);
    } else {
        // domain targetId format: 'domainName' or 'floor:room:domainName'
        const parts = targetId.split(':');
        const domainName = parts[parts.length - 1];
        if (parts.length > 1) {
            const roomName = parts[parts.length - 2];
            const floorName = parts[parts.length - 3];
            return entities.filter(e => e.domain === domainName && e.floor === floorName && e.area === roomName);
        }
        return entities.filter(e => e.domain === domainName);
    }
}

// Helpers for Direct updates
async function setExposureDirectly(entityId, newExposeStatus) {
    try {
        const response = await authFetch('/api/google_assistant_entity_console/entities/update', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
            body: JSON.stringify({
                entity_id: entityId,
                should_expose: newExposeStatus
            })
        });
        if (response.ok) {
            const entity = entities.find(e => e.entity_id === entityId);
            if (entity) entity.should_expose = newExposeStatus;
            return true;
        }
    } catch (e) {
        console.error("Failed to update exposure for " + entityId, e);
    }
    return false;
}

async function setAliasesDirectly(entityId, aliases) {
    try {
        const entity = entities.find(e => e.entity_id === entityId);
        if (!entity) return false;
        const response = await authFetch('/api/google_assistant_entity_console/entities/update', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
            body: JSON.stringify({
                entity_id: entityId,
                name: entity.name,
                aliases: aliases,
                should_expose: entity.should_expose
            })
        });
        if (response.ok) {
            entity.aliases = aliases;
            return true;
        }
    } catch (e) {
        console.error("Failed to update aliases for " + entityId, e);
    }
    return false;
}

window.generateSingleEntityNickname = async function(entityId, event) {
    if (event) event.stopPropagation();
    const entity = entities.find(e => e.entity_id === entityId);
    if (!entity) return;
    
    // Find all other entities in the same room/area context
    const roomEntities = entities.filter(e => e.area === entity.area);
    
    // Show loading toast
    showToast(`AI suggesting nicknames for ${entity.display_name}...`, 'info');
    
    try {
        const response = await authFetch('/api/google_assistant_entity_console/ai/generate_single_nickname', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...getAuthHeaders()
            },
            body: JSON.stringify({
                entity_id: entityId,
                display_name: entity.display_name,
                room_entities: roomEntities
            })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to suggest nickname');
        }
        
        const data = await response.json();
        const aliases = data.aliases || [];
        
        if (aliases.length === 0) {
            showToast('AI returned no nickname suggestions.', 'error');
            return;
        }
        
        // Update aliases directly in registry
        const success = await setAliasesDirectly(entityId, aliases);
        if (success) {
            showToast(`AI suggested nicknames added for ${entity.display_name}`, 'success');
            applyFilters();
        } else {
            showToast('Failed to save AI suggested nicknames.', 'error');
        }
    } catch (error) {
        showToast('AI suggestions failed: ' + error.message, 'error');
    }
};

window.switchSettingsTab = function(tabName, event) {
    if (event) event.preventDefault();
    const tabs = ['connection', 'prompts'];
    tabs.forEach(t => {
        const btn = document.getElementById(`btn-tab-${t}`);
        const panel = document.getElementById(`tab-panel-${t}`);
        if (t === tabName) {
            if (btn) {
                btn.classList.add('active');
                btn.style.borderBottomColor = 'var(--primary)';
                btn.style.color = 'var(--primary)';
            }
            if (panel) {
                panel.style.display = 'flex';
            }
        } else {
            if (btn) {
                btn.classList.remove('active');
                btn.style.borderBottomColor = 'transparent';
                btn.style.color = 'var(--on-surface-variant)';
            }
            if (panel) {
                panel.style.display = 'none';
            }
        }
    });
};


