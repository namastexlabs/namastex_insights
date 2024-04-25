import os
from uuid import uuid1
import discord
from honcho import Honcho
from honcho.ext.langchain import messages_to_langchain
from graph import chat
from dspy import Example

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True
intents.reactions = True  # Enable reactions intent

app_name = str(uuid1())

honcho = Honcho(app_name=app_name, base_url="http://localhost:8001") # uncomment to use local
#honcho = Honcho(app_name=app_name)  # uses demo server at https://demo.honcho.dev
honcho.initialize()

bot = discord.Bot(intents=intents)

thumbs_up_messages = []
thumbs_down_messages = []


@bot.event
async def on_ready():
    print(f"We have logged in as {bot.user}")


@bot.event
async def on_member_join(member):
    await member.send(
        f"*Hello {member.name}, welcome to the Namastex Labs server! I'm an AI-powered bot designed to assist with data analysis, task management, and intelligent conversation.* "
        "*Feel free to ask me about our AI solutions, data insights, or any other topics related to our services.* "
        "*I'm here to help you navigate our offerings and provide relevant information.* "
        "*You can use the /restart command to restart our conversation at any time.* "
        "*If you have any questions or feedback, please let me know!* "
        "*Looking forward to our interaction.*"
    )

@bot.event
async def on_message(message):
    if message.author == bot.user or message.guild is not None:
        return

    user_id = f"discord_{str(message.author.id)}"
    user = honcho.get_or_create_user(user_id)
    location_id = str(message.channel.id)

    sessions = list(
        user.get_sessions_generator(location_id, is_active=True, reverse=True)
    )

    if len(sessions) > 0:
        session = sessions[0]
    else:
        session = user.create_session(location_id)

    history = list(session.get_messages_generator())[:5]
    chat_history = messages_to_langchain(history)

    inp = message.content
    user_message = session.create_message(is_user=True, content=inp)

    async with message.channel.typing():
        response = await chat(
            chat_history=chat_history,
            user_message=user_message,
            session=session,
            input=inp,
        )
        await message.channel.send(response)

    session.create_message(is_user=False, content=response)


@bot.event
async def on_reaction_add(reaction, user):
    # Ensure the bot does not react to its own reactions
    if user == bot.user:
        return

    user_id = f"discord_{str(user.id)}"
    honcho_user = honcho.get_or_create_user(user_id)
    location_id = str(reaction.message.channel.id)

    sessions = list(
        honcho_user.get_sessions_generator(location_id, is_active=True, reverse=True)
    )
    if len(sessions) > 0:
        session = sessions[0]
    else:
        session = honcho_user.create_session(location_id)

    messages = list(session.get_messages_generator(reverse=True))
    ai_responses = [message for message in messages if not message.is_user]
    user_responses = [message for message in messages if message.is_user]
    # most recent AI response
    ai_response = ai_responses[0].content
    user_response = user_responses[0]

    user_state_storage = dict(honcho_user.metadata)
    user_state = list(
        session.get_metamessages_generator(
            metamessage_type="user_state", message=user_response, reverse=True
        )
    )[0].content
    examples = user_state_storage[user_state]["examples"]

    # Check if the reaction is a thumbs up
    if str(reaction.emoji) == "👍":
        example = Example(
            chat_input=user_response.content,
            response=ai_response,
            assessment_dimension=user_state,
            label="yes",
        ).with_inputs("chat_input", "response", "assessment_dimension")
        examples.append(example.toDict())
    # Check if the reaction is a thumbs down
    elif str(reaction.emoji) == "👎":
        example = Example(
            chat_input=user_response.content,
            response=ai_response,
            assessment_dimension=user_state,
            label="no",
        ).with_inputs("chat_input", "response", "assessment_dimension")
        examples.append(example.toDict())

    user_state_storage[user_state]["examples"] = examples
    honcho_user.update(metadata=user_state_storage)


@bot.slash_command(name="restart", description="Restart the Conversation")
async def restart(ctx):
    user_id = f"discord_{str(ctx.author.id)}"
    user = honcho.get_or_create_user(user_id)
    location_id = str(ctx.channel_id)
    sessions = list(user.get_sessions_generator(location_id, reverse=True))
    sessions[0].close() if len(sessions) > 0 else None

    msg = (
        "Great! The conversation has been restarted. What would you like to talk about?"
    )
    await ctx.respond(msg)


bot.run(os.environ["BOT_TOKEN"])
