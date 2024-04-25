    Directory: C:\Users\strau\Namastex_Insights\langchain_prompts


Mode                 LastWriteTime         Length Name
----                 -------------         ------ ----
-a----         4/24/2024   8:53 PM            527 state_check.yaml
-a----         4/24/2024   8:53 PM            487 state_commentary.yaml
-a----         4/24/2024   8:53 PM            523 state_labeling.yaml


Directory: C:\Users\strau\Namastex_Insights


Mode                 LastWriteTime         Length Name
----                 -------------         ------ ----
d-----         4/25/2024  11:55 AM                .lumentis
d-----         4/25/2024   1:50 AM                langchain_prompts
d-----         4/25/2024   1:50 AM                local_cache
d-----         4/25/2024   2:42 AM                __pycache__
-a----         4/24/2024   9:55 PM            278 .env
-a----         4/24/2024   8:53 PM             26 .gitignore
-a----         4/25/2024   2:05 AM          26802 artmaestro.py
-a----         4/25/2024   2:42 AM          19399 art_maestro.py
-a----         4/24/2024   9:13 PM              0 assertion.log
-a----         4/25/2024   4:30 AM          17264 bot.py
-a----         4/25/2024   1:33 AM           5538 chain.py
-a----         4/25/2024   1:30 AM           4813 graph.py
-a----         4/25/2024   4:30 AM         488184 groq_usage.log
-a----         4/24/2024   8:53 PM         218771 poetry.lock
-a----         4/24/2024   8:53 PM            458 pyproject.toml
-a----         4/25/2024   1:59 AM             19 README.md
-a----         4/24/2024   8:53 PM           1286 response_metric.py

#state_check.yaml

_type: prompt
input_variables:
    ["existing_states", "state"]
template: >
    Given the list of existing states, determine whether or not the new state is represented in the list of existing states.

    existing states: """{existing_states}"""
    new state: """{state}"""

    If the new state is sufficiently similar to a value in the list of existing states, return that existing state value. If the new state is NOT sufficiently similar to anything in existing states, return "None". Output a single value only.


#state_commentary.yaml

_type: prompt
input_variables:
    ["existing_states", "chat_history", "user_input"]
template: >
    Your job is to make a prediction about the task the user might be engaging in. Some people might be researching, exploring curiosities, or just asking questions for general inquiry. Provide commentary that would shed light on the "mode" the user might be in.

    existing states: """{existing_states}"""
    chat history: """{chat_history}"""
    user input: """{user_input}"""


#state_labeling.yaml

_type: prompt
input_variables:
    ["state_commentary", "existing_states"]
template: >
    Your job is to label the state the user might be in. Some people might be conducting research, exploring a interest, or just asking questions for general inquiry.

    commentary: """{state_commentary}"""
    Prior states, from oldest to most recent:"""
    {existing_states}
    """

    Take into account the user's prior states when making your prediction. Output your prediction as a concise, single word label.

#art_maestro.py

import os
from anthropic import Anthropic
import re
from rich.console import Console
from rich.panel import Panel
from datetime import datetime
import json
import requests
import base64
from PIL import Image
from io import BytesIO
from tavily import TavilyClient
import time

# Set up the Anthropic API client
client = Anthropic(api_key="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")

def calculate_subagent_cost(model, input_tokens, output_tokens):
    # Pricing information per model
    pricing = {
        "claude-3-opus-20240229": {"input_cost_per_mtok": 15.00, "output_cost_per_mtok": 75.00},
        "claude-3-haiku-20240307": {"input_cost_per_mtok": 0.25, "output_cost_per_mtok": 1.25},
    }

    # Calculate cost
    input_cost = (input_tokens / 1_000_000) * pricing[model]["input_cost_per_mtok"]
    output_cost = (output_tokens / 1_000_000) * pricing[model]["output_cost_per_mtok"]
    total_cost = input_cost + output_cost

    return total_cost
# Initialize the Rich Console
console = Console()

