// Load result data directly from FastAPI when the page loads
document.addEventListener('DOMContentLoaded', function() {
    // Get the result ID from the URL path
    const pathParts = window.location.pathname.split('/');
    const resultId = pathParts[pathParts.length - 1];
    
    if (resultId) {
        // Create tables from existing data
        const primaryVotes = {};
        document.querySelectorAll('.primary-vote').forEach(input => {
            primaryVotes[input.dataset.candidate] = parseInt(input.value) || 0;
        });

        // Find the primary votes section
        const primaryVotesSection = Array.from(document.querySelectorAll('h5')).find(h5 => h5.textContent.includes('Primary Votes'))?.nextElementSibling;
        if (primaryVotesSection) {
            const primaryVotesTable = document.getElementById('primaryVotesTable');
            if (primaryVotesTable) {
                const newTable = createPrimaryVotesTable(primaryVotes);
                primaryVotesTable.parentNode.replaceChild(newTable, primaryVotesTable);
            } else {
                // If table doesn't exist, create a new one
                const tableContainer = document.createElement('div');
                tableContainer.className = 'table-responsive mb-4';
                tableContainer.appendChild(createPrimaryVotesTable(primaryVotes));
                primaryVotesSection.appendChild(tableContainer);
            }
        }

        const tcpVotes = {};
        document.querySelectorAll('.tcp-vote').forEach(input => {
            const candidate = input.dataset.candidate;
            const tcpCandidate = input.dataset.tcpCandidate;
            if (!tcpVotes[tcpCandidate]) {
                tcpVotes[tcpCandidate] = {};
            }
            tcpVotes[tcpCandidate][candidate] = parseInt(input.value) || 0;
        });

        // Find the TCP votes section
        const tcpVotesSection = Array.from(document.querySelectorAll('h5')).find(h5 => h5.textContent.includes('Two-Candidate Preferred'))?.nextElementSibling;
        if (tcpVotesSection) {
            const tcpVotesTable = document.getElementById('tcpVotesTable');
            if (tcpVotesTable) {
                const newTable = createTCPVotesTable(tcpVotes);
                tcpVotesTable.parentNode.replaceChild(newTable, tcpVotesTable);
            } else {
                // If table doesn't exist, create a new one
                const tableContainer = document.createElement('div');
                tableContainer.className = 'table-responsive mb-4';
                tableContainer.appendChild(createTCPVotesTable(tcpVotes));
                tcpVotesSection.appendChild(tableContainer);
            }
        }

        const totals = {};
        document.querySelectorAll('.total-vote').forEach(input => {
            totals[input.dataset.type] = parseInt(input.value) || 0;
        });

        // Find the totals section
        const totalsSection = Array.from(document.querySelectorAll('h5')).find(h5 => h5.textContent.includes('Vote Totals'))?.nextElementSibling;
        if (totalsSection) {
            const totalsTable = document.getElementById('totalsTable');
            if (totalsTable) {
                const newTable = createVoteTotalsTable(totals);
                totalsTable.parentNode.replaceChild(newTable, totalsTable);
            } else {
                // If table doesn't exist, create a new one
                const tableContainer = document.createElement('div');
                tableContainer.className = 'table-responsive';
                tableContainer.appendChild(createVoteTotalsTable(totals));
                totalsSection.appendChild(tableContainer);
            }
        }
        
        // Load polling places for the electorate
        const electorateCell = Array.from(document.getElementsByTagName('td')).find(td => td.textContent === 'Electorate');
        if (electorateCell) {
            const electorate = electorateCell.nextElementSibling.textContent.trim();
            if (electorate && electorate !== 'Unknown') {
                fetch(`/api/polling-places/division/${electorate}`)
                    .then(response => response.json())
                    .then(data => {
                        if (data.status === 'success') {
                            const selector = document.getElementById('polling_place_selector');
                            selector.innerHTML = '<option value="">Select a polling place...</option>';
                            data.polling_places.forEach(place => {
                                const option = document.createElement('option');
                                option.value = place.polling_place_name;
                                option.textContent = place.polling_place_name;
                                selector.appendChild(option);
                            });
                        }
                    })
                    .catch(error => console.error('Error loading polling places:', error));
            }
        }
    }
});

// Function to format numbers with commas
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Function to create a table for primary votes
function createPrimaryVotesTable(primaryVotes) {
    const table = document.createElement('table');
    table.className = 'table table-striped';
    
    const thead = document.createElement('thead');
    thead.innerHTML = `
        <tr>
            <th>Candidate</th>
            <th>Votes</th>
            <th>Percentage</th>
        </tr>
    `;
    
    const tbody = document.createElement('tbody');
    
    // Calculate total votes
    const totalVotes = Object.values(primaryVotes).reduce((sum, votes) => sum + votes, 0);
    
    // Create rows for each candidate
    Object.entries(primaryVotes).forEach(([candidate, votes]) => {
        const percentage = totalVotes > 0 ? ((votes / totalVotes) * 100).toFixed(2) : '0.00';
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${candidate}</td>
            <td>${formatNumber(votes)}</td>
            <td>${percentage}%</td>
        `;
        tbody.appendChild(row);
    });
    
    table.appendChild(thead);
    table.appendChild(tbody);
    return table;
}

// Function to create a table for TCP votes
function createTCPVotesTable(tcpVotes) {
    const table = document.createElement('table');
    table.className = 'table table-striped';
    
    const thead = document.createElement('thead');
    thead.innerHTML = `
        <tr>
            <th>Candidate</th>
            <th>Primary Votes</th>
            <th>Distributions</th>
        </tr>
    `;
    
    const tbody = document.createElement('tbody');
    
    // Create rows for each candidate
    Object.entries(tcpVotes).forEach(([candidate, data]) => {
        const row = document.createElement('tr');
        const distributions = Object.entries(data.distributions)
            .map(([tcpCandidate, votes]) => `${tcpCandidate}: ${formatNumber(votes)} (${votes.percentage.toFixed(2)}%)`)
            .join('<br>');
        
        row.innerHTML = `
            <td>${candidate}</td>
            <td>${formatNumber(data.primary_votes)}</td>
            <td>${distributions}</td>
        `;
        tbody.appendChild(row);
    });
    
    table.appendChild(thead);
    table.appendChild(tbody);
    return table;
}

// Function to create a table for vote totals
function createVoteTotalsTable(totals) {
    const tbody = document.getElementById('vote-totals-body');
    tbody.innerHTML = '';
    
    Object.entries(totals).forEach(([category, count]) => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${category}</td>
            <td>${formatNumber(count)}</td>
        `;
        tbody.appendChild(row);
    });
}

