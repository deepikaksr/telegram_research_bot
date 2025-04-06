import nest_asyncio
nest_asyncio.apply()

import logging
import requests
import os
import html  # for escaping HTML special characters
import re
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import asyncio
from dotenv import load_dotenv
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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)


def gemini_summarize(prompt: str) -> str:
    """
    Summarizes the provided text using the Gemini API.
    Uses the endpoint and payload format you provided.
    """
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
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

def format_for_pdf(digest_html: str) -> str:
    """
    1. Replaces <a href="...">Read more</a> with 'Read more: <link>' so the link is visible.
    2. Strips remaining HTML tags.
    3. Removes any ** markers (replacing them with nothing).
    """
    # 1. Insert the actual link text so it's visible in PDF
    digest_with_links = re.sub(
        r'<a href="([^"]+)">Read more</a>',
        r'Read more: \1',
        digest_html
    )
    # 2. Strip remaining HTML tags
    plain_digest = re.sub(r'<[^>]+>', '', digest_with_links)
    # 3. Remove double-asterisks, e.g. **this** => this
    plain_digest = plain_digest.replace('**', '')
    return plain_digest

def generate_pdf(plain_text: str, topic: str) -> BytesIO:
    """
    Generates a PDF file from the plain text summary using ReportLab.
    - The topic is displayed in a larger, bold font.
    - The rest of the text is displayed in normal font.
    """
    buffer = BytesIO()
    # Set page size, e.g., LETTER
    pdf = canvas.Canvas(buffer, pagesize=LETTER)
    pdf.setTitle("Research Summary")

    # Start drawing at (x, y)
    width, height = LETTER
    x_margin = inch
    y_position = height - inch  # 1 inch from the top

    # 1) Draw the topic in larger bold font
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(x_margin, y_position, f"Research Summary for: {topic}")
    y_position -= 0.5 * inch  # Move down half an inch

    # 2) Switch to normal font for the rest of the text
    pdf.setFont("Helvetica", 12)

    # Split the plain text by lines and draw each line
    lines = plain_text.splitlines()
    for line in lines:
        # If the line starts with something like "*Bullet point*" we can do some simple bold.
        # But let's keep it straightforward: just normal text for all lines.
        # If you want a bullet point, you could do line = f"• {line}" or something similar.
        pdf.drawString(x_margin, y_position, line)
        y_position -= 14  # move down 14 points (~ line spacing)

        # If we run out of space, create a new page
        if y_position < inch:
            pdf.showPage()
            y_position = height - inch
            pdf.setFont("Helvetica", 12)

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    await update.message.reply_text(
        "Hello! Use /research <topic> to get a research summary "
        "or /researchpdf <topic> for a PDF summary."
    )

async def research(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /research command by processing the topic and sending a summary in text."""
    if context.args:
        topic = " ".join(context.args)
        await update.message.reply_text(
            f"Searching for: {html.escape(topic)}", parse_mode=ParseMode.HTML
        )
        digest = await perform_research(topic)
        await update.message.reply_text(digest, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("Usage: /research <topic>")

async def research_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /researchpdf command by processing the topic, generating a PDF, and sending it."""
    if context.args:
        topic = " ".join(context.args)
        # Let the user know we're working
        await update.message.reply_text(
            f"Searching for: {html.escape(topic)}", parse_mode=ParseMode.HTML
        )

        # Get the HTML digest
        digest_html = await perform_research(topic)
        # Convert to plain text for PDF
        plain_digest = format_for_pdf(digest_html)

        # Generate PDF in a separate thread
        pdf_file = await asyncio.to_thread(generate_pdf, plain_digest, topic)

        # Send the PDF
        await update.message.reply_document(
            document=pdf_file, filename="research_summary.pdf"
        )
    else:
        await update.message.reply_text("Usage: /researchpdf <topic>")

async def perform_research(topic: str) -> str:
    """
    Searches for the topic using SerpAPI, summarizes the top 3 results via Gemini,
    and returns a compiled digest using HTML formatting.
    """
    serpapi_url = "https://serpapi.com/search"
    params = {
        "engine": "google",
        "q": topic,
        "api_key": SERPAPI_API_KEY,
        "num": 3  # Retrieve the top 3 results
    }

    response = requests.get(serpapi_url, params=params)
    results = response.json().get("organic_results", [])

    if not results:
        return "No results found."

    summaries = []
    for result in results:
        title = html.escape(result.get("title", "No Title"))
        link = result.get("link", "No Link")  # URLs don't need escaping
        snippet = html.escape(result.get("snippet", ""))

        prompt = (
            f"Summarize the following text in key bullet points:\n\n"
            f"{snippet}\n\nBullet Points:"
        )
        try:
            # Run the Gemini API call in a separate thread to avoid blocking the event loop
            summary_text = await asyncio.to_thread(gemini_summarize, prompt)
            summary_text = html.escape(summary_text)
        except Exception as e:
            logger.error(f"Error summarizing text for prompt '{prompt}': {e}")
            summary_text = "Summary not available."

        # Format the summary in HTML with bold title and a clickable link
        summaries.append(
            f"<b>{title}</b>\n{summary_text}\n<a href=\"{link}\">Read more</a>\n\n"
        )

    digest = f"<b>Research Summary for:</b> {html.escape(topic)}\n\n" + "".join(summaries)
    return digest

async def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("research", research))
    app.add_handler(CommandHandler("researchpdf", research_pdf))
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
