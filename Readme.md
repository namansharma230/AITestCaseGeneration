# Test Case Automator 🤖

AI-powered tool that reads Jira tickets and Confluence pages and automatically generates comprehensive QA test cases — exported to a formatted Excel workbook. Includes a browser-based dashboard with live logs.

---

## How It Works

```
Your Jira Ticket URL  ──or──  Confluence Page URL
              │
              ▼
   Edge Browser (Selenium)
   → Opens the page using your existing login session
   → Reads the requirement / description text
              │
              ▼
   AI Model (Groq — free)
   → Generates 5–10 structured test cases
              │
              ▼
   Excel File (test_cases.xlsx)
   → Saves to Documents\TestCaseAutomator\
   → Columns: ID · Title · Steps · Expected Result · Priority…
```

---

## What You Need Before Starting

| Requirement | Details |
|---|---|
| Windows PC | The tool is built and tested on Windows 10/11 |
| Python 3.10 or higher | The programming language the tool runs on |
| Microsoft Edge browser | Pre-installed on all modern Windows machines |
| Groq API key (free) | Powers the AI — no credit card required |
| Jira / Confluence access | Your normal browser login is reused |

---

## Step 1 — Install Python

1. Go to **https://www.python.org/downloads**
2. Click **Download Python 3.x.x** (latest stable)
3. Run the installer
4. ✅ **Tick "Add Python to PATH"** at the bottom of the installer — this is essential
5. Click **Install Now**

**Verify it worked** — open **Command Prompt** (`Win + R` → type `cmd` → Enter) and run:

```cmd
python --version
```

You should see something like `Python 3.12.3`. If you see an error, restart your PC and try again.

---

## Step 2 — Get the Project Files

Copy the entire `TestcaseautomationApp` folder to your machine. The recommended location is your Desktop:

```
C:\Users\YourName\Desktop\TestcaseautomationApp\
```

Make sure the folder contains all these files:

```
TestcaseautomationApp/
├── app.py                  ← Flask web server (the dashboard)
├── launcher.py             ← Opens the browser automatically
├── main.py                 ← Command-line entry point
├── scraper.py              ← Reads Jira page content via Edge
├── confluence_scraper.py   ← Reads Confluence page content
├── prompt_template.py      ← Sends text to AI, gets test cases
├── summary_prompt.py       ← AI prompt for requirement summary
├── parser.py               ← Converts AI JSON into Excel rows
├── excel_handler.py        ← Writes rows to Excel
├── config.py               ← Central settings (selector, model, etc.)
├── requirements.txt        ← Python package list
├── run_app.bat             ← Double-click to launch the dashboard
├── start_edge.bat          ← Double-click to open Edge for Jira login
├── templates/
│   ├── index.html          ← Dashboard main page
│   └── summary.html        ← Requirement summary page
└── static/
    ├── style.css
    ├── script.js
    └── summary.js
```

> ⚠️ You will create the `.env` file yourself in Step 5.

---

## Step 3 — Open a Command Prompt in the Project Folder

1. Open **File Explorer** and navigate to the `TestcaseautomationApp` folder
2. Click on the address bar at the top, type `cmd`, and press **Enter**

A Command Prompt will open already pointing to the right folder. You should see something like:

```
C:\Users\YourName\Desktop\TestcaseautomationApp>
```

Keep this window open for the next steps.

---

## Step 4 — Create a Virtual Environment

A virtual environment keeps this project's packages separate from the rest of your PC.

In the Command Prompt from Step 3, run these **one at a time**:

```cmd
python -m venv .venv
```

```cmd
.venv\Scripts\activate
```

You will see `(.venv)` appear at the start of your prompt — this means it is active:

```
(.venv) C:\Users\YourName\Desktop\TestcaseautomationApp>
```

> ⚠️ **Every time you open a new Command Prompt window**, you must run `.venv\Scripts\activate` again before running any Python commands.

Now install all required packages:

```cmd
pip install -r requirements.txt
```

This may take 1–2 minutes. You will see packages being downloaded and installed. Wait until your prompt returns before continuing.

---

## Step 5 — Get a Free Groq API Key

Groq is the AI provider. It is **completely free** and requires no credit card.

1. Go to **https://console.groq.com**
2. Click **Sign Up** and create a free account (you can use Google or GitHub)
3. Once logged in, click **API Keys** in the left sidebar
4. Click **Create API Key**, give it any name (e.g. `test-automator`)
5. **Copy the key** — it starts with `gsk_...`
   
