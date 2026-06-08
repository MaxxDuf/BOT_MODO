import os
import threading
from flask import Flask

import discord
from discord.ext import commands
from dotenv import load_dotenv

from mistralai import Mistral

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

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
MISTRAL_KEY = os.getenv("MISTRAL_API_KEY")

mistral = Mistral(api_key=MISTRAL_KEY)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot connecté : {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # exemple simple test
    if "badword" in message.content.lower():
        await message.delete()
        await message.channel.send("Message supprimé (toxique détecté)")

    await bot.process_commands(message)

def run_bot():
    bot.run(TOKEN)

# =====================
# LANCEMENT
# =====================

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    threading.Thread(target=run_bot).start()
