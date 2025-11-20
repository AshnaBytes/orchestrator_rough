# Purpose: Isolates all external LLM API logic.

from groq import AsyncGroq
from .schemas import PhraserInput
from .prompt_templates import get_formatted_prompt
import logging

logger = logging.getLogger(__name__)

# This is the "Adapter" for our LLM.
# All the logic for calling the Groq API lives here.
async def generate_llm_response(
    input_data: PhraserInput,
    client: AsyncGroq
) -> str:
    """
    Generates a persuasive response from the Groq API.
    """
    
    # 1. Get the prompt
    system_prompt, user_prompt = get_formatted_prompt(input_data)
    
    logger.info(f"Generating phrase for key: {input_data.response_key}")

    # 2. Call Groq API
    try:
        chat_completion = await client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            model="llama-3.3-70b-versatile", # Fast and capable model
            temperature=0.7,
            max_tokens=128,
        )
        
        # 3. Parse and return the response
        response_text = chat_completion.choices[0].message.content
        
        if not response_text:
            logger.error("LLM returned an empty response.")
            return "I'm sorry, I'm not sure how to respond to that."

        logger.info(f"Generated response: {response_text}")
        return response_text

    except Exception as e:
        logger.error(f"Error calling Groq API: {e}", exc_info=True)
        # Return a safe, generic fallback response
        return "We seem to be having a technical issue. Please try again in a moment."