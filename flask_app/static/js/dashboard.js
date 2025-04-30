// Global variables
let primaryVotesChart = null;
let tcpVotesChart = null;
let currentElectorate = null;
let pollingPlaces = [];

// Initialize the dashboard
document.addEventListener('DOMContentLoaded', function() {
    // Get the currently selected division from the navbar
    const selectedDivision = document.querySelector('#divisionDropdown')?.textContent.trim();
    
    if (selectedDivision) {
        // Initialize the dashboard with the selected division
        selectElectorate(selectedDivision);
    }
    
    // Listen for changes in the division dropdown
    document.getElementById('divisionDropdown').addEventListener('click', function(e) {
        if (e.target.classList.contains('dropdown-item')) {
            const newDivision = e.target.textContent.trim();
            selectElectorate(newDivision);
        }
    });
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

// Function to select an electorate and load its data
async function selectElectorate(electorate) {
    console.log('Selecting electorate:', electorate);
    currentElectorate = electorate;
    
    // Update the UI
    document.getElementById('electorate-title').textContent = electorate;
    
    // Load all data for the selected electorate
    try {
        await Promise.all([
            loadResults(electorate),
            loadTCPCandidates(electorate)
        ]);
    } catch (error) {
        console.error('Error loading electorate data:', error);
        showError('Failed to load electorate data');
    }
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

// Function to load results for an electorate
async function loadResults(electorate) {
    console.log('Loading results for:', electorate);
    try {
        const response = await fetch(`/api/results/${encodeURIComponent(electorate)}`);
        console.log('Response status:', response.status);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Received data:', data);
        
        if (data.status === 'success') {
            console.log('Processing booth results:', data.booth_results.length);
            updateDashboard(data);
        } else {
            throw new Error(data.message || 'Failed to load results');
        }
    } catch (error) {
        console.error('Error loading results:', error);
        showError('Failed to load results');
    }
}

// Function to load TCP candidates for an electorate
async function loadTCPCandidates(electorate) {
    console.log('Loading TCP candidates for:', electorate);
    try {
        const response = await fetch(`/api/tcp-candidates/${encodeURIComponent(electorate)}`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.status === 'success') {
            updateTCPCandidates(data.tcp_candidates);
        } else {
            throw new Error(data.message || 'Failed to load TCP candidates');
        }
    } catch (error) {
        console.error('Error loading TCP candidates:', error);
        showError('Failed to load TCP candidates');
    }
}

// Function to update the dashboard with new data
function updateDashboard(data) {
    // Update booth reporting count
    document.getElementById('booths-reporting').textContent = 
        `${data.booth_count} of ${data.total_booths} booths reporting`;
    
    // Update last updated time
    const lastUpdated = new Date(data.last_updated);
    document.getElementById('update-time').textContent = 
        lastUpdated.toLocaleTimeString();
    
    // Update primary votes chart and table
    updatePrimaryVotes(data.primary_votes);
    
    // Update TCP votes chart and table
    updateTCPVotes(data.tcp_votes);
    
    // Update booth results table
    updateBoothResults(data.booth_results);
}

// Function to update primary votes display
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
            <td>${v.votes.toLocaleString()}</td>
            <td>${v.percentage.toFixed(2)}%</td>
        </tr>
    `).join('');
}

// Function to update TCP votes display
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
            <td>${v.votes.toLocaleString()}</td>
            <td>${v.percentage.toFixed(2)}%</td>
        </tr>
    `).join('');
}

// Function to update booth results table
function updateBoothResults(booths) {
    const tableBody = document.getElementById('booth-results-table');
    tableBody.innerHTML = booths.map(booth => {
        // Calculate total primary votes
        const totalPrimaryVotes = Object.values(booth.primary_votes || {}).reduce((sum, votes) => sum + votes, 0);
        // Calculate total TCP votes
        const totalTCPVotes = Object.values(booth.tcp_votes || {}).reduce((sum, votes) => sum + votes, 0);
        
        return `
            <tr>
                <td>${booth.booth_name}</td>
                <td>${new Date(booth.timestamp).toLocaleString()}</td>
                <td>${totalPrimaryVotes.toLocaleString()}</td>
                <td>${totalTCPVotes.toLocaleString()}</td>
                <td>
                    <a href="/results/${booth.id}" class="btn btn-sm btn-primary">View Details</a>
                </td>
            </tr>
        `;
    }).join('');
}

// Function to update TCP candidates display
function updateTCPCandidates(candidates) {
    // Store TCP candidates for use in other functions
    window.tcpCandidates = candidates;
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
    // You can implement a more sophisticated error display here
    alert(message);
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