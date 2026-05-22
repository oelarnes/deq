let deq_table = [];
let currentRenderedData = [];
let sortState = { col: 'deq', dir: 'desc' };
let currentSetCode = '';

// Grade ordered worst→best so desc sort puts A+ first
const GRADE_ORDER = ['N/A', 'F', 'D-', 'D', 'D+', 'C-', 'C', 'C+', 'B-', 'B', 'B+', 'A-', 'A', 'A+'];
const RARITY_ORDER = { common: 0, uncommon: 1, rare: 2, mythic: 3 };
const WUBRG = { W: 0, U: 1, B: 2, R: 3, G: 4 };

const METRIC_INFO = {
    'Grade':      '<strong>Grade:</strong> A+ to F letter grade, using fixed DEq increments.',
    'DEq':        '<strong>Estimated Draft Equity:</strong> Expected win-rate gain from picking this card over a basic land.',
    'MWR':        '<strong>Marginal Win Rate:</strong> GP WR versus the set mean.',
    'PEq':        '<strong>Pick Equity:</strong> Estimated opportunity cost in win rate at the observed ATA.',
    'Adj':        '<strong>Adjustment:</strong> Correction for selection bias and expected metagame drift.',
    'Played DEq': '<strong>Played DEq:</strong> Sum of components before scaling by % GP, representing the expected marginal win-rate when registered.',
    '% GP':       '<strong>Play Rate:</strong> The rate at which this card was included in the deck (when available in the card pool).',
    'NPR':        '<strong>Normalized Pick Rate:</strong> Top-player pick preference; each +1.0 means twice as likely to be taken from a fresh pack.',
    '% Top':      '<strong>% Top:</strong> Share of DEq and component metrics derived from top-player data, based on sample size.',
};

const COL_METRIC = {
    'grade':       'Grade',
    'deq':         'DEq',
    'mwr':         'MWR',
    'pick_equity': 'PEq',
    'adj':         'Adj',
    'pct_top':     '% Top',
    'npr':         'NPR',
};

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

document.querySelectorAll('.col-info[data-col]').forEach(btn => {
    btn.dataset.colDesc = METRIC_INFO[COL_METRIC[btn.dataset.col]] || '';
});

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
        case 'npr':          return row.npr;
        case 'pct_gp':       return row.pct_gp;
        case 'mwr':          return row.mwr;
        case 'pick_equity':  return row.pick_equity;
        case 'adj':          return row.adj;
        default:             return null;
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
const modalImage = document.getElementById('modalImage');
const modalPrev = document.getElementById('modalPrev');
const modalNext = document.getElementById('modalNext');
const modalBody = document.querySelector('.modal-body');
const modalToggle = document.getElementById('modalToggle');
const modalToggleBack = document.getElementById('modalToggleBack');
const modalContent = document.querySelector('.modal-content');
let openModalIdx = -1;
let isEmbargoed = false;

