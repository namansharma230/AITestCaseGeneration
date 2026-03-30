# Test Case Automator 🤖

Automatically scrape Jira (or any web page) requirement sections and generate comprehensive QA test cases using AI — all exported to a formatted Excel workbook.

---

## How It Works

```
Your Jira Ticket URL
        │
        ▼
 Edge Browser (Selenium)
 → Reads the requirement text
        │
        ▼
 AI Model (Groq or OpenAI)
 → Generates 5–10 test cases
        │
        ▼
 Excel File (test_cases.xlsx)
 → Saves Test Case ID, Title, Steps, Expected Result, Priority...
```

---

## What You Need Before Starting

| Requirement | Why |
|---|---|
| Windows PC | Script is configured for Microsoft Edge on Windows |
| Python 3.10 or higher | The language the tool is built in |
| Microsoft Edge browser | Already installed on most Windows machines |
| Groq API key (free) | The AI that generates test cases — no credit card needed |
| Access to your Jira | To scrape requirement text |

---

## Step 1 — Install Python

1. Open https://python.org/downloads
2. Download the latest Python 3.x installer
3. Run the installer — **tick "Add Python to PATH"** before clicking Install
4. Verify it worked — open Command Prompt and type:
   ```
   python --version
   ```
   You should see something like `Python 3.11.x`

---

## Step 2 — Download the Project Files

Download all these files into **one folder** on your Desktop, for example:
```
C:\Users\YourName\Desktop\TestCaseAutomation\
```

Make sure you have all of these:
```
TestCaseAutomation/
├── main.py
├── scraper.py
├── prompt_template.py
├── parser.py
├── excel_handler.py
├── config.py
├── requirements.txt
└── .env              ← you will create this in Step 4
```

---

## Step 3 — Set Up a Virtual Environment

A virtual environment keeps this project's dependencies separate from the rest of your system.

Open **Command Prompt**, navigate to your project folder, and run:

```cmd
cd C:\Users\YourName\Desktop\TestCaseAutomation

python -m venv .venv

.venv\Scripts\activate
```

You will see `(.venv)` at the start of your command prompt — this means the virtual environment is active.

> ⚠️ **Every time you open a new Command Prompt window**, you must run `.venv\Scripts\activate` again before running the script.

Then install all dependencies:

```cmd
pip install -r requirements.txt
```

---

## Step 4 — Get a Free Groq API Key

Groq is free and requires no credit card.

1. Go to **https://console.groq.com**
2. Click **Sign Up** and create a free account
3. After logging in, go to **API Keys** in the left menu
4. Click **Create API Key**
5. Copy the key — it starts with `gsk_...`

---

## Step 5 — Create Your `.env` File

In your project folder, create a new file called exactly **`.env`** (no other extension).

> In Windows, open Notepad, paste the content below, then go to **File → Save As**, set "Save as type" to **All Files**, and name it `.env`

Paste this into the file:

```
GROQ_API_KEY=gsk_paste_your_groq_key_here
LLM_PROVIDER=groq
EXCEL_FILE_PATH=test_cases.xlsx
```

Replace `gsk_paste_your_groq_key_here` with the key you copied in Step 4.

**No quotes around any of the values.** It should look exactly like:
```
GROQ_API_KEY=gsk_abc123xyz...
LLM_PROVIDER=groq
EXCEL_FILE_PATH=test_cases.xlsx
```

---

## Step 6 — Set Up Edge for Jira (One-Time Login)

Because Jira requires you to be logged in, we launch Edge in a special mode that lets the script reuse your login session. You only need to do this once.

**Run this command in Command Prompt** (copy the whole thing):

```cmd
"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="C:\EdgeDebug"
```

> If Edge is installed somewhere else, find it by typing `where msedge` in Command Prompt.

An Edge window will open. In that window:
1. Go to `https://astrogo.atlassian.net`
2. Log in to Jira as normal
3. **Leave this Edge window open** — do not close it

The script will automatically connect to this window every time you run it.

---

## Step 7 — Run the Tool

With your virtual environment active and the Edge window open, run:

```cmd
python main.py <JIRA_URL> "<SELECTOR>"
```

**Example:**
```cmd
python main.py https://astrogo.atlassian.net/browse/ALTV-551 "[data-testid='issue.views.field.rich-text.description']"
```

The selector `[data-testid='issue.views.field.rich-text.description']` works for most Jira Cloud tickets. If it doesn't work for a specific ticket, see the Troubleshooting section below.

