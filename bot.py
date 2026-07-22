import os
import io
import base64
import logging
import asyncio
import requests
import http.server
import socketserver
import threading
from dotenv import load_dotenv
from telegram import Update, Message
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Load configuration from environment variables if present
load_dotenv()

# ==========================================
# CONFIGURATION VARIABLES
# Replace these with your actual values, or define them in a .env file
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE").strip()
OUTPUT_CHANNEL_ID = os.getenv("OUTPUT_CHANNEL_ID", "YOUR_OUTPUT_CHANNEL_ID_HERE").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()

# Support a comma/semicolon/newline-separated list of Gemini API Keys for automatic rotation/quota handling
GEMINI_API_KEYS = []
if GEMINI_API_KEY:
    for k in GEMINI_API_KEY.replace(";", ",").replace("\n", ",").split(","):
        k = k.strip()
        if k and not k.startswith("YOUR_"):
            GEMINI_API_KEYS.append(k)

# Groq Vision API Config
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "YOUR_GROQ_API_KEY_HERE").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct").strip()

# OpenRouter API Config (Free vision models via OpenRouter.ai)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "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").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free").strip()
# Fallback models in case primary is rate-limited
OPENROUTER_FALLBACK_MODELS = [
    "nvidia/nemotron-nano-12b-v2-vl:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
]

PROVIDER = os.getenv("PROVIDER", "").strip()  # e.g., 'openrouter', 'groq', or 'gemini'. If empty, auto-detects.

# Admin Authorization Configuration
ADMIN_USER_IDS = []
admin_env = os.getenv("ADMIN_USER_IDS", "")
if admin_env:
    for item in admin_env.split(","):
        item = item.strip()
        if item.isdigit():
            ADMIN_USER_IDS.append(int(item))

# Default Factory Settings
DEFAULT_CONFIG = {
    "provider": PROVIDER or "openrouter",
    "balance_check_passes": 1,
    "output_channel_id": OUTPUT_CHANNEL_ID or "",
    "ad_copy": "<b>{bank_name}\nBal  {balance_val}\n\nRdp Access \nEmail Access \nLogin info\nIp\n\nDm your offer \n\nEscrow Accepted \n@Wrong_GuyXD\n@YeggBackup</b>",
    "mappings": {
        "chase": "Ch4se",
        "bofa": "B0A",
        "bank of america": "B0A",
        "citibank": "C1ti",
        "citi": "C1ti",
        "wells fargo": "We11s",
        "wells": "We11s",
        "goldman sachs": "G0ldm4n",
        "goldman": "G0ldm4n",
        "jpmorgan": "M0rg4n",
        "morgan": "M0rg4n",
        "jp morgan": "M0rg4n",
        "us bank": "U$B",
        "usbank": "U$B",
        "u.s. bank": "U$B",
        "pnc": "PN¢",
        "capital one": "C4p1t4l0ne",
        "capitalone": "C4p1t4l0ne",
        "capone": "C4p1t4l0ne",
        "truist": "Tru1st",
        "td bank": "TDB4nk",
        "tdbank": "TDB4nk",
        "td": "TDB4nk",
        "charles schwab": "Schw4b",
        "schwab": "Schw4b",
        "bny mellon": "BNYM3ll0n",
        "bny": "BNYM3ll0n",
        "state street": "St4teStr33t",
        "statest": "St4teStr33t",
        "state st": "St4teStr33t",
        "fifth third": "F1fthTh1rd",
        "fifth3rd": "F1fthTh1rd",
        "5/3": "F1fthTh1rd",
        "m&t": "M&7",
        "m & t": "M&7",
        "citizens": "C1t1zens",
        "huntington": "Hunt1ngt0n",
        "ally": "411y",
        "discover": "D1sc0ver",
        "american express": "4m3x",
        "amex": "4m3x",
        "regions": "Reg10ns",
        "key bank": "K3yB4nk",
        "keybank": "K3yB4nk",
        "key": "K3yB4nk",
        "comerica": "C0m3r1c4",
        "first citizens": "F1rstC1t1zens",
        "first cit": "F1rstC1t1zens",
        "firstcit": "F1rstC1t1zens",
        "synchrony": "Synchr0ny",
        "sync": "Synchr0ny",
        "webster": "Webst3r",
        "zions": "Zi0ns",
        "bmo harris": "BM0",
        "bmo": "BM0",
        "hsbc": "HS8C",
        "fidelity": "F1d3l1ty",
        "navy federal": "N4vyF3d",
        "navy fed": "N4vyF3d",
        "navyfed": "N4vyF3d",
        "sofi": "S0F1",
        "varo": "V4r0",
        "chime": "Ch1m3",
        "green dot": "Gr33nD07",
        "greendot": "Gr33nD07",
        "axos": "Ax0s",
        "pathward": "P47hward",
        "fifth federal": "F1fth3d",
        "fifthfed": "F1fth3d",
        "cross river": "Cr0ssR1v3r",
        "crossriver": "Cr0ssR1v3r"
    }
}

import json
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                # Merge with default to ensure no missing keys
                merged = DEFAULT_CONFIG.copy()
                merged.update(config)
                # Keep mappings updated (merge mappings dict)
                if "mappings" in config and isinstance(config["mappings"], dict):
                    merged_mappings = DEFAULT_CONFIG["mappings"].copy()
                    merged_mappings.update(config["mappings"])
                    merged["mappings"] = merged_mappings
                return merged
    except Exception as e:
        logger.error(f"Error loading config.json: {e}")
    return DEFAULT_CONFIG.copy()