function openModal(idx, preserveToggle = false) {
    modalContent.style.transition = '';
    modalContent.style.transform = '';
    const card = currentRenderedData[idx];
    openModalIdx = idx;
    modalImage.src = card.image_url || '';
    modalImage.alt = card.name;

    document.getElementById('modalCardName').textContent = card.name;
    document.getElementById('modalCardSet').textContent = currentSetCode;
    document.getElementById('modalCardColor').innerHTML = colorPipsHtml(card.color);
    document.getElementById('modalCardRarity').innerHTML = rarityPipHtml(card.rarity);

    const gradeEl = document.getElementById('modalGrade');
    gradeEl.textContent = card.deq_grade === 'N/A' ? '—' : card.deq_grade;
    gradeEl.className = 'info-grade ' + gradeColorClass(card.deq_grade);

    const deqEl = document.getElementById('modalDeq');
    deqEl.textContent = deqFormat(card.deq);

    document.getElementById('modalNpr').textContent = nprFormat(card.npr);
    document.getElementById('modalPctTop').textContent = pctFormat(card.pct_top);
    document.getElementById('modalPctGp').textContent = pctFormat(card.pct_gp);

    if (isEmbargoed) {
        ['modalMwr', 'modalPeq', 'modalAdj', 'modalPlayedDeq', 'modalPctGp'].forEach(id => {
            const el = document.getElementById(id);
            el.textContent = '—';
            el.className = 'calc-value';
        });
        document.getElementById('modalPeqOp').textContent = '';
        document.getElementById('modalAdjOp').textContent = '';
        document.getElementById('modalPctGpOp').textContent = '';
    } else {
        const setComp = (id, val) => {
            const el = document.getElementById(id);
            el.textContent = deqFormatAbs(val);
            el.className = 'calc-value ' + signClass(val);
        };
        const mwrEl = document.getElementById('modalMwr');
        mwrEl.textContent = deqFormat(card.mwr);
        mwrEl.className = 'calc-value ' + signClass(card.mwr);
        document.getElementById('modalPeqOp').textContent = (typeof card.pick_equity === 'number' && card.pick_equity < 0) ? '−' : '+';
        setComp('modalPeq', card.pick_equity);
        document.getElementById('modalAdjOp').textContent = (typeof card.adj === 'number' && card.adj < 0) ? '−' : '+';
        setComp('modalAdj', card.adj);

        const playedDeq = (typeof card.mwr === 'number' && typeof card.pick_equity === 'number' && typeof card.adj === 'number')
            ? card.mwr + card.pick_equity + card.adj : null;
        const playedDeqEl = document.getElementById('modalPlayedDeq');
        playedDeqEl.textContent = playedDeq !== null ? deqFormat(playedDeq) : 'N/A';
        playedDeqEl.className = 'calc-value ' + (playedDeq !== null ? signClass(playedDeq) : '');
        document.getElementById('modalPctGpOp').textContent = '×';
    }

    if (!preserveToggle) modalBody.classList.remove('show-stats');
    showTooltip('DEq');
    modalPrev.disabled = idx <= 0;
    modalNext.disabled = idx >= currentRenderedData.length - 1;
    modal.classList.add('active');
}

function closeModal() {
    modal.classList.remove('active');
}

modalPrev.addEventListener('click', () => openModal(openModalIdx - 1, true));
modalNext.addEventListener('click', () => openModal(openModalIdx + 1, true));
modalToggle.addEventListener('click', () => modalBody.classList.add('show-stats'));
modalToggleBack.addEventListener('click', () => modalBody.classList.remove('show-stats'));
document.getElementById('infoDeqTitle').addEventListener('click', () => {
    modalBody.classList.add('show-stats');
    showTooltip('DEq');
});
modal.addEventListener('click', function(e) {
    if (e.target === modal) { closeModal(); return; }
    const el = e.target.closest('.tip-label[data-metric]');
    if (!el) return;
    e.stopPropagation();
    showTooltip(el.dataset.metric);
});

let touchStartX = 0, touchStartY = 0, swipeLocked = false, swipeIsHorizontal = false;

modal.addEventListener('touchstart', e => {
    touchStartX = e.touches[0].clientX;
    touchStartY = e.touches[0].clientY;
    swipeLocked = false;
    swipeIsHorizontal = false;
    modalContent.style.transition = 'none';
}, { passive: true });

modal.addEventListener('touchmove', e => {
    const dx = e.touches[0].clientX - touchStartX;
    const dy = e.touches[0].clientY - touchStartY;
    if (!swipeLocked) {
        swipeLocked = true;
        swipeIsHorizontal = Math.abs(dx) > Math.abs(dy);
    }
    if (!swipeIsHorizontal) return;
    const atEdge = (dx > 0 && modalPrev.disabled) || (dx < 0 && modalNext.disabled);
    const tx = Math.sign(dx) * Math.min(Math.abs(dx), atEdge ? 10 : 20);
    modalContent.style.transform = `translateX(${tx}px)`;
}, { passive: true });

