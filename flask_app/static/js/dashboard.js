// Global variables
let primaryVotesChart = null;
let tcpVotesChart = null;
let currentElectorate = null;
let pollingPlaces = [];

// Initialize the dashboard
document.addEventListener('DOMContentLoaded', function() {
    loadElectorates();
    initializeCharts();
    setupEventListeners();
});

// Set up event listeners
function setupEventListeners() {
    // Add booth button click handler
    document.getElementById('add-booth-btn').addEventListener('click', function() {
        openManualEntryModal('', '', currentElectorate);
    });
}

// Load electorates from FastAPI
async function loadElectorates() {
    try {
        const response = await fetch('/api/electorates');
        if (!response.ok) throw new Error('Failed to fetch electorates');
        
        const data = await response.json();
        const electorateList = document.getElementById('electorate-list');
        electorateList.innerHTML = '';
        
        data.forEach(electorate => {
            const button = document.createElement('button');
            button.className = 'list-group-item list-group-item-action';
            button.textContent = electorate;
            button.onclick = () => selectElectorate(electorate);
            electorateList.appendChild(button);
        });
    } catch (error) {
        console.error('Error loading electorates:', error);
        showError('Failed to load electorates');
    }
}

// Select an electorate and load its data
async function selectElectorate(electorate) {
    currentElectorate = electorate;
    document.getElementById('electorate-title').textContent = `${electorate} Results`;
    
    // Update active state in electorate list
    document.querySelectorAll('#electorate-list button').forEach(btn => {
        btn.classList.remove('active');
        if (btn.textContent === electorate) btn.classList.add('active');
    });
    
    // Load all data for the electorate
    await Promise.all([
        loadPollingPlaces(electorate),
        loadResults(electorate),
        loadTCPCandidates(electorate)
    ]);
}

// Load polling places for an electorate
async function loadPollingPlaces(electorate) {
    try {
        const response = await fetch(`/api/polling-places/${encodeURIComponent(electorate)}`);
        if (!response.ok) throw new Error('Failed to fetch polling places');
        
        pollingPlaces = await response.json();
    } catch (error) {
        console.error('Error loading polling places:', error);
        showError('Failed to load polling places');
    }
}

// Load results for an electorate
async function loadResults(electorate) {
    try {
        const response = await fetch(`/api/results/${encodeURIComponent(electorate)}`);
        if (!response.ok) throw new Error('Failed to fetch results');
        
        const data = await response.json();
        updateDashboard(data);
    } catch (error) {
        console.error('Error loading results:', error);
        showError('Failed to load results');
    }
}

// Load TCP candidates for an electorate
async function loadTCPCandidates(electorate) {
    try {
        const response = await fetch(`/api/tcp-candidates/${encodeURIComponent(electorate)}`);
        if (!response.ok) throw new Error('Failed to fetch TCP candidates');
        
        const data = await response.json();
        updateTCPCandidates(data);
    } catch (error) {
        console.error('Error loading TCP candidates:', error);
        showError('Failed to load TCP candidates');
    }
}

// Update the dashboard with new data
function updateDashboard(data) {
    // Update booth reporting count
    document.getElementById('booths-reporting').textContent = 
        `${data.booth_count} of ${data.total_booths} Booths Reporting`;
    
    // Update last updated time
    document.getElementById('update-time').textContent = new Date().toLocaleTimeString();
    
    // Update primary votes chart and table
    updatePrimaryVotes(data.primary_votes);
    
    // Update TCP votes chart and table
    updateTCPVotes(data.tcp_votes);
    
    // Update booth results table
    updateBoothResults(data.booth_results);
}

// Update primary votes display
function updatePrimaryVotes(votes) {
    // Update chart
    if (primaryVotesChart) {
        primaryVotesChart.destroy();
    }
    
    const ctx = document.getElementById('primary-votes-chart').getContext('2d');
    primaryVotesChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: votes.map(v => v.candidate),
            datasets: [{
                label: 'Primary Votes',
                data: votes.map(v => v.votes),
                backgroundColor: 'rgba(54, 162, 235, 0.5)',
                borderColor: 'rgba(54, 162, 235, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
    
    // Update table
    const tableBody = document.getElementById('primary-votes-table');
    tableBody.innerHTML = votes.map(v => `
        <tr>
            <td>${v.candidate}</td>
            <td>${v.votes}</td>
            <td>${v.percentage.toFixed(2)}%</td>
        </tr>
    `).join('');
}

// Update TCP votes display
function updateTCPVotes(votes) {
    // Update chart
    if (tcpVotesChart) {
        tcpVotesChart.destroy();
    }
    
    const ctx = document.getElementById('tcp-votes-chart').getContext('2d');
    tcpVotesChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: votes.map(v => v.candidate),
            datasets: [{
                label: 'TCP Votes',
                data: votes.map(v => v.votes),
                backgroundColor: 'rgba(255, 99, 132, 0.5)',
                borderColor: 'rgba(255, 99, 132, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
    
    // Update table
    const tableBody = document.getElementById('tcp-votes-table');
    tableBody.innerHTML = votes.map(v => `
        <tr>
            <td>${v.candidate}</td>
            <td>${v.votes}</td>
            <td>${v.percentage.toFixed(2)}%</td>
        </tr>
    `).join('');
}

// Update booth results table
function updateBoothResults(results) {
    const tableBody = document.getElementById('booth-results-table');
    tableBody.innerHTML = results.map(result => `
        <tr>
            <td>${result.booth_name}</td>
            <td>${new Date(result.timestamp).toLocaleString()}</td>
            <td>${result.totals.formal}</td>
            <td>${result.totals.informal}</td>
            <td>${result.totals.total}</td>
            <td>
                ${result.swing !== null ? 
                    result.swing > 0 ? 
                        `<span class="text-danger">+${result.swing.toFixed(2)}% to ALP</span>` :
                        `<span class="text-primary">${result.swing.toFixed(2)}% to LNP</span>` :
                    'N/A'}
            </td>
            <td>
                <a href="/results/${result.id}" class="btn btn-sm btn-primary">View</a>
                ${isAdmin ? `
                    <button type="button" class="btn btn-sm btn-warning" 
                        onclick="openManualEntryModal('${result.id}', '${result.booth_name}', '${currentElectorate}')">
                        Manual Entry
                    </button>
                ` : ''}
            </td>
        </tr>
    `).join('');
}

// Initialize charts
function initializeCharts() {
    const primaryCtx = document.getElementById('primary-votes-chart').getContext('2d');
    const tcpCtx = document.getElementById('tcp-votes-chart').getContext('2d');
    
    primaryVotesChart = new Chart(primaryCtx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: 'Primary Votes',
                data: [],
                backgroundColor: 'rgba(54, 162, 235, 0.5)',
                borderColor: 'rgba(54, 162, 235, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
    
    tcpVotesChart = new Chart(tcpCtx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: 'TCP Votes',
                data: [],
                backgroundColor: 'rgba(255, 99, 132, 0.5)',
                borderColor: 'rgba(255, 99, 132, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
}

// Show error message
function showError(message) {
    // You can implement a toast or alert system here
    console.error(message);
}

// Manual entry modal functions
function openManualEntryModal(resultId, boothName, electorate) {
    // Implement manual entry modal logic here
    console.log('Opening manual entry modal:', { resultId, boothName, electorate });
}

// Set up auto-refresh
setInterval(() => {
    if (currentElectorate) {
        loadResults(currentElectorate);
    }
}, 30000); // Refresh every 30 seconds 