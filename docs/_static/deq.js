let deq_table = [];

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

function renderTable(data) {
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
            <td class="col-hidden">${i + 1}</td>
            <td>${row.deq_grade}</td>
            <td>${deqFormat(row.deq)}</td>
            <td>${row.name}</td>
            <td>${row.color}</td>
            <td class="col-hidden">${row.rarity}</td>
            <td class="col-hidden">${pctFormat(row.pct_top)}</td>
            <td class="col-hidden">${nprFormat(row.npr)}</td>
        </tr>
    `).join('');
}

function colorFilter(row) {
    return term => {
        orSplit = term.split('/');
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
        orSplit = term.split('/');
        return orSplit.some(
            item => row.rarity.toLowerCase().startsWith(item.toLowerCase())
        )
    }
}

function nameFilter(row) {
    return term => {
        orSplit = term.split('/');
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

const searchInput = document.getElementById('searchInput');
let searchTimeout;

searchInput.addEventListener('input', function() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        renderTable(filterData(this.value));
    }, 150);
});

searchInput.addEventListener('focus', function() {
    this.style.transform = 'translateY(-2px)';
});

searchInput.addEventListener('blur', function() {
    this.style.transform = 'translateY(0)';
});

const linkSelect = document.getElementById('link-select');

async function loadSet(setCode) {
    const response = await fetch(`data/${setCode}.json`);
    const data = await response.json();
    document.getElementById('startDate').textContent = data.start_date;
    document.getElementById('endDate').textContent = data.end_date;
    document.title = `${data.set_code} DEq: Estimated Draft Equity`;
    deq_table = data.cards;
    searchInput.value = '';
    renderTable(deq_table);
    searchInput.focus();
}

linkSelect.addEventListener('change', function() {
    loadSet(this.value);
});

loadSet(linkSelect.value);
