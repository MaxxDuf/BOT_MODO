import os
import json
import threading
import requests
from datetime import datetime

import discord
from flask import Flask
from dotenv import load_dotenv

# =========================
# FLASK (Render keep alive)
# =========================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"

# =========================
# ENV
# =========================

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

SALON_REPORT = 1513274703572373504

SALONS_SURVEILLES = {
    1499033414358142977,
    1500213292403134486
}

JSON_FILE = "toxicite.json"

# =========================
# DISCORD SETUP (IMPORTANT FIX)
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)

# =========================
# DEBUG CACHE REPORT
# =========================

report_cache = None

async def get_report():
    global report_cache

    if report_cache:
        return report_cache

    try:
        report_cache = await client.fetch_channel(SALON_REPORT)
        return report_cache
    except Exception as e:
        print("REPORT ERROR FETCH:", e)
        return None

# =========================
# JSON SAFE
# =========================

def load_scores():
    if not os.path.exists(JSON_FILE):
        return {}
    try:
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_scores(data):
    try:
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except:
        pass

# =========================
# IA MODERATION (REAL)
# =========================

def analyze(content: str):

    if not MISTRAL_API_KEY:
        return {"delete": False, "score": 0, "reason": "no_api_key"}

    prompt = f"""
Tu es une IA de modération Discord.

Analyse :
- insultes
- racisme direct ou indirect
- moqueries agressives
- généralisations
- haine implicite

Message:
\"\"\"{content}\"\"\"

Répond UNIQUEMENT JSON :
{{
 "delete": true/false,
 "score": 0.5 à 3,
 "reason": "court"
}}
"""

    try:
        r = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {MISTRAL_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "mistral-small",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2
            },
            timeout=8
        )

        data = r.json()
        text = data["choices"][0]["message"]["content"]

        result = json.loads(text)

        return {
            "delete": bool(result.get("delete", False)),
            "score": float(result.get("score", 0)),
            "reason": result.get("reason", "IA")
        }

    except Exception as e:
        print("IA ERROR:", e)
        return {"delete": False, "score": 0, "reason": "ia_fail"}

# =========================
# EVENTS
# =========================

@client.event
async def on_ready():
    print(f"BOT CONNECTÉ : {client.user}")

@client.event
async def on_message(message):

    if message.author.bot:
        return

    print("MSG RECU:", message.content)  # DEBUG IMPORTANT

    if message.channel.id not in SALONS_SURVEILLES:
        return

    scores = load_scores()
    uid = str(message.author.id)

    result = analyze(message.content)

    print("IA RESULT:", result)  # DEBUG

    if not result["delete"]:
        return

    try:
        await message.delete()
    except Exception as e:
        print("DELETE ERROR:", e)

    scores[uid] = scores.get(uid, 0) + result["score"]
    total = scores[uid]

    save_scores(scores)

    report = await get_report()

    if report:
        try:
            embed = discord.Embed(
                title="🚨 MODÉRATION IA",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )

            embed.add_field(name="User", value=str(message.author), inline=False)
            embed.add_field(name="Reason", value=result["reason"], inline=False)
            embed.add_field(name="Score", value=str(result["score"]), inline=True)
            embed.add_field(name="Total", value=str(total), inline=True)
            embed.add_field(name="Message", value=message.content[:1000], inline=False)

            await report.send(embed=embed)

        except Exception as e:
            print("REPORT SEND ERROR:", e)

# =========================
# RUN
# =========================

def run():
    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    threading.Thread(target=run).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
