from graph.state import State
import asyncio
import feedparser
from newspaper import Article
from datetime import datetime
from ai_resources.initialize_db import insert_embeddings
from ai_resources.initialize_llm import initialize_model, chat_with_model
from langchain_mcp_adapters.client import MultiServerMCPClient, load_mcp_tools
from langgraph.prebuilt import create_react_agent
from langchain_mcp_adapters.tools import load_mcp_tools
from smolagents import ToolCallingAgent, LiteLLMModel

def news_scraper(state: State):
    """
    Scrapes news articles from Economic Times and NDTV Sports and processes them.
    """
    rss_url_list = [
        "https://b2b.economictimes.indiatimes.com/rss/recentstories",
        "https://sports.ndtv.com/rss/all"        
                    ]
    corpus = []
    # Parsing the RSS feeds from Economic Times and NDTV 
    for news_url in rss_url_list:
        parsed_feed = feedparser.parse(news_url)
        # Iterating through each entry in the feed
        for entry in parsed_feed.entries:
            try:
                url = entry.link
                # published = entry.published_parsed
                # pub_date = datetime(*published[:6])
                
                article = Article(url)
                article.download()
                article.parse()

                # adding article title and text to corpus
                data = article.title + '\n' + article.text
                corpus.append(data)
            except Exception as e:
                print(f"Error processing article {entry.title}: {e}")
                continue
    print("Successfully scraped and processed news articles.")
    return{
        "extracted_text": corpus,
        "request_id": state.get("request_id", ""),
    }

def summarize_articles(state: State):
    """  
    Uses an LLM to generate clean and detailed summaries of extracted news articles.
    Returns:
        Numbered summaries of all articles, each on a new line.
    """

    corpus = state.get("extracted_text", "")
    added_prompt = state.get("prompt", "")
    if not corpus:
        return {"summary": ""}
    
    combined_text = "\n\n".join(corpus)
    prompt = (
    "Summarize each of the following news articles individually.\n\n"
    "Instructions:\n"
    "- Number each summary (e.g., 1., 2., 3.).\n"
    "- Keep each summary factual, concise, and relevant.\n"
    "- Remove all advertisements, promotional content, and external links.\n"
    "- If available, include date/time and source-specific facts.\n"
    "- Do not add introductions, conclusions, or extra commentary.\n\n "
    f"{added_prompt}\n\n"
    "Begin summarizing the articles below:\n\n"
    f"{combined_text}"
    )

    response = chat_with_model(prompt)
    content = response[0] if isinstance(response, list) else response
    
    print("Articles summarized successfully.")
    return {
        "summary": content, #saving the current generated summary of news articles
        "request_id": state.get("request_id", ""),
    }

def save_embeddings(state: State):
    """
    Saves the embeddings of the articles to the database.
    """
    # creating embedding of article title and text and pushing to vector DB
    corpus = state.get("extracted_text", [])
    insert_embeddings(corpus)
    print("Embeddings saved successfully.")

#Only for testing purposes
def display_summary(state: State):
    """
    Displays the summary of all the articles spacing them appropriately with line breaks and numbering them.
    """
    summary = state.get("summary", "")

    if not summary:
        print("No summary available.")
    else:
        print("Summary:")
        print(summary)
    
async def handle_user_query(state: State):
    user_input = state.get("user_input", "")
    # user_input = "news summaries related to Meesho and PhonePe from vector database"
    
    client = MultiServerMCPClient({
        "yfin-server": {
            "url" :"http://127.0.0.1:8000/mcp",
            "transport": "streamable_http"
        }}
    )

    mcp_tools = await client.get_tools()

    ##To get the list of available tools in the MCP server
    # print("Available tools in the MCP server:")
    # for tool in mcp_tools:
    #     print(tool.name)
    model = initialize_model()
    agent = create_react_agent(model, mcp_tools)
    agent_response = await agent.ainvoke(
        {"messages": [
            {"role": "user",
            "content": user_input}
        ]}
    )
    # To handle state persistence
    state["extracted_text"] = ""
    # Taking only message content into consideration as metadata is not required here
    state['extracted_text'] = "\n".join(m.content for m in agent_response["messages"])


    # For testing agent tool calls
    for m in agent_response["messages"]:
        m.pretty_print()

    #For updating the final prompt in summarize_articles
    prompt = """
            Summarize latest news first followed by the past similar news articles.
            """
    state["prompt"] = prompt

    # Generate a summary indicating latest and past news 


    # --------- Using Ollama (Currently having issues in fetching tools) -------

    # mcp_tools = await load_mcp_tools(client)
    # model = LiteLLMModel(
    #     model_id = "ollama/phi3"
    # )
    # agent = ToolCallingAgent(tools = mcp_tools, model = model)
    # result = agent.run(user_input)

    # print(result)
    return state

def greet_node(state:State):
    print("Hello User. The AI news generation has begun.")