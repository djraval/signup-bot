import requests
import time
import random
import string
import re
from bs4 import BeautifulSoup
import html2text
import json
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

class PromoCodeParser:
    def __init__(self):
        self.code_pattern = re.compile(r'[A-Z0-9]{10,12}')
        self.validity_pattern = re.compile(r'Valid\s+until\s+(\d{1,2}/\d{1,2})', re.IGNORECASE)

    def extract_codes_from_html(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        result = {
            'online_code': None,
            'store_code': None,
            'valid_until': None,
            'all_codes': []
        }

        # First try to find codes in the coupon class (Gap Canada format)
        coupon_tag = soup.find('p', class_='coupon')
        if coupon_tag:
            text = coupon_tag.get_text()
            codes = self.code_pattern.findall(text)
            if len(codes) >= 2:
                result['online_code'] = codes[0]
                result['store_code'] = codes[1]
                result['all_codes'] = codes
                return result

        # Fallback to original parsing logic for other formats
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
            print(f"Error checking messages: {e}")
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
            print(f"Error reading message: {e}")
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
            print(f"Successfully subscribed to Old Navy with email: {email}")
            return True
        else:
            print(f"Failed to subscribe. Status code: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Error subscribing to Old Navy: {e}")
        return False

def subscribe_to_gap(email):
    url = 'https://api.gapcanada.ca/commerce/communication-preference/v2/subscriptions/email'
    headers = {
        'accept': 'application/json',
        'content-type': 'application/json',
        'origin': 'https://www.gapcanada.ca',
        'referer': 'https://www.gapcanada.ca/'    }
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
            print(f"Successfully subscribed to Gap Canada with email: {email}")
            return True
        else:
            print(f"Failed to subscribe. Status code: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Error subscribing to Gap: {e}")
        return False

def process_email(html_content, subject):
    # Parse promo codes
    parser = PromoCodeParser()
    return parser.extract_codes_from_html(html_content)

def wait_for_email(tm, email, timeout_hours=24, refresh_interval=5):
    # Wait for and process the welcome email
    print(f"\nWaiting for emails... (timeout: {timeout_hours} hours, refreshing every {refresh_interval} seconds)")
    start_time = time.time()
    timeout_seconds = timeout_hours * 3600
    
    oldnavy_done = False
    gap_done = False

    while time.time() - start_time < timeout_seconds:
        if oldnavy_done and gap_done:
            break

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

                retailer = None
                if not oldnavy_done and sender_email.lower().endswith('oldnavy.ca'):
                    retailer = 'oldnavy'
                elif not gap_done and sender_email.lower().endswith('gapcanada.ca'):
                    retailer = 'gap'
                else:
                    continue

                print(f"\n{retailer.title()} email received!")
                html_body = full_message.get('htmlBody', '')
                if html_body:
                    promo_results = process_email(
                        html_body,
                        full_message.get('subject', 'No subject')
                    )
                    
                    if promo_results:
                        display_promo_results(Console(), retailer, promo_results)
                        if retailer == 'oldnavy':
                            oldnavy_done = True
                        else:
                            gap_done = True

        time.sleep(refresh_interval)

    if not (oldnavy_done or gap_done):
        print("\nTimeout reached. No emails received.")

def display_promo_results(console, retailer, promo_results):
    if promo_results and (promo_results['online_code'] or promo_results['store_code']):
        table = Table(box=box.ROUNDED, border_style="blue", header_style="bold magenta")
        table.add_column("Type", style="cyan")
        table.add_column("Code", style="green")
        
        if promo_results['online_code']:
            table.add_row("Online Code", promo_results['online_code'])
        if promo_results['store_code']:
            table.add_row("Store Code", promo_results['store_code'])
        if retailer == 'oldnavy' and promo_results['valid_until']:
            table.add_row("Valid Until", promo_results['valid_until'])
            
        console.print(f"\n[bold]{retailer.upper()} Promo Codes:[/bold]")
        console.print(table)

def main():
    console = Console()
    
    # Create a fancy title
    console.print(Panel.fit(
        "[bold yellow]Gap & Old Navy Promo Code Fetcher[/bold yellow]",
        border_style="blue",
        padding=(1, 2)
    ))
    
    # Create temporary email
    tm = TempMail()
    email = tm.generate_email()
    console.print(f"\n[cyan]Generated email:[/cyan] [green]{email}[/green]")
    
    # Subscribe to both newsletters
    oldnavy_success = subscribe_to_oldnavy(email)
    gap_success = subscribe_to_gap(email)
    
    if not (oldnavy_success or gap_success):
        console.print("[red]Failed to subscribe to any newsletters. Exiting...[/red]")
        return
    
    # Wait for and process welcome emails
    wait_for_email(tm, email)

if __name__ == "__main__":
    main()