> ⚠️ You only get to see the key once. Copy it now before closing the dialog.

---

## Step 6 — Create Your `.env` File

This file stores your secret API key. It must be created manually.

**Method A — Using Notepad:**

1. Open Notepad
2. Paste the following:

```
GROQ_API_KEY=gsk_paste_your_key_here
LLM_PROVIDER=groq
EXCEL_FILE_PATH=test_cases.xlsx
```

3. Replace `gsk_paste_your_key_here` with the key you copied in Step 5
4. Go to **File → Save As**
5. Navigate to your `TestcaseautomationApp` folder
6. Set **Save as type** to **All Files (\*.\*)**
7. Set the filename to `.env` (with a dot at the start, no other extension)
8. Click **Save**

**Sample `.env` file (your key will be different):**

```
GROQ_API_KEY=gsk_abc123xyz456def789...
LLM_PROVIDER=groq
EXCEL_FILE_PATH=test_cases.xlsx
```

**Rules:**
- ❌ No quotes around values — `GROQ_API_KEY=gsk_abc...` ✅ not `GROQ_API_KEY="gsk_abc..."` ❌
- ❌ No spaces around `=`
- ✅ The file must be named exactly `.env` and saved inside the `TestcaseautomationApp` folder

**Verify the key is loading correctly** (optional):

```cmd
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(repr(os.getenv('GROQ_API_KEY')))"
```

It should print your key. If it prints `None`, the file is in the wrong location or named incorrectly.

---

## Step 7 — Set Up Edge for Jira Login (One-Time)

The tool reuses your existing Jira login by connecting to a special Edge window. You only need to set this up once per session.

**Double-click `start_edge.bat`** in the project folder.

A new Edge window will open. In that window:

1. Go to `https://astrogo.atlassian.net`
2. Log in to Jira with your normal credentials
3. ✅ **Leave this Edge window open** — do not close it while using the tool

> The tool will automatically connect to this window every time you run it, reusing your login session without asking you to log in again.

---

## Step 8 — Launch the Dashboard

**Double-click `run_app.bat`** in the project folder.

A terminal window will appear, and your browser will automatically open at:

```
http://localhost:5000
```

> ⚠️ Keep the terminal window open while using the app. Closing it stops the server.

You will see the dashboard with two sections:
- **🔗 Generate from Jira Ticket** — paste a Jira URL and generate test cases
- **📄 Generate from Confluence Page** — paste a Confluence URL and generate test cases

---

## Using the Dashboard

### Generate Test Cases from Jira

1. In the **Generate from Jira Ticket** section, paste a Jira ticket URL:
   ```
   https://astrogo.atlassian.net/browse/ALTV-551
   ```
2. Click **🚀 Generate from Jira**
3. Watch the live logs — you will see: Scraping → AI Generating → Parsing → Writing Excel
4. When complete, click **⬇ Download Excel** to save the file

### Generate Test Cases from Confluence

1. In the **Generate from Confluence Page** section, paste a Confluence page URL:
   ```
   https://astrogo.atlassian.net/wiki/spaces/ALC/pages/...
   ```
2. Click **📄 Generate from Confluence**
3. Process runs automatically — no selector needed for Confluence

### Requirement Summary & Analysis (📋 Summary tab)

Click the **📋 Summary** tab in the navigation to switch to the analyser. This page:
- Generates a structured **overview, key features, and scope** from any Jira or Confluence page
- Identifies **testing dependencies** (APIs, services, hardware, etc.)
- Exports everything to a separate Excel file

---

## Output Files

Both files are saved to:
```
C:\Users\YourName\Documents\TestCaseAutomator\
```

| File | Contents |
|---|---|
| `test_cases.xlsx` | All generated test cases, one sheet per Jira ticket |
| `summary_requirements.xlsx` | Requirement summaries and dependency tables |

### Test Cases Excel Columns

| Column | Contents |
|---|---|
| A — Test Case ID | Auto-generated unique ID (e.g. TC-3A7F2D1B) |
| B — Title | Short description of what is being tested |
| C — Preconditions | What must be set up before running the test |
| D — Steps | Numbered step-by-step instructions |
| E — Expected Result | What should happen if the feature works correctly |
| F — Postconditions | Cleanup or follow-up checks |
| G — Priority | High / Medium / Low |

