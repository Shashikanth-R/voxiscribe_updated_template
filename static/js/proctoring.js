document.addEventListener('DOMContentLoaded', function() {
    const videoBox = document.getElementById('proctoring-videobox');
    if (!videoBox) return;

    const videoEl = document.getElementById('proctor-video');
    const elapsedEl = document.getElementById('proctor-elapsed');
    const consentButton = document.getElementById('proctor-consent-btn');
    const consentOverlay = document.getElementById('proctor-consent');

    let mediaRecorder;
    let chunks = [];
    let startTime;
    let timerInterval;
    let chunkOrder = 0;

    const examDataEl = document.getElementById('exam-data');
    const exam = JSON.parse(examDataEl.textContent);

    async function initProctoring() {
        if (consentOverlay) consentOverlay.style.display = 'none';
        videoBox.style.display = 'flex';

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ video: true });
            videoEl.srcObject = stream;

            // Face detection setup (using a placeholder, replace with a real library if desired)
            setInterval(() => detectFaces(videoEl), 2000);

            mediaRecorder = new MediaRecorder(stream, { mimeType: 'video/webm' });
            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    uploadChunk(event.data);
                }
            };
            mediaRecorder.start(5000); // New chunk every 5 seconds

            startTime = Date.now();
            timerInterval = setInterval(updateTimer, 1000);
        } catch (err) {
            console.error("Proctoring setup failed:", err);
            alert("Webcam access is required for this exam.");
            videoBox.style.display = 'none';
        }
    }

    function updateTimer() {
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        const minutes = String(Math.floor(elapsed / 60)).padStart(2, '0');
        const seconds = String(elapsed % 60).padStart(2, '0');
        if (elapsedEl) elapsedEl.textContent = `${minutes}:${seconds}`;
    }

    async function uploadChunk(chunk) {
        const formData = new FormData();
        formData.append('exam_id', exam.id);
        formData.append('chunk_order', chunkOrder++);
        formData.append('video_chunk', chunk);

        try {
            await fetch('/proctoring/chunk', {
                method: 'POST',
                body: formData
            });
        } catch (err) {
            console.error('Failed to upload video chunk:', err);
        }
    }

    async function logProctoringEvent(eventType) {
        try {
            await fetch('/proctoring/log', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    exam_id: exam.id,
                    event_type: eventType
                })
            });
        } catch (err) {
            console.error('Failed to log proctoring event:', err);
        }
    }

    function detectFaces(video) {
        // This is a placeholder for actual face detection logic.
        // In a real implementation, you would use a library like face-api.js.
        const isFacePresent = Math.random() > 0.1; // Simulate face presence

        if (!isFacePresent) {
            logProctoringEvent('student_left_frame');
            videoBox.style.borderColor = 'red';
        } else {
            videoBox.style.borderColor = '#e53935';
        }
    }

    if (consentButton) {
        consentButton.addEventListener('click', initProctoring);
    } else {
        // If no consent button, start immediately
        initProctoring();
    }
});
