import asyncio
import requests
import logging
from capmonstercloudclient import CapMonsterClient, ClientOptions
from capmonstercloudclient.requests import RecaptchaV2ProxylessRequest
import string
import random
import time
import re
from bs4 import BeautifulSoup
import os
from datetime import datetime
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class TempMail:
    def __init__(self):
        self.api_base = "https://www.1secmail.com/api/v1/"
        self.domains = ["1secmail.com", "1secmail.org", "1secmail.net"]
        
    def generate_email(self):
        prefix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        domain = random.choice(self.domains)
        email = f"{prefix}@{domain}"
        return email
        
    def get_messages(self, email):
        login, domain = email.split('@')
        params = {
            'action': 'getMessages',
            'login': login,
            'domain': domain
        }
        try:
            response = requests.get(self.api_base, params=params)
            if response.status_code == 200:
                return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error checking messages: {e}")
            return []
        
    def read_message(self, email, message_id):
        login, domain = email.split('@')
        params = {
            'action': 'readMessage',
            'login': login,
            'domain': domain,
            'id': message_id
        }
        try:
            response = requests.get(self.api_base, params=params)
            if response.status_code == 200:
                return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error reading message: {e}")
            return None

class RonaPromoSubscriber:
    def __init__(self, capmonster_api_key):
        logger.info("Initializing RonaPromoSubscriber")
        self.base_url = "https://www.rona.ca"
        self.subscribe_endpoint = "/webapp/wcs/stores/servlet/RonaAjaxConsentSubscribeCmd"
        
        # Initialize CapMonster client
        client_options = ClientOptions(api_key=capmonster_api_key)
        self.cap_monster_client = CapMonsterClient(options=client_options)
        
        # Headers based on the curl request
        self.headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': 'https://www.rona.ca',
            'referer': 'https://www.rona.ca/en/newsletter-subscription',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'x-requested-with': 'XMLHttpRequest'
        }

    async def solve_captcha(self):
        logger.info("Starting captcha solving process")
        try:
            # Create RecaptchaV2 request with updated parameters
            recaptcha_request = RecaptchaV2ProxylessRequest(
                websiteUrl="https://www.rona.ca/en/newsletter-subscription",
                websiteKey="6LdYpSUTAAAAABv51aNjgZRMbbYxLyxPKUM7TBpq",
            )
            
            logger.info("Sending captcha solve request to CapMonster")
            # Solve the captcha
            solution = await self.cap_monster_client.solve_captcha(recaptcha_request)
            logger.info(f"Captcha solution length: {len(solution.get('gRecaptchaResponse', '')) if solution else 0}")
            logger.debug(f"Captcha solution: {solution.get('gRecaptchaResponse') if solution else 'No solution'}")
            return solution.get('gRecaptchaResponse') if solution else None
        except Exception as e:
            logger.error(f"Error solving captcha: {str(e)}")
            raise

    async def subscribe(self, email, zip_code):
        logger.info(f"Starting subscription process for email: {email}")
        
        # Get captcha solution
        logger.info("Getting captcha solution")
        captcha_response = await self.solve_captcha()
        logger.info("Captcha response received")
        
        # Prepare form data with modified captcha response handling
        data = {
            'storeId': '10151',
            'catalogId': '10051',
            'langId': '-1',
            'newsletterConso': 'Y',
            'source': 'RONA_NEWSLETTER_RETAIL',
            'userId': '-1002',
            'firstName': '',
            'lastName': '',
            'email': email,
            'zipCode': zip_code,
            'g-recaptcha-response': captcha_response,
        }
        
        logger.debug(f"Sending data: {data}")
        
        # Send subscription request
        logger.info("Sending subscription request")
        try:
            response = requests.post(
                f"{self.base_url}{self.subscribe_endpoint}",
                headers=self.headers,
                data=data
            )
            logger.info(f"Response status code: {response.status_code}")
            logger.debug(f"Response headers: {response.headers}")
            
            if response.status_code != 200:
                logger.error(f"Unexpected status code: {response.status_code}")
                logger.error(f"Response content: {response.text}")
            
            return response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
        except Exception as e:
            logger.error(f"Error sending subscription request: {str(e)}")
            raise

@dataclass
class PromoDetails:
    promo_code: str
    valid_until: str
    in_store_link: Optional[str] = None
    online_code: Optional[str] = None

