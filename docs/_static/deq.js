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
    updateSortIndicators();
    renderTable(sortData(filterData(searchInput.value)));
    updateURL();
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

function openModal(idx, preserveToggle = false, skipURLUpdate = false) {
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
    if (!skipURLUpdate) updateURL();
}

function closeModal() {
    modal.classList.remove('active');
    openModalIdx = -1;
    updateURL();
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

    tbody.innerHTML = data.map((row, i) => `
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

// The three double-quote varieties: straight (U+0022), left curly (U+201C), right curly (U+201D)
const QUOTE_CHARS = /["“”]/;
const QUOTE_CHARS_G = /["“”]/g;

function stripQuotes(s) {
    return s.replace(QUOTE_CHARS_G, '').trim();
}

// Split a predicate value on / for OR, but only on / that lies OUTSIDE quotes —
// so // inside a quoted split-card name is left intact.
function splitOnUnquotedSlash(value) {
    const parts = [];
    let current = '';
    let inQuote = false;
    for (const ch of value) {
        if (QUOTE_CHARS.test(ch)) {
            inQuote = !inQuote;
            current += ch;
        } else if (ch === '/' && !inQuote) {
            parts.push(current);
            current = '';
        } else {
            current += ch;
        }
    }
    parts.push(current);
    return parts;
}

function nameFilter(row) {
    return term => {
        const orSplit = splitOnUnquotedSlash(term).map(stripQuotes).filter(s => s.length > 0);
        return orSplit.length === 0 || orSplit.some(
            item => row.name.toLowerCase().includes(item)
        )
    }
}

// Tokenize on unquoted whitespace. Quote characters are PRESERVED in the token so
// later stages (prefix categorization, / OR-splitting) see phrase boundaries;
// quotes are only stripped at the final value-matching step.
function splitTokens(searchTerm) {
    const tokens = [];
    let current = '';
    let inQuote = false;
    for (const ch of searchTerm) {
        if (QUOTE_CHARS.test(ch)) {
            inQuote = !inQuote;
            current += ch;
        } else if (/\s/.test(ch) && !inQuote) {
            if (current.length) tokens.push(current);
            current = '';
        } else {
            current += ch;
        }
    }
    if (current.length) tokens.push(current);
    return tokens;
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
const searchChips = document.getElementById('searchChips');
const searchContainer = document.querySelector('.search-container');
let searchTimeout;

// Parse search text — find first c: and r: token; everything else is name remainder.
// Chip system owns these canonical tokens; on write-back they're placed at the front.
function parseSearchTokens(text) {
    const tokens = splitTokens(text);
    let colorToken = null, rarityToken = null;
    let colorSeen = false, raritySeen = false;
    const nameTokens = [];
    for (const t of tokens) {
        const lower = t.toLowerCase();
        if (!colorSeen && lower.startsWith('c:')) {
            colorSeen = true;
            const v = lower.slice(2);
            if (v.length > 0) colorToken = v;
        } else if (!raritySeen && lower.startsWith('r:')) {
            raritySeen = true;
            const v = lower.slice(2);
            if (v.length > 0) rarityToken = v;
        } else {
            // Token already retains its own quotes if it was a phrase
            nameTokens.push(t);
        }
    }
    return { nameRemainder: nameTokens.join(' '), colorToken, rarityToken };
}

function reconstructSearch({ nameRemainder, colorToken, rarityToken }) {
    const parts = [];
    if (colorToken) parts.push(`c:${colorToken}`);
    if (rarityToken) parts.push(`r:${rarityToken}`);
    if (nameRemainder) parts.push(nameRemainder);
    return parts.join(' ');
}

const WUBRG_LETTERS = ['W', 'U', 'B', 'R', 'G'];
const SPECIAL_COLORS = ['C', 'M'];
const RARITY_LETTERS = ['C', 'U', 'R', 'M'];

function sortWUBRG(letters) {
    const ORDER = { w: 0, u: 1, b: 2, r: 3, g: 4 };
    return letters.toLowerCase().split('').sort((a, b) => (ORDER[a] ?? 5) - (ORDER[b] ?? 5)).join('');
}

function isPairPattern(token) {
    const parts = token.split('/');
    if (parts.length !== 3) return false;
    const [a, b, ab] = parts;
    if (a.length !== 1 || b.length !== 1 || ab.length !== 2) return false;
    return ab.split('').sort().join('') === (a + b).split('').sort().join('');
}

// Matches w*/b* — two single-letter wildcards OR'd, representing a color pair
function isWildcardPairPattern(token) {
    const parts = token.split('/');
    return parts.length === 2 && parts.every(p => p.length === 2 && p.endsWith('*'));
}

// Canonical 3-color combinatorial: a/b/c/ab/bc/ac/abc
function tripleComboToken(a, b, c) {
    const sorted = sortWUBRG(a + b + c);
    const [x, y, z] = sorted;
    return `${x}/${y}/${z}/${x}${y}/${y}${z}/${x}${z}/${sorted}`;
}

function isTripleCombo(token) {
    const parts = token.split('/');
    if (parts.length !== 7) return false;
    const singles = parts.filter(p => p.length === 1);
    if (singles.length !== 3) return false;
    const pairs = parts.filter(p => p.length === 2);
    if (pairs.length !== 3) return false;
    const triples = parts.filter(p => p.length === 3);
    if (triples.length !== 1) return false;
    const singleSet = new Set(singles);
    return [...pairs, ...triples].every(p => p.split('').every(c => singleSet.has(c)));
}

// Returns { mainRow, wideRow } — wideRow is empty [] when not applicable.
function generateColorChips(colorToken) {
    if (!colorToken) {
        return {
            mainRow: [...WUBRG_LETTERS, ...SPECIAL_COLORS].map(c => ({
                label: c, kind: 'add', group: 'color', newValue: c.toLowerCase(), manaColor: c.toLowerCase(),
            })),
            wideRow: [],
        };
    }

    // Any state containing colorless: normalize c to last position
    if (colorToken.split('/').includes('c')) {
        const WUBRG_ORDER = { w: 0, u: 1, b: 2, r: 3, g: 4 };
        const parts = colorToken.split('/').sort((a, b) => (WUBRG_ORDER[a] ?? 99) - (WUBRG_ORDER[b] ?? 99));
        const nonCParts = parts.filter(p => p !== 'c');
        const nonCToken = nonCParts.join('/');
        const singles = nonCParts.filter(p => p.length === 1);

        // Pair+c or triple+c: show combo as single label chip + C ×, commutes with WUBRG depth
        if (isPairPattern(nonCToken) || isTripleCombo(nonCToken)) {
            const displayLabel = sortWUBRG(singles.join('')).toUpperCase().split('').join('/');
            const canonicalNonC = isTripleCombo(nonCToken)
                ? tripleComboToken(...sortWUBRG(singles.join('')).split(''))
                : nonCToken;
            const mainRow = [
                { label: displayLabel, kind: 'active', group: 'color', newValue: 'c', manaColor: null },
                { label: 'C', kind: 'active', group: 'color', newValue: canonicalNonC, manaColor: 'c' },
            ];
            // Pair+c can expand to triple+c; triple+c is terminal
            const wideRow = isPairPattern(nonCToken)
                ? WUBRG_LETTERS
                    .filter(c => !singles.includes(c.toLowerCase()))
                    .map(c => ({
                        label: `/${c}`, kind: 'add', group: 'color',
                        newValue: `${tripleComboToken(singles[0], singles[1], c.toLowerCase())}/c`,
                        manaColor: c.toLowerCase(),
                    }))
                : [];
            return { mainRow, wideRow };
        }

        // Empty or single: each part is its own chip, expand with remaining WUBRG
        const mainRow = parts.map(p => {
            const remaining = parts.filter(x => x !== p);
            return {
                label: p.toUpperCase(), kind: 'active', group: 'color',
                newValue: remaining.length > 0 ? remaining.join('/') : null,
                manaColor: p.length === 1 ? p : null,
            };
        });
        const wideRow = WUBRG_LETTERS
            .filter(c => !parts.includes(c.toLowerCase()))
            .map(c => {
                const cL = c.toLowerCase();
                const newValue = nonCParts.length === 0
                    ? `${cL}/c`
                    : (() => { const combo = sortWUBRG(nonCParts[0] + cL); return `${combo[0]}/${combo[1]}/${combo}/c`; })();
                return { label: `/${c}`, kind: 'add', group: 'color', newValue, manaColor: cL };
            });
        return { mainRow, wideRow };
    }

    // m — no expansion
    if (colorToken === 'm') {
        return {
            mainRow: [{ label: 'M', kind: 'active', group: 'color', newValue: null, manaColor: 'm' }],
            wideRow: [],
        };
    }

    let mainRow, wideRow;

    // Slash path: w/b/wb — active label only, no *. Wide row: remaining WUBRG → triple combo, plus /C, /M
    if (isPairPattern(colorToken)) {
        const [a, b] = colorToken.split('/').slice(0, 2);
        mainRow = [{ label: `${a.toUpperCase()}/${b.toUpperCase()}`, kind: 'active', group: 'color', newValue: null }];
        wideRow = [];
        for (const c of WUBRG_LETTERS) {
            const cL = c.toLowerCase();
            if (cL !== a && cL !== b) {
                wideRow.push({ label: `/${c}`, kind: 'add', group: 'color', newValue: tripleComboToken(a, b, cL), manaColor: cL });
            }
        }
        wideRow.push({ label: '/C', kind: 'add', group: 'color', newValue: `${colorToken}/c`, manaColor: 'c' });

    // Triple combo: w/u/b/wu/ub/wb/wub — /C available, then terminal
    } else if (isTripleCombo(colorToken)) {
        const singles = colorToken.split('/').filter(p => p.length === 1);
        const displayLabel = sortWUBRG(singles.join('')).toUpperCase().split('').join('/');
        mainRow = [{ label: displayLabel, kind: 'active', group: 'color', newValue: null }];
        wideRow = [{ label: '/C', kind: 'add', group: 'color', newValue: `${colorToken}/c`, manaColor: 'c' }];

    // Wildcard path: w*, wu*, etc. — restricted, no slash options, no /C
    } else if (colorToken.endsWith('*')) {
        const base = colorToken.slice(0, -1);
        mainRow = [
            { label: colorToken.toUpperCase(), kind: 'active', group: 'color', newValue: null, manaColor: base.length === 1 ? base : null },
            { label: '-*', kind: 'add', group: 'color', newValue: base || null },
        ];
        for (const c of WUBRG_LETTERS) {
            const cL = c.toLowerCase();
            if (!base.includes(cL)) {
                mainRow.push({ label: `+${c}*`, kind: 'add', group: 'color', newValue: `${sortWUBRG(base + cL)}*`, manaColor: cL });
            }
        }
        wideRow = [];

    // Arbitrary OR fallback (user-typed: w/b, w/u/b, w*/b*, etc.)
    } else if (colorToken.includes('/')) {
        const parts = colorToken.split('/');
        mainRow = parts.map(p => {
            const remaining = parts.filter(x => x !== p);
            return {
                label: p.toUpperCase(), kind: 'active', group: 'color',
                newValue: remaining.length > 0 ? remaining.join('/') : null,
                manaColor: p.length === 1 ? p : null,
            };
        });
        wideRow = [];

    // Exact path: single w or multi wb, wub, etc.
    } else {
        const isSingle = colorToken.length === 1;
        mainRow = [
            { label: colorToken.toUpperCase(), kind: 'active', group: 'color', newValue: null, manaColor: isSingle ? colorToken : null },
            { label: `${colorToken.toUpperCase()}*`, kind: 'add', group: 'color', newValue: `${colorToken}*`, manaColor: isSingle ? colorToken : null },
        ];
        for (const c of WUBRG_LETTERS) {
            const cL = c.toLowerCase();
            if (!colorToken.includes(cL)) {
                mainRow.push({ label: `+${c}`, kind: 'add', group: 'color', newValue: sortWUBRG(colorToken + cL), manaColor: cL });
            }
        }
        // Single exact: wide row for slash path; multi exact: terminal (no wide row, no /C)
        wideRow = [];
        if (isSingle) {
            for (const c of WUBRG_LETTERS) {
                const cL = c.toLowerCase();
                if (cL !== colorToken) {
                    const combo = sortWUBRG(colorToken + cL);
                    wideRow.push({ label: `/${c}`, kind: 'add', group: 'color', newValue: `${colorToken}/${cL}/${combo}`, manaColor: cL });
                }
            }
            wideRow.push({ label: '/C', kind: 'add', group: 'color', newValue: `${colorToken}/c`, manaColor: 'c' });
        }
    }

    return { mainRow, wideRow };
}

const RARITY_NAMES = { c: 'common', u: 'uncommon', r: 'rare', m: 'mythic' };

function generateRarityChips(rarityToken) {
    if (!rarityToken) {
        return RARITY_LETTERS.map(r => ({
            label: r, kind: 'add', group: 'rarity', newValue: r.toLowerCase(),
            rarityCode: RARITY_NAMES[r.toLowerCase()],
        }));
    }
    const chips = [];
    if (rarityToken.includes('/')) {
        const parts = rarityToken.split('/');
        for (const p of parts) {
            const remaining = parts.filter(x => x !== p);
            chips.push({
                label: p.toUpperCase(), kind: 'active', group: 'rarity',
                newValue: remaining.length > 0 ? remaining.join('/') : null,
                rarityCode: RARITY_NAMES[p],
            });
        }
        for (const r of RARITY_LETTERS) {
            const rL = r.toLowerCase();
            if (!parts.includes(rL)) {
                chips.push({ label: `/${r}`, kind: 'add', group: 'rarity', newValue: `${rarityToken}/${rL}`, rarityCode: RARITY_NAMES[rL] });
            }
        }
    } else {
        chips.push({ label: rarityToken.toUpperCase(), kind: 'active', group: 'rarity', newValue: null, rarityCode: RARITY_NAMES[rarityToken[0]] });
        for (const r of RARITY_LETTERS) {
            const rL = r.toLowerCase();
            if (!rarityToken.startsWith(rL)) {
                chips.push({ label: `/${r}`, kind: 'add', group: 'rarity', newValue: `${rarityToken}/${rL}`, rarityCode: RARITY_NAMES[rL] });
            }
        }
    }
    return chips;
}

function chipHtml(chip) {
    const display = chip.kind === 'active' ? `${chip.label} ×` : chip.label;
    const value = chip.newValue === null ? '' : chip.newValue;
    const clear = chip.newValue === null ? '1' : '0';
    const colorAttr = chip.manaColor ? ` data-color="${chip.manaColor}"` : '';
    const rarityAttr = chip.rarityCode ? ` data-rarity="${chip.rarityCode}"` : '';
    return `<button type="button" class="chip chip-${chip.kind}"${colorAttr}${rarityAttr} data-group="${chip.group}" data-value="${value}" data-clear="${clear}">${display}</button>`;
}

function renderChips() {
    const { colorToken, rarityToken } = parseSearchTokens(searchInput.value);
    const { mainRow, wideRow } = generateColorChips(colorToken);
    const rarityChips = generateRarityChips(rarityToken);
    const rows = [`<div class="chip-row">${mainRow.map(chipHtml).join('')}</div>`];
    if (wideRow.length > 0) {
        rows.push(`<div class="chip-row chip-row-wide">${wideRow.map(chipHtml).join('')}</div>`);
    }
    rows.push(`<div class="chip-row">${rarityChips.map(chipHtml).join('')}</div>`);
    searchChips.innerHTML = rows.join('');
}

function updateChipsVisibility() {
    const focused = document.activeElement === searchInput;
    const hasValue = searchInput.value.trim().length > 0;
    searchContainer.classList.toggle('chips-visible', focused || hasValue);
}

function applyChip(group, newValue) {
    const parsed = parseSearchTokens(searchInput.value);
    if (group === 'color') parsed.colorToken = newValue;
    else parsed.rarityToken = newValue;
    searchInput.value = reconstructSearch(parsed);
    renderChips();
    updateChipsVisibility();
    renderTable(sortData(filterData(searchInput.value)));
    updateURL();
}

// Prevent chip clicks from blurring the input
searchChips.addEventListener('mousedown', e => {
    if (e.target.closest('.chip')) e.preventDefault();
});

searchChips.addEventListener('click', e => {
    const btn = e.target.closest('.chip');
    if (!btn) return;
    const group = btn.dataset.group;
    const newValue = btn.dataset.clear === '1' ? null : btn.dataset.value;
    applyChip(group, newValue);
});

searchInput.addEventListener('input', function() {
    renderChips();
    updateChipsVisibility();
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        renderTable(sortData(filterData(this.value)));
        updateURL();
    }, 150);
});

searchInput.addEventListener('focus', function() {
    this.style.transform = 'translateY(-2px)';
    updateChipsVisibility();
});

searchInput.addEventListener('blur', function() {
    this.style.transform = 'translateY(0)';
    updateChipsVisibility();
});

renderChips();

// URL state
function buildURLParams() {
    const params = new URLSearchParams();
    if (currentSetCode) params.set('set', currentSetCode);
    if (searchInput.value.trim()) params.set('q', searchInput.value.trim());
    if (sortState.col !== 'deq' || sortState.dir !== 'desc') {
        params.set('sort', `${sortState.col}:${sortState.dir}`);
    }
    if (openModalIdx >= 0 && currentRenderedData[openModalIdx]) {
        params.set('card', currentRenderedData[openModalIdx].name);
    }
    return params;
}

function updateURL() {
    const qs = buildURLParams().toString();
    history.replaceState(null, '', qs ? `${location.pathname}?${qs}` : location.pathname);
}

// Set switching
const linkSelect = document.getElementById('link-select');

async function loadSet(setCode) {
    const response = await fetch(`data/${setCode}.json`);
    const data = await response.json();
    document.getElementById('startDate').textContent = data.start_date;
    document.getElementById('endDate').textContent = data.end_date;
    currentSetCode = data.set_code;
    document.title = 'DEq: Estimated Draft Equity';
    isEmbargoed = !!data.embargoed;
    document.getElementById('dataTable').classList.toggle('embargo-active', isEmbargoed);
    modal.classList.toggle('embargo-active', isEmbargoed);
    deq_table = data.cards;
    openModalIdx = -1;
    modal.classList.remove('active');
    searchInput.value = '';
    renderChips();
    renderTable(sortData(deq_table));
    updateURL();
    searchInput.focus();
}

linkSelect.addEventListener('change', function() {
    loadSet(this.value);
});

// Init: apply query params then load
(async function init() {
    const params = new URLSearchParams(location.search);
    const setParam  = params.get('set');
    const qParam    = params.get('q');
    const sortParam = params.get('sort');
    const cardParam = params.get('card');
    const kParam    = params.get('k');

    if (sortParam) {
        const [col, dir] = sortParam.split(':');
        if (col) {
            sortState.col = col;
            sortState.dir = dir || ((col === 'name' || col === 'color' || col === 'rarity') ? 'asc' : 'desc');
            updateSortIndicators();
        }
    }

    if (setParam) {
        const opt = linkSelect.querySelector(`option[value="${setParam.toUpperCase()}"]`);
        if (opt) linkSelect.value = setParam.toUpperCase();
    }

    await loadSet(linkSelect.value);

    if (qParam) {
        searchInput.value = qParam;
        renderChips();
        updateChipsVisibility();
        renderTable(sortData(filterData(qParam)));
        updateURL();
    }

    if (cardParam) {
        const lower = cardParam.toLowerCase();
        const idx = currentRenderedData.findIndex(c => c.name.toLowerCase() === lower);
        if (idx >= 0) openModal(idx, false, true);
        updateURL();
    } else if (kParam) {
        const k = parseInt(kParam, 10);
        if (!isNaN(k) && k >= 1 && k <= currentRenderedData.length) {
            openModal(k - 1, false, true);
            updateURL();
        }
    }
})();
