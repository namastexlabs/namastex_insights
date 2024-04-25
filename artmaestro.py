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

# State: Get Objective
objective = input("Please enter your objective with or without a text file path: ")

# Check if the input contains a file path
if "./" in objective or "/" in objective:
    # Extract the file path from the objective
    file_path = re.findall(r'[./\w]+\.[\w]+', objective)[0]
    # Read the file content
    with open(file_path, 'r') as file:
        file_content = file.read()
    # Update the objective string to remove the file path
    objective = objective.split(file_path)[0].strip()
else:
    file_content = None

# State: Use Search Decision
use_search = input("Do you want to use search? (y/n): ").lower() == 'y'

# Create the .md filename
sanitized_objective = re.sub(r'\W+', '_', objective)
timestamp = datetime.now().strftime("%H-%M-%S")

# Define the project_name variable
project_name = f"{timestamp}_{sanitized_objective}"

# Prompt the user for the number of images to generate
image_count = int(input("Enter the number of images to generate: "))

# Provide pre-selected size options
size_options = {
    "1": (256, 256),
    "2": (680, 240),
    "3": (768, 768),
    "4": (1024, 1024)
}

print("Select an image size:")
for option, size in size_options.items():
    print(f"{option}. {size[0]}x{size[1]}")

size_choice = input("Enter the option number: ")
image_size = size_options.get(size_choice, (512, 512))

# Prompt the user for additional parameters
num_steps = int(input("Enter the number of refinement steps (default: 30): ") or 30)
cfg_scale = float(input("Enter the configuration scale (default: 7.0): ") or 7.0)

sampler_options = {
    "1": "K_DPM_2_ANCESTRAL",
    "2": "K_EULER_ANCESTRAL",
    "3": "K_HEUN",
    "4": "K_DPM_2"
}

print("Select a sampling method:")
for option, sampler in sampler_options.items():
    print(f"{option}. {sampler}")

sampler_choice = input("Enter the option number: ")
sampler = sampler_options.get(sampler_choice, "K_DPM_2_ANCESTRAL")

task_exchanges = []
haiku_tasks = []

while True:
    # State: Orchestrator
    previous_results = [result for _, result, _ in task_exchanges]
    if not task_exchanges:
        # Pass the file content only in the first iteration if available
        opus_result, file_content_for_haiku, search_query = opus_orchestrator(objective, file_content, previous_results, use_search)
    else:
        opus_result, _, search_query = opus_orchestrator(objective, previous_results=previous_results, use_search=use_search)

    if "The task is complete:" in opus_result:
        # If Opus indicates the task is complete, exit the loop
        final_output = opus_result.replace("The task is complete:", "").strip()
        break
    else:
        sub_task_prompt = opus_result
        # Append file content to the prompt for the initial call to haiku_sub_agent, if applicable
        if file_content_for_haiku and not haiku_tasks:
            sub_task_prompt = f"{sub_task_prompt}\n\nFile content:\n{file_content_for_haiku}"
        
        while True:
            # State: Sub-agent
            sub_task_result, generated_images = haiku_sub_agent(sub_task_prompt, search_query, haiku_tasks, use_search, project_name=project_name, image_count=image_count, image_size=image_size, num_steps=num_steps, cfg_scale=cfg_scale, sampler=sampler)
            # Log the task and its result for future reference
            haiku_tasks.append({"task": sub_task_prompt, "result": sub_task_result})
            # Record the exchange for processing and output generation
            task_exchanges.append((sub_task_prompt, sub_task_result, [image_file_path for _, image_file_path in generated_images]))
            
            # State: Image Confirmation
            image_confirmed, feedback = user_image_confirmation()
            if image_confirmed:
                # State: Video Generation Prompt
                selected_image_path, seed, cfg_scale, motion_bucket_id = user_video_generation_prompt([image_file_path for _, image_file_path in generated_images])
                if selected_image_path:
                    # State: Video Generation
                    try:
                        video_file_path = generate_video(selected_image_path, seed, cfg_scale, motion_bucket_id)
                        # Display the generated video to the user (you can use a HTML5 video player or any other method)
                        console.print(f"Generated video: {video_file_path}")
                    except Exception as e:
                        console.print(f"Error generating video: {str(e)}")
                break
            else:
                console.print("The generated images do not meet the objective. Updating the sub-task prompt with user feedback.")
                sub_task_prompt += f"\n\nUser Feedback: {feedback}"
        
        # Prevent file content from being included in future haiku_sub_agent calls
        file_content_for_haiku = None

# State: Refine Output
refined_output = opus_refine(objective, [result for _, result, _ in task_exchanges], timestamp, project_name)

# Extract the project name from the refined output
project_name_match = re.search(r'Project Name: (.*)', refined_output)
project_name = project_name_match.group(1).strip() if project_name_match else project_name

# Extract the folder structure from the refined output
folder_structure_match = re.search(r'<folder_structure>(.*?)</folder_structure>', refined_output, re.DOTALL)
folder_structure = {}
if folder_structure_match:
    json_string = folder_structure_match.group(1).strip()
    try:
        folder_structure = json.loads(json_string)
    except json.JSONDecodeError as e:
        console.print(Panel(f"Error parsing JSON: {e}", title="[bold red]JSON Parsing Error[/bold red]", title_align="left", border_style="red"))
        console.print(Panel(f"Invalid JSON string: [bold]{json_string}[/bold]", title="[bold red]Invalid JSON String[/bold red]", title_align="left", border_style="red"))

# Extract code files from the refined output
code_blocks = re.findall(r'Filename: (\S+)\s*```[\w]*\n(.*?)\n```', refined_output, re.DOTALL)

# State: Create Folder Structure
create_folder_structure(project_name, folder_structure, code_blocks)

# Truncate the sanitized_objective to a maximum of 50 characters
max_length = 25
truncated_objective = sanitized_objective[:max_length] if len(sanitized_objective) > max_length else sanitized_objective

# Update the filename to include the project name
filename = f"{timestamp}_{truncated_objective}.md"

# State: Save Exchange Log
exchange_log = f"Objective: {objective}\n\n"
exchange_log += "=" * 40 + " Task Breakdown " + "=" * 40 + "\n\n"
for i, (prompt, result, image_file_paths) in enumerate(task_exchanges, start=1):
    exchange_log += f"Task {i}:\n"
    exchange_log += f"Prompt: {prompt}\n"
    exchange_log += f"Result: {result}\n"
    for j, image_file_path in enumerate(image_file_paths):
        exchange_log += f"Image {j+1}: {image_file_path}\n"
    exchange_log += "\n"

exchange_log += "=" * 40 + " Refined Final Output " + "=" * 40 + "\n\n"
exchange_log += refined_output

console.print(f"\n[bold]Refined Final output:[/bold]\n{refined_output}")

with open(filename, 'w') as file:
    file.write(exchange_log)
print(f"\nFull exchange log saved to {filename}")