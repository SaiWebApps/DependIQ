// DependIQ - Progress Page JavaScript

document.addEventListener('DOMContentLoaded', function () {
  const sessionId = window.location.pathname.split('/')[2];
  const eventSource = new EventSource(`/progress-stream/${sessionId}`);

  eventSource.onmessage = function (event) {
    const data = JSON.parse(event.data);

    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    const stepDetails = document.getElementById('stepDetails');
    const downloadSection = document.getElementById('downloadSection');

    if (progressFill) {
      progressFill.style.width = data.progress + '%';
    }

    if (progressText) {
      progressText.textContent = data.progress + '% - ' + data.step;
    }

    if (stepDetails) {
      if (data.progress === 100) {
        stepDetails.innerHTML = '<h4><span class="material-icons status-icon" style="color: #4caf50;">check_circle</span>' + data.step + '</h4><div>' + data.details + '</div>';
        stepDetails.className = 'step-details complete';

        if (downloadSection) {
          downloadSection.style.display = 'block';
        }

        eventSource.close();
      } else {
        stepDetails.innerHTML = '<div class="spinner"></div><h4><span class="material-icons status-icon">autorenew</span>' + data.step + '</h4><p>' + data.details + '</p>';
      }
    }
  };

  eventSource.onerror = function (event) {
    console.error('EventSource failed.', event);
    const stepDetails = document.getElementById('stepDetails');
    if (stepDetails) {
      stepDetails.innerHTML = '<h4><span class="material-icons status-icon" style="color: #f44336;">error</span>Connection Error</h4><p>Unable to connect to progress stream. Please refresh the page.</p>';
      stepDetails.className = 'step-details';
      stepDetails.style.background = '#ffebee';
      stepDetails.style.borderLeft = '4px solid #f44336';
    }
  };

  // Start the update process
  fetch(`/start-update/${sessionId}`, { method: 'POST' })
    .then(response => response.json())
    .then(data => {
      if (!data.success) {
        console.error('Failed to start update process:', data.message);
      }
    })
    .catch(error => {
      console.error('Error starting update process:', error);
    });
});
