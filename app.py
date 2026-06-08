import os
import json
import threading
import requests
from datetime import datetime

import discord
from flask import Flask
from dotenv import load_dotenv

# =========================
# FLASK
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

# =========================
# DISCORD
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)

# =========================
# DEBUG REPORT CACHE
# =========================

report_channel = None

async def get_report():
    global report_channel

    if report_channel:
        return report_channel

    try:
        report_channel = await client.fetch_channel(SALON_REPORT)
        print("REPORT CHANNEL OK")
        return report_channel
    except Exception as e:
        print("REPORT ERROR:", e)
        return None

# =========================
# IA
# =========================

def analyze(content: str):

    if not MISTRAL_API_KEY:
        return {"delete": False, "score": 0, "reason": "no_api_key"}

    prompt = f"""
Tu es une IA de modération Discord.

Analyse :
- insultes
- racisme
- moqueries
- harcèlement
- haine directe ou indirecte

Message:
\"\"\"{content}\"\"\"

Répond uniquement JSON :
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
            timeout=10
        )

        data = r.json()
        text = data["choices"][0]["message"]["content"]

        result = json.loads(text)

        return {
            "delete": result.get("delete", False),
            "score": float(result.get("score", 0)),
            "reason": result.get("reason", "IA")
        }

    except Exception as e:
        print("IA ERROR:", e)
        return {"delete": False, "score": 0, "reason": "ia_error"}

# =========================
# EVENTS (IMPORTANT FIX)
# =========================

@client.event
async def on_ready():
    print("BOT CONNECTÉ :", client.user)

@client.event
async def on_message(message):

    # DEBUG OBLIGATOIRE
    print("MESSAGE RECU:", message.content)

    if message.author.bot:
        return

    result = analyze(message.content)

    print("IA RESULT:", result)

    if not result["delete"]:
        return

    try:
        await message.delete()
    except Exception as e:
        print("DELETE ERROR:", e)

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
