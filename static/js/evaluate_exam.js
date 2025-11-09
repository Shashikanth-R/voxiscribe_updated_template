document.addEventListener('DOMContentLoaded', () => {
    const plagiarismButtons = document.querySelectorAll('.plagiarism-btn');
    const finishButtons = document.querySelectorAll('.finish-eval-btn');
    const markInputs = document.querySelectorAll('.mark-input');

    plagiarismButtons.forEach(button => {
        button.addEventListener('click', async (event) => {
            const questionBox = event.target.closest('.question-box');
            const studentBox = event.target.closest('.student-eval-box');
            const studentId = studentBox.dataset.studentId;
            const questionId = questionBox.dataset.questionId;
            const answerText = questionBox.querySelector('.answer-text').textContent;
            const resultSpan = questionBox.querySelector('.plagiarism-result');

            resultSpan.textContent = 'Checking...';

            try {
                const response = await fetch('/plagiarism_check', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ text: answerText })
                });

                const data = await response.json();

                if (data.success) {
                    resultSpan.textContent = `Plagiarism: ${data.plagiarism_percentage.toFixed(2)}%`;
                } else {
                    resultSpan.textContent = 'Error checking plagiarism.';
                }
            } catch (error) {
                resultSpan.textContent = 'Error checking plagiarism.';
            }
        });
    });

    finishButtons.forEach(button => {
        button.addEventListener('click', async (event) => {
            const studentBox = event.target.closest('.student-eval-box');
            const studentId = studentBox.dataset.studentId;
            const examId = window.location.pathname.split('/').pop();
            const questionBoxes = studentBox.querySelectorAll('.question-box');

            const grades = [];
            questionBoxes.forEach(box => {
                const questionId = box.dataset.questionId;
                const markInput = box.querySelector('.mark-input');
                if (markInput) {
                    const score = parseFloat(markInput.value);
                    if (!isNaN(score)) {
                        grades.push({ student_id: studentId, question_id: questionId, score: score });
                    }
                }
            });

            try {
                const response = await fetch(`/grade/${examId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ grades: grades })
                });

                const data = await response.json();

                if (data.success) {
                    alert('Evaluation finished successfully!');
                } else {
                    alert('Error finishing evaluation.');
                }
            } catch (error) {
                alert('Error finishing evaluation.');
            }
        });
    });

    markInputs.forEach(input => {
        input.addEventListener('input', (event) => {
            const studentBox = event.target.closest('.student-eval-box');
            const scoreValue = studentBox.querySelector('.score-value');
            const allMarkInputs = studentBox.querySelectorAll('.mark-input');
            let totalScore = 0;
            allMarkInputs.forEach(inp => {
                const score = parseFloat(inp.value);
                if (!isNaN(score)) {
                    totalScore += score;
                }
            });
            scoreValue.textContent = totalScore.toFixed(2);
        });
    });
});