modal.addEventListener('touchend', e => {
    if (!swipeIsHorizontal) return;
    const dx = e.changedTouches[0].clientX - touchStartX;
    if (Math.abs(dx) > 50) {
        if (dx < 0 && !modalNext.disabled) { openModal(openModalIdx + 1, true); return; }
        if (dx > 0 && !modalPrev.disabled) { openModal(openModalIdx - 1, true); return; }
    }
    modalContent.style.transition = 'transform 0.2s ease';
    modalContent.style.transform = 'translateX(0)';
    modalContent.addEventListener('transitionend', () => {
        modalContent.style.transition = '';
        modalContent.style.transform = '';
    }, { once: true });
}, { passive: true });

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeModal();
    if (!modal.classList.contains('active')) return;
    if (e.key === 'ArrowLeft' && !modalPrev.disabled) openModal(openModalIdx - 1, true);
    if (e.key === 'ArrowRight' && !modalNext.disabled) openModal(openModalIdx + 1, true);
});

document.getElementById('tableBody').addEventListener('click', function(e) {
    const cell = e.target.closest('.name-cell');
    if (!cell) return;
    openModal(parseInt(cell.dataset.idx, 10));
});

function showTooltip(metric) {
    document.getElementById('tooltipName').textContent = metric;
    document.getElementById('tooltipText').innerHTML = METRIC_INFO[metric] || '';
}

function colorPipsHtml(color) {
    if (!color) return '<span class="color-pip pip-C"></span>C';
    return color.split('').map(c => `<span class="color-pip pip-${c}"></span>`).join('') + color;
}

function rarityPipHtml(rarity) {
    if (!rarity) return '';
    const label = rarity.charAt(0).toUpperCase() + rarity.slice(1);
    return `<span class="rarity-pip pip-${rarity}"></span>${label}`;
}

// Grade and sign color helpers
function gradeColorClass(grade) {
    const map = {
        'A+': 'grade-aplus',  'A': 'grade-a',      'A-': 'grade-aminus',
        'B+': 'grade-bplus',  'B': 'grade-b',      'B-': 'grade-bminus',
        'C+': 'grade-cplus',  'C': 'grade-c',      'C-': 'grade-cminus',
        'D+': 'grade-dplus',  'D': 'grade-d',      'D-': 'grade-dminus',
        'F':  'grade-f',
    };
    return map[grade] || '';
}

function signClass(num) {
    if (typeof num !== 'number') return '';
    return num > 0 ? 'val-pos' : num < 0 ? 'val-neg' : '';
}

// Formatters
function deqFormat(num) {
    return typeof num === 'number' ? num.toLocaleString('en-US', {
        style: 'percent',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
        signDisplay: 'always',
    }) : 'N/A';
}

function deqFormatAbs(num) {
    return typeof num === 'number' ? Math.abs(num).toLocaleString('en-US', {
        style: 'percent',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }) : 'N/A';
}

function nprFormat(num) {
    return typeof num === 'number' ? num.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }) : 'N/A';
}

function pctFormat(num) {
    return typeof num === 'number' ? num.toLocaleString('en-US', {
        style: 'percent',
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
    }) : 'N/A';
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
        ? `<tr class="col-desc-row"><td colspan="11">${openColDesc}</td></tr>`
        : ''
    ) + data.map((row, i) => `
        <tr>
            <td>${row.deq_grade}</td>
            <td>${deqFormat(row.deq)}</td>
            <td class="name-cell" data-idx="${i}">${row.name}</td>
            <td>${row.color}</td>
            <td class="col-hidden">${row.rarity}</td>
            <td class="col-hidden col-embargo">${deqFormat(row.mwr)}</td>
            <td class="col-hidden col-embargo">${deqFormatAbs(row.pick_equity)}</td>
            <td class="col-hidden col-embargo">${deqFormat(row.adj)}</td>
            <td class="col-hidden col-embargo">${pctFormat(row.pct_gp)}</td>
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
    currentSetCode = data.set_code;
    document.title = `${data.set_code} DEq: Estimated Draft Equity`;
    isEmbargoed = !!data.embargoed;
    document.getElementById('dataTable').classList.toggle('embargo-active', isEmbargoed);
    modal.classList.toggle('embargo-active', isEmbargoed);
    deq_table = data.cards;
    searchInput.value = '';
    renderTable(sortData(deq_table));
    searchInput.focus();
}

linkSelect.addEventListener('change', function() {
    loadSet(this.value);
});

loadSet(linkSelect.value);
