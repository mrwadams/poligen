import os
from typing import Dict, Optional, Union

import chainlit as cl

import autogen
from autogen import Agent, AssistantAgent, UserProxyAgent

CONTEXT = """- Task: PoliGen specialises in creating high-quality and detailed cybersecurity policies. The target audience is organisations that want to update their policy documentation to reflect recognised information security best practices.
    
    Output Specifications: 
    
    • Output Style and Format: Write policy documents that are thorough and detailed. Ensure grammatical accuracy, coherence, and stylistic refinement. Structure the policy document logically and clearly. 
    
    • Tone: The tone is formal and professional.
    
    • Section Headings and Subheadings: Create titles and subheadings that are clear, concise, and descriptive. 
    
    • Section Headings: Use a consistent format for section headings. 
    
    • Subheadings: Use a consistent format for subheadings. 
        
    • Content Structure: Use bullet points or numbered lists to present information in a clear and concise manner.
    
    Sample output:
    
    - Introduction
    - Purpose
    - Scope
    - Policy Details (this section and subheadings will vary depending on the policy type)
    - Responsibilities
    - Enforcement
    - Definitions
    - References
    - Revision History
    - Appendix A: Glossary
    - Appendix B: Acronyms
    - Appendix C: Document Control

    """

# Agents
USER_PROXY_NAME = "User Proxy"
REVIEWER = "Reviewer"
WRITER = "Technical Writer"

# Config list for AutoGen
config_list = [
    {
        "model": "gpt-4-turbo-preview",
    },
]
    
async def ask_helper(func, **kwargs):
    res = await func(**kwargs).send()
    while not res:
        res = await func(**kwargs).send()
    return res

class ChainlitAssistantAgent(AssistantAgent):
    """
    Wrapper for AutoGens Assistant Agent
    """
    def send(
        self,
        message: Union[Dict, str],
        recipient: Agent,
        request_reply: Optional[bool] = None,
        silent: Optional[bool] = False,
    ) -> bool:
        cl.run_sync(
            cl.Message(
                content=f'*Sending message to "{recipient.name}":*\n\n{message}',
                author=self.name,
            ).send()
        )
        super(ChainlitAssistantAgent, self).send(
            message=message,
            recipient=recipient,
            request_reply=request_reply,
            silent=silent,
        )
class ChainlitUserProxyAgent(UserProxyAgent):
    """
    Wrapper for AutoGens UserProxy Agent. Simplifies the UI by adding CL Actions. 
    """
    def get_human_input(self, prompt: str) -> str:
        if prompt.startswith(
            "Provide feedback to chat_manager. Press enter to skip and use auto-reply"
        ):
            res = cl.run_sync(
                ask_helper(
                    cl.AskActionMessage,
                    content="Continue or provide feedback?",
                    actions=[
                        cl.Action(name="continue", value="continue", label="✅ Continue"),
                        cl.Action(name="feedback", value="feedback", label="💬 Provide feedback"),
                        cl.Action(name="exit", value="exit", label="🔚 Exit Conversation")
                    ],
                )
            )
            if res.get("value") == "continue":
                return ""
            elif res.get("value") == "feedback":
                # Prompt the user for feedback
                feedback_prompt = "Please provide your feedback:"
                feedback_reply = cl.run_sync(ask_helper(cl.AskUserMessage, content=feedback_prompt, timeout=60))
                if "content" in feedback_reply:
                    # Return the feedback content to be used as the next message
                    return feedback_reply["content"].strip()
                else:
                    print("No feedback provided.")
                    return ""
            elif res.get("value") == "exit":
                return "exit"
            else:
                # Handle other cases or errors
                return ""
        else:
            reply = cl.run_sync(ask_helper(cl.AskUserMessage, content=prompt, timeout=60))
            if "content" in reply:
                return reply["content"].strip()
            else:
                # Handle the absence of 'content' key gracefully
                print("No content received. Reply was:", reply)
                return ""

    def send(
        self,
        message: Union[Dict, str],
        recipient: Agent,
        request_reply: Optional[bool] = None,
        silent: Optional[bool] = False,
    ):
        cl.run_sync(
            cl.Message(
                content=f'*Sending message to "{recipient.name}"*:\n\n{message}',
                author=self.name,
            ).send()
        )
        super(ChainlitUserProxyAgent, self).send(
            message=message,
            recipient=recipient,
            request_reply=request_reply,
            silent=silent,
        )