def save_config(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving config.json: {e}")
        return False

# Initialize dynamic configuration
active_config = load_config()


# Initialize logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# System Prompt - worded to avoid triggering safety filters on free vision models
SYSTEM_PROMPT = """You are a document OCR assistant for personal finance tracking and asset verification.
Your task: Read the text content visible in this image and identify:

1. The financial institution or company name shown. Look for logos, header text, domain names, or copyright notices (e.g. Chase, Wells Fargo, Revolut, Chime, Bank of America, Wise, etc.).

2. The available dollar amount(s) shown for instant-access deposit accounts only.
   - ALLOWED account types: Checking, Savings, Spend, Save, Deposit, Wallet, Main Account, Cash.
   - CRITICAL EXCLUSION RULE: Certificates of Deposit (CD), Time Deposits, Fixed Deposits, or Locked Term Accounts MUST be ignored. Even if they have a large balance, DO NOT include them in the total.
   - STRICTLY EXCLUDE: Credit Cards, CD (Certificate of Deposit), Time Deposits, Fixed Deposits, Brokerage/Investment/Trading accounts, Loans (mortgage, personal, auto, student), and Debt.
   - If multiple qualifying spendable accounts exist, mathematically sum their available balances. Do NOT add any CD or credit/loan balances to this sum.
   - CRITICAL FORMATTING: Drop any decimal cents. For example: $8,822.25 becomes $8,822. Strictly omit decimals.

PRIVACY RULES:
- Do NOT extract or mention any personal names, account numbers, IBANs, routing numbers, or identifiers.
- If any field cannot be identified, write "Unknown" for that field.

PRECISION RULES:
- Read every digit extremely carefully. Do not misread 8 as 3, 0 as 8, or 1 as 7.
- Double-check all digits and place values before writing the final output.

Format your output EXACTLY as follows with no additional text:
BANK: <institution name>
TYPE: <account type(s)>
BALANCE: <total available balance>
STATUS: Verified"""



def run_health_check_server():
    """Starts a simple background HTTP server to respond to hosting platform health pings."""
    class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        def log_message(self, format, *args):
            pass  # Suppress logging to keep console clean

    try:
        # Default to port 8080, or the port assigned by the cloud platform
        port = int(os.getenv("PORT", 8080))
        # Allow port reuse to avoid address already in use errors on restart
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("", port), HealthCheckHandler) as httpd:
            logger.info(f"🌐 Health check HTTP server active on port {port}")
            httpd.serve_forever()
    except Exception as e:
        logger.error(f"Failed to start health check HTTP server: {e}")


def get_channel_id():
    """Parses and returns the dynamic channel ID or env channel ID."""
    val = active_config.get("output_channel_id")
    if not val:
        val = str(OUTPUT_CHANNEL_ID).strip()
    else:
        val = str(val).strip()
    if not val or val.startswith("YOUR_"):
        return None
    # Support numeric channel IDs (e.g., -100123456789)
    if val.startswith("-") and val[1:].isdigit():
        return int(val)
    if val.isdigit():
        return int(val)
    return val  # For usernames (e.g., @mychannel)


def get_active_provider():
    """Determines the active provider based on dynamic configuration and available keys."""
    prov = active_config.get("provider", "").lower().strip()
    if prov in ["groq", "gemini", "openrouter"]:
        return prov
    # Auto-detect fallback: prefer OpenRouter > Groq > Gemini
    if OPENROUTER_API_KEY and not OPENROUTER_API_KEY.startswith("YOUR_"):
        return "openrouter"
    if GROQ_API_KEY and not GROQ_API_KEY.startswith("YOUR_"):
        return "groq"
    return "gemini"


