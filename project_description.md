# Testcase Automation Dashboard 🤖

A comprehensive Python-based web application that automates the Quality Assurance (QA) workflow. Using advanced Web Scraping (Selenium) and AI Large Language Models (Groq / OpenAI), the dashboard extracts requirement text from Jira tickets and Confluence wiki pages to automatically generate test cases, summarize requirements, and identify technical dependencies.

---

## 🌟 Core Features

### 1. Automated Test Case Generation
- **Supported Sources:** Jira Tickets and Confluence Pages.
- **AI-Powered:** Uses Groq (Llama-3) or OpenAI to generate 5-10 detailed QA test cases.
- **Structured Output:** Automatically structures test cases with a Title, Preconditions, Steps, Expected Results, Postconditions, and Priority.
- **Excel Export:** Test cases are automatically appended to a formatted `test_cases.xlsx` workbook without overwriting past data.

### 2. Requirement Summary & Dependency Analysis
- **Summarization:** Extracts the core business goals and key features of complex requirement documents.
- **Dependency Mapping:** Intelligently identifies external systems, API dependencies, database interactions, and potential out-of-scope risks.
- **Excel Export:** Saves analysis results to a `summary_requirements.xlsx` workbook.

### 3. Real-Time Web Dashboard
- **Flask Backend:** A lightweight, robust web server (`app.py`) providing a clean, accessible UI.
- **Live Logging (SSE):** Uses Server-Sent Events to stream terminal logs directly to the browser UI, letting users monitor scraping and AI generation in real time.
- **Modern UI:** A polished frontend with modern design aesthetics, ensuring a premium user experience.

---

## 🏗️ Architecture & Tech Stack

- **Backend / Web Server:** Python 3.10+ and Flask.
- **Scraper:** Selenium WebDriver (Microsoft Edge) + BeautifulSoup4. The scraper uses a debugging port to attach to an active browser session, preventing the need for manual Jira/Confluence logins on each run.
- **AI Integration:** Direct integration with LLM Providers via API (Groq API as the default for fast, free generation).
- **Data Persistence:** `openpyxl` for dynamically generating and updating Excel workbooks.
- **Concurrency:** Uses background threading and queue-based log handlers so the main web server remains responsive during long AI or scraping tasks.

---

## 📂 Project Structure

| Component | Description |
|---|---|
| **`app.py`** | The main Flask web server. Handles routing, background job threading, and SSE log streaming. |
| **`config.py`** | Configuration file managing environment variables, LLM prompts, Excel schemas, and logging settings. |
| **`scraper.py & confluence_scraper.py`** | Specialized headless scrapers for pulling out requirement segments from Jira Cloud and long documentation text from Confluence wikis. |
| **`prompt_template.py & summary_prompt.py`** | AI Prompt Templates that manage instructions and payload formatting logic for Test Case generation vs. Summarization. |
| **`excel_handler.py`** | Handles safe reading, writing, and formatting of the output Excel workbooks that export all LLM-analyzed output. |
| **`main.py`** | The legacy Command-Line Interface (CLI) version for running the automator entirely headless via terminal. |
| **`templates/` & `static/`** | The frontend HTML, modern vanilla CSS, and JavaScript responsible for the styling and live dashboard interface. |
