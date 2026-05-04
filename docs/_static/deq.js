let deq_table = [];
let currentRenderedData = [];
let sortState = { col: 'deq', dir: 'desc' };

// Grade ordered worst→best so desc sort puts A+ first
const GRADE_ORDER = ['N/A', 'F', 'D-', 'D', 'D+', 'C-', 'C', 'C+', 'B-', 'B', 'B+', 'A-', 'A', 'A+'];
const RARITY_ORDER = { common: 0, uncommon: 1, rare: 2, mythic: 3 };
const WUBRG = { W: 0, U: 1, B: 2, R: 3, G: 4 };

function colorSortKey(color) {
    if (!color) return -1;
    let val = 0;
    for (const c of color) val = val * 5 + (WUBRG[c] ?? 0);
    return color.length * 10000 + val;
}

// Doc panel toggle
const docButton = document.getElementById('docButton');
const docText = document.getElementById('docText');

docButton.addEventListener('click', function() {
    const isExpanded = docText.classList.contains('expanded');
    if (isExpanded) {
        docText.classList.remove('expanded');
        docButton.classList.remove('expanded');
        docButton.querySelector('span').textContent = '▼';
    } else {
        docText.classList.add('expanded');
        docButton.classList.add('expanded');
        docButton.querySelector('span').textContent = '▲';
    }
});

document.addEventListener('click', function(event) {
    if (!event.target.closest('.info-table-container') && docText.classList.contains('expanded')) {
        docText.classList.remove('expanded');
        docButton.classList.remove('expanded');
        docButton.querySelector('span').textContent = '▼';
    }
});

// Column description row (shown as first tbody row when a ? is active)
let openColDesc = null;

document.querySelectorAll('.col-info').forEach(btn => {
    btn.addEventListener('click', function(e) {
        e.stopImmediatePropagation();
        const text = this.dataset.colDesc;
        openColDesc = openColDesc === text ? null : text;
        renderTable(sortData(filterData(searchInput.value)));
    });
});

// Sorting
function sortKey(row, col) {
    switch (col) {
        case 'deq':     return row.deq;
        case 'name':    return row.name;
        case 'color':   return colorSortKey(row.color);
        case 'rarity':  return RARITY_ORDER[row.rarity] ?? -1;
        case 'pct_top': return row.pct_top;
        case 'npr':     return row.npr;
        default:        return null;
    }
}

function sortData(data) {
    const { col, dir } = sortState;
    const mult = dir === 'asc' ? 1 : -1;
    return [...data].sort((a, b) => {
        const ka = sortKey(a, col);
        const kb = sortKey(b, col);
        if (ka == null && kb == null) return 0;
        if (ka == null) return 1;
        if (kb == null) return -1;
        if (typeof ka === 'string') return mult * ka.localeCompare(kb);
        return mult * (ka - kb);
    });
}

function updateSortIndicators() {
    document.querySelectorAll('#dataTable .sort-ind').forEach(el => el.textContent = '');
    const th = document.querySelector(`#dataTable th[data-sort="${sortState.col}"]`);
    if (th) th.querySelector('.sort-ind').textContent = sortState.dir === 'desc' ? '▼' : '▲';
}

document.querySelector('#dataTable thead').addEventListener('click', function(e) {
    const th = e.target.closest('th[data-sort]');
    if (!th) return;
    const col = th.dataset.sort;
    if (sortState.col === col) {
        sortState.dir = sortState.dir === 'asc' ? 'desc' : 'asc';
    } else {
        sortState.col = col;
        sortState.dir = (col === 'name' || col === 'color' || col === 'rarity') ? 'asc' : 'desc';
    }
    openColDesc = null;
    updateSortIndicators();
    renderTable(sortData(filterData(searchInput.value)));
});

// Modal
const modal = document.getElementById('modal');
const modalClose = document.getElementById('modalClose');
const modalPrev = document.getElementById('modalPrev');
const modalNext = document.getElementById('modalNext');
let openModalIdx = -1;

function openModal(idx) {
    const card = currentRenderedData[idx];
    openModalIdx = idx;
    document.getElementById('modalImage').src = card.image_url || '';
    document.getElementById('modalImage').alt = card.name;
    document.getElementById('modalGrade').textContent = card.deq_grade;
    document.getElementById('modalDeq').textContent = deqFormat(card.deq);
    document.getElementById('modalNpr').textContent = nprFormat(card.npr);
    document.getElementById('modalPctTop').textContent = pctFormat(card.pct_top);
    modalPrev.disabled = idx <= 0;
    modalNext.disabled = idx >= currentRenderedData.length - 1;
    modal.classList.add('active');
}

function closeModal() {
    modal.classList.remove('active');
}

modalClose.addEventListener('click', closeModal);
modalPrev.addEventListener('click', () => openModal(openModalIdx - 1));
modalNext.addEventListener('click', () => openModal(openModalIdx + 1));

modal.addEventListener('click', function(e) {
    if (e.target === modal) closeModal();
});

let touchStartX = 0, touchStartY = 0;

modal.addEventListener('touchstart', e => {
    touchStartX = e.touches[0].clientX;
    touchStartY = e.touches[0].clientY;
}, { passive: true });

modal.addEventListener('touchend', e => {
    const dx = e.changedTouches[0].clientX - touchStartX;
    const dy = e.changedTouches[0].clientY - touchStartY;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) {
        if (dx < 0 && !modalNext.disabled) openModal(openModalIdx + 1);
        if (dx > 0 && !modalPrev.disabled) openModal(openModalIdx - 1);
    }
}, { passive: true });

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeModal();
    if (!modal.classList.contains('active')) return;
    if (e.key === 'ArrowLeft' && !modalPrev.disabled) openModal(openModalIdx - 1);
    if (e.key === 'ArrowRight' && !modalNext.disabled) openModal(openModalIdx + 1);
});

