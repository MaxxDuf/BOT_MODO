import os
import asyncio
from flask import Flask
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

# =====================
# WEB SERVER
# =====================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"

# =====================
# DISCORD BOT
# =====================
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Connecté : {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if "merde" in message.content.lower():
        try:
            await message.delete()
        except:
            pass

    await bot.process_commands(message)

# =====================
# START PROPRE
# =====================
async def run():
    import threading

    # Flask en background
    threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=10000),
        daemon=True
    ).start()

    # Discord bot
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(run())
