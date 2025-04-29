
document.addEventListener('DOMContentLoaded', function() {
    console.log('Amalfi Results app initialized');
    
    if (window.location.pathname === '/results') {
        setInterval(checkForNewResults, 30000);
    }
    
    const imageUploadForm = document.getElementById('imageUploadForm');
    if (imageUploadForm) {
        imageUploadForm.addEventListener('submit', function(e) {
            const submitBtn = imageUploadForm.querySelector('button[type="submit"]');
            const originalText = submitBtn.textContent;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Processing...';
            
        });
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
