import os
import json
import threading
from datetime import datetime

import discord
from flask import Flask
from dotenv import load_dotenv

# =========================
# FLASK (Render "site web")
# =========================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"

@app.route("/health")
def health():
    return "OK"

# =========================
# CHARGEMENT ENV
# =========================

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# =========================
# DISCORD BOT
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

client = discord.Client(intents=intents)

JSON_FILE = "toxicite.json"


def charger_scores():
    if not os.path.exists(JSON_FILE):
        with open(JSON_FILE, "w") as f:
            json.dump({}, f)

    with open(JSON_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def sauvegarder_scores(data):
    with open(JSON_FILE, "w") as f:
        json.dump(data, f, indent=4)


@client.event
async def on_ready():
    print(f"Bot connecté : {client.user}")


@client.event
async def on_message(message):
    if message.author.bot:
        return

    # exemple simple (tu peux remettre ton IA après)
    contenu = message.content.lower()

    score = 0
    if "insulte" in contenu:
        score = 1
    elif "spam" in contenu:
        score = 2

    if score == 0:
        return

    try:
        await message.delete()
    except:
        pass

    scores = charger_scores()
    user_id = str(message.author.id)

    scores[user_id] = scores.get(user_id, 0) + score
    sauvegarder_scores(scores)

# =========================
# RUN DISCORD BOT
# =========================

def run_bot():
    if DISCORD_TOKEN is None:
        print("DISCORD_TOKEN manquant")
        return
    client.run(DISCORD_TOKEN)

# =========================
# LANCEMENT
# =========================

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()

    # Render écoute ce serveur web
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
