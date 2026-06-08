import os
import json
from datetime import datetime

import discord
from dotenv import load_dotenv
from mistralai import Mistral

# =========================
# CONFIGURATION
# =========================

SALON_REPORT = 1513274703572373504

SALONS_SURVEILLES = {
    1499033414358142977,
    1500213292403134486
}

SEUIL_ALERTE = 10
SEUIL_CRITIQUE = 20

# =========================
# CHARGEMENT .ENV
# =========================

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

mistral = Mistral(api_key=MISTRAL_API_KEY)

# =========================
# DISCORD
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)

# =========================
# FICHIER JSON
# =========================

JSON_FILE = "toxicite.json"


def charger_scores():
    if not os.path.exists(JSON_FILE):
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)

    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def sauvegarder_scores(data):
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


# =========================
# ANALYSE IA
# =========================

def analyser_message(contenu):
    try:
        prompt = f"""
Analyse ce message Discord.

Message :
{contenu}

Réponds UNIQUEMENT avec un JSON valide.

Format :

{{
    "delete": true ou false,
    "score": nombre entre 0 et 3,
    "reason": "raison courte"
}}

Règles :
- score 0 = aucun problème
- score 0.5 = langage agressif léger
- score 1 = insulte
- score 2 = harcèlement ou contenu grave
- score 3 = menace, discrimination grave ou contenu illégal

Aucune explication supplémentaire.
"""

        response = mistral.chat.complete(
            model="mistral-small-latest",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Tu es un système de modération. "
                        "Tu réponds uniquement en JSON."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        texte = response.choices[0].message.content

        debut = texte.find("{")
        fin = texte.rfind("}") + 1

        if debut == -1 or fin == 0:
            return None

        return json.loads(texte[debut:fin])

    except Exception as e:
        print("Erreur IA :", e)
        return None


# =========================
# EVENEMENTS
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

    if not resultat:
        return

    delete = resultat.get("delete", False)
    score = float(resultat.get("score", 0))
    reason = resultat.get("reason", "Inconnue")

    if not delete:
        return

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

        contenu = message.content[:1000]

        embed.add_field(
            name="Message",
            value=contenu,
            inline=False
        )

        if total >= SEUIL_CRITIQUE:
            embed.add_field(
                name="⚠️ Alerte",
                value=(
                    "L'utilisateur a atteint le seuil critique.\n"
                    "Une vérification humaine est recommandée."
                ),
                inline=False
            )

        elif total >= SEUIL_ALERTE:
            embed.add_field(
                name="⚠️ Alerte",
                value=(
                    "L'utilisateur a atteint le seuil d'alerte.\n"
                    "Les modérateurs doivent décider d'une sanction."
                ),
                inline=False
            )

        await report_channel.send(embed=embed)

<<<<<<< HEAD
client.run(DISCORD_TOKEN)
=======
client.run(DISCORD_TOKEN)
>>>>>>> 3c86cedbdfffe5db2a279ca135677195e929ee63
