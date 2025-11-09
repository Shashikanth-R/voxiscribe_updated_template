// static/js/proctoring.js

class ProctoringRecorder {
  constructor(examId) {
    this.examId = examId;
    this.mediaRecorder = null;
    this.stream = null;
    this.isFirstChunk = true;
  }

  async start() {
    try {
      // 1. Get screen and video streams
      const screenStream = await navigator.mediaDevices.getDisplayMedia({
        video: { mediaSource: "screen" },
        audio: true
      });

      const voiceStream = await navigator.mediaDevices.getUserMedia({
        audio: true,
        video: true
      });

      // 2. Combine streams
      // A simple approach is to just record the screen with its audio.
      // A more complex approach involves combining video tracks, but for simplicity,
      // we will focus on the primary screen recording. The user's voice will be
      // captured if they select to share system/mic audio with the screen.
      this.stream = screenStream;

      // 3. Create MediaRecorder
      this.mediaRecorder = new MediaRecorder(this.stream, {
        mimeType: 'video/webm; codecs=vp8,opus'
      });

      // 4. Set up event listener for data chunks
      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          this.uploadChunk(event.data);
        }
      };

      // 5. Start recording and upload in intervals
      this.mediaRecorder.start(5000); // Create a chunk every 5 seconds

      console.log("Proctoring started.");
      this.showProctoringIndicator(true);

    } catch (err) {
      console.error("Error starting proctoring:", err);
      alert("Proctoring could not be started. Please ensure you grant screen and camera permissions. The exam cannot continue without it.");
      // Redirect or disable exam functionality
      window.location.href = '/student/dashboard';
    }
  }

  stop() {
    if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
      this.mediaRecorder.stop();
    }
    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
    }
    console.log("Proctoring stopped.");
    this.showProctoringIndicator(false);
  }

  async uploadChunk(chunk) {
    const formData = new FormData();
    formData.append('exam_id', this.examId);
    formData.append('video_chunk', chunk, 'chunk.webm');
    if (this.isFirstChunk) {
      formData.append('is_first', 'true');
      this.isFirstChunk = false;
    }

    try {
      const response = await fetch('/proctoring/upload', {
        method: 'POST',
        body: formData
      });
      const result = await response.json();
      if (!result.success) {
        console.error('Failed to upload proctoring chunk:', result.message);
      }
    } catch (error) {
      console.error('Error uploading proctoring chunk:', error);
    }
  }

  showProctoringIndicator(isRecording) {
    let indicator = document.getElementById('proctoring-indicator');
    if (!indicator) {
      indicator = document.createElement('div');
      indicator.id = 'proctoring-indicator';
      indicator.style = 'position:fixed;top:10px;right:10px;padding:5px 10px;background:red;color:white;border-radius:5px;font-size:12px;z-index:1000;';
      document.body.appendChild(indicator);
    }
    indicator.textContent = isRecording ? '● Recording' : 'Recording Paused';
    indicator.style.display = isRecording ? 'block' : 'none';
  }
}