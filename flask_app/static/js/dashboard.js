// Function to initialize charts
function initializeCharts() {
    // Primary Votes Chart
    const primaryVotesCtx = document.getElementById('primary-votes-chart').getContext('2d');
    const primaryVotesData = {
        labels: [],
        datasets: [{
            label: 'Primary Votes',
            data: [],
            backgroundColor: 'rgba(54, 162, 235, 0.5)',
            borderColor: 'rgba(54, 162, 235, 1)',
            borderWidth: 1
        }]
    };

    const primaryVotesChart = new Chart(primaryVotesCtx, {
        type: 'bar',
        data: primaryVotesData,
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Votes'
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                }
            }
        }
    });

    // TCP Votes Chart
    const tcpVotesCtx = document.getElementById('tcp-votes-chart').getContext('2d');
    const tcpVotesData = {
        labels: [],
        datasets: [{
            label: 'TCP Votes',
            data: [],
            backgroundColor: 'rgba(255, 99, 132, 0.5)',
            borderColor: 'rgba(255, 99, 132, 1)',
            borderWidth: 1
        }]
    };

    const tcpVotesChart = new Chart(tcpVotesCtx, {
        type: 'bar',
        data: tcpVotesData,
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Votes'
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                }
            }
        }
    });

    return { primaryVotesChart, tcpVotesChart };
}

// Function to update charts with new data
function updateCharts(primaryVotesChart, tcpVotesChart, data) {
    // Update Primary Votes Chart
    primaryVotesChart.data.labels = data.primary_votes.map(item => item.candidate);
    primaryVotesChart.data.datasets[0].data = data.primary_votes.map(item => item.votes);
    primaryVotesChart.update();

    // Update TCP Votes Chart
    tcpVotesChart.data.labels = data.tcp_votes.map(item => item.candidate);
    tcpVotesChart.data.datasets[0].data = data.tcp_votes.map(item => item.votes);
    tcpVotesChart.update();
}

// Function to load electorates
function loadElectorates() {
    fetch('/api/electorates')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                const electorateList = document.getElementById('electorate-list');
                electorateList.innerHTML = '';
                
                data.electorates.forEach(electorate => {
                    const link = document.createElement('a');
                    link.href = `/dashboard/${encodeURIComponent(electorate)}`;
                    link.className = 'list-group-item list-group-item-action';
                    link.textContent = electorate;
                    electorateList.appendChild(link);
                });
            }
        })
        .catch(error => console.error('Error loading electorates:', error));
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    const charts = initializeCharts();
    loadElectorates();

    // Set up polling for updates
    setInterval(() => {
        const selectedElectorate = document.querySelector('.list-group-item.active')?.textContent;
        if (selectedElectorate) {
            console.log(`[Dashboard] Fetching results for electorate: ${selectedElectorate}`);
            fetch(`/api/results/${encodeURIComponent(selectedElectorate)}`)
                .then(response => {
                    console.log(`[Dashboard] Response status: ${response.status}`);
                    return response.json();
                })
                .then(data => {
                    console.log(`[Dashboard] Received data:`, data);
                    if (data.status === 'success') {
                        console.log(`[Dashboard] Processing ${data.booth_results?.length || 0} booth results`);
                        updateCharts(charts.primaryVotesChart, charts.tcpVotesChart, data);
                        document.getElementById('booths-reporting').textContent = 
                            `${data.booth_count} of ${data.total_booths} Booths Reporting`;
                        document.getElementById('last-updated').textContent = 
                            `Last Updated: ${new Date().toLocaleTimeString()}`;
                    } else {
                        console.error('[Dashboard] Error in response:', data.message);
                    }
                })
                .catch(error => {
                    console.error('[Dashboard] Error fetching results:', error);
                });
        }
    }, 30000); // Update every 30 seconds
}); 