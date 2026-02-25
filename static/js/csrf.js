// CSRF Token Handler for AJAX requests

// Get CSRF token from meta tag
function getCsrfToken() {
    return document.querySelector('meta[name="csrf-token"]').getAttribute('content');
}

// Add CSRF token to all fetch requests
const originalFetch = window.fetch;
window.fetch = function (url, options = {}) {
    // Only add CSRF for same-origin requests
    if (!url.startsWith('http') || url.startsWith(window.location.origin)) {
        options.headers = options.headers || {};

        // Add CSRF token for non-GET requests
        if (!options.method || options.method.toUpperCase() !== 'GET') {
            const token = getCsrfToken();
            if (token) {
                if (options.headers instanceof Headers) {
                    options.headers.append('X-CSRFToken', token);
                } else {
                    options.headers['X-CSRFToken'] = token;
                }
            }
        }
    }

    return originalFetch(url, options);
};

// Add CSRF token to all forms on submit
document.addEventListener('DOMContentLoaded', function () {
    const forms = document.querySelectorAll('form');

    forms.forEach(form => {
        // Skip if form already has CSRF token
        if (form.querySelector('input[name="csrf_token"]')) {
            return;
        }

        // Only for POST/PUT/DELETE forms
        if (form.method && form.method.toUpperCase() !== 'GET') {
            const token = getCsrfToken();
            if (token) {
                // Add hidden CSRF input
                const csrfInput = document.createElement('input');
                csrfInput.type = 'hidden';
                csrfInput.name = 'csrf_token';
                csrfInput.value = token;

                form.appendChild(csrfInput);
            }
        }
    });
});