def opus_orchestrator(objective, file_content=None, previous_results=None, use_search=False):
    console.print(f"\n[bold]Calling Orchestrator for your objective[/bold]")
    previous_results_text = "\n".join(previous_results) if previous_results else "None"
    if file_content:
        console.print(Panel(f"File content:\n{file_content}", title="[bold blue]File Content[/bold blue]", title_align="left", border_style="blue"))
    
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"Based on the following objective{' and file content' if file_content else ''}, and the previous sub-task results (if any), please break down the objective into the next sub-task, and create a concise and detailed prompt for a subagent so it can execute that task. IMPORTANT!!! when dealing with code tasks make sure you check the code for errors and provide fixes and support as part of the next sub-task. If you find any bugs or have suggestions for better code, please include them in the next sub-task prompt. Please assess if the objective has been fully achieved. If the previous sub-task results comprehensively address all aspects of the objective, include the phrase 'The task is complete:' at the beginning of your response. If the objective is not yet fully achieved, break it down into the next sub-task and create a concise and detailed prompt for a subagent to execute that task.:\n\nObjective: {objective}" + ('\\nFile content:\\n' + file_content if file_content else '') + f"\n\nPrevious sub-task results:\n{previous_results_text}"}
            ]
        }
    ]
    if use_search:
        messages[0]["content"].append({"type": "text", "text": "Please also generate a JSON object containing a single 'search_query' key, which represents a question that, when asked online, would yield important information for solving the subtask. The question should be specific and targeted to elicit the most relevant and helpful resources. Format your JSON like this, with no additional text before or after:\n{\"search_query\": \"<question>\"}\n"})

    opus_response = client.messages.create(
        model="claude-3-opus-20240229",
        max_tokens=4096,
        messages=messages
    )

    response_text = opus_response.content[0].text
    console.print(f"Input Tokens: {opus_response.usage.input_tokens}, Output Tokens: {opus_response.usage.output_tokens}")
    total_cost = calculate_subagent_cost("claude-3-opus-20240229", opus_response.usage.input_tokens, opus_response.usage.output_tokens)
    console.print(f"Opus Orchestrator Cost: ${total_cost:.2f}")

    search_query = None
    if use_search:
        # Extract the JSON from the response
        json_match = re.search(r'{.*}', response_text, re.DOTALL)
        if json_match:
            json_string = json_match.group()
            try:
                search_query = json.loads(json_string)["search_query"]
                console.print(Panel(f"Search Query: {search_query}", title="[bold blue]Search Query[/bold blue]", title_align="left", border_style="blue"))
                response_text = response_text.replace(json_string, "").strip()
            except json.JSONDecodeError as e:
                console.print(Panel(f"Error parsing JSON: {e}", title="[bold red]JSON Parsing Error[/bold red]", title_align="left", border_style="red"))
                console.print(Panel(f"Skipping search query extraction.", title="[bold yellow]Search Query Extraction Skipped[/bold yellow]", title_align="left", border_style="yellow"))
        else:
            search_query = None

    console.print(Panel(response_text, title=f"[bold green]Opus Orchestrator[/bold green]", title_align="left", border_style="green", subtitle="Sending task to Haiku 👇"))
    return response_text, file_content, search_query

video_image_size = (768, 768)  # Choose one of the supported dimensions

def generate_image(prompt, api_key, project_name, image_count, image_size, num_steps, cfg_scale, sampler):
    api_host = "https://api.stability.ai"
    endpoint = "/v2beta/stable-image/generate/sd3"  # Adjusted endpoint
    api_key = api_key

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "image/*"
    }

    for i in range(image_count):
        data = {
            "prompt": prompt,
            "output_format": "jpeg",  # or "png" based on your requirement
            "seed": 992446758 + i,   # Seed for image generation consistency
            "steps": num_steps,       # Number of refinement steps
            "cfg_scale": cfg_scale,   # Configuration scale influencing randomness
            "width": image_size[0],   # Width of the output image
            "height": image_size[1],  # Height of the output image
            "sampler": sampler        # Sampling method
        }

        # The `files` parameter is empty if there's no file part of the payload
        response = requests.post(f"{api_host}{endpoint}", headers=headers, files={"none": (None, '')}, data=data)
        
        if response.status_code == 200:
            img_data = response.content
            img = Image.open(BytesIO(img_data))
            img.show()  # This will display the image if possible
            
            # Generate a unique file name based on the image prompt
            image_file_name = f"{project_name}_image_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i+1}.png"
            image_file_path = os.path.join(project_name, image_file_name)
            
            # Create the project folder if it doesn't exist
            os.makedirs(project_name, exist_ok=True)
            
            # Save the image in the project folder
            img.save(image_file_path)
            
            yield img, image_file_path
        else:
            # Handle non-200 responses and provide more information about the error
            raise Exception(str(response.json()))

