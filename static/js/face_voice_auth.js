
document.addEventListener('DOMContentLoaded', () => {
    const video = document.getElementById('video');
    const captureFaceButton = document.getElementById('capture-face');
    const recordVoiceButton = document.getElementById('record-voice');
    const stopRecordingButton = document.getElementById('stop-recording');
    const submitAuthButton = document.getElementById('submit-auth');

    let faceBlob = null;
    let voiceBlob = null;
    let mediaRecorder;
    let audioChunks = [];

    // Access webcam
    navigator.mediaDevices.getUserMedia({ video: true, audio: false })
        .then(stream => {
            video.srcObject = stream;
        })
        .catch(err => {
            console.error("Error accessing webcam: ", err);
            alert("Error accessing webcam. Please ensure you have a webcam connected and have granted permission.");
        });

    // Capture face
    captureFaceButton.addEventListener('click', () => {
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const context = canvas.getContext('2d');
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        canvas.toBlob(blob => {
            faceBlob = blob;
            captureFaceButton.textContent = "Face Captured";
            captureFaceButton.disabled = true;
            checkIfReadyToSubmit();
        }, 'image/jpeg');
    });

    // Record voice
    recordVoiceButton.addEventListener('click', () => {
        navigator.mediaDevices.getUserMedia({ audio: true, video: false })
            .then(stream => {
                mediaRecorder = new MediaRecorder(stream);
                mediaRecorder.start();
                audioChunks = [];
                recordVoiceButton.disabled = true;
                stopRecordingButton.disabled = false;

                mediaRecorder.addEventListener("dataavailable", event => {
                    audioChunks.push(event.data);
                });

                mediaRecorder.addEventListener("stop", () => {
                    voiceBlob = new Blob(audioChunks, { type: 'audio/webm' });
                    recordVoiceButton.textContent = "Voice Recorded";
                    stopRecordingButton.disabled = true;
                    checkIfReadyToSubmit();
                });
            })
            .catch(err => {
                console.error("Error accessing microphone: ", err);
                alert("Error accessing microphone. Please ensure you have a microphone connected and have granted permission.");
            });
    });

    stopRecordingButton.addEventListener('click', () => {
        mediaRecorder.stop();
    });

    function checkIfReadyToSubmit() {
        if (faceBlob && voiceBlob) {
            submitAuthButton.disabled = false;
        }
    }

    // Submit to server
    submitAuthButton.addEventListener('click', () => {
        const formData = new FormData();
        formData.append('face', faceBlob, 'face.jpg');
        formData.append('voice', voiceBlob, 'voice.webm');
        // get username from the url
        const urlParams = new URLSearchParams(window.location.search);
        const username = urlParams.get('username');
        formData.append('username', username);


        fetch('/save_auth', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert("Authentication data saved successfully!");
                window.location.href = '/';
            } else {
                alert("Error saving authentication data: " + data.error);
            }
        })
        .catch(err => {
            console.error("Error submitting authentication data: ", err);
            alert("Error submitting authentication data.");
        });
    });
});
