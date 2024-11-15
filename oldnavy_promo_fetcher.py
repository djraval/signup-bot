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
        response.raise_for_status()
        print(f"Successfully subscribed with email: {email}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error subscribing to Old Navy: {e}")
        return False

def process_email(html_content, subject):
    # Parse promo codes
    parser = PromoCodeParser()
    return parser.extract_codes_from_html(html_content)

def wait_for_email(tm, email, timeout_hours=24, refresh_interval=5):
    # Wait for and process the welcome email
    print(f"\nWaiting for email... (timeout: {timeout_hours} hours, refreshing every {refresh_interval} seconds)")
    start_time = time.time()
    timeout_seconds = timeout_hours * 3600

    while True:
        if time.time() - start_time > timeout_seconds:
            print("Timeout reached. No email received.")
            return None

        messages = tm.get_messages(email)
        
        if messages:
            message_id = messages[0]['id']
            full_message = tm.read_message(email, message_id)
            
            if full_message:
                print("\nEmail received!")
                sender = full_message.get('from', 'Unknown')
                
                # Extract email address from sender field and check if it's from oldnavy.ca
                email_match = re.search(r'<(.+?)>', sender)
                sender_email = email_match.group(1) if email_match else sender
                if not sender_email.lower().endswith('oldnavy.ca'):
                    print(f"Email not from Old Navy ({sender_email}). \nWaiting for the correct email...")
                    continue
                
                html_body = full_message.get('htmlBody', '')
                if html_body:
                    promo_results = process_email(
                        html_body,
                        full_message.get('subject', 'No subject')
                    )
                    
                    if not promo_results:
                        print(f"No promo codes found in the email with subject: {full_message.get('subject', 'No subject')}. \nWaiting for the correct email...")
                        continue
                    return promo_results
                else:
                    print("\nNo HTML content found in the email.")
                    return None
        time.sleep(refresh_interval)

def main():
    console = Console()
    
    # Create a fancy title
    console.print(Panel.fit(
        "[bold yellow]Old Navy Promo Code Fetcher[/bold yellow]",
        border_style="blue",
        padding=(1, 2)
    ))
    
    # Get current timestamp
    timestamp = datetime.now()
    
    # Create temporary email
    tm = TempMail()
    email = tm.generate_email()
    console.print(f"\n[cyan]Generated email:[/cyan] [green]{email}[/green]")
    
    # Subscribe to Old Navy newsletter
    if not subscribe_to_oldnavy(email):
        console.print("[red]Failed to subscribe to Old Navy newsletter. Exiting...[/red]")
        return
    
    # Wait for and process the welcome email
    with console.status("[bold green]Waiting for welcome email...") as status:
        promo_results = wait_for_email(tm, email)
    
    if promo_results and (promo_results['online_code'] or promo_results['store_code']):
        # Create a table for display
        table = Table(box=box.ROUNDED, border_style="blue", header_style="bold magenta")
        table.add_column("Type", style="cyan")
        table.add_column("Code", style="green")
        
        if promo_results['online_code']:
            table.add_row("Online Code", promo_results['online_code'])
        if promo_results['store_code']:
            table.add_row("In-Store Code", promo_results['store_code'])
        if promo_results['valid_until']:
            table.add_row("Valid Until", promo_results['valid_until'])
            
        console.print("\n[bold]Promo Codes Found:[/bold]")
        console.print(table)

if __name__ == "__main__":
    main()
