from flask import Flask, jsonify, request, url_for, render_template
import time
import logging
import re
import random
import string
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import os
import uuid
from collections import defaultdict

app = Flask(__name__)

# Comment out or conditionally set the HTTPS scheme based on environment
if not app.debug:  # Only use HTTPS in production
    app.config['PREFERRED_URL_SCHEME'] = 'https'

# Add this new route at the top of your routes
@app.route('/')
def home():
    return render_template('index.html')

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add these to your existing global variables
task_queue = {}
task_results = defaultdict(dict)

class PromoCodeParser:
    def __init__(self, debug_mode=False):
        self.code_pattern = re.compile(r'[A-Z0-9]{10,12}')
        self.validity_pattern = re.compile(r'Valid\s+until\s+(\d{1,2}/\d{1,2})', re.IGNORECASE)
        self.discount_pattern = re.compile(r'(\d+)\s*%(?:\s+off|\s*\.)?', re.IGNORECASE)
        self.debug_mode = debug_mode
        if debug_mode:
            self.debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'debug_emails')
            os.makedirs(self.debug_dir, exist_ok=True)

    def extract_codes_from_html(self, html_content, email_type=None):
        if self.debug_mode and email_type:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            debug_file = os.path.join(self.debug_dir, f'{email_type}_{timestamp}.html')
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(html_content)

        soup = BeautifulSoup(html_content, 'html.parser')
        result = {
            'online_code': None,
            'store_code': None,
            'valid_until': None,
            'all_codes': [],
            'discount_percentage': None
        }

        # Check for discount in mobile-hidden elements
        for element in soup.find_all(class_='mobile-hidden'):
            text = element.get_text().strip()
            discount_match = self.discount_pattern.search(text)
            if discount_match:
                result['discount_percentage'] = discount_match.group(1)
                break

        if not result['discount_percentage']:
            for link in soup.find_all('a'):
                link_text = link.get_text().strip()
                discount_match = self.discount_pattern.search(link_text)
                if discount_match:
                    result['discount_percentage'] = discount_match.group(1)
                    break

            if not result['discount_percentage']:
                body = soup.find('body')
                if body:
                    body_text = body.get_text()
                    discount_match = self.discount_pattern.search(body_text)
                    if discount_match:
                        result['discount_percentage'] = discount_match.group(1)

        # Try to find codes in the coupon class
        coupon_tag = soup.find('p', class_='coupon')
        if coupon_tag:
            text = coupon_tag.get_text()
            codes = self.code_pattern.findall(text)
            if len(codes) >= 2:
                result['online_code'] = codes[0]
                result['store_code'] = codes[1]
                result['all_codes'] = codes
                return result

        # Fallback parsing logic
        all_codes = []
        for text in soup.stripped_strings:
            matches = self.code_pattern.findall(text)
            all_codes.extend(matches)

        result['all_codes'] = all_codes

        for tag in soup.find_all(['td', 'p', 'div']):
            text = tag.get_text().strip().upper()
            
            if 'ONLINE' in text:
                nearby_codes = self._find_nearby_codes(tag)
                if nearby_codes:
                    result['online_code'] = nearby_codes[0]
            
            if 'IN-STORE' in text or 'INSTORE' in text:
                nearby_codes = self._find_nearby_codes(tag)
                if nearby_codes:
                    result['store_code'] = nearby_codes[0]

            validity_match = self.validity_pattern.search(text)
            if validity_match:
                result['valid_until'] = validity_match.group(1)

        if not result['online_code'] and not result['store_code'] and len(all_codes) == 2:
            result['online_code'] = all_codes[0]
            result['store_code'] = all_codes[1]

        return result

    def _find_nearby_codes(self, tag):
        codes = []
        current = tag
        for _ in range(3):
            if current:
                text = current.get_text()
                matches = self.code_pattern.findall(text)
                codes.extend(matches)
                current = current.find_next_sibling()
        return codes

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