def user_video_generation_prompt(image_file_paths):
    while True:
        confirmation = input("Do you want to use one of the generated images for video generation? (y/n): ").lower()
        if confirmation == 'y':
            print("Select an image to use for video generation:")
            for i, image_file_path in enumerate(image_file_paths, start=1):
                print(f"{i}. {image_file_path}")
            selection = int(input("Enter the image number: "))
            if 1 <= selection <= len(image_file_paths):
                selected_image_path = image_file_paths[selection - 1]
                seed = int(input("Enter the seed value (optional, default=0): ") or 0)
                cfg_scale = float(input("Enter the cfg_scale value (0-10, default=1.8): ") or 1.8)
                motion_bucket_id = int(input("Enter the motion_bucket_id value (1-255, default=127): ") or 127)
                return selected_image_path, seed, cfg_scale, motion_bucket_id
            else:
                print("Invalid selection. Please try again.")
        elif confirmation == 'n':
            return None, None, None, None
        else:
            print("Invalid input. Please enter 'y' or 'n'.")

def generate_video(image_file_path, seed, cfg_scale, motion_bucket_id):
    api_host = "https://api.stability.ai"
    endpoint = "/v2beta/image-to-video"
    api_key = "sk-AuAAM6v7JpfkyDPsiQC5GqJFolxlMdt70lZ9RQAgFoGuQ9vw"

    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    with open(image_file_path, "rb") as image_file:
        image = Image.open(image_file)
        video_image_size = (768, 768)  # Choose one of the supported dimensions
        resized_image = image.resize(video_image_size)

        image_bytes = BytesIO()
        resized_image.save(image_bytes, format="PNG")
        image_bytes.seek(0)

        files = {"image": image_bytes}
        data = {
            "seed": seed,
            "cfg_scale": cfg_scale,
            "motion_bucket_id": motion_bucket_id
        }

        response = requests.post(f"{api_host}{endpoint}", headers=headers, files=files, data=data)

        if response.status_code == 200:
            generation_id = response.json().get("id")
            console.print(f"Video generation started with ID: {generation_id}")

            while True:
                result_headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "video/*"  # Add the accept header with the appropriate value
                }
                result_response = requests.get(f"{api_host}/v2beta/image-to-video/result/{generation_id}", headers=result_headers)

                if result_response.status_code == 200:
                    console.print("Video generation complete!")
                    video_data = result_response.content
                    video_file_name = f"{project_name}_video_{generation_id}.mp4"
                    video_file_path = os.path.join(project_name, video_file_name)

                    with open(video_file_path, "wb") as video_file:
                        video_file.write(video_data)

                    console.print(f"Video saved to: {video_file_path}")
                    return video_file_path
                elif result_response.status_code == 202:
                    console.print("Video generation in progress. Waiting for 10 seconds...")
                    time.sleep(10)
                else:
                    raise Exception(str(result_response.json()))
        else:
            raise Exception(str(response.json()))
                
