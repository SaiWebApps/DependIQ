// DependIQ - Main Page JavaScript

// Helper function to get auth token
function getAuthToken() {
  return localStorage.getItem('access_token');
}

// Helper function to check if user is authenticated
function isAuthenticated() {
  return !!getAuthToken();
}

// Helper function to add auth header to fetch requests
function getAuthHeaders() {
  const token = getAuthToken();
  const headers = {
    'Content-Type': 'application/json'
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  return headers;
}

// Helper function to handle auth errors
function handleAuthError() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  window.location.href = '/login?return_to=' + encodeURIComponent(window.location.pathname);
}

document.addEventListener('DOMContentLoaded', function () {
  const fileInput = document.getElementById('fileInput');
  const display = document.querySelector('.file-input-display');
  const form = document.querySelector('form');
  const submitBtn = document.querySelector('.upload-btn');

  if (fileInput && display) {
    fileInput.addEventListener('change', function (e) {
      if (e.target.files.length > 0) {
        display.innerHTML = `
                    <span class="material-icons" style="font-size: 3rem; color: var(--color-success); margin-bottom: 16px;">check_circle</span>
                    <div style="font-size: 1.1rem; color: var(--color-success); font-weight: 500;">${e.target.files[0].name}</div>
                    <div style="color: var(--color-secondary); margin-top: 8px;">Ready to analyze</div>
                `;
        display.classList.remove('drag-active');
        display.classList.add('drag-success');
      }
    });

    // Handle drag and drop
    display.addEventListener('dragover', function (e) {
      e.preventDefault();
      display.classList.remove('drag-success');
      display.classList.add('drag-active');
    });

    display.addEventListener('dragleave', function (e) {
      e.preventDefault();
      display.classList.remove('drag-active');
    });

    display.addEventListener('drop', function (e) {
      e.preventDefault();
      display.classList.remove('drag-active');
      const files = e.dataTransfer.files;
      if (files.length > 0) {
        fileInput.files = files;
        fileInput.dispatchEvent(new Event('change'));
      }
    });
  }

  // Handle form submission with progress
  if (form && submitBtn) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();

      const formData = new FormData(form);
      const file = formData.get('file');

      if (!file || file.size === 0) {
        alert('Please select a ZIP file to upload');
        return;
      }

      // Get user instructions from textarea
      const userInstructions = document.getElementById('userInstructions');
      if (userInstructions && userInstructions.value.trim()) {
        formData.set('user_instructions', userInstructions.value.trim());
      }

      // Update button to show loading state
      submitBtn.innerHTML = `
        <div class="spinner" style="width: 20px; height: 20px; margin-right: 8px; border-width: 2px;"></div>
        <span>Uploading & Starting Analysis...</span>
      `;
      submitBtn.disabled = true;

      // Submit form and redirect to analysis page
      const token = getAuthToken();
      const fetchOptions = {
        method: 'POST',
        body: formData,
        redirect: 'follow'
      };

      // Add auth header if token exists
      if (token) {
        fetchOptions.headers = {
          'Authorization': `Bearer ${token}`
        };
      }

      fetch('/analyze/', fetchOptions)
        .then(response => {
          // Handle authentication errors
          if (response.status === 401 || response.status === 403) {
            handleAuthError();
            return;
          }

          if (response.redirected) {
            // Follow the redirect to the analysis page
            window.location.href = response.url;
          } else if (response.ok) {
            return response.json();
          } else {
            throw new Error('Upload failed');
          }
        })
        .then(data => {
          if (data && data.error) {
            alert(data.error);
            // Reset button
            submitBtn.innerHTML = `
              <span class="material-icons" style="vertical-align: middle; margin-right: 8px;">psychology</span>
              Analyze Dependencies
            `;
            submitBtn.disabled = false;
          }
        })
        .catch(error => {
          console.error('Error:', error);
          alert('Upload failed. Please try again.');

          // Reset button
          submitBtn.innerHTML = `
          <span class="material-icons" style="vertical-align: middle; margin-right: 8px;">psychology</span>
          Analyze Dependencies
        `;
          submitBtn.disabled = false;
        });
    });
  }
});

// Tab switching functionality
function switchTab(tabName) {
  // Remove active class from all tab headers
  const tabHeaders = document.querySelectorAll('.tab-header');
  tabHeaders.forEach(header => {
    header.classList.remove('active');
  });

  // Remove active class from all tab panels
  const tabPanels = document.querySelectorAll('.tab-panel');
  tabPanels.forEach(panel => {
    panel.classList.remove('active');
  });

  // Add active class to selected tab header
  const selectedHeader = document.querySelector(`[data-tab="${tabName}"]`);
  if (selectedHeader) {
    selectedHeader.classList.add('active');
  }

  // Add active class to selected tab panel
  const selectedPanel = document.getElementById(`${tabName}-panel`);
  if (selectedPanel) {
    selectedPanel.classList.add('active');
  }
}

// GitHub authentication
function initiateGitHubAuth() {
  const githubBtn = document.querySelector('.github-auth-btn');

  // Store GitHub user instructions in sessionStorage before redirecting
  const githubInstructions = document.getElementById('githubUserInstructions');
  if (githubInstructions && githubInstructions.value.trim()) {
    sessionStorage.setItem('github_user_instructions', githubInstructions.value.trim());
  }

  // Show loading state
  githubBtn.innerHTML = `
    <div class="spinner" style="width: 16px; height: 16px; margin-right: 8px; border-width: 2px;"></div>
    Connecting to GitHub...
  `;
  githubBtn.disabled = true;

  // Redirect to GitHub OAuth
  window.location.href = '/auth/github';
}
