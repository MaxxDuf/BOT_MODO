import os
import json
import threading
import re
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
# CONFIG
# =========================

SALON_REPORT = 1513274703572373504

SALONS_SURVEILLES = {
    1499033414358142977,
    1500213292403134486
}

SEUIL_ALERTE = 10
SEUIL_CRITIQUE = 20

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
# JSON SCORE
# =========================

def charger_scores():
    if not os.path.exists(JSON_FILE):
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)

    try:
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def sauvegarder_scores(data):
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# =========================
# FALLBACK SIMPLE (si IA fail)
# =========================

REGEX_FALLBACK = [
    (r"\bcon(nard)?\b", 1),
    (r"\bfdp\b", 1),
    (r"\bencul(e|é)\b", 1),
    (r"ta mère", 0.5),
    (r"ta gueule", 1.5),
    (r"je vais te tuer", 3),
]

def fallback_analyse(text):
    t = text.lower()
    for pattern, score in REGEX_FALLBACK:
        if re.search(pattern, t):
            return {
                "delete": True,
                "score": score,
                "reason": "fallback détection"
            }

    return {"delete": False, "score": 0, "reason": "OK"}

# =========================
# IA MISTRAL
# =========================

def analyser_message(contenu: str):

    # si pas de clé → fallback
    if not MISTRAL_API_KEY:
        return fallback_analyse(contenu)

    prompt = f"""
Tu es un modérateur Discord très strict.

Analyse ce message :

\"\"\"{contenu}\"\"\"

Détecte :
- insultes
- moqueries
- harcèlement
- discrimination
- menaces

Réponds UNIQUEMENT en JSON :

{{
  "delete": true/false,
  "score": 0.5 à 3,
  "reason": "catégorie courte"
}}
"""

    try:
        response = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {MISTRAL_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": MISTRAL_MODEL,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2
            },
            timeout=6
        )

        data = response.json()
        content = data["choices"][0]["message"]["content"]

        result = json.loads(content)

        return {
            "delete": bool(result.get("delete", False)),
            "score": float(result.get("score", 0)),
            "reason": result.get("reason", "IA")
        }

    except Exception as e:
        print("IA error:", e)
        return fallback_analyse(contenu)

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

    scores = charger_scores()
    user_id = str(message.author.id)

    # =========================
    # COMMANDES
    # =========================

    if message.content.startswith("!reset"):
        if message.mentions:
            scores[str(message.mentions[0].id)] = 0
            sauvegarder_scores(scores)
            await message.channel.send("✅ Score reset")
        return

    if message.content.startswith("!score"):
        if message.mentions:
            uid = str(message.mentions[0].id)
            await message.channel.send(f"📊 Score: {scores.get(uid, 0)}")
        return

    if message.content.startswith("!toptoxic"):
        top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:5]
        msg = "🏆 Top toxicité :\n"
        for uid, sc in top:
            msg += f"- <@{uid}> : {sc}\n"
        await message.channel.send(msg)
        return

    # =========================
    # FILTRAGE SALONS
    # =========================

    if message.channel.id not in SALONS_SURVEILLES:
        return

    result = analyser_message(message.content)

    if not result["delete"]:
        return

    try:
        await message.delete()
    except:
        pass

    if user_id not in scores:
        scores[user_id] = 0

    scores[user_id] += result["score"]
    total = scores[user_id]

    sauvegarder_scores(scores)

    report_channel = client.get_channel(SALON_REPORT)

    if report_channel:

        embed = discord.Embed(
            title="🚨 Modération IA",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(name="Utilisateur", value=f"{message.author} ({message.author.id})", inline=False)
        embed.add_field(name="Salon", value=message.channel.mention, inline=False)
        embed.add_field(name="Raison", value=result["reason"], inline=False)
        embed.add_field(name="Score ajouté", value=str(result["score"]), inline=True)
        embed.add_field(name="Score total", value=str(total), inline=True)
        embed.add_field(name="Message", value=message.content[:1000], inline=False)

        if total >= SEUIL_CRITIQUE:
            embed.add_field(name="⚠️ CRITIQUE", value="Utilisateur très toxique", inline=False)
        elif total >= SEUIL_ALERTE:
            embed.add_field(name="⚠️ ALERTE", value="Surveillance", inline=False)

        await report_channel.send(embed=embed)

# =========================
# BOT + FLASK
# =========================

def run_bot():
    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
