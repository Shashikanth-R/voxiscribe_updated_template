// Exam page logic: render questions, timer, autosave, navigation, submit
(function(){
  let exam = null;
  let currentIndex = 0;
  let timerInterval = null;
  let endTime = null;
  let markedForReview = {};

  function getState(){ return exam; }

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
    console.log('renderQuestion called. Current index:', currentIndex);
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
      if (speakerBtn) speakerBtn.onclick = () => { readCurrentQuestion(); showHud('Reading current question aloud...'); emitProctorEvent('voice_command', {command:'read', rawText:'speaker button'}); };
    }
    // Add mark for review button state
    document.getElementById('mark-review').textContent = markedForReview[q.id] ? 'Unmark Review' : 'Mark for Review';
    renderNavPanel();
    // Automatically read aloud the question when rendered
    readCurrentQuestion();
  }

  function renderNavPanel() {
    console.log('renderNavPanel called.');
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
  function loadExam(){
    console.log('loadExam called.');
    // exam data injected via template into #exam-data script tag
    const dataScript = document.getElementById('exam-data');
    let examData = null;
    try {
      examData = JSON.parse(dataScript.textContent);
    } catch (e) {
      document.getElementById('question-container').innerHTML = '<div style="color:red;font-weight:bold;">Error: Exam data is corrupted or missing.</div>';
      console.error('Error parsing exam data:', e);
      return;
    }
    if (!examData || !examData.questions || examData.questions.length === 0) {
      document.getElementById('question-container').innerHTML = '<div style="color:red;font-weight:bold;">No questions found for this exam. Please contact your teacher.</div>';
      console.warn('No questions found for this exam.');
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
    console.log('Exam loaded:', exam);
  }

  function updateTimer(){
    const left = Math.max(0, endTime - Date.now());
    const totalSec = Math.floor(left/1000);
    const mm = String(Math.floor(totalSec/60)).padStart(2,'0');
    const ss = String(totalSec%60).padStart(2,'0');
    document.getElementById('time').textContent = `${mm}:${ss}`;
    if (left <= 0) {
      clearInterval(timerInterval);
      console.log('Timer ended. Submitting exam.');
      submitExam();
    }
  }

  function collectCurrentAnswer(){
    console.log('collectCurrentAnswer called.');
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
    console.log('Current answer collected for question:', q.id, exam.answers[q.id]);
  }

  function goToNextQuestion(){
    console.log('goToNextQuestion called.');
    collectCurrentAnswer();
    if (window.VoiceControl) { window.VoiceControl.stopRecording(); }
    if (currentIndex < exam.questions.length - 1) {
      currentIndex++;
      renderQuestion();
      // Question will be read aloud automatically by renderQuestion
    }
  }

  function goToPreviousQuestion(){
    console.log('goToPreviousQuestion called.');
    collectCurrentAnswer();
    if (currentIndex > 0) {
      currentIndex--;
      renderQuestion();
      // Question will be read aloud automatically by renderQuestion
    }
  }

  async function autosave(){
    console.log('autosave called.');
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
      console.log('Autosave successful.');
    }catch(e){
      console.error('Autosave failed:', e);
     }
  }

  async function submitExam(){
    console.log('submitExam called.');
    collectCurrentAnswer();
    await autosave();
    try{
      const res = await fetch(`/submit_exam/${exam.id}`, { method: 'POST' });
      const data = await res.json();
      if (data.success){
        if (window.VoiceControl && window.VoiceControl.speak) {
          window.VoiceControl.speak('Exam submitted successfully');
        }
        window.location.href = data.redirect;
        console.log('Exam submitted successfully. Redirecting to:', data.redirect);
      } else {
        showToast(data.message||'Submit failed', true);
        console.error('Exam submission failed:', data.message);
      }
    }catch(e){
      showToast('Network error on submit', true);
      console.error('Network error on submit:', e);
    }
  }

  function readCurrentQuestion(){
    console.log('readCurrentQuestion called.');
    const q = exam.questions[currentIndex];
    const text = `Question ${currentIndex+1}. ${q.question_text}`;
    if (window.VoiceControl && window.VoiceControl.speak) {
        window.VoiceControl.speak(text);
    }
  }

  function toast(msg, err){
    const t = document.createElement('div');
    t.className = 'toast' + (err?' toast-error':'');
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(()=>{ t.classList.add('show'); }, 10);
    setTimeout(()=>{ t.classList.remove('show'); setTimeout(()=>t.remove(), 500); }, 2000);
  }
  window.toast = toast;
  console.log('window.toast exposed.');

  document.addEventListener('DOMContentLoaded', function(){
    console.log('DOMContentLoaded in exam.js');
    if (!document.getElementById('exam-data')) {
      console.warn('No exam-data script tag found.');
      return;
    }
    loadExam();

    document.getElementById('next-question').addEventListener('click', goToNextQuestion);
    console.log('next-question button event listener added.');
    document.getElementById('prev-question').addEventListener('click', goToPreviousQuestion);
    console.log('prev-question button event listener added.');
    document.getElementById('mark-review').addEventListener('click', function(){
      const q = exam.questions[currentIndex];
      markedForReview[q.id] = !markedForReview[q.id];
      renderNavPanel();
      renderQuestion();
      console.log('Mark for review toggled for question:', q.id, 'Status:', markedForReview[q.id]);
    });
    console.log('mark-review button event listener added.');
    document.getElementById('submit-exam').addEventListener('click', function(){
      if (confirm('Are you sure you want to submit?')) submitExam();
      console.log('Submit exam button clicked.');
    });
    console.log('submit-exam button event listener added.');

    // When focusing textarea, make it class answer-input so dictation targets it
    document.addEventListener('focusin', function(e){
      if (e.target && e.target.id === 'answer-input') e.target.classList.add('answer-input');
      console.log('Focusin event on:', e.target.id);
    });

    setInterval(autosave, 30000); // 30s autosave
    console.log('Autosave interval started.');
  });

  // Expose for voice.js
  window.goToNextQuestion = goToNextQuestion;
  window.goToPreviousQuestion = goToPreviousQuestion;
  window.readCurrentQuestion = readCurrentQuestion;
  window.submitExam = submitExam;
  window.getCurrentQuestionId = function() {
    const qid = exam && exam.questions && exam.questions[currentIndex] ? exam.questions[currentIndex].id : null;
    console.log('getCurrentQuestionId called. Returning:', qid);
    return qid;
  };
  console.log('Global functions exposed for voice.js');
})();