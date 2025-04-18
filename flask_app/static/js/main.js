
document.addEventListener('DOMContentLoaded', function() {
    console.log('Amalfi Results app initialized');
    
    if (window.location.pathname === '/results') {
        setInterval(checkForNewResults, 30000);
    }
});

function checkForNewResults() {
    fetch('/api/results')
        .then(response => response.json())
        .then(data => {
            const currentCount = document.querySelectorAll('tbody tr').length;
            if (data.length > currentCount) {
                window.location.reload();
            }
        })
        .catch(error => console.error('Error checking for new results:', error));
}