---

## What Happens When You Run It

You will see logs like this — everything is working if you see all 4 steps:

```
✓ Connected to existing Edge session.         ← Jira login reused
✓ 1 element(s) found using: [data-testid=...] ← Requirement text found
LLM call attempt 1/3 (provider: groq)         ← AI generating test cases
Saved 8 row(s) to 'test_cases.xlsx'           ← Written to Excel ✅
```

Open `test_cases.xlsx` in your project folder to see the results.

---

## Excel Output

| Column | What It Contains |
|---|---|
| A — Test Case ID | Auto-generated unique ID (e.g. TC-3A7F2D1B) |
| B — Title | Short description of the test case |
| C — Preconditions | What needs to be set up before running the test |
| D — Steps | Numbered step-by-step instructions |
| E — Expected Result | What should happen if the feature works correctly |
| F — Postconditions | Cleanup or follow-up checks |
| G — Priority | High / Medium / Low |

Each run **appends** new rows — it never overwrites existing test cases.

---

## Running in Batch Mode (Multiple Tickets at Once)

Create a file called `batch.csv` in your project folder:

```csv
url,selector
https://astrogo.atlassian.net/browse/ALTV-551,[data-testid='issue.views.field.rich-text.description']
https://astrogo.atlassian.net/browse/ALTV-552,[data-testid='issue.views.field.rich-text.description']
https://astrogo.atlassian.net/browse/ALTV-553,[data-testid='issue.views.field.rich-text.description']
```

Then run:
```cmd
python main.py --batch batch.csv
```

All test cases from all tickets will be appended to the same Excel file.

---

## Switching to OpenAI (When You Add Billing)

When you are ready to use OpenAI instead of Groq, just update your `.env` file:

```
OPENAI_API_KEY=sk-proj-your-openai-key-here
LLM_PROVIDER=openai
EXCEL_FILE_PATH=test_cases.xlsx
```

No code changes needed.

---

## Troubleshooting

### ❌ "No existing Edge on port 9222"
The debug Edge window is not open. Run the Step 6 command again to launch it, log in to Jira, and leave it open.

### ❌ "Selector not found on page"
The selector doesn't match this particular Jira ticket. Run the discover command to see what selectors are available:
```cmd
python main.py --discover https://astrogo.atlassian.net/browse/YOUR-TICKET
```
Pick the selector whose content preview matches the description text of the ticket.

### ❌ "GROQ_API_KEY is not set"
Your `.env` file either doesn't exist, is in the wrong folder, or has quotes around the value. Check that:
- The file is named `.env` (not `.env.txt`)
- It is in the same folder as `main.py`
- There are no quotes: `GROQ_API_KEY=gsk_abc...` ✅ not `GROQ_API_KEY="gsk_abc..."` ❌

To verify the key is loading correctly, run:
```cmd
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(repr(os.getenv('GROQ_API_KEY')))"
```
It should print your key, not `None`.

### ❌ "Cannot save test_cases.xlsx"
The Excel file is currently open in Excel. Close it and run the script again.

### ❌ "ModuleNotFoundError"
Your virtual environment is not active. Run:
```cmd
.venv\Scripts\activate
```
Then try again.

### ❌ Jira redirects to login page
The Edge debug window was closed. Re-run the Step 6 launch command, log back in, and leave the window open.

---

## All Command Reference

```cmd
# Single ticket
python main.py <URL> "<SELECTOR>"

# Single ticket — show browser window (for debugging)
python main.py <URL> "<SELECTOR>" --no-headless

# Batch mode from CSV
python main.py --batch batch.csv

# Discover available selectors on a page
python main.py --discover <URL>

# Save to a custom Excel file
python main.py <URL> "<SELECTOR>" --output C:\Reports\sprint5.xlsx

# More detailed logs
python main.py <URL> "<SELECTOR>" --log-level DEBUG
```

---

## Project File Reference

| File | What It Does |
|---|---|
| `main.py` | Entry point — handles the CLI commands |
| `scraper.py` | Opens Edge and reads the Jira ticket |
| `prompt_template.py` | Sends text to the AI and gets test cases back |
| `parser.py` | Converts AI response into Excel rows |
| `excel_handler.py` | Writes rows to the Excel file |
| `config.py` | All settings — model, columns, prompt template |
| `.env` | Your secret keys — never share this file |
| `requirements.txt` | List of Python packages needed |