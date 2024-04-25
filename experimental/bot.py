import os
from uuid import uuid1
import discord
from honcho import Honcho
from honcho.ext.langchain import messages_to_langchain
from graph import chat
from dspy import Example
from art_maestro import opus_orchestrator, haiku_sub_agent, opus_refine, create_folder_structure
import re
import asyncio
import random

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True
intents.reactions = True
intents.members = True  # Enable the members intent

app_name = str(uuid1())

honcho = Honcho(app_name=app_name, base_url="http://localhost:8001") # uncomment to use local
#honcho = Honcho(app_name=app_name)  # uses demo server at https://demo.honcho.dev
honcho.initialize()

bot = discord.Bot(intents=intents)

thumbs_up_messages = []
thumbs_down_messages = []

async def get_server_admins(guild):
    admin_role = guild.get_role(1108537792981631038)  # Replace with your admin role ID
    members = await guild.fetch_members().flatten()
    admin_members = [member.mention for member in members if admin_role in member.roles]
    return admin_members

@bot.event
async def on_ready():
    print(f"We have logged in as {bot.user}")
    for guild in bot.guilds:
        admin_mentions = await get_server_admins(guild)
        general_channel = discord.utils.get(guild.text_channels, name="general")  # Replace with the name of the channel you want to use
        if general_channel:
            admin_mention_string = " ".join(admin_mentions)
            intro_message = f"{admin_mention_string}\n\nHello, I'm your server's AI assistant! I'm here to help with a variety of tasks, including data analysis, task management, and intelligent conversation. Let me know if you need any assistance!"
            await general_channel.send(intro_message)


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

MAX_FILE_SIZE = 8 * 1024 * 1024  # 8 MB in bytes
MAX_MESSAGE_SIZE = 8 * 1024 * 1024  # 8 MB in bytes
MAX_MESSAGES_PER_MINUTE = 5  # Adjust this value based on your needs
last_message_times = []

async def send_message_with_backoff(channel, message, max_retries=5, base_delay=2):
    retries = 0
    while retries < max_retries:
        try:
            await channel.send(message)
            return
        except discord.errors.HTTPException as e:
            if e.code == 50035:  # Invalid Form Body
                delay = base_delay * (2 ** retries) + random.uniform(0, 1)
                print(f"Retrying in {delay:.2f} seconds...")
                await asyncio.sleep(delay)
                retries += 1
            else:
                raise e
    print("Maximum retries exceeded, unable to send message.")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.guild is None:  # Direct message
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

            # Clean up the response text
            cleaned_response = re.sub(r'[^\x00-\x7F]+', '', response)

            # Check if the response is too long
            if len(cleaned_response) > 2000:
                # Split the cleaned response into multiple files
                chunks = [cleaned_response[i:i+MAX_FILE_SIZE] for i in range(0, len(cleaned_response), MAX_FILE_SIZE)]
                total_file_size = sum(len(chunk.encode()) for chunk in chunks)

                if total_file_size > MAX_MESSAGE_SIZE:
                    await message.channel.send("The response is too large to send as attachments. Please try again with a shorter input.")
                else:
                    for i, chunk in enumerate(chunks, start=1):
                        temp_file = io.StringIO(chunk)
                        temp_file.name = f"response_{i}.txt"
                        await send_message_with_backoff(message.channel, file=discord.File(temp_file, temp_file.name))
            else:
                await send_message_with_backoff(message.channel, cleaned_response)

        session.create_message(is_user=False, content=response)

    else:  # Message in a channel
        if bot.user.mentioned_in(message) or message.reference and message.reference.resolved.author == bot.user:
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

        # Check if the user is an admin
        admin_members = await get_server_admins(message.guild)
        if message.author.mention in admin_members:
            # Handle admin messages here
            # e.g., respond with higher priority, provide additional functionality
            pass

@bot.event
async def on_reaction_add(reaction, user):
    # Ensure the bot does not react to its own reactions
    if user == bot.user:
        return

    # Check if the reaction was added to the intro message
    if reaction.message.content.startswith(f"{user.mention}"):
        # Check if the user is an admin
        admin_members = await get_server_admins(reaction.message.guild)
        if user.mention in admin_members:
            # Start a conversation with the admin
            await user.send("Hello! Thanks for your interest. How can I assist you today?")

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

