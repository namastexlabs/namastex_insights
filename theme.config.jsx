export default {
      logo: <span>Namastex Insights: Elevating Discord Interactions with AI-Powered Personalization and Context Management - made with Lumentis</span>,
      editLink: {
        component: null,
      },
      project: {
        link: "https://github.com/hrishioa/lumentis",
      },
      feedback: {
        content: null,
      },
      footer: {
        text: (
          <>
            Made with 🫶 by&nbsp;
            <a href="https://twitter.com/hrishioa" target="_blank">
              Hrishi - say hi!
            </a>
          </>
        ),
      },
      head: (
        <>
          <meta property="og:title" content="Namastex Insights: Elevating Discord Interactions with AI-Powered Personalization and Context Management" />
          <meta property="og:description" content="This is a Discord bot source code written in Python. The bot is designed to provide AI-powered conversation and art generation capabilities. It uses Anthropic's Claude API for natural language processing and conversation, and StabilityAI's API for generating images and videos based on user prompts.The code is structured into several files:art_maestro.py: Contains functions for orchestrating the art generation process, including breaking down user objectives, executing sub-tasks, and refining the final output.bot.py: The main entry point of the bot, handling Discord events, slash commands, and user interactions.chain.py: Defines the StateExtractor class for determining user states based on chat history and input.graph.py: Implements the ChatWithThought module for generating thoughts and responses based on user states, and optimizing the chat module using few-shot learning.response_metric.py: Defines a metric function for assessing the quality of generated responses using GPT-4.The bot leverages the Honcho framework for managing user sessions, message history, and metadata. It uses a loop of orchestration, sub-task execution, and refinement to handle complex art generation tasks based on user objectives.Overall, the source code demonstrates a sophisticated Discord bot that combines AI-driven conversation and art generation to provide an engaging and interactive user experience." />
          <meta name="robots" content="noindex, nofollow" />
          <link rel="icon" type="image/x-icon" href="https://raw.githubusercontent.com/HebeHH/lumentis/choose-favicon/assets/default-favicon.png" />
        </>
      ),
    };
    