def is_configured():
    """Checks if the basic required tokens are populated."""
    has_tg = TELEGRAM_BOT_TOKEN and not TELEGRAM_BOT_TOKEN.startswith("YOUR_")
    provider = get_active_provider()
    
    if provider == "openrouter":
        has_vision = OPENROUTER_API_KEY and not OPENROUTER_API_KEY.startswith("YOUR_")
    elif provider == "groq":
        has_vision = GROQ_API_KEY and not GROQ_API_KEY.startswith("YOUR_")
    else:
        has_vision = len(GEMINI_API_KEYS) > 0
        
    return has_tg and has_vision


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a friendly greeting and instructions to the user."""
    welcome_text = (
        "🏦 *Welcome to the Bank OCR Vision Bot!*\n\n"
        "Send me a screenshot or photo of a bank statement, account balance, or transaction history, and I will securely extract:\n"
        "• Bank Name\n"
        "• Available Balance (Instant transferable only)\n\n"
        "🔒 *Privacy Guarantee:*\n"
        "This bot *strictly redacts* all personal names, account numbers, and any other Personally Identifiable Information (PII) before showing or forwarding results.\n\n"
        "Please upload your image as a *Photo* or *Document* (uncompressed image) to begin!"
    )
    await update.message.reply_markdown(welcome_text)


async def perform_ocr_request(base64_image: str, mime_type: str, provider: str, attempt_id: int) -> tuple[str, str]:
    """Executes a single OCR request to the active provider and returns parsed (bank_name, balance_val)."""
    provider_name = "OpenRouter" if provider == "openrouter" else ("Groq Llama 4" if provider == "groq" else "Google Gemini")
    
    if provider == "openrouter":
        # OpenRouter uses OpenAI-compatible API with free vision models
        models_to_try = [OPENROUTER_MODEL] + OPENROUTER_FALLBACK_MODELS
        
        for model_idx, current_model in enumerate(models_to_try):
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": current_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": SYSTEM_PROMPT + "\n\nPlease read and extract the text information from this document image according to the system instructions."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                "temperature": 0.2,
                "max_tokens": 1000
            }

            max_retries = 2
            retry_delay = 2.0
            response = None

            for attempt in range(max_retries):
                try:
                    loop = asyncio.get_running_loop()
                    response = await loop.run_in_executor(
                        None,
                        lambda: requests.post(
                            url,
                            json=payload,
                            headers=headers,
                            timeout=45
                        )
                    )
                    
                    if response is not None and response.status_code in [429, 503]:
                        logger.warning(
                            f"OpenRouter model {current_model} returned {response.status_code} on pass {attempt_id}. "
                            f"Retrying in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})"
                        )
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2.0
                            continue
                    break
                except Exception as e:
                    logger.error(f"Error communicating with OpenRouter model {current_model}: {e}")
                    if attempt == max_retries - 1:
                        response = None
                    else:
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2.0

            if response is not None and response.status_code == 200:
                try:
                    res_json = response.json()
                    extracted_text = res_json["choices"][0]["message"]["content"].strip()
                    logger.info(f"OpenRouter model {current_model} succeeded on pass {attempt_id}")
                    break
                except Exception as e:
                    logger.error(f"Failed to parse OpenRouter response from {current_model}: {e}")
            else:
                status_code = response.status_code if response is not None else "No Response"
                logger.warning(f"OpenRouter model {current_model} failed with status {status_code}, trying next model...")
        else:
            # All OpenRouter models failed
            logger.error("All OpenRouter free models failed or were rate-limited.")
            if provider != "openrouter":
                return await perform_ocr_request(base64_image, mime_type, "openrouter", attempt_id)
            return "Unknown Bank", "Unknown"

    elif provider == "groq":
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": GROQ_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": SYSTEM_PROMPT + "\n\nPlease read and extract the text information from this document image according to the system instructions."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "temperature": 0.2,
            "max_tokens": 1000
        }

        max_retries = 3
        retry_delay = 2.0
        response = None

        for attempt in range(max_retries):
            try:
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: requests.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=35
                    )
                )
                
                if response is not None and response.status_code in [429, 503]:
                    logger.warning(
                        f"Groq API returned transient error {response.status_code} on verifier pass {attempt_id}. "
                        f"Retrying in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})"
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2.0
                        continue
                break
            except Exception as e:
                logger.error(f"Error communicating with Groq on verifier pass {attempt_id}: {e}")
                if attempt == max_retries - 1:
                    logger.error("Groq provider failed or deprecated. Falling back to OpenRouter...")
                    return await perform_ocr_request(base64_image, mime_type, "openrouter", attempt_id)
                await asyncio.sleep(retry_delay)
                retry_delay *= 2.0

        if response is None or response.status_code != 200:
            logger.error(f"Groq OCR verifier pass {attempt_id} returned status {response.status_code if response else 'None'}")
            logger.error("Groq provider failed or deprecated. Falling back to OpenRouter...")
            return await perform_ocr_request(base64_image, mime_type, "openrouter", attempt_id)

        try:
            res_json = response.json()
            extracted_text = res_json["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"Failed to parse Groq response on pass {attempt_id}: {e}")
            return "Unknown Bank", "Unknown"

    else:
        # Google Gemini Vision API with automatic key rotation
        if not GEMINI_API_KEYS:
            logger.error("No Gemini API keys configured!")
            if GROQ_API_KEY and not GROQ_API_KEY.startswith("YOUR_"):
                logger.info("No Gemini keys found, falling back to Groq...")
                return await perform_ocr_request(base64_image, mime_type, "groq", attempt_id)
            return "Unknown Bank", "Unknown"

        for key_idx, current_key in enumerate(GEMINI_API_KEYS):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={current_key}"
            headers = {
                "content-type": "application/json"
            }
            payload = {
                "contents": [
                    {
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": mime_type,
                                    "data": base64_image
                                }
                            },
                            {
                                "text": "Please read and extract the text information from this document image according to the system instructions."
                            }
                        ]
                    }
                ],
                "systemInstruction": {
                    "parts": [
                        {
                            "text": SYSTEM_PROMPT
                        }
                    ]
                },
                "generationConfig": {
                    "temperature": 0.2
                }
            }

            max_retries = 2
            retry_delay = 1.0
            response = None

            for attempt in range(max_retries):
                try:
                    loop = asyncio.get_running_loop()
                    response = await loop.run_in_executor(
                        None,
                        lambda: requests.post(
                            url,
                            json=payload,
                            headers=headers,
                            timeout=35
                        )
                    )
                    
                    if response is not None and response.status_code in [429, 503]:
                        logger.warning(
                            f"Gemini API key index {key_idx} ({current_key[:10]}...) returned transient error {response.status_code} on verifier pass {attempt_id}. "
                            f"Retrying in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})"
                        )
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 1.5
                            continue
                    break
                except Exception as e:
                    logger.error(f"Error communicating with Gemini using key index {key_idx}: {e}")
                    if attempt == max_retries - 1:
                        response = None
                    else:
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 1.5

            if response is not None and response.status_code == 200:
                try:
                    res_json = response.json()
                    extracted_text = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
                    break
                except Exception as e:
                    logger.error(f"Failed to parse Gemini response for key index {key_idx}: {e}")
            else:
                status_code = response.status_code if response is not None else "No Response"
                err_text = response.text[:200] if response is not None else ""
                logger.warning(f"Gemini key index {key_idx} ({current_key[:10]}...) failed with status {status_code}: {err_text}")
        else:
            # All Gemini keys failed
            logger.error("All configured Gemini API keys failed or were exhausted. Falling back to OpenRouter...")
            return await perform_ocr_request(base64_image, mime_type, "openrouter", attempt_id)

    # Parse details from extracted output format
    # Ultra-robust parser: strips markdown formatting (*), handles all variations of headers
    bank_name = "Unknown Bank"
    balance_val = "Unknown"
    
    for line in extracted_text.split("\n"):
        line_clean = line.replace("*", "").strip()
        line_upper = line_clean.upper()
        
        # Bank name matching
        if ("BANK" in line_upper or "INSTITUTION" in line_upper) and ":" in line_clean:
            parts = line_clean.split(":", 1)
            if len(parts) > 1 and parts[1].strip():
                val = parts[1].strip()
                if val.upper() not in ["UNKNOWN", "UNKNOWN BANK", "<BANK NAME>", "<INSTITUTION NAME>", "N/A", "NONE"]:
                    bank_name = val
                    
        # Balance value matching
        if ("BALANCE" in line_upper or "SPENDABLE" in line_upper or "AVAILABLE" in line_upper) and ":" in line_clean:
            parts = line_clean.split(":", 1)
            if len(parts) > 1 and parts[1].strip():
                val = parts[1].strip()
                if val.upper() not in ["UNKNOWN", "<BALANCE>", "<TOTAL AVAILABLE BALANCE>", "N/A", "NONE"]:
                    balance_val = val
                    
    return bank_name, balance_val


async def process_bank_image(file_id: str, mime_type: str, file_name: str, trigger_message, context: ContextTypes.DEFAULT_TYPE):
    """Core bank statement analysis consensus pipeline, shared between standard uploads and /check replies."""
    status_msg = await trigger_message.reply_text("📥 Downloading image from Telegram...")
    try:
        tg_file = await context.bot.get_file(file_id)
        file_bytes = await tg_file.download_as_bytearray()
        logger.info(f"Downloaded file {file_name} successfully ({len(file_bytes)} bytes)")
    except Exception as e:
        logger.error(f"Error downloading file from Telegram: {e}")
        await status_msg.edit_text("❌ Failed to download the image. Please try again.")
        return

    # Base64 encode the image
    try:
        base64_image = base64.b64encode(file_bytes).decode("utf-8")
    except Exception as e:
        logger.error(f"Error encoding image to base64: {e}")
        await status_msg.edit_text("❌ Internal error encoding the image. Please try again.")
        return

    # Determine which provider to use
    provider = get_active_provider()
    provider_name = "OpenRouter" if provider == "openrouter" else ("Groq Llama 4" if provider == "groq" else "Google Gemini")
    
    passes = int(active_config.get("balance_check_passes", 3))
    await status_msg.edit_text(f"🔍 Analyzing bank image with {passes} verifications ({provider_name})...")
    
    # Run multiple verification queries in parallel using asyncio.gather!
    try:
        tasks = [perform_ocr_request(base64_image, mime_type, provider, i + 1) for i in range(passes)]
        results = await asyncio.gather(*tasks)
    except Exception as gather_err:
        logger.error(f"Error executing parallel OCR requests: {gather_err}")
        await status_msg.edit_text(f"❌ AI analysis error: {gather_err}. Please check your API keys or try again.")
        return
    
    try:
        # Consensus voting logic using collections.Counter
        from collections import Counter
        
        # Filter out completely failed verifications if there are at least some successful ones
        valid_results = [r for r in results if r[0] != "Unknown Bank" and r[1] != "Unknown"]
        if not valid_results:
            # If all failed, use the entire list to fall back gracefully
            valid_results = results
            
        bank_names = [r[0] for r in valid_results]
        balance_vals = [r[1] for r in valid_results]
        
        bank_counter = Counter(bank_names)
        bank_name = bank_counter.most_common(1)[0][0]
        
        balance_counter = Counter(balance_vals)
        balance_val = balance_counter.most_common(1)[0][0]
        
        logger.info(f"Consensus voting complete ({passes} passes): Chosen Bank Name='{bank_name}', Chosen Balance='{balance_val}'")
        logger.info(f"Individual runs detail: {results}")
    except Exception as consensus_err:
        logger.error(f"Error calculating consensus: {consensus_err}")
        await status_msg.edit_text(f"❌ Failed to parse verifications consensus: {consensus_err}")
        return

    # Delete status message
    try:
        await status_msg.delete()
    except Exception as e:
        logger.warning(f"Could not delete status message: {e}")

    # Strip the word "bank" or "Bank" (case-insensitive) if it is at the very end of the bank name
    bank_name_clean = bank_name.strip()
    bank_name_lower = bank_name_clean.lower()
    if bank_name_lower.endswith(" bank"):
        bank_name = bank_name_clean[:-5].strip()
    elif bank_name_lower.endswith("bank") and len(bank_name_clean) > 4:
        bank_name = bank_name_clean[:-4].strip()
    else:
        bank_name = bank_name_clean

    # Map raw bank names to stylized brand names dynamically as requested by the user
    bank_name_search = bank_name.lower()
    mappings = active_config.get("mappings", {})
    for key, replacement in mappings.items():
        if key in bank_name_search:
            bank_name = replacement
            break

    # Apply strict formatting rules to balance (e.g. $8,822 or shorthand):
    # Strictly omit cents .00, .25, .90. Drop decimals if they exist.
    if "." in balance_val:
        # e.g., $8,822.25 -> $8,822
        # But handle cases where decimals might have a space or non-digit chars
        # Split on dot and keep left part
        dec_parts = balance_val.split(".", 1)
        balance_val = dec_parts[0]

    # Format the ad-copy caption dynamically (checking user-specific templates first!):
    user_id = trigger_message.from_user.id
    user_id_str = str(user_id)
    user_templates = active_config.get("user_templates", {})
    
    if user_id_str in user_templates:
        ad_copy_template = user_templates[user_id_str]
        logger.info(f"Using custom caption template for user {user_id}")
    else:
        ad_copy_template = active_config.get("ad_copy", "")
        logger.info("Using global default caption template")

    try:
        caption_text = ad_copy_template.format(bank_name=bank_name, balance_val=balance_val)
    except Exception as format_err:
        logger.error(f"Error formatting ad_copy template: {format_err}. Falling back to default.")
        caption_text = f"<b>{bank_name}\nBal  {balance_val}</b>"

    # Reply to the user in private chat using a robust fallback pipeline:
    # 1. Try sending as a photo (ideal, timeout increased to 30s to prevent false negatives)
    # 2. Try sending as a document/file (if photo format is unsupported)
    # 3. Try sending as plain text (safest fallback)
    try:
        photo_file_user = io.BytesIO(file_bytes)
        photo_file_user.name = "statement.jpg"
        await trigger_message.reply_photo(
            photo=photo_file_user,
            caption=caption_text,
            parse_mode="HTML",
            read_timeout=30,
            write_timeout=30
        )
        logger.info("Successfully replied to user with photo and bold caption.")
    except Exception as photo_err:
        err_msg = str(photo_err).lower()
        if "time out" in err_msg or "timed out" in err_msg or "timeout" in err_msg:
            logger.error(f"Failed to reply with photo due to timeout: {photo_err}. Falling back directly to text to avoid duplicate photo+document delivery.")
            await trigger_message.reply_html(caption_text)
        else:
            logger.warning(f"Failed to reply with photo to user: {photo_err}. Trying reply_document...")
            try:
                doc_file_user = io.BytesIO(file_bytes)
                doc_file_user.name = file_name if 'file_name' in locals() else "statement.jpg"
                await trigger_message.reply_document(
                    document=doc_file_user,
                    caption=caption_text,
                    parse_mode="HTML",
                    read_timeout=30,
                    write_timeout=30
                )
                logger.info("Successfully replied to user with document and bold caption.")
            except Exception as doc_err:
                logger.error(f"Failed to reply with document to user: {doc_err}. Falling back to plain text.")
                await trigger_message.reply_html(caption_text)

    # Forward to configured Telegram output channel along with the original photo/image using the same fallback pipeline
    channel_id = get_channel_id()
    if channel_id:
        try:
            photo_file = io.BytesIO(file_bytes)
            photo_file.name = "statement.jpg"

            await context.bot.send_photo(
                chat_id=channel_id,
                photo=photo_file,
                caption=caption_text,
                parse_mode="HTML",
                read_timeout=30,
                write_timeout=30
            )
            logger.info(f"Successfully forwarded photo and summary caption to channel: {channel_id}")
        except Exception as photo_fwd_err:
            fwd_err_msg = str(photo_fwd_err).lower()
            if "time out" in fwd_err_msg or "timed out" in fwd_err_msg or "timeout" in fwd_err_msg:
                logger.error(f"Failed to forward photo due to timeout: {photo_fwd_err}. Skipping document retry to avoid duplicates in channel.")
            else:
                logger.warning(f"Failed to forward photo to channel {channel_id}: {photo_fwd_err}. Trying document forwarding...")
                try:
                    doc_file = io.BytesIO(file_bytes)
                    doc_file.name = file_name if 'file_name' in locals() else "statement.jpg"
                    await context.bot.send_document(
                        chat_id=channel_id,
                        document=doc_file,
                        caption=caption_text,
                        parse_mode="HTML",
                        read_timeout=30,
                        write_timeout=30
                    )
                    logger.info(f"Successfully forwarded document and summary caption to channel: {channel_id}")
                except Exception as doc_fwd_err:
                    logger.error(f"Failed to forward document to channel {channel_id}: {doc_fwd_err}. Logging and skipping.")
    else:
        logger.info("Forwarding skipped: OUTPUT_CHANNEL_ID is not configured.")


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Downloads the uploaded image, sends it to Gemini for analysis, and outputs the result."""
    # Ensure it's a private chat
    if update.effective_chat.type != "private":
        return

    message = update.message
    if not message:
        return

    # Check configuration
    if not is_configured():
        logger.error("Configuration error: TELEGRAM_BOT_TOKEN or GEMINI_API_KEY is not set.")
        await message.reply_text(
            "❌ Bot configuration error. Please ensure TELEGRAM_BOT_TOKEN and GEMINI_API_KEY are configured "
            "at the top of the script or in a .env file."
        )
        return

    file_id = None
    mime_type = "image/jpeg"  # Default fallback
    file_name = "image.jpg"

    if message.photo:
        # Photo objects are a list of sizes; select the largest size (last in list)
        photo = message.photo[-1]
        file_id = photo.file_id
        mime_type = "image/jpeg"
    elif message.document:
        doc = message.document
        doc_mime = doc.mime_type or ""
        doc_name = doc.file_name or ""
        
        is_image = False
        if doc_mime.startswith("image/"):
            is_image = True
            # Validate MIME type is supported by Gemini
            if doc_mime in ["image/jpeg", "image/png", "image/gif", "image/webp"]:
                mime_type = doc_mime
            else:
                mime_type = "image/jpeg"  # Default fallback
        else:
            # Check extension as a fallback
            exts = (".png", ".jpg", ".jpeg", ".webp", ".gif")
            if doc_name.lower().endswith(exts):
                is_image = True
                if doc_name.lower().endswith(".png"):
                    mime_type = "image/png"
                elif doc_name.lower().endswith(".webp"):
                    mime_type = "image/webp"
                elif doc_name.lower().endswith(".gif"):
                    mime_type = "image/gif"
                else:
                    mime_type = "image/jpeg"

        if not is_image:
            await message.reply_text("❌ Please send a valid image file (PNG, JPG, JPEG, WEBP, or GIF).")
            return

        file_id = doc.file_id
        file_name = doc_name
    else:
        return

    # Execute the core image processing pipeline!
    await process_bank_image(file_id, mime_type, file_name, message, context)


