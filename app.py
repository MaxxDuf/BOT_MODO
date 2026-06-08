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
# ROLE CHECK
# =========================

def est_fondateur(member: discord.Member):
    return any(role.name == "Fondateur" for role in member.roles)

# =========================
# NORMALISATION
# =========================

def normaliser_texte(text: str):
    text = text.lower()
    text = ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )
    text = re.sub(r"[^a-zàâçéèêëîïôûùüÿñæœ\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

# =========================
# FILTRE HAINE
# =========================

HATE = [
    "sale noir", "sale blanc", "nigga", "nigger",
    "vous les noirs", "vous les blancs",
    "les noirs sont", "les blancs sont",
    "vous etes tous des voleurs",
    "retourne dans ton pays",
    "fdp", "connard", "encule", "pute"
]

def hard_filter(text):
    t = normaliser_texte(text)
    return any(x in t for x in HATE)

# =========================
# IA
# =========================

def analyser_message(content: str):

    if hard_filter(content):
        return {"delete": True, "score": 3, "reason": "contenu haineux"}

    if not MISTRAL_API_KEY:
        return {"delete": False, "score": 0, "reason": "no ai"}

    prompt = f"""
Modération Discord stricte.

Détecte :
- insultes
- racisme direct/indirect
- généralisations
- haine

Message:
\"\"\"{content}\"\"\"

Répond JSON:
{{
 "delete": true/false,
 "score": 0.5 à 3,
 "reason": "type"
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
            timeout=6
        )

        data = r.json()
        result = json.loads(data["choices"][0]["message"]["content"])

        return {
            "delete": result.get("delete", False),
            "score": float(result.get("score", 0)),
            "reason": result.get("reason", "IA")
        }

    except:
        return {"delete": False, "score": 0, "reason": "error"}

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
    # COMMANDES SECURISEES
    # =========================

    if message.content.startswith("!reset"):
        if not est_fondateur(message.author):
            await message.channel.send("❌ Permission refusée")
            return

        if not message.mentions:
            await message.channel.send("❌ Mentionne un utilisateur")
            return

        for m in message.mentions:
            scores[str(m.id)] = 0

        sauvegarder_scores(scores)
        await message.channel.send("✅ Reset OK")
        return

    if message.content.startswith("!score"):
        if not est_fondateur(message.author):
            await message.channel.send("❌ Permission refusée")
            return

        if not message.mentions:
            await message.channel.send("❌ Mentionne un utilisateur")
            return

        u = str(message.mentions[0].id)
        await message.channel.send(f"📊 Score: {scores.get(u, 0)}")
        return

    # =========================
    # SALONS
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

    # =========================
    # REPORT FIX
    # =========================

    try:
        report = await client.fetch_channel(SALON_REPORT)
    except:
        report = None

    if report:
        embed = discord.Embed(
            title="🚨 MODÉRATION IA",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(name="Utilisateur", value=str(message.author), inline=False)
        embed.add_field(name="Raison", value=result["reason"], inline=False)
        embed.add_field(name="Score", value=str(result["score"]), inline=True)
        embed.add_field(name="Total", value=str(total), inline=True)
        embed.add_field(name="Message", value=message.content[:1000], inline=False)

        await report.send(embed=embed)

# =========================
# RUN
# =========================

def run_bot():
    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
