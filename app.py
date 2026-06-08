import os
import json
import threading
import re
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

SERVEUR_ID = 1513274703572373504  # pour commandes admin

# =========================
# ENV
# =========================

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

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
# DETECTION AVANCÉE
# =========================

CATEGORIES = {
    "insulte": {
        "patterns": [
            r"\bcon(nard)?\b",
            r"\bfdp\b",
            r"\bencul(e|é)\b",
            r"\bsalope\b",
            r"\bpute\b",
        ],
        "score": 1
    },

    "moquerie": {
        "patterns": [
            r"ta mère",
            r"ta mere",
            r"t'es nul",
            r"t es nul",
            r"mdr t'es",
            r"haha t'es",
        ],
        "score": 0.5
    },

    "harcelement_leger": {
        "patterns": [
            r"tg\b",
            r"ta gueule",
            r"ferme[- ]?la",
        ],
        "score": 1.5
    },

    "discrimination": {
        "patterns": [
            r"sale (noir|blanc|arabe|juif|femme|gars)",
        ],
        "score": 3
    },

    "menace": {
        "patterns": [
            r"je vais te frapper",
            r"je vais te tuer",
            r"t'es mort",
        ],
        "score": 3
    }
}

def analyser_message(contenu: str):
    texte = contenu.lower()

    for categorie, data in CATEGORIES.items():
        for pattern in data["patterns"]:
            if re.search(pattern, texte):
                return {
                    "delete": True,
                    "score": data["score"],
                    "reason": f"{categorie} détecté"
                }

    return {
        "delete": False,
        "score": 0,
        "reason": "Aucun problème"
    }

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
            cible = str(message.mentions[0].id)
            scores[cible] = 0
            sauvegarder_scores(scores)
            await message.channel.send(f"✅ Score remis à zéro pour {message.mentions[0].mention}")
        return

    if message.content.startswith("!score"):
        if message.mentions:
            cible = str(message.mentions[0].id)
            score = scores.get(cible, 0)
            await message.channel.send(f"📊 Score de toxicité : {score}")
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

    resultat = analyser_message(message.content)

    if not resultat["delete"]:
        return

    score = float(resultat["score"])
    reason = resultat["reason"]

    try:
        await message.delete()
    except Exception as e:
        print("Suppression impossible :", e)

    if user_id not in scores:
        scores[user_id] = 0

    scores[user_id] += score
    total = scores[user_id]

    sauvegarder_scores(scores)

    report_channel = client.get_channel(SALON_REPORT)

    if report_channel:

        embed = discord.Embed(
            title="🚨 Message supprimé",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(name="Utilisateur", value=f"{message.author} ({message.author.id})", inline=False)
        embed.add_field(name="Salon", value=message.channel.mention, inline=False)
        embed.add_field(name="Raison", value=reason, inline=False)
        embed.add_field(name="Score ajouté", value=str(score), inline=True)
        embed.add_field(name="Score total", value=str(total), inline=True)
        embed.add_field(name="Message", value=message.content[:1000], inline=False)

        if total >= SEUIL_CRITIQUE:
            embed.add_field(name="⚠️ CRITIQUE", value="Utilisateur très toxique", inline=False)
        elif total >= SEUIL_ALERTE:
            embed.add_field(name="⚠️ ALERTE", value="Surveillance recommandée", inline=False)

        await report_channel.send(embed=embed)

# =========================
# BOT
# =========================

def run_bot():
    client.run(DISCORD_TOKEN)

# =========================
# START
# =========================

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