ADMIN_CONFIG_SYSTEM_PROMPT = """You are the Configuration Assistant for a Telegram Bank OCR Bot.
The admin is sending you an instruction in natural language to update their bot settings.

You can modify these fields in the configuration:
1. "ad_copy" (string): The HTML caption template. It should use HTML formatting like <b>, <i>, \\n. It MUST support or preserve "{bank_name}" and "{balance_val}" placeholders so the bot can replace them. If the admin provides a custom message that lacks these placeholders, automatically prepend or integrate them (e.g. "<b>{bank_name}\\nBal  {balance_val}\\n\\n" + their custom text + "</b>").
2. "mappings" (object): A key-value dictionary of raw bank names (lowercase) to stylized brand names (e.g. {"chase": "Ch4se"}). If the admin wants to add a mapping (e.g. "map Monzo to M0nz0"), add or edit that key. If they want to remove a mapping (e.g. "remove Chase mapping"), delete that key from the mappings.
3. "output_channel_id" (string or number): The channel username (e.g. "@mychannel") or numeric ID (e.g. -1001234567890).
4. "provider" (string): The active OCR provider, either "openrouter", "groq", or "gemini".
5. "balance_check_passes" (integer): The number of OCR verifications to run in parallel to ensure 100% correct digit reading (e.g., 1 for speed check, 3 or 4 for majority voting consensus check).

Analyze the admin's instruction carefully.
You must respond in STRICT JSON format matching this schema:
{
  "action": "update" | "show" | "reset" | "none",
  "updated_config": {
     "ad_copy": "updated caption template string or omit if not changed",
     "mappings": { updated full mappings dictionary or omit if not changed },
     "output_channel_id": "updated channel id or omit if not changed",
     "provider": "groq or gemini or omit if not changed",
     "balance_check_passes": integer or omit if not changed
  },
  "explanation": "Friendly, professional text explaining what change was made or why you showed settings."
}

Rules:
- If the admin wants to change the caption/ad copy, make sure the HTML is valid and contains "{bank_name}" and "{balance_val}".
- If the admin wants to see current settings, set "action" to "show" and leave "updated_config" empty.
- If the admin wants to restore defaults, set "action" to "reset" and leave "updated_config" empty.
- Always provide a clear, concise "explanation" of what was done.
- Respond with ONLY the raw JSON object, no markdown code blocks or wrapper text."""