def haiku_sub_agent(prompt, search_query=None, previous_haiku_tasks=None, use_search=False, continuation=False, project_name=None, image_count=1, image_size=(512, 512), num_steps=30, cfg_scale=7.0, sampler="K_DPM_2_ANCESTRAL"):
    if previous_haiku_tasks is None:
        previous_haiku_tasks = []

    continuation_prompt = "Continuing from the previous answer, please complete the response."
    system_message = "Previous Haiku tasks:\n" + "\n".join(f"Task: {task['task']}\nResult: {task['result']}" for task in previous_haiku_tasks)
    if continuation:
        prompt = continuation_prompt

    qna_response = None
    if search_query and use_search:
        # Initialize the Tavily client
        tavily = TavilyClient(api_key="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")
        # Perform a QnA search based on the search query
        qna_response = tavily.qna_search(query=search_query)
        console.print(f"QnA response: {qna_response}", style="yellow")

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "text", "text": f"\nSearch Results:\n{qna_response}" if qna_response else ""}
            ]
        }
    ]

    haiku_response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=4096,
        messages=messages,
        system=system_message
    )

    response_text = haiku_response.content[0].text
    console.print(f"Input Tokens: {haiku_response.usage.input_tokens}, Output Tokens: {haiku_response.usage.output_tokens}")
    total_cost = calculate_subagent_cost("claude-3-haiku-20240307", haiku_response.usage.input_tokens, haiku_response.usage.output_tokens)
    console.print(f"Haiku Sub-agent Cost: ${total_cost:.2f}")
    
    # Generate images using the StabilityAI API
    stability_api_key = "sk-AuAAM6v7JpfkyDPsiQC5GqJFolxlMdt70lZ9RQAgFoGuQ9vw"
    generated_images = list(generate_image(prompt, stability_api_key, project_name, image_count, image_size, num_steps, cfg_scale, sampler))
    
    if haiku_response.usage.output_tokens >= 4000:  # Threshold set to 4000 as a precaution
        console.print("[bold yellow]Warning:[/bold yellow] Output may be truncated. Attempting to continue the response.")
        continuation_response_text = haiku_sub_agent(prompt, search_query, previous_haiku_tasks, use_search, continuation=True)
        response_text += continuation_response_text

    console.print(Panel(response_text, title="[bold blue]Haiku Sub-agent Result[/bold blue]", title_align="left", border_style="blue", subtitle="Task completed, sending result to Opus 👇"))
    return response_text, generated_images

def opus_refine(objective, sub_task_results, filename, projectname, continuation=False):
    print("\nCalling Opus to provide the refined final output for your objective:")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Objective: " + objective + "\n\nSub-task results:\n" + "\n".join(sub_task_results) + "\n\nPlease review and refine the sub-task results into a cohesive final output. Add any missing information or details as needed. When working on code projects, ONLY AND ONLY IF THE PROJECT IS CLEARLY A CODING ONE please provide the following:\n1. Project Name: Create a concise and appropriate project name that fits the project based on what it's creating. The project name should be no more than 20 characters long.\n2. Folder Structure: Provide the folder structure as a valid JSON object, where each key represents a folder or file, and nested keys represent subfolders. Use null values for files. Ensure the JSON is properly formatted without any syntax errors. Please make sure all keys are enclosed in double quotes, and ensure objects are correctly encapsulated with braces, separating items with commas as necessary.\nWrap the JSON object in <folder_structure> tags.\n3. Code Files: For each code file, include ONLY the file name NEVER EVER USE THE FILE PATH OR ANY OTHER FORMATTING YOU ONLY USE THE FOLLOWING format 'Filename: <filename>' followed by the code block enclosed in triple backticks, with the language identifier after the opening backticks, like this:\n\n​python\n<code>\n​"}
            ]
        }
    ]

    opus_response = client.messages.create(
        model="claude-3-opus-20240229",
        max_tokens=4096,
        messages=messages
    )

    refined_output = opus_response.content[0].text.strip()
    console.print(f"Input Tokens: {opus_response.usage.input_tokens}, Output Tokens: {opus_response.usage.output_tokens}")
    total_cost = calculate_subagent_cost("claude-3-opus-20240229", opus_response.usage.input_tokens, opus_response.usage.output_tokens)
    console.print(f"Opus Refine Cost: ${total_cost:.2f}")
    
    # Include the generated images in the refined output
    for i, image_file_path in enumerate(sub_task_results[-1][2]):
        refined_output += f"\n\nGenerated Image {i+1}:\n![{projectname} Image {i+1}]({image_file_path})"

    if opus_response.usage.output_tokens >= 4000 and not continuation:  # Threshold set to 4000 as a precaution
        console.print("[bold yellow]Warning:[/bold yellow] Output may be truncated. Attempting to continue the response.")
        continuation_response_text = opus_refine(objective, sub_task_results + [refined_output], filename, projectname, continuation=True)
        refined_output += "\n" + continuation_response_text

    console.print(Panel(refined_output, title="[bold green]Final Output[/bold green]", title_align="left", border_style="green"))
    return refined_output

