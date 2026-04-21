import os
from dotenv import load_dotenv
import requests

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")

models = [
    "llama3-70b-8192", 
    "llama3-8b-8192", 
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "mixtral-8x7b-32768"
]

for m in models:
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": m,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 10
        }
    )
    if resp.status_code == 200:
        lim_tpm = resp.headers.get("x-ratelimit-limit-tokens")
        rem_tpm = resp.headers.get("x-ratelimit-remaining-tokens")
        lim_tpd = resp.headers.get("x-ratelimit-limit-tokens") # wait, TPD might be in different header
        # Let's just print all x-rate headers
        print(f"Model {m} OK:")
        for k, v in resp.headers.items():
            if 'ratelimit' in k.lower():
                print(f"  {k}: {v}")
    else:
        print(f"Model {m} Failed: {resp.status_code} - {resp.text[:100]}")