def subscribe_to_oldnavy(email):
    url = 'https://api.gapcanada.ca/commerce/communication-preference/v2/subscriptions/email'
    headers = {
        'accept': 'application/json',
        'content-type': 'application/json',
        'origin': 'https://oldnavy.gapcanada.ca',
        'referer': 'https://oldnavy.gapcanada.ca/'
    }
    data = {
        "emailAddress": email,
        "brand": "ON",
        "market": "CA",
        "locale": "en_CA",
        "mainSource": "WEBSITE EMAIL SIGNUP",
        "subSource": "ON"
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 201:
            logger.info(f"Successfully subscribed to Old Navy with email: {email}")
            return True
        else:
            logger.error(f"Failed to subscribe to Old Navy. Status code: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Error subscribing to Old Navy: {e}")
        return False

def subscribe_to_gap(email):
    url = 'https://api.gapcanada.ca/commerce/communication-preference/v2/subscriptions/email'
    headers = {
        'accept': 'application/json',
        'content-type': 'application/json',
        'origin': 'https://www.gapcanada.ca',
        'referer': 'https://www.gapcanada.ca/'
    }
    data = {
        "emailAddress": email,
        "brand": "GP",
        "market": "CA",
        "locale": "en_CA",
        "mainSource": "WEBSITE EMAIL SIGNUP",
        "subSource": "GP"
    }
    
    try: 
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 201:
            logger.info(f"Successfully subscribed to Gap Canada with email: {email}")
            return True
        else:
            logger.error(f"Failed to subscribe to Gap. Status code: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Error subscribing to Gap: {e}")
        return False

def wait_for_email(temp_mail, email, timeout=120, check_interval=10):
    start_time = time.time()
    while time.time() - start_time < timeout:
        messages = temp_mail.get_messages(email)
        if messages:
            message = temp_mail.read_message(email, messages[0]['id'])
            if message:
                return {
                    'subject': message['subject'],
                    'html': message['htmlBody']
                }
        time.sleep(check_interval)
    return None

def process_promo_request(task_id, retailer):
    try:
        # Initialize services
        temp_mail = TempMail()
        parser = PromoCodeParser()
        
        # Generate email
        email = temp_mail.generate_email()
        logger.info(f"Generated email: {email}")
        
        # Update task status
        task_results[task_id].update({
            'status': 'subscribing',
            'email': email
        })
        
        # Subscribe to newsletter
        if retailer == 'oldnavy':
            success = subscribe_to_oldnavy(email)
        else:
            success = subscribe_to_gap(email)
            
        if not success:
            task_results[task_id]['status'] = 'failed'
            task_results[task_id]['error'] = f'Failed to subscribe to {retailer}'
            return
        
        # Update status
        task_results[task_id]['status'] = 'waiting_for_email'
        
        # Wait for and process email
        email_content = wait_for_email(temp_mail, email)
        if not email_content:
            task_results[task_id]['status'] = 'failed'
            task_results[task_id]['error'] = 'No email received within timeout period'
            return
            
        # Parse promo codes
        promo_results = parser.extract_codes_from_html(email_content['html'], retailer)
        
        # Store final results
        task_results[task_id].update({
            'status': 'completed',
            'codes': promo_results
        })
        
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        task_results[task_id].update({
            'status': 'failed',
            'error': str(e)
        })

@app.route('/api/promo', methods=['POST'])
def create_promo_request():
    data = request.get_json()
    retailer = data.get('retailer', '').lower()
    
    if retailer not in ['oldnavy', 'gap']:
        return jsonify({'error': 'Invalid retailer. Must be either "oldnavy" or "gap"'}), 400
    
    task_id = str(uuid.uuid4())
    task_results[task_id] = {
        'status': 'queued',
        'retailer': retailer
    }
    
    # Start processing in a background thread
    import threading
    thread = threading.Thread(target=process_promo_request, args=(task_id, retailer))
    thread.start()
    
    # Use _scheme parameter conditionally
    if app.debug:
        status_url = url_for('get_promo_status', task_id=task_id, _external=True)
    else:
        status_url = url_for('get_promo_status', task_id=task_id, _external=True, _scheme='https')
        
    return jsonify({
        'task_id': task_id,
        'status': 'queued',
        'status_url': status_url
    })

@app.route('/api/promo/<task_id>', methods=['GET'])
def get_promo_status(task_id):
    if task_id not in task_results:
        return jsonify({'error': 'Task not found'}), 404
        
    result = task_results[task_id]
    
    # Clean up completed or failed tasks after some time
    if result['status'] in ['completed', 'failed']:
        def cleanup():
            import time
            time.sleep(3600)  # Keep results for 1 hour
            task_results.pop(task_id, None)
        
        import threading
        cleanup_thread = threading.Thread(target=cleanup)
        cleanup_thread.start()
    
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True)
