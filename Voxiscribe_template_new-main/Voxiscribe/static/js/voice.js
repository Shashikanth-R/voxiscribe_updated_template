// Live transcription and voice command integration using Web Speech API
(function(){
  const synth = window.speechSynthesis;
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let mainRecognition = null;
  let wakewordRecognition = null;
  let isRecording = false;
  let autoCommandMode = true; // interpret command phrases

  // --- Core Functions ---

  function speak(text){
    if (!synth) return;
    const utter = new SpeechSynthesisUtterance(text);
    utter.rate = 1;
    utter.pitch = 1;
    synth.speak(utter);
  }

  function supportsSpeechRecognition() {
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
      toast('SpeechRecognition not supported in this browser', true);
      return false;
    }
    return true;
  }

  // --- Wakeword Listener (Stage 1) ---

  function startWakewordListener() {
    if (!supportsSpeechRecognition() || wakewordRecognition) return;

    wakewordRecognition = new SpeechRecognition();
    wakewordRecognition.continuous = true;
    wakewordRecognition.interimResults = false;
    wakewordRecognition.lang = 'en-US';

    wakewordRecognition.onresult = function(event) {
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          const transcript = event.results[i][0].transcript.trim().toLowerCase();
          if (includesAny(transcript, ['start answering', 'start recording'])) {
            stopWakewordListener();
            startMainRecognition();
          }
        }
      }
    };

    wakewordRecognition.onerror = function(event) {
      // Ignore common, non-fatal errors
      if (event.error !== 'no-speech' && event.error !== 'audio-capture') {
        toast('Wakeword recognition error: ' + event.error, true);
      }
    };

    wakewordRecognition.onend = function() {
      // Keep the wakeword listener running
      if (wakewordRecognition) {
        wakewordRecognition.start();
      }
    };

    wakewordRecognition.start();
    console.log("Wakeword listener started.");
  }

  function stopWakewordListener() {
    if (wakewordRecognition) {
      wakewordRecognition.onend = null; // Prevent automatic restart
      wakewordRecognition.stop();
      wakewordRecognition = null;
      console.log("Wakeword listener stopped.");
    }
  }


  // --- Main Recognition (Stage 2) ---

  function startMainRecognition(){
    if (isRecording) return;
    if (!supportsSpeechRecognition()) return;

    stopWakewordListener(); // Ensure wakeword listener is off

    mainRecognition = new SpeechRecognition();
    mainRecognition.continuous = true;
    mainRecognition.interimResults = true;
    mainRecognition.lang = 'en-US';
    isRecording = true;
    setMicActive(true);
    toast('Listening…');

    const qid = window.getCurrentQuestionId && window.getCurrentQuestionId();
    let active = document.getElementById(`answer-input-${qid}`);
    if (active) {
      active.classList.add('recording-active');
    }

    let finalTranscript = '';
    mainRecognition.onresult = function(event) {
      let interimTranscript = '';
      let commandHandled = false;

      for (let i = event.resultIndex; i < event.results.length; ++i) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          if (handleMainTranscript(transcript.trim())) {
            commandHandled = true;
          } else {
            finalTranscript += transcript.trim() + ' ';
          }
        } else {
          interimTranscript += transcript;
        }
      }

      if (commandHandled) {
        interimTranscript = ''; // Don't show interim if a command was handled.
      }

      showLiveTranscript(finalTranscript + interimTranscript);
      const qid = window.getCurrentQuestionId && window.getCurrentQuestionId();
      let active = document.getElementById(`answer-input-${qid}`);
      if (active) {
        active.value = (finalTranscript + interimTranscript).trim();
        active.dispatchEvent(new Event('input', { bubbles: true }));
        if (window.collectCurrentAnswer) {
          window.collectCurrentAnswer();
        }
      }
    };

    mainRecognition.onerror = function(event) {
      if (event.error === 'no-speech' || event.error === 'audio-capture') {
        toast('No speech detected. Stopping recording.', true);
        stopMainRecognition();
      } else {
        toast('Speech recognition error: ' + event.error, true);
      }
    };

    mainRecognition.onend = function() {
      if (isRecording) { // If it stops unexpectedly, restart it
        mainRecognition.start();
      } else { // Normal stop
        setMicActive(false);
        toast('Stopped listening');
        startWakewordListener(); // Go back to waiting for wakeword
      }
    };

    mainRecognition.start();
  }

  function stopMainRecognition() {
    if (!isRecording) return;
    isRecording = false;
    if (mainRecognition) {
        mainRecognition.stop();
    }
    mainRecognition = null;

    const qid = window.getCurrentQuestionId && window.getCurrentQuestionId();
    let active = document.getElementById(`answer-input-${qid}`);
    if (active) {
      active.classList.remove('recording-active');
    }
  }

  // --- Transcript and Command Handling ---

  function showLiveTranscript(text){
    const el = document.getElementById('live-transcript');
    if (!el) return;
    el.textContent = text;
    el.style.display = 'block';
    el.style.opacity = 1;
    clearTimeout(showLiveTranscript._timer);
    showLiveTranscript._timer = setTimeout(()=> {
      el.style.opacity = 0;
      setTimeout(()=> { el.style.display = 'none'; }, 400);
    }, 3500);
  }

  function handleMainTranscript(text){
    const lower = text.toLowerCase();
    if (autoCommandMode) {
      if (includesAny(lower, ['next question', 'next'])) { window.goToNextQuestion && window.goToNextQuestion(); return true; }
      if (includesAny(lower, ['previous question', 'back', 'previous'])) { window.goToPreviousQuestion && window.goToPreviousQuestion(); return true; }
      if (includesAny(lower, ['submit exam', 'submit'])) { window.submitExam && window.submitExam(); return true; }
      if (includesAny(lower, ['repeat question', 'repeat'])) { window.readCurrentQuestion && window.readCurrentQuestion(); return true; }
      // "start recording" is handled by wakeword, "stop" is the main action here
      if (includesAny(lower, ['stop recording', 'stop answering'])) { stopMainRecognition(); return true; }
    }
    return false;
  }

  function includesAny(s, phrases){ return phrases.some(p=> s.includes(p)); }

  // --- UI and Utility ---

  function setMicActive(active){
    const btnStart = document.getElementById('voice-record');
    const btnStop = document.getElementById('voice-stop');
    if (!btnStart || !btnStop) return;

    if (active) {
        btnStart.style.display = 'none';
        btnStop.style.display = 'inline-block';
        btnStop.disabled = false;
        btnStop.textContent = 'Stop';
        btnStart.classList.add('listening');
    } else {
        btnStart.style.display = 'inline-block';
        btnStop.style.display = 'none';
        btnStart.classList.remove('listening');
        btnStart.textContent = 'Start Recording';
    }
  }

  function toast(msg, isError){
    const t = document.createElement('div');
    t.className = 'toast' + (isError?' toast-error':'');
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(()=> { t.classList.add('show'); }, 10);
    setTimeout(()=> { t.classList.remove('show'); setTimeout(()=>t.remove(), 500); }, 3000);
  }

  // --- Initialization ---

  // Expose control for button clicks
  window.VoiceControl = {
      startRecording: startMainRecognition,
      stopRecording: stopMainRecognition,
      speak
  };

  document.addEventListener('DOMContentLoaded', function(){
    const btnStart = document.getElementById('voice-record');
    const btnStop = document.getElementById('voice-stop');

    if (btnStart) btnStart.addEventListener('click', startMainRecognition);
    if (btnStop) btnStop.addEventListener('click', stopMainRecognition);

    // Start listening for the wakeword automatically
    startWakewordListener();
  });
})();