def create_folder_structure(project_name, folder_structure, code_blocks):
    # Create the project folder
    try:
        os.makedirs(project_name, exist_ok=True)
        console.print(Panel(f"Created project folder: [bold]{project_name}[/bold]", title="[bold green]Project Folder[/bold green]", title_align="left", border_style="green"))
    except OSError as e:
        console.print(Panel(f"Error creating project folder: [bold]{project_name}[/bold]\nError: {e}", title="[bold red]Project Folder Creation Error[/bold red]", title_align="left", border_style="red"))
        return

    # Recursively create the folder structure and files
    create_folders_and_files(project_name, folder_structure, code_blocks)

def create_folders_and_files(current_path, structure, code_blocks):
    for key, value in structure.items():
        path = os.path.join(current_path, key)
        if isinstance(value, dict):
            try:
                os.makedirs(path, exist_ok=True)
                console.print(Panel(f"Created folder: [bold]{path}[/bold]", title="[bold blue]Folder Creation[/bold blue]", title_align="left", border_style="blue"))
                create_folders_and_files(path, value, code_blocks)
            except OSError as e:
                console.print(Panel(f"Error creating folder: [bold]{path}[/bold]\nError: {e}", title="[bold red]Folder Creation Error[/bold red]", title_align="left", border_style="red"))
        else:
            code_content = next((code for file, code in code_blocks if file == key), None)
            if code_content:
                try:
                    with open(path, 'w') as file:
                        file.write(code_content)
                    console.print(Panel(f"Created file: [bold]{path}[/bold]", title="[bold green]File Creation[/bold green]", title_align="left", border_style="green"))
                except IOError as e:
                    console.print(Panel(f"Error creating file: [bold]{path}[/bold]\nError: {e}", title="[bold red]File Creation Error[/bold red]", title_align="left", border_style="red"))
            else:
                console.print(Panel(f"Code content not found for file: [bold]{key}[/bold]", title="[bold yellow]Missing Code Content[/bold yellow]", title_align="left", border_style="yellow"))


def read_file(file_path):
    with open(file_path, 'r') as file:
        content = file.read()
    return content

def user_image_confirmation():
    while True:
        confirmation = input("Does the generated image meet the objective? (y/n): ").lower()
        if confirmation == 'y':
            return True, None
        elif confirmation == 'n':
            feedback = input("Please provide feedback on how to improve the image: ")
            return False, feedback
        else:
            print("Invalid input. Please enter 'y' or 'n'.")


#bot.py

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

#chain.py

import os
import logging
from typing import List
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, load_prompt
from langchain.schema import AIMessage, HumanMessage
from honcho import Message

# Initialize logging
logging.basicConfig(level=logging.INFO)

# Load environment variables
load_dotenv()
def format_chat_history(chat_history: List[Message], user_input=None):
    messages = [
        (
            "user: " + message.content
            if isinstance(message, HumanMessage)
            else "ai: " + message.content
        )
        for message in chat_history
    ]
    if user_input:
        messages.append(f"user: {user_input}")

    return "\n".join(messages)
# LangChain prompts
SYSTEM_STATE_COMMENTARY = load_prompt(
    os.path.join(os.path.dirname(__file__), "langchain_prompts/state_commentary.yaml")
)
SYSTEM_STATE_LABELING = load_prompt(
    os.path.join(os.path.dirname(__file__), "langchain_prompts/state_labeling.yaml")
)
SYSTEM_STATE_CHECK = load_prompt(
    os.path.join(os.path.dirname(__file__), "langchain_prompts/state_check.yaml")
)

