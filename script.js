// Smooth scrolling for navigation links
document.querySelectorAll('nav a').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
        e.preventDefault();
        const targetId = this.getAttribute('href').substring(1);
        const targetElement = document.getElementById(targetId);
        targetElement.scrollIntoView({ behavior: 'smooth' });
    });
});

// Alert on download click (optional)
document.querySelector('.download-btn').addEventListener('click', () => {
    alert('Downloading APPTEST. Use it ethically on authorized targets only!');
});
