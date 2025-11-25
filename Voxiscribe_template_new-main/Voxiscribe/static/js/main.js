// This file can be used for general purpose JavaScript functions

// Example: Function to fetch and display exams on student dashboard
async function getExams() {
    const response = await fetch('/api/exams');
    const exams = await response.json();

    const examsList = document.getElementById('exams-list');
    examsList.innerHTML = '';

    for (const exam of exams) {
        const listItem = document.createElement('li');
        listItem.innerHTML = `
            <span>${exam.title}</span>
            <a href="/take_exam/${exam.id}">Start Exam</a>
        `;
        examsList.appendChild(listItem);
    }
}

// Example: Function to get and display results
async function getResults() {
    const response = await fetch('/api/results');
    const results = await response.json();

    const resultsContainer = document.getElementById('results-container');
    resultsContainer.innerHTML = '';

    for (const result of results) {
        const resultDiv = document.createElement('div');
        resultDiv.innerHTML = `
            <h3>${result.exam_title}</h3>
            <p>Score: ${result.score}</p>
            <p>Your Answer: ${result.answer_text}</p>
        `;
        resultsContainer.appendChild(resultDiv);
    }
}

// Load exams or results based on the page
if (document.getElementById('exams-list')) {
    getExams();
}

if (document.getElementById('results-container')) {
    getResults();
}