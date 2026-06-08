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
# JSON SAFE
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
    try:
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print("JSON error:", e)

# =========================
# FILTRE DUR
# =========================

HARD_KEYWORDS = [
    "trafic d'armes", "trafic d’armes",
    "fdp", "connard", "enculé", "pute",
    "ta mère", "ta mere", "tg", "nique",
    "je vais te tuer", "arme", "viol"
]

def hard_filter(text: str):
    t = text.lower()
    return any(w in t for w in HARD_KEYWORDS)

# =========================
# FALLBACK
# =========================

def fallback(text):
    return {
        "delete": False,
        "score": 0,
        "reason": "fallback"
    }

# =========================
# IA MISTRAL ULTRA STRICTE
# =========================

def analyser_message(contenu: str):

    # 1. FILTRE DUR
    if hard_filter(contenu):
        return {
            "delete": True,
            "score": 2.5,
            "reason": "contenu critique"
        }

    if not MISTRAL_API_KEY:
        return fallback(contenu)

    prompt = f"""
Tu es une IA de modération Discord ULTRA STRICTE.

Tu dois détecter :
- insultes directes
- insultes implicites
- moqueries
- sarcasme
- double sens
- humiliation
- provocations

RÈGLE :
Si le message est agressif, humiliant ou provocateur → delete = true

Message :
\"\"\"{contenu}\"\"\"

Réponds UNIQUEMENT en JSON :

{{
  "delete": true/false,
  "score": 0.5 à 3,
  "reason": "catégorie"
}}

Si doute → delete = true
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
            timeout=6
        )

        data = r.json()
        content = data["choices"][0]["message"]["content"]

        try:
            result = json.loads(content)
        except:
            return fallback(contenu)

        if result.get("delete") and float(result.get("score", 0)) < 1:
            result["score"] = 1.5

        return {
            "delete": bool(result.get("delete", False)),
            "score": float(result.get("score", 0)),
            "reason": result.get("reason", "IA")
        }

    except Exception as e:
        print("IA error:", e)
        return fallback(contenu)

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
    uid = str(message.author.id)

    # =========================
    # COMMANDES
    # =========================

    if message.content.startswith("!reset"):
        if not message.mentions:
            await message.channel.send("❌ Mentionne un utilisateur")
            return

        for m in message.mentions:
            scores[str(m.id)] = 0

        sauvegarder_scores(scores)
        await message.channel.send("✅ Reset effectué")
        return

    if message.content.startswith("!score"):
        if message.mentions:
            u = str(message.mentions[0].id)
            await message.channel.send(f"📊 Score: {scores.get(u, 0)}")
        return

    if message.content.startswith("!toptoxic"):
        top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:5]
        msg = "🏆 Top toxicité :\n"
        for u, s in top:
            msg += f"- <@{u}> : {s}\n"
        await message.channel.send(msg)
        return

    # =========================
    # FILTRE SALONS
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

    scores[uid] = scores.get(uid, 0) + result["score"]
    total = scores[uid]

    sauvegarder_scores(scores)

    report = client.get_channel(SALON_REPORT)

    if report:
        embed = discord.Embed(
            title="🚨 MODÉRATION IA",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(name="Utilisateur", value=f"{message.author}", inline=False)
        embed.add_field(name="Raison", value=result["reason"], inline=False)
        embed.add_field(name="Score ajouté", value=str(result["score"]), inline=True)
        embed.add_field(name="Score total", value=str(total), inline=True)
        embed.add_field(name="Message", value=message.content[:1000], inline=False)

        if total >= SEUIL_CRITIQUE:
            embed.add_field(name="⚠️ CRITIQUE", value="Utilisateur très toxique", inline=False)
        elif total >= SEUIL_ALERTE:
            embed.add_field(name="⚠️ ALERTE", value="Surveillance", inline=False)

        await report.send(embed=embed)

# =========================
# RUN
# =========================

def run_bot():
    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
