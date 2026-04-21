# Test Case Automator — Setup Guide

> **Generate QA test cases from Jira tickets & Confluence pages in seconds, using AI.**
> Powered by Groq LLM + Selenium · Built for local use only.

---

## 📋 Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11 or 3.12 | Download from [python.org](https://www.python.org/downloads/) |
| Microsoft Edge | Any recent version | Built-in on Windows 10/11 |
| Groq API Key | Free | Sign up at [console.groq.com](https://console.groq.com) |

---

## 🚀 First-Time Setup

### Step 1 — Clone or extract the project

Place the project folder anywhere on your machine, e.g.:
```
C:\Tools\TestCaseAutomator\
```

### Step 2 — Create a virtual environment

Open **Command Prompt** or **PowerShell** inside the project folder:

```cmd
python -m venv .venv
```

### Step 3 — Install dependencies

```cmd
.venv\Scripts\activate
pip install -r requirements.txt
```

### Step 4 — Configure your API key

Copy the sample environment file and fill in your key:

```cmd
copy .env.example .env
```

Then open `.env` and set:

```env
GROQ_API_KEY=your_groq_api_key_here
LLM_PROVIDER=groq
```

> **Where to get a free Groq API key?**
> 1. Go to [console.groq.com](https://console.groq.com)
> 2. Sign up (free, no credit card needed)
> 3. Navigate to **API Keys** → Create key
> 4. Paste it into `.env`

---

## ▶️ Running the Application

### Every time you use the app — Two steps:

#### Step A — Launch Edge with remote debugging

Double-click **`start_edge.bat`**

This opens a special Edge window that allows Selenium to read your logged-in sessions.

```
⚠️  Use ONLY this Edge window for Jira/Confluence.
    Do NOT log out of or close this window while using the app.
```

1. Wait for Edge to open
2. Log into **Atlassian Jira** at your organisation's URL
3. Log into **Confluence** if you'll be using that
4. Leave this Edge window open in the background

#### Step B — Launch the app

Double-click **`run_app.bat`**

Your browser will open automatically at `http://localhost:5000`.

---

## 📖 Using the App

### Test Cases Page (`/`)

| Feature | How to use |
|---|---|
| **Generate from Jira** | Paste a Jira ticket URL + CSS selector → click Generate |
| **Generate from Confluence** | Paste a Confluence page URL → click Generate (no selector needed) |
| **Live Logs** | Watch the progress terminal as your test cases are generated |
| **Download Excel** | Click the green Download button that appears after success |

**Default CSS selector for Jira tickets:**
```
[data-testid='issue.views.field.rich-text.description']
```

### Summary Page (`/summary`)

Analyses any Jira ticket or Confluence page and produces:
- **Requirement Overview** — plain-language summary
- **Key Features** — bullet list of features being implemented
- **Scope** — what is in/out of scope
- **Testing Dependencies** — systems, APIs, devices needed for testing

### Output Files

All generated Excel files are saved to:
```
C:\Users\<YourName>\Documents\TestCaseAutomator\
```

| File | Contents |
|---|---|
| `test_cases.xlsx` | Generated test cases (appended per run) |
| `summary_requirements.xlsx` | Requirement summaries and dependency tables |

---

## 🔧 Debugging & Development

If you need to troubleshoot or extend the application, you can use these standalone scripts:

- `debug_browser.py`: Verifies the Selenium connection to Edge.
- `test_groq.py`: Tests the AI API key and response parsing.
- `test_chunking.py`: Validates text splitting for large pages.
- `test_e2e.py`: Runs a full scraping-to-excel flow via CLI.

---

## 📦 Building the .exe (Optional)

To create a standalone executable that runs without Python installed:

```cmd
build_exe.bat
```

The output will be at `dist\TestCaseAutomator.exe`.

**Before distributing the .exe:**
1. Place your `.env` file **in the same folder** as `TestCaseAutomator.exe`
2. Users still need to run `start_edge.bat` before launching the `.exe`

---

## 🔧 Troubleshooting

### "Edge not found" error
Run `where msedge` in Command Prompt to find the correct path, then update `start_edge.bat`.

### "Failed to connect to Edge" / Selenium errors
- Make sure `start_edge.bat` is running and Edge opened successfully
- Ensure you're logged into Jira/Confluence in that Edge window
- Check that no firewall is blocking port 9222

### "Invalid API key" / LLM errors
- Re-check your `GROQ_API_KEY` in the `.env` file
- Verify the key is active at [console.groq.com](https://console.groq.com)
- Make sure `LLM_PROVIDER=groq` is set (not `openai`)

### "Port 5000 already in use"
Another process is using port 5000. Either close it or change the port in `app.py`:
```python
app.run(port=5001, ...)  # pick any free port
```

### Excel file is locked / Can't save
Close `test_cases.xlsx` or `summary_requirements.xlsx` in Excel before generating new test cases.

---

## 🗂️ Project Structure

```
TestCaseAutomator/
├── app.py                  # Flask web server + API routes
├── launcher.py             # Desktop app launcher (starts Flask + opens browser)
├── config.py               # Configuration (API keys, paths, model settings)
├── scraper.py              # Jira page scraper (Selenium + BeautifulSoup)
├── confluence_scraper.py   # Confluence page scraper
├── prompt_template.py      # LLM prompts for test case generation
├── summary_prompt.py       # LLM prompts for requirement summarisation
├── parser.py               # JSON → Excel row parser
├── excel_handler.py        # openpyxl workbook writer
│
├── templates/
│   ├── index.html          # Test Cases dashboard
│   └── summary.html        # Requirement Summary page
│
├── static/
│   ├── style.css           # Glassmorphism light theme
│   ├── script.js           # Test Cases page logic
│   └── summary.js          # Summary page logic
│
├── start_edge.bat          # Launch Edge with remote debugging
├── run_app.bat             # Launch the app (dev mode)
├── build_exe.bat           # Build standalone .exe with PyInstaller
├── requirements.txt        # Python dependencies
├── .env                    # Your API keys (not committed to git)
│
├── debug_browser.py        # Edge connectivity test
├── test_chunking.py        # Text processing test
├── test_groq.py            # AI connectivity test
└── test_e2e.py            # End-to-end CLI test
```

---

## 📬 Notes

- This app is **strictly local** — no data is sent anywhere except to the Groq API for LLM inference
- Groq's free tier is sufficient for typical test case volumes
- The app connects to your **existing** logged-in browser session via Selenium remote debugging
- No username/password is ever handled by this app