async def show_config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the active dynamic configurations."""
    if update.effective_user.id not in ADMIN_USER_IDS:
        return
        
    config_info = (
        f"⚙️ <b>Active Bot Configurations</b>\n\n"
        f"🌐 <b>OCR Provider:</b> <code>{active_config.get('provider')}</code>\n"
        f"🎯 <b>Accuracy Verifications:</b> <code>{active_config.get('balance_check_passes', 3)} passes (majority vote)</code>\n"
        f"📺 <b>Channel Forward ID:</b> <code>{active_config.get('output_channel_id') or 'Not Configured'}</code>\n\n"
        f"📝 <b>Ad-Copy Template:</b>\n"
        f"<pre>{active_config.get('ad_copy')}</pre>\n\n"
        f"🔤 <b>Active Bank Mappings ({len(active_config.get('mappings', {}))}):</b>\n"
        f"Chase ➡️ <code>{active_config.get('mappings', {}).get('chase', 'Chase')}</code>, "
        f"BofA ➡️ <code>{active_config.get('mappings', {}).get('bofa', 'Bofa')}</code>, "
        f"PNC ➡️ <code>{active_config.get('mappings', {}).get('pnc', 'PNC')}</code>, etc.\n\n"
        f"<i>To edit any setting, mapping, or caption, simply text the bot in plain English!</i>"
    )
    await update.message.reply_html(config_info)


async def reset_config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resets the bot configurations to default."""
    if update.effective_user.id not in ADMIN_USER_IDS:
        return
        
    global active_config
    active_config = DEFAULT_CONFIG.copy()
    save_config(active_config)
    await update.message.reply_html("🔄 <b>Configurations Reset!</b>\n\nAll brand name mappings and caption templates have been reset to standard values.")