Each run **appends** new rows to the existing file — it never overwrites previous test cases.

---

## Changing the CSS Selector (Advanced)

The tool uses a CSS selector to find the description/requirement text on Jira pages. For ALTV tickets, this is hardcoded to:

```
[data-testid='issue.views.field.rich-text.description']
```

If this ever stops working (e.g. after a Jira update), open `config.py` and update this single line:

```python
JIRA_CSS_SELECTOR: str = "[data-testid='issue.views.field.rich-text.description']"
```

No other files need to be changed.

---

## Switching to OpenAI (Optional)

If you prefer OpenAI (requires a paid account), update your `.env`:

```
OPENAI_API_KEY=sk-proj-your-key-here
LLM_PROVIDER=openai
EXCEL_FILE_PATH=test_cases.xlsx
```

No code changes needed — the switch is automatic.

---

## Troubleshooting

### ❌ "No existing Edge on port 9222"
The debug Edge window is not open. Double-click `start_edge.bat`, log in to Jira in the new window, and leave it open.

### ❌ Jira redirects to a login page
The Edge debug window was closed or the session expired. Close all Edge windows, double-click `start_edge.bat` again, and log back in to Jira.

### ❌ "Selector not found on page"
The Jira page structure may have changed. Open `config.py` and update `JIRA_CSS_SELECTOR`. To discover what selectors are available on a ticket, run in Command Prompt:
```cmd
python main.py --discover https://astrogo.atlassian.net/browse/YOUR-TICKET
```
Pick the selector whose content preview matches the requirement description text.

### ❌ "GROQ_API_KEY is not set" or API authentication error
Your `.env` file is missing, in the wrong folder, or the key is invalid. Check:
- It is named exactly `.env` (not `.env.txt` or `env.txt`)
- It is inside the `TestcaseautomationApp` folder
- There are no quotes around the key value
- The key is not expired — generate a new one at https://console.groq.com if needed

### ❌ "ModuleNotFoundError: No module named 'flask'" (or similar)
The virtual environment is not active. In Command Prompt, run:
```cmd
.venv\Scripts\activate
```
Then try again.

### ❌ "Cannot save / open test_cases.xlsx"
The Excel file is open in Microsoft Excel. Close it and try again.

### ❌ Dashboard shows blank page or can't connect
The Flask server is not running. Double-click `run_app.bat` and wait for the terminal to say the server has started, then refresh the browser.

### ❌ Browser shows old/cached version after an update
Press `Ctrl + Shift + R` in your browser to force a full reload bypassing the cache.

---

## Project File Reference

| File | What It Does |
|---|---|
| `app.py` | Flask web server — all API routes and background job management |
| `launcher.py` | Starts Flask and opens your browser automatically |
| `main.py` | Command-line entry point (for advanced/batch use) |
| `scraper.py` | Opens Edge, navigates to Jira, extracts requirement text |
| `confluence_scraper.py` | Same as above but for Confluence wiki pages |
| `prompt_template.py` | Formats the AI prompt and calls the LLM for test cases |
| `summary_prompt.py` | AI prompt for requirement summary and dependency analysis |
| `parser.py` | Parses AI JSON response into Excel-ready rows |
| `excel_handler.py` | Creates/appends to Excel workbooks |
| `config.py` | All settings — CSS selector, model, output path, API keys |
| `.env` | Your secret keys — **never share or commit this file** |
| `requirements.txt` | Python package dependencies |
| `run_app.bat` | Double-click launcher for the dashboard |
| `start_edge.bat` | Launches Edge with remote debugging for Jira login |
| `templates/` | HTML pages served by Flask |
| `static/` | CSS and JavaScript for the dashboard UI |

---

## Quick Start Checklist

Use this checklist when setting up on a new machine:

- [ ] Python 3.10+ installed with "Add to PATH" ticked
- [ ] Project folder copied to Desktop (or any location)
- [ ] Virtual environment created: `python -m venv .venv`
- [ ] Virtual environment activated: `.venv\Scripts\activate`
- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] Groq API key obtained from https://console.groq.com
- [ ] `.env` file created with `GROQ_API_KEY=gsk_...`
- [ ] `start_edge.bat` run and logged in to Jira in the debug window
- [ ] `run_app.bat` double-clicked and dashboard opened at http://localhost:5000
- [ ] First test case generated ✅