# Telegram Research Bot

A smart research bot built on Telegram that gathers research on a given topic by searching Google results via SERPAPI, summarizing information with Google Gemini, and generating a PDF report using ReportLab. Optionally, the bot can email you the PDF summary directly.

## Overview

This bot integrates several services to offer a smooth research workflow:
- **Search & Summarization:** Uses SERPAPI to fetch top Google search results and the Google Gemini API to generate concise bullet-point summaries.
- **PDF Generation:** Creates a well-formatted PDF report using ReportLab.
- **Email Functionality:** Sends the PDF report as an email attachment when requested.
- **Telegram Interaction:** Managed through Telegram commands for a user-friendly experience.

## Prerequisites

- **Python 3.8+**  
- **Telegram Bot Token:** Obtain one from [BotFather](https://core.telegram.org/bots#6-botfather).  
- **Google Gemini API Key:** For summarization capabilities.  
- **SERPAPI API Key:** To fetch Google search results.  
- **Email Credentials:** A valid email (e.g., Gmail) and its app password for SMTP operations.

## Project Structure

- **main.py** - Main script for the research telegram bot.
- **.env** - Environment variables for API keys and email credentials.
- **README.md** - Project documentation.


## Installation & Setup

### Clone this repository.
git clone https://github.com/deepikaksr/telegram_research_bot.git cd telegram_research_bot

### Install Required Packages
Use pip to install the necessary libraries:
```bash
pip install nest_asyncio requests python-dotenv python-telegram-bot reportlab google-generativeai
```

### Set Up .env:
Create a `.env` file in the project root with:
```ini
TELEGRAM_TOKEN=your_telegram_bot_token_here
GEMINI_API_KEY=your_gemini_api_key_here
SERPAPI_API_KEY=your_serpapi_api_key_here
EMAIL_USER=your_email_here
EMAIL_PASS=your_email_password_here
```

## Commands & Workflow

- **/start**
  - **Usage:** `/start`
  - **Description:** Greets the user and provides instructions.

- **/research <topic>**
  - **Usage:** `/research <topic>`
  - **Description:** 
    - Searches for the specified topic.
    - Fetches and summarizes the top 3 research results.
    - Replies with the summary and offers a PDF version via email.

- **/researchpdf <topic>**
  - **Usage:** `/researchpdf <topic>`
  - **Description:**
    - Similar to `/research`, but directly sends a PDF summary in the chat.
    - Also asks if you want the PDF emailed.

- **Email Response**
  - **Usage:** Reply with your email (e.g., `example@gmail.com`).
  - **Description:**  
    - After `/research` or `/researchpdf`, reply with your email to receive the PDF.
    - You can decline by replying with "no", "not now", etc.

### How It Works

- **Data Fetching:** Uses SERPAPI to get Google search results.
- **Summarization:** Utilizes Google Gemini to generate bullet-point summaries.
- **PDF Generation:** Creates a PDF report with ReportLab.
- **Email Sending:** Delivers the PDF via Gmail's SMTP service.


## Running the App
Run the main script with:
```bash
python3 main.py
```
This will initiate the Telegram polling loop and set your bot live. Once running, use the Telegram client (mobile or desktop) to interact with your bot using the commands above.

