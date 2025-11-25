// Exam page logic: render questions, timer, autosave, navigation, submit
(function(){
  let exam = null;
  let currentIndex = 0;
  let timerInterval = null;
  let endTime = null;
  let markedForReview = {};

  function getState(){ return exam; }

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
      html += `<textarea class="answer-input" id="answer-input-${q.id}" data-qid="${q.id}" placeholder="Type your answer here...">${text}</textarea>`;
    }
    html += '</div>';
    container.innerHTML = html;
    // Autofocus descriptive answer box for dictation
    if (q.question_type !== 'MCQ') {
      const ta = document.getElementById(`answer-input-${q.id}`);
      if (ta) ta.focus();
    }
    // Add mark for review button state
    document.getElementById('mark-review').textContent = markedForReview[q.id] ? 'Unmark Review' : 'Mark for Review';
    renderNavPanel();
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
  function loadExam(){
    // exam data injected via template into #exam-data script tag
    const dataScript = document.getElementById('exam-data');
    exam = JSON.parse(dataScript.textContent);

    document.getElementById('exam-title').textContent = exam.title;

    // Timer setup
    const durationMs = exam.duration * 60 * 1000;
    endTime = Date.now() + durationMs;
    updateTimer();
    timerInterval = setInterval(updateTimer, 1000);

    renderQuestion();
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
    }
  }

  function goToPreviousQuestion(){
    collectCurrentAnswer();
    if (currentIndex > 0) {
      currentIndex--;
      renderQuestion();
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