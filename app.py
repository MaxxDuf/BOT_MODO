import os
import json
import threading
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
# DETECTION SIMPLE
# =========================

MOTS_INTERDITS = [
    "con",
    "connard",
    "pute",
    "fdp",
    "enculé",
    "encule",
    "salope",
    "tg",
    "ta gueule",
    "nique",
]

def analyser_message(contenu):
    texte = contenu.lower()

    for mot in MOTS_INTERDITS:
        if mot in texte:
            return {
                "delete": True,
                "score": 1,
                "reason": f"Mot interdit détecté : {mot}"
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

    scores = charger_scores()

    user_id = str(message.author.id)

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

        embed.add_field(
            name="Utilisateur",
            value=f"{message.author} ({message.author.id})",
            inline=False
        )

        embed.add_field(
            name="Serveur",
            value=message.guild.name,
            inline=False
        )

        embed.add_field(
            name="Salon",
            value=message.channel.mention,
            inline=False
        )

        embed.add_field(
            name="Raison",
            value=reason,
            inline=False
        )

        embed.add_field(
            name="Score ajouté",
            value=str(score),
            inline=True
        )

        embed.add_field(
            name="Score total",
            value=str(total),
            inline=True
        )

        embed.add_field(
            name="Message",
            value=message.content[:1000],
            inline=False
        )

        if total >= SEUIL_CRITIQUE:
            embed.add_field(
                name="⚠️ Alerte critique",
                value="Utilisateur à surveiller.",
                inline=False
            )

        elif total >= SEUIL_ALERTE:
            embed.add_field(
                name="⚠️ Alerte",
                value="Score élevé détecté.",
                inline=False
            )

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