class StateExtractor:
    """Handles state extraction and label generation using Anthropic's API."""

    def __init__(self):
        """Initializes the API client with security best practices."""
        self.api_key = os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            logging.error("ANTHROPIC_API_KEY not set. Please configure the environment variable.")
            raise EnvironmentError("API key not found in environment variables.")
        self.anthropic = ChatAnthropic(api_key=self.api_key, model='claude-3-opus-20240229')

    def format_chat_history(self, chat_history: List[Message], user_input=None) -> str:
        """Formats chat history into a string."""
        messages = [
            f"user: {msg.content}" if isinstance(msg, HumanMessage) else f"ai: {msg.content}"
            for msg in chat_history
        ]
        if user_input:
            messages.append(f"user: {user_input}")
        return "\n".join(messages)

    async def generate_state_commentary(self, existing_states: List[str], chat_history: List[Message], input: str) -> str:
        """Generate a commentary on the current state of the user."""
        chat_history_str = self.format_chat_history(chat_history)
        existing_states_str = "\n".join(existing_states) if existing_states else "None"
        
        # Create the prompt using templates
        system_message = "Review the following states and inputs: {existing_states}, {chat_history}"
        user_message = input  # Direct user input
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message.format(existing_states=existing_states_str, chat_history=chat_history_str)),
            ("human", user_message)
        ])
        
        # Formatting into a proper message for the model
        formatted_prompt = prompt.format_messages()
        messages = [msg.content for msg in formatted_prompt]  # Extracting content from formatted messages
        
        # Invoking the model
        response = self.anthropic.invoke(messages)
        return response.content

    async def generate_state_label(self, existing_states: List[str], state_commentary: str) -> str:
        """Generate a state label from a commentary on the user's state."""
        
        # Constructing a proper message format
        formatted_message = "Review state commentary: {state_commentary}".format(
            state_commentary=state_commentary
        )
        
        # If your system expects a single string or a structured prompt value 
        # Here I assume that a string is acceptable
        try:
            # Directly pass the string if the API supports it
            response = self.anthropic.invoke(formatted_message)
            return response.content
        except Exception as e:
            # Log the error or handle it according to your application's needs
            print(f"Failed to invoke model with error: {str(e)}")
            return "Error generating state label"
        

    async def check_state_exists(self, existing_states: List[str], state: str) -> bool:
        """Check if a user state is new or already is stored."""
        system_message_prompt = SystemMessagePromptTemplate(prompt=SYSTEM_STATE_CHECK)
        state_check = ChatPromptTemplate.from_messages([system_message_prompt])
        messages = state_check.format_messages(
            existing_states="\n".join(existing_states),
            state=state,
        )
        system_message_content = messages[0].content if messages else ""
        input_message = f"{system_message_content}\n{state}"
        response = self.anthropic.invoke(
            input=input_message,
            max_tokens=500,
        )
        return response != "None"

    async def generate_state(self, existing_states: List[str], chat_history: List[Message], input: str):
        """Determine the user's state from the current conversation state."""
        state_commentary = await self.generate_state_commentary(existing_states, chat_history, input)
        state_label = await self.generate_state_label(existing_states, state_commentary)
        is_state_new = await self.check_state_exists(existing_states, state_label)
        return is_state_new, state_label
    
#graph.py

import os
import dspy
from dspy import Example
from typing import List, Optional
from dspy.teleprompt import BootstrapFewShot
from dotenv import load_dotenv
from chain import StateExtractor, format_chat_history
from response_metric import metric

from honcho import Message, Session

load_dotenv()

# Configure DSPy
dspy_claude = dspy.Claude(model="claude-3-haiku-20240307", max_tokens=1000)
dspy.settings.configure(lm=dspy_claude)


# DSPy Signatures
class Thought(dspy.Signature):
    """Generate a thought about the user's needs"""

    user_input = dspy.InputField()
    thought = dspy.OutputField(desc="a prediction about the user's mental state")


class Response(dspy.Signature):
    """Generate a response for the user based on the thought provided"""

    user_input = dspy.InputField()
    thought = dspy.InputField()
    response = dspy.OutputField(desc="keep the conversation going, be engaging")


# DSPy Module
class ChatWithThought(dspy.Module):
    generate_thought = dspy.Predict(Thought)
    generate_response = dspy.Predict(Response)

    def forward(
        self,
        chat_input: str,
        user_message: Optional[Message] = None,
        session: Optional[Session] = None,
        response: Optional[str] = None,
        assessment_dimension: Optional[str] = None,
    ):
        # call the thought predictor
        thought = self.generate_thought(user_input=chat_input)

        if session and user_message:
            session.create_metamessage(
                user_message, metamessage_type="thought", content=thought.thought
            )

        # call the response predictor
        response = self.generate_response(
            user_input=chat_input, thought=thought.thought
        )

        return response  # this is a prediction object