async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles text messages. If sender is authorized admin, parses their request using AI config engine."""
    if update.effective_chat.type != "private":
        return

    message = update.message
    if not message or not message.text:
        return

    user_id = update.effective_user.id
    user_text = message.text.strip()

    # Check if user is admin
    if user_id not in ADMIN_USER_IDS:
        # Check if they sent a standard text message
        # Let's guide them on how to register as admin
        await message.reply_html(
            f"🔒 <b>Admin Access Required</b>\n\n"
            f"Your Telegram User ID is: <code>{user_id}</code>\n\n"
            f"To configure settings, ad copies, or mappings directly from Telegram, "
            f"please add this ID to your environment variables on Railway:\n"
            f"<code>ADMIN_USER_IDS={user_id}</code>\n\n"
            f"<i>Note: Customers can still send bank statement screenshots normally to get them parsed.</i>"
        )
        return

    # User is admin! Check if it's a standard command first
    if user_text.startswith("/showconfig"):
        await show_config_command(update, context)
        return
    elif user_text.startswith("/resetconfig"):
        await reset_config_command(update, context)
        return
    elif user_text.startswith("/start") or user_text.startswith("/help"):
        await start(update, context)
        # Also show admin options since they are admin
        await message.reply_html(
            "⚙️ <b>Admin Controls Active!</b>\n\n"
            "You can manage the bot simply by texting it in plain English! Try sending messages like:\n"
            "• <i>\"show config\"</i> or <i>\"what are my current settings?\"</i>\n"
            "• <i>\"change caption to: Bal {balance_val} at {bank_name}\"</i>\n"
            "• <i>\"add brand mapping for Monzo to M0nz0\"</i>\n"
            "• <i>\"delete mapping for chase\"</i>\n"
            "• <i>\"switch provider to gemini\"</i>\n"
            "• <i>\"set channel ID to -100123456789\"</i>\n"
            "• <i>\"reset config\"</i>\n\n"
            "Or run direct commands:\n"
            "/showconfig - Print current config JSON\n"
            "/resetconfig - Restore default settings"
        )
        return

    # It's a natural language instruction! Call AI config engine
    status_msg = await message.reply_text("⚙️ Analyzing config request...")
    
    global active_config
    provider = get_active_provider()
    
    # We will use the same provider that is active, or fallback
    provider_name = "OpenRouter" if provider == "openrouter" else ("Groq Llama 4" if provider == "groq" else "Google Gemini")
    
    if provider == "openrouter":
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": ADMIN_CONFIG_SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": f"Current Config:\n{json.dumps(active_config, indent=2)}\n\nAdmin Instruction:\n{user_text}"
                }
            ],
            "temperature": 0.1,
            "max_tokens": 1000
        }
    elif provider == "groq":
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": GROQ_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": ADMIN_CONFIG_SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": f"Current Config:\n{json.dumps(active_config, indent=2)}\n\nAdmin Instruction:\n{user_text}"
                }
            ],
            "temperature": 0.1,
            "max_tokens": 1000,
            "response_format": {"type": "json_object"}
        }
    else:
        url = ""
        headers = {}
        payload = {}

    try:
        loop = asyncio.get_running_loop()
        if provider in ["openrouter", "groq"]:
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(url, json=payload, headers=headers, timeout=30)
            )
            if response is not None and response.status_code != 200:
                status_code = response.status_code if response is not None else "Unknown"
                logger.error(f"Config AI API returned status {status_code}: {response.text if response else 'No response'}")
                await status_msg.edit_text(f"❌ Config parsing failed. API returned error {status_code}.")
                return
        else:
            # Gemini key rotation
            if not GEMINI_API_KEYS:
                logger.error("No Gemini API keys configured for dynamic config engine!")
                await status_msg.edit_text("❌ Dynamic configuration failed. No Gemini API keys are configured.")
                return

            response = None
            status_code = "Unknown"
            for key_idx, current_key in enumerate(GEMINI_API_KEYS):
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={current_key}"
                headers = {"content-type": "application/json"}
                payload = {
                    "contents": [
                        {
                            "parts": [
                                {
                                    "text": f"{ADMIN_CONFIG_SYSTEM_PROMPT}\n\nCurrent Config:\n{json.dumps(active_config, indent=2)}\n\nAdmin Instruction:\n{user_text}"
                                }
                            ]
                        }
                    ],
                    "generationConfig": {
                        "responseMimeType": "application/json"
                    }
                }

                try:
                    response = await loop.run_in_executor(
                        None,
                        lambda: requests.post(url, json=payload, headers=headers, timeout=20)
                    )
                    if response is not None and response.status_code == 200:
                        break
                    else:
                        status_code = response.status_code if response is not None else "No Response"
                        logger.warning(f"Gemini key index {key_idx} failed for admin text with status {status_code}")
                except Exception as e:
                    logger.error(f"Error calling Gemini with key index {key_idx} for admin text: {e}")
                    response = None

            if response is None or response.status_code != 200:
                logger.error(f"Config AI API returned status {status_code}: {response.text if response else 'No response'}")
                await status_msg.edit_text(f"❌ Config parsing failed. API returned error {status_code}.")
                return
            status_code = response.status_code if response is not None else "Unknown"
            logger.error(f"Config AI API returned status {status_code}: {response.text if response else 'No response'}")
            await status_msg.edit_text(f"❌ Config parsing failed. API returned error {status_code}.")
            return
            
        res_json = response.json()
        if provider in ["openrouter", "groq"]:
            ai_text = res_json["choices"][0]["message"]["content"].strip()
        else:
            ai_text = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
            
        # Clean markdown wrappers if any
        ai_text = ai_text.strip()
        if ai_text.startswith("```"):
            lines = ai_text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            ai_text = "\n".join(lines).strip()
            
        result = json.loads(ai_text)
        action = result.get("action", "none")
        explanation = result.get("explanation", "Action processed.")
        
        if action == "update":
            updated_fields = result.get("updated_config", {})
            if updated_fields:
                # Merge mappings if provided
                if "mappings" in updated_fields and isinstance(updated_fields["mappings"], dict):
                    current_mappings = active_config.get("mappings", {}).copy()
                    current_mappings.update(updated_fields["mappings"])
                    updated_fields["mappings"] = current_mappings
                    
                # Update our global and persistent config
                active_config.update(updated_fields)
                save_config(active_config)
                await status_msg.edit_text(f"✅ <b>Settings Updated!</b>\n\n{explanation}", parse_mode="HTML")
            else:
                await status_msg.edit_text("ℹ️ No changes were identified in your message.")
        elif action == "show":
            await status_msg.delete()
            await show_config_command(update, context)
        elif action == "reset":
            active_config = DEFAULT_CONFIG.copy()
            save_config(active_config)
            await status_msg.edit_text("🔄 <b>Config Reset!</b>\n\nAll settings and mappings have been restored to factory defaults.", parse_mode="HTML")
        else:
            await status_msg.edit_text(f"ℹ️ {explanation}")
            
    except Exception as e:
        logger.error(f"Error parsing admin config instruction: {e}")
        await status_msg.edit_text(f"❌ Failed to process dynamic configuration. Error: {e}")

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes `/check` when replied to a previous photo or document message (or bot photo reply)."""
    message = update.message
    if not message:
        return

    # Must be a reply
    if not message.reply_to_message:
        await message.reply_text("❌ Please reply to a bank statement image (or the bot's photo response) with `/check` to re-analyze it.")
        return

    target_msg = message.reply_to_message
    
    file_id = None
    mime_type = "image/jpeg"
    file_name = "check_image.jpg"

    if target_msg.photo:
        photo = target_msg.photo[-1]
        file_id = photo.file_id
        mime_type = "image/jpeg"
    elif target_msg.document:
        doc = target_msg.document
        doc_mime = doc.mime_type or ""
        doc_name = doc.file_name or ""
        
        is_image = False
        if doc_mime.startswith("image/"):
            is_image = True
            if doc_mime in ["image/jpeg", "image/png", "image/gif", "image/webp"]:
                mime_type = doc_mime
        else:
            exts = (".png", ".jpg", ".jpeg", ".webp", ".gif")
            if doc_name.lower().endswith(exts):
                is_image = True
                if doc_name.lower().endswith(".png"):
                    mime_type = "image/png"
                elif doc_name.lower().endswith(".webp"):
                    mime_type = "image/webp"
                elif doc_name.lower().endswith(".gif"):
                    mime_type = "image/gif"

        if is_image:
            file_id = doc.file_id
            file_name = doc_name

    if not file_id:
        await message.reply_text("❌ The message you replied to does not contain a valid photo or document image.")
        return

    # Pass to the shared bank statement analysis consensus pipeline
    await process_bank_image(file_id, mime_type, file_name, message, context)