document.getElementById('tableBody').addEventListener('click', function(e) {
    const cell = e.target.closest('.name-cell');
    if (!cell) return;
    openModal(parseInt(cell.dataset.idx, 10));
});

document.querySelector('.modal-stats').addEventListener('click', function(e) {
    const label = e.target.closest('.stat-label');
    if (!label) return;
    const desc = document.getElementById(label.dataset.desc);
    if (desc) desc.classList.toggle('open');
});

// Formatters
function deqFormat(num) {
    return typeof(num) === "number" ? num.toLocaleString('en-US', {
        style: 'percent',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
        signDisplay: 'always',
    }) : "N/A"
}

function nprFormat(num) {
    return typeof(num) == "number" ? num.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }) : "N/A"
}

function pctFormat(num) {
    return typeof(num) == "number" ? num.toLocaleString('en-US', {
        style: "percent",
        minimumFractionDigits: 1,
        maximumFractionDigits: 1
    }) : "N/A"
}

// Table rendering
function renderTable(data) {
    currentRenderedData = data;
    const tbody = document.getElementById('tableBody');
    const noResults = document.getElementById('noResults');

    if (data.length === 0) {
        tbody.innerHTML = '';
        noResults.style.display = 'block';
        return;
    }

    noResults.style.display = 'none';

    tbody.innerHTML = (openColDesc
        ? `<tr class="col-desc-row"><td colspan="7">${openColDesc}</td></tr>`
        : ''
    ) + data.map((row, i) => `
        <tr>
            <td>${row.deq_grade}</td>
            <td>${deqFormat(row.deq)}</td>
            <td class="name-cell" data-idx="${i}">${row.name}</td>
            <td>${row.color}</td>
            <td class="col-hidden">${row.rarity}</td>
            <td class="col-hidden">${pctFormat(row.pct_top)}</td>
            <td class="col-hidden">${nprFormat(row.npr)}</td>
        </tr>
    `).join('');
}

// Filtering
function colorFilter(row) {
    return term => {
        const orSplit = term.split('/');
        return orSplit.some(
            item => row.color.toLowerCase().split('').sort().join('') ===
                item.toLowerCase().split('').sort().join('') ||
                wildCardMatch(item, row.color) ||
                row.color === '' && item.toLowerCase() === 'c' ||
                row.color.length > 1 && item.toLowerCase() === 'm'
            );
    }
}

function wildCardMatch(item, color) {
    if (item.includes('*')) {
        const others = item.replaceAll('*', '');
        return others.toLowerCase().split('').every(char => {
            return color.toLowerCase().includes(char);
        });
    }
    return false;
}

function rarityFilter(row) {
    return term => {
        const orSplit = term.split('/');
        return orSplit.some(
            item => row.rarity.toLowerCase().startsWith(item.toLowerCase())
        )
    }
}

function nameFilter(row) {
    return term => {
        const orSplit = term.split('/');
        return orSplit.some(
            item => row.name.toLowerCase().includes(item)
        )
    }
}

function splitTokens(searchTerm) {
    const quoteSplit = searchTerm.split(/"|"|"/).reduce(
        (allTerms, term, index) => {
            if (index % 2) {
                const lastTerm = allTerms.pop()
                return [...allTerms, lastTerm + term].filter(item => item.length > 0)
            } else {
                const split = term.split(/\s+/)
                if (allTerms.length > 0) {
                    const lastTerm = allTerms.pop()
                    const firstTerm = split.shift()
                    return [...allTerms, lastTerm + firstTerm, ...split]
                }
                return split
            }
        }, []
    )
    return quoteSplit
}

function filterData(searchTerm) {
    if (!searchTerm.trim()) {
        return deq_table;
    }

    const terms = splitTokens(searchTerm.toLowerCase());

    const colorTerms = terms.filter(
        term => term.startsWith('c:')).map(
            term => term.slice(2)
        ).filter(term => term.length > 0
    );
    const rarityTerms = terms.filter(
        term => term.startsWith('r:')).map(
            term => term.slice(2)
        ).filter(term => term.length > 0
    );
    const nameTerms = terms.filter(
        term => !term.startsWith('c:') && !term.startsWith('r:')
    );

    return deq_table.filter(row => {
        return colorTerms.every(colorFilter(row)) &&
            rarityTerms.every(rarityFilter(row)) &&
            nameTerms.every(nameFilter(row));
    })
}

// Search
const searchInput = document.getElementById('searchInput');
let searchTimeout;

searchInput.addEventListener('input', function() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        renderTable(sortData(filterData(this.value)));
    }, 150);
});

searchInput.addEventListener('focus', function() {
    this.style.transform = 'translateY(-2px)';
});

searchInput.addEventListener('blur', function() {
    this.style.transform = 'translateY(0)';
});

// Set switching
const linkSelect = document.getElementById('link-select');

async function loadSet(setCode) {
    const response = await fetch(`data/${setCode}.json`);
    const data = await response.json();
    document.getElementById('startDate').textContent = data.start_date;
    document.getElementById('endDate').textContent = data.end_date;
    document.title = `${data.set_code} DEq: Estimated Draft Equity`;
    deq_table = data.cards;
    searchInput.value = '';
    renderTable(sortData(deq_table));
    searchInput.focus();
}

linkSelect.addEventListener('change', function() {
    loadSet(this.value);
});

loadSet(linkSelect.value);
