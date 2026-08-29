document.getElementById('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const button = document.getElementById('login-button');
    const errorDiv = document.getElementById('error-message');
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    
    button.disabled = true;
    button.textContent = 'Logging in...';
    errorDiv.style.display = 'none';
    // Set when the device refuses further attempts until a power cycle; the
    // button then stays disabled, since there is nothing to retry.
    let locked = false;
    
    try {
        const response = await fetch('/api/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ username, password })
        });
        
        const result = await response.json();

        locked = response.status === 423;

        if (result.success) {
            window.location.href = result.redirect || '/';
        } else {
            errorDiv.textContent = result.message || 'Login failed';
            errorDiv.style.display = 'block';
        }
    } catch (error) {
        errorDiv.textContent = 'Network error. Please try again.';
        errorDiv.style.display = 'block';
    } finally {
        button.disabled = locked;
        button.textContent = 'Login';
    }
});

// Focus username field on load
document.getElementById('username').focus();


