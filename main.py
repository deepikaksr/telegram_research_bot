import nest_asyncio
nest_asyncio.apply()

import logging
import requests
import os
import html
import asyncio
import re
from io import BytesIO
from dotenv import load_dotenv

# Telegram imports
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ReportLab imports (for PDF generation using Platypus)
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

# Google Gemini (if needed)
import google.generativeai as genai

# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

# Configure Gemini API if available
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# Summarization with Gemini
def gemini_summarize(prompt: str) -> str:
    """
    Summarizes the provided text using the Gemini API.
    Uses the endpoint and payload format you provided.
    """
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    )
    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response = requests.post(endpoint, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        result = response.json()
        candidates = result.get("candidates", [])
        if candidates:
            return candidates[0]["content"]["parts"][0]["text"]
        else:
            return "No response generated."
    except Exception as e:
        logger.error("Error generating AI response: %s", e)
        return "Summary not available."


# PDF Generation with Platypus
def generate_pdf_platypus(digest_text: str, topic: str) -> BytesIO:
    """
    Generates a PDF from the plain text digest using ReportLab's Platypus.
    The digest_text is expected to have newline characters.
    For PDF formatting, we convert newlines to <br/> tags.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=inch,
        rightMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
        title="Research Summary",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        spaceAfter=0.3 * inch,
    )
    body_style = styles["BodyText"]
    body_style.fontName = "Helvetica"
    body_style.fontSize = 12

    story = []
    # Add the topic as a title
    topic_paragraph = Paragraph(f"Research Summary for: {html.escape(topic)}", title_style)
    story.append(topic_paragraph)
    story.append(Spacer(1, 0.2 * inch))

    # For PDF, convert newline characters into <br/> tags for proper line breaks.
    digest_html = digest_text.replace("\n", "<br/>")
    digest_paragraph = Paragraph(digest_html, body_style)
    story.append(digest_paragraph)

    doc.build(story)
    buffer.seek(0)
    return buffer


# Telegram Bot Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command."""
    await update.message.reply_text(
        "Hello! Use /research <topic> to get a research summary.\n"
        "Use /researchpdf <topic> to get a PDF summary."
    )

async def research(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /research command by sending a text summary."""
    if context.args:
        topic = " ".join(context.args)
        await update.message.reply_text(f"Searching for: {html.escape(topic)}")
        digest = await perform_research(topic)
        # Send the digest as HTML; newlines will be preserved.
        await update.message.reply_text(digest, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("Usage: /research <topic>")

async def research_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /researchpdf command by generating a PDF summary and sending it."""
    if context.args:
        topic = " ".join(context.args)
        await update.message.reply_text(f"Searching for: {html.escape(topic)}")
        digest = await perform_research(topic)
        # For PDF, we use the plain text version (which has newline characters)
        pdf_file = await asyncio.to_thread(generate_pdf_platypus, digest, topic)
        await update.message.reply_document(
            document=pdf_file,
            filename="research_summary.pdf",
            disable_notification=True
        )
    else:
        await update.message.reply_text("Usage: /researchpdf <topic>")


# Main Research Logic
async def perform_research(topic: str) -> str:
    """
    Searches for the topic using SerpAPI, summarizes the top 3 results via Gemini,
    and returns a digest as HTML-formatted text with clickable links.
    The digest uses newline characters for line breaks.
    """
    serpapi_url = "https://serpapi.com/search"
    params = {
        "engine": "google",
        "q": topic,
        "api_key": SERPAPI_API_KEY,
        "num": 3,
    }
    response = requests.get(serpapi_url, params=params)
    results = response.json().get("organic_results", [])
    if not results:
        return "No results found."

    digest_lines = []
    digest_lines.append(f"<b>Research Summary for:</b> {html.escape(topic)}\n\n")
    for result in results:
        title = html.escape(result.get("title", "No Title"))
        link = result.get("link", "No Link")
        snippet = html.escape(result.get("snippet", ""))
        prompt = f"Summarize the following text in key bullet points:\n\n{snippet}\n\nBullet Points:"
        try:
            summary_text = await asyncio.to_thread(gemini_summarize, prompt)
            summary_text = html.escape(summary_text)
        except Exception as e:
            logger.error(f"Error summarizing text for prompt '{prompt}': {e}")
            summary_text = "Summary not available."

        digest_lines.append(f"<b>{title}</b>\n")
        digest_lines.append(f"{summary_text}\n")
        digest_lines.append(f"<b>Source link:</b> <a href=\"{link}\">{link}</a>\n\n")
    return "".join(digest_lines)


# Main Entry Point
async def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("research", research))
    app.add_handler(CommandHandler("researchpdf", research_pdf))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