# ... (rest of the code remains the same)
@bot.slash_command(name="generate", description="Generate art based on user input")
async def generate_art(ctx, objective: str, file_path: str = None):
    user_id = f"discord_{str(ctx.author.id)}"
    user = honcho.get_or_create_user(user_id)
    location_id = str(ctx.channel_id)
    session = user.get_or_create_session(location_id)

    # Check if the input contains a file path
    if file_path:
        with open(file_path, 'r') as file:
            file_content = file.read()
    else:
        file_content = None

    # Prompt the user for search decision
    await ctx.respond("Do you want to use search? (y/n)")
    search_message = await bot.wait_for("message", check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
    use_search = search_message.content.lower() == 'y'

    # Create the .md filename
    sanitized_objective = re.sub(r'\W+', '_', objective)
    timestamp = datetime.now().strftime("%H-%M-%S")
    project_name = f"{timestamp}_{sanitized_objective}"

    # Prompt the user for the number of images to generate
    await ctx.respond("Enter the number of images to generate:")
    image_count_message = await bot.wait_for("message", check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
    image_count = int(image_count_message.content)

    # Provide pre-selected size options
    size_options = {
        "1": (256, 256),
        "2": (680, 240),
        "3": (768, 768),
        "4": (1024, 1024)
    }
    size_options_text = "\n".join([f"{option}. {size[0]}x{size[1]}" for option, size in size_options.items()])
    await ctx.respond(f"Select an image size:\n{size_options_text}")
    size_choice_message = await bot.wait_for("message", check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
    size_choice = size_choice_message.content
    image_size = size_options.get(size_choice, (512, 512))

    # Prompt the user for additional parameters
    await ctx.respond("Enter the number of refinement steps (default: 30):")
    num_steps_message = await bot.wait_for("message", check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
    num_steps = int(num_steps_message.content) if num_steps_message.content else 30

    await ctx.respond("Enter the configuration scale (default: 7.0):")
    cfg_scale_message = await bot.wait_for("message", check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
    cfg_scale = float(cfg_scale_message.content) if cfg_scale_message.content else 7.0

    sampler_options = {
        "1": "K_DPM_2_ANCESTRAL",
        "2": "K_EULER_ANCESTRAL",
        "3": "K_HEUN",
        "4": "K_DPM_2"
    }
    sampler_options_text = "\n".join([f"{option}. {sampler}" for option, sampler in sampler_options.items()])
    await ctx.respond(f"Select a sampling method:\n{sampler_options_text}")
    sampler_choice_message = await bot.wait_for("message", check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
    sampler_choice = sampler_choice_message.content
    sampler = sampler_options.get(sampler_choice, "K_DPM_2_ANCESTRAL")

    task_exchanges = []
    haiku_tasks = []

    while True:
        # State: Orchestrator
        previous_results = [result for _, result, _ in task_exchanges]
        if not task_exchanges:
            opus_result, file_content_for_haiku, search_query = opus_orchestrator(objective, file_content, previous_results, use_search)
        else:
            opus_result, _, search_query = opus_orchestrator(objective, previous_results=previous_results, use_search=use_search)

        if "The task is complete:" in opus_result:
            final_output = opus_result.replace("The task is complete:", "").strip()
            break
        else:
            sub_task_prompt = opus_result
            if file_content_for_haiku and not haiku_tasks:
                sub_task_prompt = f"{sub_task_prompt}\n\nFile content:\n{file_content_for_haiku}"

            while True:
                # State: Sub-agent
                sub_task_result, generated_images = haiku_sub_agent(sub_task_prompt, search_query, haiku_tasks, use_search, project_name=project_name, image_count=image_count, image_size=image_size, num_steps=num_steps, cfg_scale=cfg_scale, sampler=sampler)
                haiku_tasks.append({"task": sub_task_prompt, "result": sub_task_result})
                task_exchanges.append((sub_task_prompt, sub_task_result, [image_file_path for _, image_file_path in generated_images]))

                # State: Image Confirmation
                for image_file_path in [image_file_path for _, image_file_path in generated_images]:
                    await ctx.respond(file=discord.File(image_file_path))
                await ctx.respond("Do the generated images meet the objective? (y/n)")
                confirmation_message = await bot.wait_for("message", check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
                if confirmation_message.content.lower() == 'y':
                    break
                else:
                    await ctx.respond("Please provide feedback on how to improve the image:")
                    feedback_message = await bot.wait_for("message", check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
                    feedback = feedback_message.content
                    sub_task_prompt += f"\n\nUser Feedback: {feedback}"

            # State: Video Generation Prompt
            await ctx.respond("Do you want to use one of the generated images for video generation? (y/n)")
            video_confirmation_message = await bot.wait_for("message", check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
            if video_confirmation_message.content.lower() == 'y':
                await ctx.respond("Please select an image number for video generation:")
                for i, image_file_path in enumerate(generated_images, start=1):
                    await ctx.respond(f"{i}. {image_file_path}")
                selection_message = await bot.wait_for("message", check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
                selection = int(selection_message.content)
                selected_image_path = generated_images[selection - 1][1]

                # State: Video Generation
                # ... (code for generating video)

    # State: Refine Output
    refined_output = opus_refine(objective, [result for _, result, _ in task_exchanges], timestamp, project_name)

    # State: Create Folder Structure
    create_folder_structure(project_name, folder_structure, code_blocks)

    # Send the final output and exchange log to the user
    await ctx.respond(f"**Refined Final Output:**\n{refined_output}")
    
    with open(filename, 'r') as file:
        exchange_log = file.read()
    await ctx.respond(f"**Full Exchange Log:**\n```{exchange_log}```")

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


@bot.event
async def on_connect():
    await bot.sync_commands()

bot.run(os.environ["BOT_TOKEN"])