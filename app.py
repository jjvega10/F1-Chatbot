#### Streamlit Streaming using LM Studio as OpenAI Standin
#### run with `streamlit run app.py`

# !pip install pypdf langchain langchain_openai selenium webdriver-manager htmltabletomd beautifulsoup4

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from typing import Annotated
from webdriver_manager.chrome import ChromeDriverManager
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
import htmltabletomd
import re
import pandas as pd
from io import StringIO
import htmlmin
from bs4 import BeautifulSoup


# ------------------------------
# Utility: scrape site
# ------------------------------
def extract_text_from_dynamic_site(url, wait_time=10):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        driver.get(url)
        print(f"Loaded: {url}")
        time.sleep(wait_time)
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        return soup
    except Exception as e:
        print(f"Error: {e}")
        return None
    finally:
        driver.quit()


# Drivers
with open("data-cache/drivers_standings.html", "r") as f:
    dr_minified = f.read()

# Teams
with open("data-cache/team_standings.html", "r") as f:
    tm_minified = f.read()

# Schedule
with open("data-cache/schedule_text.txt", "r") as f:
    schedule_text = f.read()

# Current date
curr_date = pd.Timestamp.now().strftime('%b %d, %Y')

# ------------------------------
# Tool: Get F1 standings
# ------------------------------
@tool
def get_f1_driver_standings() -> str:
    """Get the current F1 driver standings. 
    Use it to determine the points for each driver in the drivers' championship."""
    return dr_minified

@tool
def get_f1_team_standings() -> str:
    """Get the current F1 team standings. 
    Use it to determine the points for each team in the teams' championship."""
    return tm_minified


# ------------------------------
# Initialize Toolkit
# ------------------------------
toolkit = [get_f1_driver_standings, get_f1_team_standings]


# ------------------------------
# App Config
# ------------------------------
st.set_page_config(page_title="F1 Chatbot", page_icon="🏎️")
st.title("🏎️ F1 Chatbot")


# ------------------------------
# Response Function
# ------------------------------
def get_response(user_query, chat_history):
    # Build conversation history string
    history_str = "\n".join(
        f"Human: {m.content}" if isinstance(m, HumanMessage) else f"AI: {m.content}"
        for m in chat_history
    )

    # Local LM Studio endpoint
    llm = ChatOpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")

    # Define prompt (must include input + agent_scratchpad)
    prompt = ChatPromptTemplate.from_template(
        f"""You are an expert in Formula 1 that will assist the user with questions regarding the sport.
There are 24 races in the current season and the schedule is as follows:
{schedule_text}
The current date is {curr_date}. Consider this date when asked about the next race (closest date after the current date) or the previous race (closest date before the current date).
There have been a few changes in terms of driver line-ups.
If you need to know which driver belongs to a certain team or which team a driver belongs to, use `get_f1_driver_standings`.
Use `get_f1_driver_standings` and `get_f1_team_standings` to assist the user."""+
        """
Conversation so far:
{input}

Use tools if needed to answer questions.
{agent_scratchpad}"""
    )

    # Build agent
    agent = create_openai_tools_agent(llm, toolkit, prompt)
    agent_executor = AgentExecutor(agent=agent, tools=toolkit, verbose=True)

    # Merge history and user input
    full_input = f"{history_str}\n\nUser: {user_query}"

    # Get the final response (no streaming)
    result = agent_executor.invoke({"input": full_input})

    return result["output"]

# ------------------------------
# Session State
# ------------------------------
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        AIMessage(content="Hello, I am an F1 chatbot. How can I help you?"),
    ]

# Display history
for message in st.session_state.chat_history:
    role = "AI" if isinstance(message, AIMessage) else "Human"
    with st.chat_message(role):
        st.write(message.content)

# ------------------------------
# User Input
# ------------------------------
user_query = st.chat_input("Type your message here...")
if user_query:
    st.session_state.chat_history.append(HumanMessage(content=user_query))

    with st.chat_message("Human"):
        st.markdown(user_query)

    with st.chat_message("AI"):
        response_text = get_response(user_query, st.session_state.chat_history)
        st.write(response_text)

    st.session_state.chat_history.append(AIMessage(content=response_text))