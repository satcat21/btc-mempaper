document.getElementById('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const button = document.getElementById('login-button');
    const errorDiv = document.getElementById('error-message');
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    
    button.disabled = true;
    button.textContent = 'Logging in...';
    errorDiv.style.display = 'none';
    
    try {
        const response = await fetch('/api/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ username, password })
        });
        
        const result = await response.json();
        
        if (result.success) {
            window.location.href = '/';
        } else {
            errorDiv.textContent = result.message || 'Login failed';
            errorDiv.style.display = 'block';
        }
    } catch (error) {
        errorDiv.textContent = 'Network error. Please try again.';
        errorDiv.style.display = 'block';
    } finally {
        button.disabled = false;
        button.textContent = 'Login';
    }
});

// Focus username field on load
document.getElementById('username').focus();

// Apply dark mode from localStorage
const storedDarkMode = localStorage.getItem('mempaper_dark_mode');
if (storedDarkMode === 'true') {
    document.body.classList.add('dark-mode');
}