async def chat(
    user_message: Message,
    session: Session,
    chat_history: List[Message],
    input: str,
    optimization_threshold=3,
):
    # Instantiate the StateExtractor
    state_extractor = StateExtractor()
    user_state_storage = dict(session.user.metadata)
    
    # First we need to see if the user has any existing states
    existing_states = list(user_state_storage.keys())
    
    # Then we need to take the user input and determine the user's state/dimension/persona
    is_state_new, user_state = await state_extractor.generate_state(
        existing_states=existing_states,
        chat_history=chat_history,
        input=input
    )
    print(f"USER STATE: {user_state}")
    print(f"IS STATE NEW: {is_state_new}")
    
    # Add metamessage to message to keep track of what label got assigned to what message
    if session and user_message:
        session.create_metamessage(
            user_message,
            metamessage_type="user_state",
            content=user_state
        )
    
    user_chat_module = ChatWithThought()
    
    # Save the user_state if it's new
    if is_state_new:
        user_state_storage[user_state] = {"chat_module": {}, "examples": []}
    user_state_data = user_state_storage[user_state]
    
    # Optimize the state's chat module if we've reached the optimization threshold
    examples = user_state_data["examples"]
    print(f"Num examples: {len(examples)}")
    session.user.update(metadata=user_state_storage)
    if len(examples) >= optimization_threshold:
        # Convert example from dicts to dspy Example objects
        optimizer_examples = []
        for example in examples:
            optimizer_example = Example(**example).with_inputs("chat_input", "response", "assessment_dimension")
            optimizer_examples.append(optimizer_example)
        
        # Optimize chat module
        optimizer = BootstrapFewShot(metric=metric, max_rounds=5)
        compiled_chat_module = optimizer.compile(user_chat_module, trainset=optimizer_examples)
        print(f"COMPILED_CHAT_MODULE: {compiled_chat_module}")
        user_state_storage[user_state]["chat_module"] = compiled_chat_module.dump_state()
        print(f"DUMPED_STATE: {compiled_chat_module.dump_state()}")
        user_chat_module = compiled_chat_module
    
    # Update User in Honcho
    session.user.update(metadata=user_state_storage)
    
    # Use that pipeline to generate a response
    chat_input = format_chat_history(chat_history, user_input=input)
    response = user_chat_module(
        user_message=user_message,
        session=session,
        chat_input=chat_input
    )
    
    # Remove AI prefix
    response = response.response.replace("ai:", "").strip()
    
    print("========== CHAT HISTORY ==========")
    dspy_claude.inspect_history(n=2)
    print("======= END CHAT HISTORY =========")
    
    return response


#response_metric.py

import dspy

gpt4T = dspy.OpenAI(model='gpt-4-1106-preview', max_tokens=1000, model_type='chat')

class MessageResponseAssess(dspy.Signature):
    """Assess the quality of a response along the specified dimension."""
    chat_input = dspy.InputField()
    assessment_dimension = dspy.InputField()  # user state
    example_response = dspy.InputField()
    ai_response_label = dspy.OutputField(desc="yes or no")


def metric(example, pred, trace=None):
    """Assess the quality of a response along the specified dimension."""

    chat_input = example.chat_input
    assessment_dimension = f"The user is in the following state: {example.assessment_dimension}. Is the AI response appropriate for this state? Respond with Yes or No."
    example_response = pred.response

    with dspy.context(lm=gpt4T):
        assessment_result = dspy.Predict(MessageResponseAssess)(
            chat_input=chat_input, 
            assessment_dimension=assessment_dimension,
            example_response=example_response
        )

    is_appropriate = assessment_result.ai_response_label.lower() == 'yes'

    print("======== OPTIMIZER HISTORY ========")
    gpt4T.inspect_history(n=5)
    print("======== END OPTIMIZER HISTORY ========")
    
    return is_appropriate