// Function to load result data from FastAPI
function loadResultData(resultId) {
    console.log('Loading result data for ID:', resultId);
    fetch(`/api/results/${resultId}`, {
        method: 'GET',
        headers: {
            'Accept': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            const result = data.result;
            const resultData = result.data;
            
            // Update booth name
            document.getElementById('booth_name').value = result.booth_name || '';
            
            // Update primary votes
            const primaryVotesTable = document.getElementById('primaryVotesTable');
            if (resultData.primary_votes) {
                primaryVotesTable.innerHTML = '';
                primaryVotesTable.appendChild(createPrimaryVotesTable(resultData.primary_votes));
            }
            
            // Update TCP votes
            const tcpVotesTable = document.getElementById('tcpVotesTable');
            if (resultData.two_candidate_preferred) {
                tcpVotesTable.innerHTML = '';
                tcpVotesTable.appendChild(createTCPVotesTable(resultData.two_candidate_preferred));
            }
            
            // Update vote totals
            if (resultData.totals) {
                createVoteTotalsTable(resultData.totals);
            }
        } else {
            console.error('Error loading result:', data.message);
        }
    })
    .catch(error => {
        console.error('Error loading result:', error);
    });
}

// Function to update primary votes data
function updatePrimaryVotes() {
    const primaryVotes = {};
    document.querySelectorAll('.primary-vote').forEach(input => {
        primaryVotes[input.dataset.candidate] = parseInt(input.value) || 0;
    });
    document.getElementById('primaryVotesInput').value = JSON.stringify(primaryVotes);
    validateVotes();
}

// Function to update TCP votes data
function updateTCPVotes() {
    const tcpVotes = {};
    document.querySelectorAll('.tcp-vote').forEach(input => {
        const candidate = input.dataset.candidate;
        const tcpCandidate = input.dataset.tcpCandidate;
        if (!tcpVotes[tcpCandidate]) {
            tcpVotes[tcpCandidate] = {};
        }
        tcpVotes[tcpCandidate][candidate] = parseInt(input.value) || 0;
    });
    document.getElementById('tcpVotesInput').value = JSON.stringify(tcpVotes);
    validateVotes();
}

// Function to update totals data
function updateTotals() {
    const totals = {};
    document.querySelectorAll('.total-vote').forEach(input => {
        totals[input.dataset.type] = parseInt(input.value) || 0;
    });
    document.getElementById('totalsInput').value = JSON.stringify(totals);
    validateVotes();
}

// Function to validate votes
function validateVotes() {
    // Get all primary votes
    let totalPrimaryVotes = 0;
    document.querySelectorAll('.primary-vote').forEach(input => {
        totalPrimaryVotes += parseInt(input.value) || 0;
    });

    // Get formal, informal, and total votes
    const formalVotes = parseInt(document.querySelector('.total-vote[data-type="formal"]').value) || 0;
    const informalVotes = parseInt(document.querySelector('.total-vote[data-type="informal"]').value) || 0;
    const totalVotes = parseInt(document.querySelector('.total-vote[data-type="total"]').value) || 0;

    // Validate totals
    if (totalPrimaryVotes !== formalVotes) {
        console.warn('Total primary votes does not equal formal votes');
    }
    if ((formalVotes + informalVotes) !== totalVotes) {
        console.warn('Sum of formal and informal votes does not equal total votes');
    }
}

// Function to submit the form
function submitForm(action) {
    // Update all the hidden inputs with current values
    updatePrimaryVotes();
    updateTCPVotes();
    updateTotals();
    
    // Set the action
    document.getElementById('actionInput').value = action;
    
    // Submit the form
    document.getElementById('reviewForm').submit();
}

// Function to update booth name
function updateBoothName() {
    const boothName = document.getElementById('boothName').value;
    const resultId = document.getElementById('resultId').value;
    
    fetch(`/api/results/${resultId}/update-booth-name`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ booth_name: boothName })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            alert('Booth name updated successfully');
        } else {
            alert('Error updating booth name: ' + data.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Error updating booth name');
    });
}

// Function to update booth name from polling place selector
function updateBoothNameFromSelector(boothName) {
    if (boothName) {
        document.getElementById('booth_name').value = boothName;
        updateBoothName();
    }
} 