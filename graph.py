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
