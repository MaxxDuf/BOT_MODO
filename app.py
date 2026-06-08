import os
import json
import threading
import re
import unicodedata
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

@app.route("/ping")
def ping():
    return "ok"

# =========================
# CONFIG
# =========================

SALON_REPORT = 1513274703572373504

SALONS_SURVEILLES = {
    1499033414358142977,
    1500213292403134486
}

JSON_FILE = "toxicite.json"

# =========================
# ENV
# =========================

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small")

# =========================
# DISCORD
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)

# =========================
# CACHE REPORT CHANNEL
# =========================

report_channel_cache = None

async def get_report_channel():
    global report_channel_cache

    if report_channel_cache:
        return report_channel_cache

    try:
        channel = await client.fetch_channel(SALON_REPORT)
        report_channel_cache = channel
        return channel
    except:
        return None

# =========================
# JSON
# =========================

def charger_scores():
    if not os.path.exists(JSON_FILE):
        return {}
    try:
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def sauvegarder_scores(data):
    try:
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except:
        pass

# =========================
# IA MODÉRATION
# =========================

def analyser_message(content: str):

    if not MISTRAL_API_KEY:
        return {"delete": False, "score": 0, "reason": "no_api_key"}

    prompt = f"""
Tu es une IA de modération Discord.

Analyse ce message et détecte :
- insultes
- racisme explicite ou implicite
- généralisations ("vous les X êtes tous...")
- harcèlement
- moqueries agressives
- propos haineux même déguisés

IMPORTANT :
- Comprends le contexte et le double sens
- Si doute → delete = true

Message:
\"\"\"{content}\"\"\"

Répond uniquement en JSON :
{{
  "delete": true/false,
  "score": 0.5 à 3,
  "reason": "court motif"
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
                "model": MISTRAL_MODEL,
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
        return {"delete": False, "score": 0, "reason": "ia_error"}

# =========================
# EVENTS
# =========================

@client.event
async def on_ready():
    print(f"Connecté : {client.user}")

@client.event
async def on_message(message):

    if message.author.bot:
        return

    if message.channel.id not in SALONS_SURVEILLES:
        return

    scores = charger_scores()
    uid = str(message.author.id)

    result = analyser_message(message.content)

    if not result["delete"]:
        return

    try:
        await message.delete()
    except:
        pass

    scores[uid] = scores.get(uid, 0) + result["score"]
    total = scores[uid]

    sauvegarder_scores(scores)

    report = await get_report_channel()

    if report:
        try:
            embed = discord.Embed(
                title="🚨 MODÉRATION IA",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )

            embed.add_field(name="Utilisateur", value=str(message.author), inline=False)
            embed.add_field(name="Raison", value=result["reason"], inline=False)
            embed.add_field(name="Score ajouté", value=str(result["score"]), inline=True)
            embed.add_field(name="Score total", value=str(total), inline=True)
            embed.add_field(name="Message", value=message.content[:1000], inline=False)

            await report.send(embed=embed)

        except Exception as e:
            print("REPORT ERROR:", e)

# =========================
# RUN
# =========================

def run_bot():
    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