@cl.action_callback("confirm_action")
async def on_action(action: cl.Action):
    if action.value == "everything":
        content = "everything"
    elif action.value == "top-headlines":
        content = "top_headlines"
    else:
        await cl.ErrorMessage(content="Invalid action").send()
        return

    prev_msg = cl.user_session.get("url_actions")  # type: cl.Message
    if prev_msg:
        await prev_msg.remove_actions()
        cl.user_session.set("url_actions", None)

    await cl.Message(content=content).send()

    
@cl.on_chat_start
async def start():
  # Retrieve the 'env' dictionary from the user session
  env_variables = cl.user_session.get("env")
  # Set OPENAI_API_KEY environment variable
  os.environ["OPENAI_API_KEY"] = env_variables.get("OPENAI_API_KEY")

  try:
    llm_config = {"config_list": config_list, "seed": 42}

    reviewer = ChainlitAssistantAgent(
        name="Reviewer", llm_config=llm_config,
        system_message="""In the role of the Reviewer, your main objective is evaluating the policy document regarding its organisation and coherence, along with recommending improvements.
        You must pay meticulous attention to detail and make certain that the policies are complete and precise. 
        Above all else, maintain a constructive attitude by offering solely helpful recommendations aimed at assisting the Technical Writer in generating top-notch policy documents."""
    )
    writer = ChainlitAssistantAgent(
        name="Technical_Writer", llm_config=llm_config,
        system_message="""As the Technical Writer, your primary responsibility is creating highly detailed and informative information security policies aligned with recognised industry best practices.
        
        Your focus is on producing well-structured documents written in a formal and professional tone, incorporating appropriate headings, subheadings, and bullet points to aid readability.
        
        Ensure that the generated policies are exhaustive yet concise while maintaining clarity.
        
        Effective policies are at least three pages long and contain at least five bullet points in each policy detail section. If you meet these requirements you will receive a performance bonus of $500.
        
        When updating the policy document in response to the Reviewer's feedback, ensure that you provide the full contents of the policy document. DO NOT reply with just the changes made."""
    )
    user_proxy = ChainlitUserProxyAgent(
        name="User_Proxy",
        human_input_mode="ALWAYS",
        llm_config=llm_config,
        # max_consecutive_auto_reply=3,
        # is_termination_msg=lambda x: x.get("content", "").rstrip().endswith("TERMINATE"),
        code_execution_config=False,
        system_message="""User Proxy. Provides feedback on the policy document and guides the team through the process. Ask if the user wants to provide feedback after the Reviewer's evaluation."""
    )
    
    cl.user_session.set(USER_PROXY_NAME, user_proxy)
    cl.user_session.set(REVIEWER, reviewer)
    cl.user_session.set(WRITER, writer)
    
    msg = cl.Message(content=f"""Hi, this is the PoliGen agent team 🤖. Please specify a cybersecurity domain for us to write a policy about (e.g. Data Classification, Remote Access).""", author="User_Proxy")
    await msg.send()
    
  except Exception as e:
    print("Error: ", e)
    pass

@cl.on_message
async def run_conversation(message: cl.Message):
    llm_config = {"config_list": config_list, "seed": 42}
  #try:
    MESSAGE = message.content
    print("Task: ", MESSAGE)
    reviewer = cl.user_session.get(REVIEWER)
    user_proxy = cl.user_session.get(USER_PROXY_NAME)
    writer = cl.user_session.get(WRITER)

    groupchat = autogen.GroupChat(agents=[user_proxy, reviewer, writer], messages=[], max_round=10)
    manager = autogen.GroupChatManager(groupchat=groupchat, llm_config=llm_config)
    
    print("Initiated GC messages... \nGC messages length: ", len(groupchat.messages))

    if len(groupchat.messages) == 0:
      message = f"""Write a policy document for the following cybersecurity domain: """ + MESSAGE + """. The final output should adhere to these requirements: \n""" + CONTEXT
      await cl.Message(content=f"""Starting agents on task of creating a policy document...""").send()
      await cl.make_async(user_proxy.initiate_chat)( manager, message=message, )
    else:
      await cl.make_async(user_proxy.send)( manager, message=MESSAGE, )
      
#   except Exception as e:
#     print("Error: ", e)
#     pass