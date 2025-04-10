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
import smtplib
from email.message import EmailMessage

# Telegram imports
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ReportLab imports
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

# Google Gemini
import google.generativeai as genai

# Load .env
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

# Gemini setup
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# State tracking
user_states = {}

# Gemini summarization
def gemini_summarize(prompt: str) -> str:
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

# PDF generation
def generate_pdf_platypus(digest_text: str, topic: str) -> BytesIO:
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
    title_style = ParagraphStyle("TitleStyle", parent=styles["Heading1"], fontSize=18)
    body_style = styles["BodyText"]
    body_style.fontSize = 12

    story = [
        Paragraph(f"Research Summary for: {html.escape(topic)}", title_style),
        Spacer(1, 0.2 * inch),
        Paragraph(digest_text.replace("\n", "<br/>"), body_style),
    ]
    doc.build(story)
    buffer.seek(0)
    return buffer

# Email sending
def send_email(recipient: str, pdf_buffer: BytesIO, topic: str) -> str:
    msg = EmailMessage()
    msg["Subject"] = f"Research Summary for {topic}"
    msg["From"] = EMAIL_USER
    msg["To"] = recipient
    msg.set_content(f"Hello,\n\nAttached is the PDF summary for the topic: {topic}.\n\nRegards,\nResearch Bot")

    pdf_buffer.seek(0)
    msg.add_attachment(pdf_buffer.read(), maintype="application", subtype="pdf", filename="research_summary.pdf")

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_USER, EMAIL_PASS)
            smtp.send_message(msg)
        return "Email sent successfully!"
    except Exception as e:
        logger.error("Failed to send email: %s", e)
        return "Failed to send email. Please try again later."

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! Use /research <topic> or /researchpdf <topic> to get summaries.")

# /research
async def research(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        topic = " ".join(context.args)
        await update.message.reply_text(f"Searching for: {html.escape(topic)}")
        digest = await perform_research(topic)
        await update.message.reply_text(digest, parse_mode=ParseMode.HTML)

        # Also offer to email the PDF version
        pdf_buffer = await asyncio.to_thread(generate_pdf_platypus, digest, topic)
        user_states[update.effective_user.id] = {
            "waiting_for_email": True,
            "pdf_buffer": pdf_buffer,
            "topic": topic,
        }
        await update.message.reply_text("📩 Would you like to receive this summary as a PDF via email? Just reply with your email ID.")
    else:
        await update.message.reply_text("Usage: /research <topic>")

# /researchpdf
async def research_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        topic = " ".join(context.args)
        await update.message.reply_text(f"Searching for: {html.escape(topic)}")
        digest = await perform_research(topic)
        pdf_buffer = await asyncio.to_thread(generate_pdf_platypus, digest, topic)
        await update.message.reply_document(pdf_buffer, filename="research_summary.pdf")

        # Ask for email
        user_states[update.effective_user.id] = {
            "waiting_for_email": True,
            "pdf_buffer": pdf_buffer,
            "topic": topic,
        }
        await update.message.reply_text("📩 Want the PDF sent to your email? Reply with your email ID.")
    else:
        await update.message.reply_text("Usage: /researchpdf <topic>")

# Email reply handler
async def handle_email_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reply = update.message.text.strip()

    if user_id in user_states and user_states[user_id].get("waiting_for_email"):
        # Handle "no" responses
        if reply.lower() in ["no", "no thanks", "nah", "not now", "later", "not interested"]:
            await update.message.reply_text("Okay! Let me know if you need anything else.")
            del user_states[user_id]
            return

        # Extract email using regex
        match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", reply)
        if match:
            email = match.group(0)
            pdf_buffer = user_states[user_id]["pdf_buffer"]
            topic = user_states[user_id]["topic"]
            result = await asyncio.to_thread(send_email, email, pdf_buffer, topic)
            await update.message.reply_text(result)
            del user_states[user_id]
        else:
            await update.message.reply_text(
                "Couldn't find a valid email in your message.\n"
                "Please reply with a valid email ID (e.g., `example@gmail.com`) or say 'no'."
            )
    else:
        await update.message.reply_text("I wasn't expecting an email/invalid text right now. Use /research or /researchpdf first.")

# Main research logic
async def perform_research(topic: str) -> str:
    serpapi_url = "https://serpapi.com/search"
    params = {
        "engine": "google",
        "q": topic,
        "api_key": SERPAPI_API_KEY,
        "num": 10,
    }

    try:
        response = requests.get(serpapi_url, params=params)
        results = response.json().get("organic_results", [])
        if not results:
            return "No results found."

        valid_results = []
        for result in results:
            title = result.get("title")
            link = result.get("link")
            snippet = result.get("snippet")

            if title and link and snippet:
                valid_results.append({
                    "title": title,
                    "link": link,
                    "snippet": snippet
                })

            if len(valid_results) == 3:
                break

        if len(valid_results) < 3:
            return "Found limited relevant information for this topic. Please try a broader query."

        digest_lines = [f"<b>Research Summary for:</b> {html.escape(topic)}\n\n"]
        for item in valid_results:
            title = html.escape(item["title"])
            link = item["link"]
            snippet = html.escape(item["snippet"])
            prompt = f"Summarize the following text in bullet points:\n\n{snippet}\n\nBullet Points:"
            summary = await asyncio.to_thread(gemini_summarize, prompt)
            digest_lines.append(f"<b>{title}</b>\n{html.escape(summary)}\n<b>Source:</b> <a href=\"{link}\">{link}</a>\n\n")

        return "".join(digest_lines)

    except Exception as e:
        logger.error("Research error: %s", e)
        return "An error occurred while performing research."


# Main app
async def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("research", research))
    app.add_handler(CommandHandler("researchpdf", research_pdf))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email_reply))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
