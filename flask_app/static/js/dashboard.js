// Global variables
let primaryVotesChart = null;
let tcpVotesChart = null;
let currentElectorate = null;
let pollingPlaces = [];

// Initialize the dashboard
document.addEventListener('DOMContentLoaded', function() {
    // Get the currently selected division from the navbar
    const selectedDivision = document.querySelector('#divisionDropdown')?.textContent.trim();
    
    if (selectedDivision && selectedDivision !== 'Select Division') {
        // Initialize the dashboard with the selected division
        selectElectorate(selectedDivision);
    }
    
    // Listen for changes in the division dropdown
    const divisionDropdown = document.querySelector('#divisionDropdown').nextElementSibling;
    if (divisionDropdown) {
        divisionDropdown.addEventListener('click', function(e) {
            if (e.target.classList.contains('dropdown-item')) {
                const newDivision = e.target.textContent.trim();
                if (newDivision !== 'All Divisions') {
                    selectElectorate(newDivision);
                }
            }
        });
    }

    // If no division dropdown, try to get the selected electorate from the template
    if (!selectedDivision) {
        const selectedElectorate = document.querySelector('#electorate-title')?.textContent.trim();
        if (selectedElectorate && selectedElectorate !== 'Select an Electorate') {
            selectElectorate(selectedElectorate);
        }
    }
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

// Function to load results for a division
async function loadResults(division) {
    try {
        const response = await fetch(`/api/results/division/${encodeURIComponent(division)}`);
        const data = await response.json();
        
        if (data.status === 'success') {
            updateDashboard(data);
        } else {
            console.error('Error loading results:', data.detail);
            showError('Failed to load results');
        }
    } catch (error) {
        console.error('Error fetching results:', error);
        showError('Failed to fetch results');
    }
}

// Function to load TCP candidates for a division
async function loadTCPCandidates(division) {
    try {
        const response = await fetch(`/api/tcp-candidates/division/${encodeURIComponent(division)}`);
        if (!response.ok) throw new Error('Failed to fetch TCP candidates');
        
        const data = await response.json();
        if (data.status === 'success') {
            updateTCPCandidates(data.candidates);
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
            <td>${v.percentage ? v.percentage.toFixed(2) : '0.00'}%</td>
        </tr>
    `).join('');
}

// Function to update booth results table
function updateBoothResults(booths) {
    const tableBody = document.getElementById('booth-results-table');
    tableBody.innerHTML = booths.map(booth => {
        // Calculate total primary votes
        const totalPrimaryVotes = Object.values(booth.primary_votes || {}).reduce((sum, votes) => sum + votes, 0);
        
        // Calculate total votes for each TCP candidate (primary + TCP)
        const totalVotes = {};
        const tcpVotes = booth.tcp_votes || booth.two_candidate_preferred || {};
        
        // Initialize TCP candidates with their primary votes
        Object.entries(tcpVotes).forEach(([tcpCandidate, distributions]) => {
            // Find the full name in primary_votes that contains the TCP candidate's last name
            const fullName = Object.keys(booth.primary_votes || {}).find(name => 
                name.toUpperCase().includes(tcpCandidate.toUpperCase())
            );
            totalVotes[tcpCandidate] = fullName ? booth.primary_votes[fullName] : 0;
        });
        
        // Add TCP distributions from all candidates
        Object.entries(tcpVotes).forEach(([tcpCandidate, distributions]) => {
            Object.entries(distributions).forEach(([fromCandidate, votes]) => {
                totalVotes[tcpCandidate] += votes;
            });
        });
        
        // Sort TCP candidates to ensure Steggall appears first
        const sortedTcpCandidates = Object.keys(totalVotes).sort((a, b) => a === 'STEGGALL' ? -1 : 1);
        
        // Calculate total TCP votes for percentage calculations
        const totalTCPVotes = Object.values(totalVotes).reduce((sum, votes) => sum + votes, 0);
        
        // Create the bar chart HTML
        const barChart = `
            <div class="tcp-bar-chart" style="position: relative; height: 30px; width: 100%; background: #f0f0f0; border-radius: 4px;">
                ${sortedTcpCandidates.map((candidate, index) => {
                    const votes = totalVotes[candidate];
                    const percentage = totalTCPVotes > 0 ? (votes / totalTCPVotes * 100) : 0;
                    const color = candidate === 'STEGGALL' ? 'rgba(92, 205, 201, 0.8)' : 'rgba(0, 0, 80, 0.8)';
                    const left = index === 0 ? '0' : `${sortedTcpCandidates.slice(0, index).reduce((sum, c) => sum + (totalVotes[c] / totalTCPVotes * 100), 0)}%`;
                    
                    return `
                        <div style="position: absolute; left: ${left}; width: ${percentage}%; height: 100%; background: ${color}; border-radius: ${index === 0 ? '4px 0 0 4px' : index === sortedTcpCandidates.length - 1 ? '0 4px 4px 0' : '0'};">
                            <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: white; font-weight: bold; text-shadow: 1px 1px 2px rgba(0,0,0,0.5);">
                                ${votes.toLocaleString()}
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
        
        return `
            <tr>
                <td>${booth.booth_name}</td>
                <td>${new Date(booth.timestamp).toLocaleString()}</td>
                <td>${totalPrimaryVotes.toLocaleString()}</td>
                <td>${barChart}</td>
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

// Function to update TCP votes display
function updateTCPVotes(votes) {
    // Update chart
    if (tcpVotesChart) {
        tcpVotesChart.destroy();
    }
    
    // Get TCP candidates from the first vote entry
    const tcpCandidates = votes.length > 0 ? Object.keys(votes[0].distributions) : [];
    
    // Create datasets for each TCP candidate
    // Sort TCP candidates to ensure Steggall appears first
    const sortedTcpCandidates = [...tcpCandidates].sort((a, b) => a === 'STEGGALL' ? -1 : 1);
    
    const datasets = sortedTcpCandidates.map((tcpCandidate) => ({
        label: tcpCandidate,
        data: votes.map(v => v.distributions[tcpCandidate].votes),
        backgroundColor: tcpCandidate === 'STEGGALL' ? 'rgba(92, 205, 201, 0.9)' : 'rgba(0, 0, 80, 0.9)',
        borderColor: tcpCandidate === 'ROGERS' ? 'rgb(30, 67, 215)' : 'rgb(59, 59, 246)',
        borderWidth: 1
    }));
    
    const ctx = document.getElementById('tcp-votes-chart').getContext('2d');
    tcpVotesChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: votes.map(v => v.candidate),
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    stacked: true
                },
                x: {
                    stacked: true
                }
            }
        }
    });
    
    // Update table
    const tableBody = document.getElementById('tcp-votes-table');
    tableBody.innerHTML = votes.map(v => {
        const distributions = sortedTcpCandidates.map(tcpCandidate => {
            const data = v.distributions[tcpCandidate];
            return `
                <td>${data.votes.toLocaleString()}</td>
                <td>${data.percentage.toFixed(2)}%</td>
            `;
        }).join('');
            
        return `
            <tr>
                <td>${v.candidate}</td>
                <td>${v.primary_votes.toLocaleString()}</td>
                ${distributions}
            </tr>
        `;
    }).join('');
    
    // Update table header
    const tableHeader = document.querySelector('#tcp-votes-table').previousElementSibling;
    tableHeader.innerHTML = `
        <tr>
            <th>Candidate</th>
            <th>Primary Votes</th>
            ${sortedTcpCandidates.map(candidate => `
                <th colspan="2">${candidate}</th>
            `).join('')}
        </tr>
        <tr>
            <th></th>
            <th></th>
            ${sortedTcpCandidates.map(() => `
                <th>Votes</th>
                <th>%</th>
            `).join('')}
        </tr>
    `;

    // Calculate and display net TCP position
    updateNetTCPPosition(votes, tcpCandidates);
}

// Function to update net TCP position display
function updateNetTCPPosition(votes, tcpCandidates) {
    // Calculate total votes for each TCP candidate
    const totalVotes = {};
    tcpCandidates.forEach(tcpCandidate => {
        totalVotes[tcpCandidate] = votes.reduce((sum, v) => {
            return sum + (v.distributions[tcpCandidate]?.votes || 0);
        }, 0);
    });

    // Calculate total votes across all TCP candidates
    const grandTotal = Object.values(totalVotes).reduce((sum, votes) => sum + votes, 0);

    // Update the summary section with a simple table
    const summary = document.getElementById('tcp-summary');
    summary.innerHTML = `
        <table class="table table-sm">
            <thead>
                <tr>
                    <th>Candidate</th>
                    <th>Total Votes</th>
                    <th>Percentage</th>
                </tr>
            </thead>
            <tbody>
                ${tcpCandidates.map(candidate => {
                    const votes = totalVotes[candidate];
                    const percentage = grandTotal > 0 ? (votes / grandTotal * 100).toFixed(2) : '0.00';
                    return `
                        <tr>
                            <td>${candidate}</td>
                            <td>${votes.toLocaleString()}</td>
                            <td>${percentage}%</td>
                        </tr>
                    `;
                }).join('')}
            </tbody>
        </table>
    `;
} 