class PromoEmailParser:
    def __init__(self, debug_mode=False):
        self.debug_mode = debug_mode
        if debug_mode:
            self.debug_dir = os.path.join('debug_emails')
            os.makedirs(self.debug_dir, exist_ok=True)

    def resolve_redirect_url(self, url: str) -> Optional[str]:
        """Follow redirect and return the final URL."""
        try:
            response = requests.head(url, allow_redirects=False)
            if response.status_code == 302:
                return response.headers.get('Location')
            return url
        except requests.exceptions.RequestException as e:
            logger.error(f"Error resolving redirect URL: {e}")
            return None

    def extract_promo_details(self, html_content: str) -> PromoDetails:
        """Extract promotion details from the email HTML content."""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract validity date
        valid_until = None
        date_text = soup.find(string=re.compile(r'valid until \d{1,2}/\d{1,2}/\d{4}'))
        if date_text:
            match = re.search(r'valid until (\d{1,2}/\d{1,2}/\d{4})', date_text)
            if match:
                valid_until = match.group(1)

        # Extract promo code
        promo_code = None
        # Look for the specific styling that contains the promo code
        code_element = soup.find('span', style=lambda x: x and 'font-size:17px' in x)
        if code_element:
            promo_code = code_element.text.strip()

        # Extract and resolve in-store coupon link
        in_store_link = None
        coupon_link = soup.find('a', {'title': 'in-store coupon'})
        if coupon_link:
            initial_link = coupon_link.get('href')
            in_store_link = self.resolve_redirect_url(initial_link)
            logger.info(f"Resolved in-store link: {in_store_link}")

        return PromoDetails(
            promo_code=promo_code,
            valid_until=valid_until,
            in_store_link=in_store_link,
            online_code=promo_code  # Same as promo_code in this case
        )

    def save_debug_email(self, html_content):
        if self.debug_mode:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            debug_file = os.path.join(self.debug_dir, f'rona_{timestamp}.html')
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(html_content)

async def wait_for_rona_email(tm, email, timeout_hours=24, refresh_interval=5):
    logger.info(f"Waiting for Rona email... (timeout: {timeout_hours} hours, refreshing every {refresh_interval} seconds)")
    start_time = time.time()
    timeout_seconds = timeout_hours * 3600
    parser = PromoEmailParser(debug_mode=True)
    
    while time.time() - start_time < timeout_seconds:
        messages = tm.get_messages(email)
        if messages:
            for message in messages:
                message_id = message.get('id')
                full_message = tm.read_message(email, message_id)
                
                if not full_message:
                    continue

                sender = full_message.get('from', 'Unknown')
                email_match = re.search(r'<(.+?)>', sender)
                sender_email = email_match.group(1) if email_match else sender

                if sender_email.lower().endswith('rona.ca'):
                    logger.info("Rona email received!")
                    html_body = full_message.get('htmlBody', '')
                    if html_body:
                        # Save debug email
                        parser.save_debug_email(html_body)
                        logger.info("Email saved to debug directory")
                        
                        # Extract promo details
                        promo_details = parser.extract_promo_details(html_body)
                        logger.info(f"Extracted promo details: {promo_details}")
                        
                        return promo_details

        await asyncio.sleep(refresh_interval)

    logger.warning("Timeout reached. No Rona email received.")
    return None

async def main():
    logger.info("Starting main process")
    
    # Configuration
    CAPMONSTER_API_KEY = os.getenv('CAPMONSTER_API_KEY')
    if not CAPMONSTER_API_KEY:
        raise ValueError("CAPMONSTER_API_KEY environment variable is not set")
    
    ZIP_CODE = "A1A 1A1"
    
    # Generate temporary email
    temp_mail = TempMail()
    EMAIL = temp_mail.generate_email()
    logger.info(f"Generated temporary email: {EMAIL}")
    
    # Initialize and run subscription
    subscriber = RonaPromoSubscriber(CAPMONSTER_API_KEY)
    try:
        logger.info("Attempting subscription")
        result = await subscriber.subscribe(EMAIL, ZIP_CODE)
        logger.debug(f"Subscription result: {result}")
        
        # Wait for confirmation email
        email_received = await wait_for_rona_email(temp_mail, EMAIL)
        if email_received:
            logger.info("Successfully received and saved Rona email")
            print(f"Promo details: {email_received.promo_code}")
            print(f"Valid until: {email_received.valid_until}")
            print(f"In-store link: {email_received.in_store_link}")
        else:
            logger.warning("Failed to receive Rona email")
        
    except Exception as e:
        logger.error(f"Error occurred in main: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Script interrupted by user")
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}")