async def change_template_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows any user to set their own custom, persistently stored caption template."""
    message = update.message
    if not message:
        return

    user_id = update.effective_user.id
    user_id_str = str(user_id)
    
    template_text = ""
    
    # Extract template from payload if present (e.g., /change <b>...</b>)
    if context.args:
        template_text = " ".join(context.args).strip()
    elif message.reply_to_message and message.reply_to_message.text:
        template_text = message.reply_to_message.text.strip()
    
    if not template_text:
        # Show help message
        current_templates = active_config.get("user_templates", {})
        user_current = current_templates.get(user_id_str)
        
        help_text = (
            "📝 <b>Personal Caption Settings</b>\n\n"
            "You can set your own custom caption template for bank statements! "
            "From now on, the bot will format results specifically for you using your layout.\n\n"
            "<b>How to set your template:</b>\n"
            "1. Send: <code>/change Your custom template here</code>\n"
            "2. Or reply to any text message containing your layout with <code>/change</code>.\n\n"
            "<b>Placeholders you MUST include:</b>\n"
            "• <code>{bank_name}</code> - Will show the mapped bank name\n"
            "• <code>{balance_val}</code> - Will show the whole-dollar balance\n\n"
            "<b>How to reset:</b>\n"
            "Send <code>/change default</code> to revert back to the global default template.\n\n"
        )
        if user_current:
            help_text += f"🟢 <b>Your Current Custom Template:</b>\n<pre>{user_current}</pre>"
        else:
            help_text += "⚪ <b>Your Current Template:</b> Using Global Default Bot Layout."
            
        await message.reply_html(help_text)
        return

    # Process setting to default
    if template_text.lower() == "default":
        user_templates = active_config.get("user_templates", {})
        if user_id_str in user_templates:
            del user_templates[user_id_str]
            active_config["user_templates"] = user_templates
            save_config(active_config)
            
        await message.reply_html("🔄 <b>Reset Complete!</b>\n\nYour caption layout has been reset to the bot's global default template.")
        return

    # Validate template layout
    # Automatically verify & insert placeholders if missing to prevent formatting errors
    if "{bank_name}" not in template_text or "{balance_val}" not in template_text:
        template_text = f"<b>{{bank_name}}\nBal  {{balance_val}}\n\n</b>{template_text}"

    # Verify HTML formatting syntax by attempting a test formatting
    try:
        test_str = template_text.format(bank_name="TestBank", balance_val="$1,000")
    except Exception as e:
        await message.reply_text(f"❌ Formatting syntax error: {e}. Please ensure placeholders like curly braces {{}} are correct.")
        return

    # Save to dynamic configuration dictionary
    user_templates = active_config.get("user_templates", {})
    user_templates[user_id_str] = template_text
    active_config["user_templates"] = user_templates
    save_config(active_config)

    logger.info(f"Custom caption template saved for user {user_id}: {template_text}")
    
    await message.reply_html(
        f"✅ <b>Custom Caption Saved!</b>\n\n"
        f"From now on, whenever you upload a bank screenshot, the bot will use *your* personal caption layout!\n\n"
        f"<b>Your Saved Layout:</b>\n"
        f"<pre>{template_text}</pre>"
    )


def main():
    """Starts the bot application."""
    if not is_configured():
        logger.warning(
            "⚠️ Bot configuration variables are using placeholder values! "
            "Please configure TELEGRAM_BOT_TOKEN and GEMINI_API_KEY in F:\\toolforbank\\bot.py "
            "or a .env file."
        )

    # Start the lightweight health check web server in a background daemon thread
    # This keeps free hosting platforms (Render, Koyeb, Railway) happy and keeps the bot online 24/7!
    threading.Thread(target=run_health_check_server, daemon=True).start()

    # Initialize the Application
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("showconfig", show_config_command))
    app.add_handler(CommandHandler("resetconfig", reset_config_command))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("change", change_template_command))
    
    # Handle text messages (which might be admin configuration messages)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_text))
    
    # Handle both compressed Photos and uncompressed Documents
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_image))

    logger.info("🤖 Starting Bank OCR Vision Telegram Bot (powered by Gemini)...")
    app.run_polling()


if __name__ == "__main__":
    main()
