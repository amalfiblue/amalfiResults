// Load result data directly from FastAPI when the page loads
document.addEventListener('DOMContentLoaded', function() {
    const resultId = document.querySelector('li.breadcrumb-item.active').textContent.split('#')[1];
    loadResultData(resultId);
});

// Function to load result data from FastAPI
function loadResultData(resultId) {
    fetch(`/api/results/${resultId}`, {
        method: 'GET',
        headers: {
            'Accept': 'application/json',
        }
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.json();
    })
    .then(data => {
        if (data.status === 'success') {
            updateResultDisplay(data.result);
        } else {
            console.error('Error loading result data:', data.message || 'Unknown error');
        }
    })
    .catch(error => {
        console.error('Error loading result data:', error);
    });
}

// Function to update the result display with data from FastAPI
function updateResultDisplay(result) {
    console.log('Updating result display with:', result);
    
    // Update metadata
    document.querySelector('li.breadcrumb-item.active').textContent = `Result #${result.id}`;
    
    // Update metadata table
    const metadataTable = document.querySelector('.col-md-6:first-child table tbody');
    metadataTable.innerHTML = `
        <tr>
            <th>ID</th>
            <td>${result.id}</td>
        </tr>
        <tr>
            <th>Timestamp</th>
            <td>${new Date(result.timestamp).toLocaleString()}</td>
        </tr>
        <tr>
            <th>Electorate</th>
            <td>${result.electorate || 'Unknown'}</td>
        </tr>
        <tr>
            <th>Booth Name</th>
            <td>${result.booth_name || 'Unknown'}</td>
        </tr>
    `;
    
    // Update image
    const imageCol = document.querySelector('.col-md-6:nth-child(2)');
    if (result.image_url) {
        imageCol.innerHTML = `
            <div class="text-center">
                <h3>Original Image</h3>
                <a href="${result.image_url}" target="_blank" class="btn btn-outline-primary">View Original Image</a>
            </div>
        `;
    } else {
        imageCol.innerHTML = `
            <div class="alert alert-info">No image available for this result.</div>
        `;
    }
    
    console.log('Primary votes data:', result.data?.primary_votes);
    console.log('TCP votes data:', result.data?.two_candidate_preferred);
    console.log('Totals data:', result.data?.totals);
    
    // Update primary votes
    const primaryVotesCard = document.getElementById('primary-votes-card');
    console.log('Primary votes card element:', primaryVotesCard);
    updatePrimaryVotes(result.data?.primary_votes || {});
    
    // Update TCP votes
    const tcpVotesCard = document.getElementById('tcp-votes-card');
    console.log('TCP votes card element:', tcpVotesCard);
    updateTCPVotes(result.data?.two_candidate_preferred || {});
    
    // Update vote totals
    const totalsTable = document.getElementById('vote-totals-body');
    console.log('Totals table element:', totalsTable);
    updateVoteTotals(result.data?.totals || {});
    
    // Update raw data
    const rawDataPre = document.querySelector('#rawData pre');
    if (rawDataPre) {
        rawDataPre.textContent = JSON.stringify(result.data || {}, null, 2);
    }
}

// Function to update primary votes table
function updatePrimaryVotes(primaryVotes) {
    const primaryVotesCard = document.getElementById('primary-votes-card');
    
    if (Object.keys(primaryVotes).length > 0) {
        let tableHtml = `
            <div class="table-responsive">
                <table class="table table-striped">
                    <thead>
                        <tr>
                            <th>Candidate</th>
                            <th>Primary Votes</th>
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        for (const [candidate, votes] of Object.entries(primaryVotes)) {
            tableHtml += `
                <tr>
                    <td>${candidate}</td>
                    <td>${votes}</td>
                </tr>
            `;
        }
        
        tableHtml += `
                    </tbody>
                </table>
            </div>
        `;
        
        primaryVotesCard.innerHTML = tableHtml;
    } else {
        primaryVotesCard.innerHTML = `
            <div class="alert alert-info">No primary vote data available.</div>
        `;
    }
}

// Function to update TCP votes table
function updateTCPVotes(tcpVotes) {
    const tcpVotesCard = document.getElementById('tcp-votes-card');
    console.log('TCP Votes data structure:', tcpVotes);
    
    if (tcpVotes && Object.keys(tcpVotes).length > 0) {
        // Get all candidates that have TCP distributions
        const allCandidates = new Set();
        Object.values(tcpVotes).forEach(distributions => {
            if (distributions) {
                Object.keys(distributions).forEach(candidate => allCandidates.add(candidate));
            }
        });
        
        console.log('All candidates with TCP distributions:', Array.from(allCandidates));
        
        let tableHtml = `
            <div class="table-responsive">
                <table class="table table-striped">
                    <thead>
                        <tr>
                            <th>Candidate</th>
                            ${Object.keys(tcpVotes).map(tcpCandidate => 
                                `<th>${tcpCandidate}</th>`).join('')}
                        </tr>
                    </thead>
                    <tbody>
        `;
        
        // Create a row for each candidate showing their distribution to TCP candidates
        Array.from(allCandidates).forEach(candidate => {
            const distributions = Object.keys(tcpVotes).map(tcpCandidate => {
                const distribution = tcpVotes[tcpCandidate]?.[candidate];
                console.log(`Distribution for ${candidate} to ${tcpCandidate}:`, distribution);
                return distribution || '-';
            });
            
            tableHtml += `
                <tr>
                    <td>${candidate}</td>
                    ${distributions.map(votes => `<td>${votes}</td>`).join('')}
                </tr>
            `;
        });
        
        tableHtml += `
                    </tbody>
                </table>
            </div>
        `;
        
        tcpVotesCard.innerHTML = tableHtml;
    } else {
        console.log('No TCP votes data available');
        tcpVotesCard.innerHTML = `
            <div class="alert alert-info">No two-candidate preferred data available.</div>
        `;
    }
}

// Function to update vote totals table
function updateVoteTotals(totals) {
    const totalsTable = document.getElementById('vote-totals-body');
    
    if (totalsTable) {
        totalsTable.innerHTML = `
            <tr>
                <td>Formal Votes</td>
                <td>${totals.formal || 'Unknown'}</td>
            </tr>
            <tr>
                <td>Informal Votes</td>
                <td>${totals.informal || 'Unknown'}</td>
            </tr>
            <tr>
                <td>Total Votes</td>
                <td>${totals.total || 'Unknown'}</td>
            </tr>
        `;
    }
} 