// Exam page logic: render questions, timer, autosave, navigation, submit
(function(){
  let exam = null;
  let currentIndex = 0;
  let timerInterval = null;
  let endTime = null;
  let markedForReview = {};

  function getState(){ return exam; }

  // TTS Service
  class TtsService {
    constructor() {
      this.synth = window.speechSynthesis;
      this.voice = null;
      this.volume = 1;
      this.lang = 'en-US';
      this.isSpeaking = false;
      this.queue = [];
      this.onSpeak = null;
      this.onEnd = null;
      this._initVoices();
    }
    _initVoices() {
      this.synth.onvoiceschanged = () => {
        const voices = this.synth.getVoices();
        this.voice = voices.find(v => v.lang === this.lang) || voices[0];
      };
      if (this.synth.getVoices().length) {
        this.voice = this.synth.getVoices().find(v => v.lang === this.lang) || this.synth.getVoices()[0];
      }
    }
    speak(text) {
      this.cancel();
      if (!text) return;
      const utter = new SpeechSynthesisUtterance(text);
      utter.voice = this.voice;
      utter.volume = this.volume;
      utter.lang = this.lang;
      this.isSpeaking = true;
      utter.onstart = () => { this.isSpeaking = true; this.onSpeak && this.onSpeak(text); };
      utter.onend = () => { this.isSpeaking = false; this.onEnd && this.onEnd(); };
      this.synth.speak(utter);
    }
    cancel() {
      this.synth.cancel();
      this.isSpeaking = false;
    }
    setConfig({lang, voice, volume}) {
      if (lang) this.lang = lang;
      if (volume !== undefined) this.volume = volume;
      if (voice) this.voice = voice;
    }
  }
  window.ttsService = new TtsService();
  window.ttsSpeak = (text) => window.ttsService.speak(text);
  window.ttsCancel = () => window.ttsService.cancel();
  
  // Voice Command Service
  class VoiceCommandService {
    constructor(commands) {
      this.recognition = null;
      this.active = false;
      this.grammar = commands;
      this.lastCommand = '';
      this.onCommand = null;
      this.onResult = null;
      this._init();
    }
    _init() {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SpeechRecognition) return;
      this.recognition = new SpeechRecognition();
      this.recognition.continuous = true;
      this.recognition.interimResults = false;
      this.recognition.lang = 'en-US';
      this.recognition.onresult = (event) => {
        const transcript = event.results[event.results.length-1][0].transcript.trim().toLowerCase();
        this.lastCommand = transcript;
        this.onResult && this.onResult(transcript);
        for (const cmd of Object.keys(this.grammar)) {
          if (this.grammar[cmd].includes(transcript)) {
            this.onCommand && this.onCommand(cmd, transcript);
            break;
          }
        }
      };
      this.recognition.onerror = (e) => { this.active = false; };
      this.recognition.onend = () => { if (this.active) this.recognition.start(); };
    }
    start() { if (this.recognition && !this.active) { this.active = true; this.recognition.start(); } }
    stop() { if (this.recognition && this.active) { this.active = false; this.recognition.stop(); } }
  }
  window.voiceCommands = {
    NAV_NEXT: ["next question", "go next", "next"],
    NAV_PREV: ["previous question", "go back", "previous"],
    SUBMIT: ["submit exam", "submit", "finish exam", "finish"],
    READ: ["read aloud", "read question", "repeat question", "say the question again", "read it", "repeat it"],
    CONFIRM: ["yes", "ok", "submit", "confirm"],
    CANCEL: ["no", "cancel", "don't submit", "do not submit"]
  };
  window.voiceService = new VoiceCommandService(window.voiceCommands);
  
  // Integration HUD
  function showHud(msg) {
    let hud = document.getElementById('voice-hud');
    if (!hud) {
      hud = document.createElement('div');
      hud.id = 'voice-hud';
      hud.style.position = 'fixed';
      hud.style.bottom = '80px';
      hud.style.right = '32px';
      hud.style.background = '#222';
      hud.style.color = '#fff';
      hud.style.padding = '12px 24px';
      hud.style.borderRadius = '8px';
      hud.style.zIndex = '9999';
      hud.style.fontSize = '1.1rem';
      document.body.appendChild(hud);
    }
    hud.textContent = msg;
    hud.style.display = 'block';
    setTimeout(() => { hud.style.display = 'none'; }, 2000);
  }
  
  // Proctoring event emitter
  function emitProctorEvent(type, detail) {
    fetch('/api/proctoring/event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event_type: type, detail, event_ts: Date.now() })
    });
  }
  
  function renderQuestion(){
    const q = exam.questions[currentIndex];
    const container = document.getElementById('question-container');
    const ans = exam.answers[q.id] || {};
    let html = `<div class="question">
      <div class="q-number">Question ${currentIndex+1} of ${exam.questions.length}</div>
      <div class="q-text">${q.question_text}</div>`;
    if (q.question_type === 'MCQ' && q.options) {
      html += '<div class="options">';
      Object.keys(q.options).forEach(key => {
        const label = q.options[key];
        const checked = (ans.selected_option || '').toUpperCase() === key ? 'checked' : '';
        html += `<label class="option"><input type="radio" name="mcq" value="${key}" ${checked}> ${key}. ${label}</label>`;
      });
      html += '</div>';
    } else {
      const text = ans.answer_text || '';
      html += `<div style="display:flex;align-items:center;gap:8px;"><textarea class="answer-input" id="answer-input-${q.id}" data-qid="${q.id}" placeholder="Type your answer here...">${text}</textarea><button id="speaker-btn" title="Read aloud" style="background:none;border:none;cursor:pointer;font-size:1.5rem;">🔊</button></div>`;
    }
    html += '</div>';
    container.innerHTML = html;
    // Autofocus descriptive answer box for dictation
    if (q.question_type !== 'MCQ') {
      const ta = document.getElementById(`answer-input-${q.id}`);
      if (ta) ta.focus();
      const speakerBtn = document.getElementById('speaker-btn');
      if (speakerBtn) speakerBtn.onclick = () => { window.ttsService.cancel(); readCurrentQuestion(); showHud('Reading current question aloud...'); emitProctorEvent('voice_command', {command:'read', rawText:'speaker button'}); };
    }
    // Add mark for review button state
    document.getElementById('mark-review').textContent = markedForReview[q.id] ? 'Unmark Review' : 'Mark for Review';
    renderNavPanel();
    // Automatically read aloud the question when rendered
    window.ttsService.cancel();
    readCurrentQuestion();
  }

  function renderNavPanel() {
    const nav = document.getElementById('nav-panel');
    nav.innerHTML = '';
    exam.questions.forEach((q, idx) => {
      const ans = exam.answers[q.id] || {};
      let status = 'unanswered';
      if (markedForReview[q.id]) status = 'review';
      else if (q.question_type === 'MCQ' ? ans.selected_option : ans.answer_text) status = 'answered';
      const btn = document.createElement('button');
      btn.className = `nav-btn ${status}`;
      btn.textContent = idx + 1;
      btn.onclick = () => {
        collectCurrentAnswer();
        currentIndex = idx;
        renderQuestion();
        renderNavPanel();
      };
      nav.appendChild(btn);
    });
    // Highlight current question
    Array.from(document.getElementsByClassName('nav-btn')).forEach((btn, idx) => {
      btn.style.border = (idx === currentIndex) ? '2px solid #007bff' : '';
    });
  }
  class ProctoringService {
    constructor(examId, chunkInterval = 10000) {
        this.examId = examId;
        this.chunkInterval = chunkInterval;
        this.mediaRecorder = null;
        this.stream = null;
        this.chunkOrder = 0;
        this.isRecording = false;
    }

    async start() {
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
            this.mediaRecorder = new MediaRecorder(this.stream, { mimeType: 'video/webm' });

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.uploadChunk(event.data);
                }
            };

            this.mediaRecorder.onstop = () => {
                if (this.isRecording) {
                    this.stop();
                }
            };

            this.mediaRecorder.start(this.chunkInterval);
            this.isRecording = true;
            console.log('Proctoring recording started.');
        } catch (error) {
            console.error('Error starting proctoring service:', error);
            emitProctorEvent('proctoring_error', { message: 'Failed to start video recording.' });
        }
    }

    stop() {
        if (this.mediaRecorder && this.isRecording) {
            this.mediaRecorder.stop();
            this.isRecording = false;
        }
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
        }
        console.log('Proctoring recording stopped.');
    }

    async uploadChunk(chunk) {
        const formData = new FormData();
        formData.append('exam_id', this.examId);
        formData.append('chunk_order', this.chunkOrder++);
        formData.append('video_chunk', chunk, `chunk_${this.chunkOrder}.webm`);

        try {
            const response = await fetch('/proctoring/chunk', {
                method: 'POST',
                body: formData
            });
            if (!response.ok) {
                console.error('Failed to upload video chunk.');
                emitProctorEvent('proctoring_error', { message: 'Failed to upload video chunk.' });
            }
        } catch (error) {
            console.error('Error uploading video chunk:', error);
            emitProctorEvent('proctoring_error', { message: 'Network error while uploading video chunk.' });
        }
    }
}
  function loadExam(){
    // exam data injected via template into #exam-data script tag
    const dataScript = document.getElementById('exam-data');
    let examData = null;
    try {
      examData = JSON.parse(dataScript.textContent);
    } catch (e) {
      document.getElementById('question-container').innerHTML = '<div style="color:red;font-weight:bold;">Error: Exam data is corrupted or missing.</div>';
      return;
    }
    if (!examData || !examData.questions || examData.questions.length === 0) {
      document.getElementById('question-container').innerHTML = '<div style="color:red;font-weight:bold;">No questions found for this exam. Please contact your teacher.</div>';
      return;
    }
    exam = examData;
    document.getElementById('exam-title').textContent = exam.title;
    // Timer setup
    const durationMs = exam.duration * 60 * 1000;
    endTime = Date.now() + durationMs;
    updateTimer();
    timerInterval = setInterval(updateTimer, 1000);
    renderQuestion();
    renderNavPanel();

    // Start proctoring
    window.proctoringService = new ProctoringService(exam.id);
    window.proctoringService.start();
  }

  function updateTimer(){
    const left = Math.max(0, endTime - Date.now());
    const totalSec = Math.floor(left/1000);
    const mm = String(Math.floor(totalSec/60)).padStart(2,'0');
    const ss = String(totalSec%60).padStart(2,'0');
    document.getElementById('time').textContent = `${mm}:${ss}`;
    if (left <= 0) {
      clearInterval(timerInterval);
      submitExam();
    }
  }

  function collectCurrentAnswer(){
    const q = exam.questions[currentIndex];
    if (q.question_type === 'MCQ'){
      const sel = document.querySelector('input[name="mcq"]:checked');
      const value = sel ? sel.value.toUpperCase() : null;
      exam.answers[q.id] = exam.answers[q.id] || {};
      exam.answers[q.id].selected_option = value;
    } else {
      const ta = document.getElementById(`answer-input-${q.id}`);
      exam.answers[q.id] = exam.answers[q.id] || {};
      exam.answers[q.id].answer_text = ta ? ta.value : '';
    }
  }

  function goToNextQuestion(){
    collectCurrentAnswer();
    if (window.VoiceControl) { window.VoiceControl.stopRecording(); }
    if (currentIndex < exam.questions.length - 1) {
      currentIndex++;
      renderQuestion();
      // Question will be read aloud automatically by renderQuestion
    }
  }

  function goToPreviousQuestion(){
    collectCurrentAnswer();
    if (currentIndex > 0) {
      currentIndex--;
      renderQuestion();
      // Question will be read aloud automatically by renderQuestion
    }
  }

  async function autosave(){
    try{
      collectCurrentAnswer();
      const answers = Object.keys(exam.answers).map(qid => ({
        question_id: Number(qid),
        answer_text: exam.answers[qid].answer_text,
        selected_option: exam.answers[qid].selected_option
      }));
      const res = await fetch('/autosave', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ exam_id: exam.id, answers })
      });
      const data = await res.json();
      if (data && data.success) showToast('Progress saved ✅');
    }catch(e){ /* ignore */ }
  }

  async function submitExam(){
    if (window.proctoringService) {
        window.proctoringService.stop();
    }
    collectCurrentAnswer();
    await autosave();
    try{
      const res = await fetch(`/submit_exam/${exam.id}`, { method: 'POST' });
      const data = await res.json();
      if (data.success){
        if (window.ttsSpeak) window.ttsSpeak('Exam submitted successfully');
        window.location.href = data.redirect;
      } else {
        showToast(data.message||'Submit failed', true);
      }
    }catch(e){
      showToast('Network error on submit', true);
    }
  }

  function readCurrentQuestion(){
    const q = exam.questions[currentIndex];
    const text = `Question ${currentIndex+1}. ${q.question_text}`;
    window.ttsSpeak && window.ttsSpeak(text);
  }

  function showToast(msg, err){
    const t = document.createElement('div');
    t.className = 'toast' + (err?' toast-error':'');
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(()=>{ t.classList.add('show'); }, 10);
    setTimeout(()=>{ t.classList.remove('show'); t.remove(); }, 2000);
  }

  document.addEventListener('DOMContentLoaded', function(){
    if (!document.getElementById('exam-data')) return;
    loadExam();

    document.getElementById('next-question').addEventListener('click', goToNextQuestion);
    document.getElementById('prev-question').addEventListener('click', goToPreviousQuestion);
    document.getElementById('mark-review').addEventListener('click', function(){
      const q = exam.questions[currentIndex];
      markedForReview[q.id] = !markedForReview[q.id];
      renderNavPanel();
      renderQuestion();
    });
    document.getElementById('submit-exam').addEventListener('click', function(){
      if (confirm('Are you sure you want to submit?')) submitExam();
    });

    // When focusing textarea, make it class answer-input so dictation targets it
    document.addEventListener('focusin', function(e){
      if (e.target && e.target.id === 'answer-input') e.target.classList.add('answer-input');
    });

    setInterval(autosave, 30000); // 30s autosave

    window.voiceService.onCommand = (cmd, raw) => {
      if (["MCQ_A","MCQ_B","MCQ_C","MCQ_D"].includes(cmd)) {
        // Only act if current question is MCQ
        const q = exam.questions[currentIndex];
        if (q.question_type === 'MCQ' && q.options) {
          let opt = cmd.slice(-1); // 'A', 'B', 'C', 'D'
          let radio = document.querySelector(`input[name='mcq'][value='${opt}']`);
          if (radio) {
            radio.checked = true;
            exam.answers[q.id] = exam.answers[q.id] || {};
            exam.answers[q.id].selected_option = opt;
            showHud(`Selected option ${opt} by voice command.`);
            emitProctorEvent('voice_command', {command:`option_${opt.toLowerCase()}`, rawText:raw});
          }
        }
      }
    };
  });

  // Expose for voice.js
  window.goToNextQuestion = goToNextQuestion;
  window.goToPreviousQuestion = goToPreviousQuestion;
  window.readCurrentQuestion = readCurrentQuestion;
  window.submitExam = submitExam;
  window.getCurrentQuestionId = function() {
    return exam && exam.questions && exam.questions[currentIndex] ? exam.questions[currentIndex].id : null;
  };
})();