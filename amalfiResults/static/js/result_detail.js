document.addEventListener('DOMContentLoaded', function() {
    // Get the result ID from the URL
    const urlParams = new URLSearchParams(window.location.search);
    const resultId = urlParams.get('id');

    if (!resultId) {
        console.error('No result ID provided');
        return;
    }

    // Function to format numbers with commas
    function formatNumber(num) {
        return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    }

    // Function to update the UI with result data
    function updateUI(data) {
        // Update basic info
        document.getElementById('result-id').textContent = data.id;
        document.getElementById('booth-name').textContent = data.booth_name;
        document.getElementById('polling-place').textContent = data.polling_place;
        document.getElementById('total-votes').textContent = formatNumber(data.total_votes);
        document.getElementById('total-voters').textContent = formatNumber(data.total_voters);
        document.getElementById('turnout').textContent = data.turnout.toFixed(2) + '%';

        // Update candidate votes
        const votesTable = document.getElementById('votes-table');
        votesTable.innerHTML = ''; // Clear existing rows

        data.candidate_votes.forEach(vote => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${vote.candidate_name}</td>
                <td>${formatNumber(vote.votes)}</td>
                <td>${vote.percentage.toFixed(2)}%</td>
            `;
            votesTable.appendChild(row);
        });

        // Update party votes
        const partyTable = document.getElementById('party-table');
        partyTable.innerHTML = ''; // Clear existing rows

        data.party_votes.forEach(vote => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${vote.party_name}</td>
                <td>${formatNumber(vote.votes)}</td>
                <td>${vote.percentage.toFixed(2)}%</td>
            `;
            partyTable.appendChild(row);
        });

        // Update metadata
        document.getElementById('created-at').textContent = new Date(data.created_at).toLocaleString();
        document.getElementById('updated-at').textContent = new Date(data.updated_at).toLocaleString();
        document.getElementById('created-by').textContent = data.created_by;
        document.getElementById('updated-by').textContent = data.updated_by;
    }

    // Function to handle errors
    function handleError(error) {
        console.error('Error loading result data:', error);
        // You might want to show an error message to the user here
    }

    // Fetch the result data
    fetch(`/api/results/${resultId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            updateUI(data);
        })
        .catch(error => {
            handleError(error);
        });
}); 