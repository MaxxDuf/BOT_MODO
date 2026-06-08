import os
import threading
from flask import Flask

import discord
from discord.ext import commands
from dotenv import load_dotenv

# =====================
# LOAD ENV
# =====================
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

# =====================
# WEB SERVER (Render)
# =====================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"

def run_web():
    app.run(host="0.0.0.0", port=10000)

# =====================
# DISCORD BOT
# =====================
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# score simple en mémoire (reset si reboot)
user_scores = {}

def add_score(user_id, value):
    if user_id not in user_scores:
        user_scores[user_id] = 0
    user_scores[user_id] += value
    return user_scores[user_id]

@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.lower()

    score_add = 0

    # SIMPLE DETECTION (tu pourras améliorer après avec IA)
    bad_words = ["connard", "idiot", "merde", "pute"]

    if any(word in content for word in bad_words):
        score_add = 1

        try:
            await message.delete()
        except:
            print("Impossible de supprimer le message (permissions)")

        score = add_score(message.author.id, score_add)

        # seuils
        if score >= 20:
            await message.channel.send(f"{message.author.mention} banni (score {score})")
            try:
                await message.guild.ban(message.author, reason="Toxicité")
            except:
                pass

        elif score >= 10:
            await message.channel.send(
                f"{message.author.mention} attention ⚠️ score: {score}"
            )

    await bot.process_commands(message)

def run_bot():
    bot.run(TOKEN)

# =====================
# START
# =====================
if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    threading.Thread(target=run_bot).start()
