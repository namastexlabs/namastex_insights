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