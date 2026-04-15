# app.py - LeadForge Pro v5.0 (Windows Compatible Edition)
from flask import Flask, request, render_template_string, jsonify, Response
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import re
from datetime import datetime, timedelta
import csv
import io
import requests
import json
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import threading
import time
import hashlib
import sqlite3
from functools import wraps
import logging
from logging.handlers import RotatingFileHandler
import validators
from email_validator import validate_email, EmailNotValidError
import phonenumbers
from phonenumbers import carrier, geocoder, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
import secrets
import asyncio
import aiohttp
from aiohttp import ClientTimeout, ClientSession
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from collections import defaultdict
import uuid
import random
import socket
import platform

# Windows compatibility fixes
IS_WINDOWS = platform.system() == 'Windows'

# Fix for asyncio on Windows
if IS_WINDOWS:
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ==================== Configuration ====================
class Config:
    SECRET_KEY = secrets.token_urlsafe(32)
    DATABASE = 'leads.db'
    MAX_CONCURRENT_REQUESTS = 5  # Lower for Windows
    REQUEST_TIMEOUT = 30
    RATE_LIMIT = "200 per hour"
    RATE_LIMIT_PER_IP = "100 per hour"
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Edg/120.0.0.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    ]
    
    # API Keys (optional - for enrichment features)
    HUNTER_API_KEY = ""  # Add your Hunter.io API key
    CLEARBIT_API_KEY = ""  # Add your Clearbit API key

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

# Rate limiting
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[Config.RATE_LIMIT],
    storage_uri="memory://"
)

# Setup logging with Windows-compatible paths
log_handler = RotatingFileHandler('leadforge.log', maxBytes=10000000, backupCount=5)
log_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
app.logger.addHandler(log_handler)
app.logger.setLevel(logging.INFO)

# ==================== Database Setup ====================
def init_db():
    """Initialize database with all necessary tables"""
    conn = sqlite3.connect(Config.DATABASE)
    c = conn.cursor()
    
    # Scraping sessions table
    c.execute('''CREATE TABLE IF NOT EXISTS scraping_sessions
                 (id TEXT PRIMARY KEY,
                  url TEXT,
                  status TEXT,
                  emails_found INTEGER DEFAULT 0,
                  phones_found INTEGER DEFAULT 0,
                  social_found INTEGER DEFAULT 0,
                  pages_scraped INTEGER DEFAULT 0,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  completed_at TIMESTAMP,
                  ip_address TEXT,
                  user_agent TEXT)''')
    
    # Leads table
    c.execute('''CREATE TABLE IF NOT EXISTS leads
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  session_id TEXT,
                  type TEXT,
                  value TEXT,
                  source_url TEXT,
                  confidence_score REAL,
                  verified BOOLEAN DEFAULT 0,
                  enrichment_data TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (session_id) REFERENCES scraping_sessions (id))''')
    
    # Blacklist table
    c.execute('''CREATE TABLE IF NOT EXISTS blacklist
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  domain TEXT UNIQUE,
                  reason TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Statistics table
    c.execute('''CREATE TABLE IF NOT EXISTS statistics
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  total_sessions INTEGER DEFAULT 0,
                  total_emails INTEGER DEFAULT 0,
                  total_phones INTEGER DEFAULT 0,
                  total_pages_scraped INTEGER DEFAULT 0,
                  date DATE UNIQUE)''')
    
    conn.commit()
    conn.close()
    
    app.logger.info("Database initialized successfully")

init_db()

# ==================== Advanced Extraction Engine ====================
class AdvancedExtractor:
    """Professional grade extractor with validation and enrichment"""
    
    EMAIL_REGEX = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    
    # International phone patterns (Windows compatible)
    PHONE_PATTERNS = [
        r'\+?1[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',  # US/Canada
        r'\+?44[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',  # UK
        r'\+?254[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{3}',      # Kenya
        r'\+?91[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}',       # India
        r'\+?61[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{3}',       # Australia
        r'\+?49[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}',       # Germany
        r'\+?33[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}',       # France
        r'\+?81[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}',       # Japan
        r'\+?55[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}',       # Brazil
        r'\+?27[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}',       # South Africa
        r'\+?86[-.\s]?\d{3}[-.\s]?\d{4}[-.\s]?\d{4}',       # China
        r'\+?7[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}',        # Russia
        r'\+?31[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}',       # Netherlands
        r'\+?34[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}',       # Spain
        r'\+?39[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}',       # Italy
        r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',             # Generic US
        r'\d{3}[-.\s]\d{3}[-.\s]\d{4}',                     # Simple format
        r'0[1-9][0-9]{8}',                                   # UK mobile
        r'\+[0-9]{1,3}[0-9]{8,12}',                          # International
    ]
    
    SOCIAL_PATTERNS = {
        'linkedin': r'(?:https?:\/\/)?(?:www\.)?linkedin\.com\/(?:company|in)\/([a-zA-Z0-9-]+)',
        'twitter': r'(?:https?:\/\/)?(?:www\.)?(?:twitter|x)\.com\/([a-zA-Z0-9_]+)',
        'facebook': r'(?:https?:\/\/)?(?:www\.)?facebook\.com\/([a-zA-Z0-9.]+)',
        'instagram': r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/([a-zA-Z0-9_.]+)',
        'github': r'(?:https?:\/\/)?(?:www\.)?github\.com\/([a-zA-Z0-9-]+)',
        'youtube': r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/(?:c\/|user\/|@)([a-zA-Z0-9_-]+)',
    }
    
    @staticmethod
    def validate_email(email: str) -> Tuple[bool, Optional[str], Dict]:
        """Validate email and return cleaned version with metadata"""
        try:
            validation = validate_email(email, check_deliverability=False)
            domain = validation.normalized.split('@')[1]
            
            # Check for role-based emails
            role_patterns = ['info', 'sales', 'support', 'admin', 'contact', 'hello', 'team', 'careers', 'help']
            is_role_based = any(role in validation.normalized.lower() for role in role_patterns)
            
            # Check for disposable domains
            disposable_domains = {
                'tempmail.com', 'guerrillamail.com', 'mailinator.com', '10minutemail.com',
                'throwawaymail.com', 'yopmail.com', 'temp-mail.org', 'mailnator.com',
                'spamgourmet.com', 'trashmail.com', 'guerrillamail.org', 'guerrillamail.net'
            }
            is_disposable = domain in disposable_domains
            
            return True, validation.normalized, {
                'domain': domain,
                'is_role_based': is_role_based,
                'is_disposable': is_disposable,
                'local_part': validation.normalized.split('@')[0]
            }
        except EmailNotValidError as e:
            return False, None, {'error': str(e)}
        except Exception as e:
            return False, None, {'error': f'Validation error: {str(e)}'}
    
    @staticmethod
    def validate_phone(phone: str) -> Tuple[bool, Optional[str], Dict]:
        """Validate phone number and get details"""
        try:
            # Clean the phone number
            cleaned = re.sub(r'[\s\-\(\)\.]', '', phone)
            
            # Try to parse with different country codes
            for country in [None, 'US', 'GB', 'KE', 'IN', 'AU', 'DE', 'FR', 'JP', 'BR', 'ZA']:
                try:
                    if country:
                        parsed = phonenumbers.parse(cleaned, country)
                    else:
                        parsed = phonenumbers.parse(cleaned, None)
                    
                    if phonenumbers.is_valid_number(parsed):
                        info = {
                            'country': geocoder.description_for_number(parsed, 'en'),
                            'country_code': parsed.country_code,
                            'national_number': parsed.national_number,
                            'carrier': carrier.name_for_number(parsed, 'en'),
                            'timezones': list(timezone.time_zones_for_number(parsed)),
                            'international': phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
                            'national': phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL),
                            'e164': phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
                            'is_mobile': 'mobile' in str(carrier.name_for_number(parsed, 'en')).lower()
                        }
                        return True, info['e164'], info
                except:
                    continue
            return False, None, {}
        except Exception as e:
            return False, None, {'error': str(e)}
    
    @staticmethod
    def extract_from_text(text: str, soup: BeautifulSoup = None) -> Dict:
        """Extract all entities from text and HTML"""
        emails = set()
        phones = set()
        social = {platform: set() for platform in AdvancedExtractor.SOCIAL_PATTERNS}
        urls = set()
        
        # Extract emails
        try:
            found_emails = re.findall(AdvancedExtractor.EMAIL_REGEX, text, re.IGNORECASE)
            for email in found_emails:
                valid, cleaned, _ = AdvancedExtractor.validate_email(email)
                if valid:
                    emails.add(cleaned)
        except Exception as e:
            app.logger.error(f"Email extraction error: {str(e)}")
        
        # Extract phones
        try:
            for pattern in AdvancedExtractor.PHONE_PATTERNS:
                found_phones = re.findall(pattern, text, re.IGNORECASE)
                for phone in found_phones:
                    valid, cleaned, _ = AdvancedExtractor.validate_phone(phone)
                    if valid:
                        phones.add(cleaned)
        except Exception as e:
            app.logger.error(f"Phone extraction error: {str(e)}")
        
        # Extract social media from HTML if provided
        if soup:
            try:
                for platform, pattern in AdvancedExtractor.SOCIAL_PATTERNS.items():
                    matches = re.findall(pattern, text, re.IGNORECASE)
                    for match in matches:
                        social[platform].add(match)
                
                # Extract all URLs
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if href.startswith(('http://', 'https://')):
                        urls.add(href)
            except Exception as e:
                app.logger.error(f"Social media extraction error: {str(e)}")
        
        return {
            'emails': sorted(list(emails)),
            'phones': sorted(list(phones)),
            'social': {k: sorted(list(v)) for k, v in social.items() if v},
            'urls': sorted(list(urls))[:100]
        }
    
    @staticmethod
    def enrich_lead(value: str, lead_type: str) -> Dict:
        """Enrich lead data with additional information"""
        enrichment = {}
        
        try:
            if lead_type == 'email':
                domain = value.split('@')[1]
                enrichment = {
                    'gravatar': f'https://www.gravatar.com/avatar/{hashlib.md5(value.lower().encode()).hexdigest()}',
                    'domain_age': None,
                    'mx_records': [],
                    'is_free_provider': domain in ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'aol.com']
                }
            elif lead_type == 'phone':
                valid, _, info = AdvancedExtractor.validate_phone(value)
                if valid:
                    enrichment = info
        except Exception as e:
            app.logger.error(f"Lead enrichment error: {str(e)}")
        
        return enrichment

# ==================== Pro Web Scraper ====================
class ProWebScraper:
    """Professional web scraper with async support"""
    
    def __init__(self):
        self.session = None
        self.executor = ThreadPoolExecutor(max_workers=Config.MAX_CONCURRENT_REQUESTS)
        self.visited_urls = set()
    
    async def get_session(self):
        if not self.session:
            timeout = ClientTimeout(total=Config.REQUEST_TIMEOUT)
            connector = aiohttp.TCPConnector(limit=Config.MAX_CONCURRENT_REQUESTS, ssl=False)
            self.session = ClientSession(timeout=timeout, connector=connector)
        return self.session
    
    def get_headers(self, referer: str = None) -> Dict:
        """Generate random headers for request"""
        headers = {
            'User-Agent': secrets.choice(Config.USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
        }
        if referer:
            headers['Referer'] = referer
        return headers
    
    async def fetch_page(self, url: str, retry_count: int = 2) -> Dict:
        """Async fetch page content with retry logic"""
        for attempt in range(retry_count):
            try:
                session = await self.get_session()
                headers = self.get_headers()
                
                async with session.get(url, headers=headers, allow_redirects=True) as response:
                    if response.status == 200:
                        html = await response.text()
                        return {
                            'success': True,
                            'html': html,
                            'url': str(response.url),
                            'status': response.status,
                            'final_url': str(response.url)
                        }
                    elif response.status in [429, 503]:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    else:
                        return {
                            'success': False,
                            'error': f'HTTP {response.status}',
                            'url': url,
                            'status': response.status
                        }
            except asyncio.TimeoutError:
                if attempt < retry_count - 1:
                    await asyncio.sleep(1)
                    continue
                return {'success': False, 'error': 'Timeout', 'url': url}
            except Exception as e:
                if attempt < retry_count - 1:
                    await asyncio.sleep(1)
                    continue
                return {'success': False, 'error': str(e), 'url': url}
        
        return {'success': False, 'error': 'Max retries exceeded', 'url': url}
    
    def parse_html(self, html: str, url: str) -> Dict:
        """Parse HTML and extract data"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove unwanted elements
            for element in soup(["script", "style", "meta", "noscript", "iframe"]):
                element.decompose()
            
            # Get text content
            text = soup.get_text()
            text = ' '.join(text.split())
            
            # Extract entities
            entities = AdvancedExtractor.extract_from_text(text, soup)
            
            # Get page metadata
            metadata = {
                'title': soup.find('title').string if soup.find('title') else '',
                'meta_description': '',
                'meta_keywords': '',
                'canonical_url': '',
                'language': soup.find('html').get('lang', '') if soup.find('html') else '',
            }
            
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                metadata['meta_description'] = meta_desc['content'][:200]
            
            meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
            if meta_keywords and meta_keywords.get('content'):
                metadata['meta_keywords'] = meta_keywords['content']
            
            canonical = soup.find('link', attrs={'rel': 'canonical'})
            if canonical and canonical.get('href'):
                metadata['canonical_url'] = canonical['href']
            
            # Find internal links
            internal_links = set()
            base_domain = urlparse(url).netloc
            
            for a in soup.find_all('a', href=True):
                href = a['href']
                full_url = urljoin(url, href)
                try:
                    link_domain = urlparse(full_url).netloc
                    if not link_domain or link_domain == base_domain:
                        if not any(x in full_url.lower() for x in ['javascript:', '#', 'mailto:', 'tel:']):
                            internal_links.add(full_url)
                except:
                    continue
            
            return {
                'entities': entities,
                'metadata': metadata,
                'internal_links': list(internal_links)[:50],
                'word_count': len(text.split()),
                'html_size': len(html)
            }
        except Exception as e:
            app.logger.error(f"HTML parsing error for {url}: {str(e)}")
            return {
                'entities': {'emails': [], 'phones': [], 'social': {}, 'urls': []},
                'metadata': {},
                'internal_links': [],
                'word_count': 0,
                'html_size': 0
            }
    
    async def deep_crawl(self, start_url: str, max_pages: int = 20, max_depth: int = 2) -> List[Dict]:
        """Deep crawl website with depth control"""
        visited = set()
        queue = [(start_url, 0)]
        results = []
        
        while queue and len(visited) < max_pages:
            url, depth = queue.pop(0)
            
            if url in visited or depth > max_depth:
                continue
            
            visited.add(url)
            app.logger.info(f"Crawling: {url} (Depth: {depth})")
            
            page_data = await self.fetch_page(url)
            
            if page_data['success']:
                parsed = self.parse_html(page_data['html'], url)
                results.append({
                    'url': url,
                    'depth': depth,
                    'entities': parsed['entities'],
                    'metadata': parsed['metadata']
                })
                
                # Add new links to queue if not at max depth
                if depth < max_depth:
                    for link in parsed['internal_links']:
                        if link not in visited and link not in [q[0] for q in queue]:
                            queue.append((link, depth + 1))
            
            # Rate limiting
            await asyncio.sleep(1)
        
        return results

# ==================== Export Handlers ====================
class ExportManager:
    """Handle various export formats professionally"""
    
    @staticmethod
    def to_csv(leads: List[Dict]) -> str:
        """Export to CSV with proper formatting"""
        output = io.StringIO()
        fieldnames = ['type', 'value', 'source_url', 'confidence_score', 'verified', 'created_at']
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        for lead in leads:
            row = {k: v for k, v in lead.items() if k in fieldnames}
            writer.writerow(row)
        
        return output.getvalue()
    
    @staticmethod
    def to_excel(leads: List[Dict]) -> bytes:
        """Export to Excel with styling"""
        data = []
        for lead in leads:
            data.append({
                'Type': lead['type'],
                'Value': lead['value'],
                'Source URL': lead.get('source_url', ''),
                'Confidence': f"{lead.get('confidence_score', 0)*100:.0f}%",
                'Verified': 'Yes' if lead.get('verified') else 'No',
                'Created At': lead.get('created_at', '')
            })
        
        df = pd.DataFrame(data)
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Leads', index=False)
            
            # Auto-adjust column widths
            worksheet = writer.sheets['Leads']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        output.seek(0)
        return output.getvalue()
    
    @staticmethod
    def to_pdf(leads: List[Dict]) -> bytes:
        """Export to PDF with professional formatting"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=30, bottomMargin=30)
        elements = []
        
        styles = getSampleStyleSheet()
        title_style = styles['Title']
        title_style.fontSize = 24
        elements.append(Paragraph("LeadForge Pro - Lead Generation Report", title_style))
        elements.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        elements.append(Paragraph("<br/><br/>", styles['Normal']))
        
        # Create table data
        data = [['#', 'Type', 'Value', 'Confidence', 'Date']]
        for idx, lead in enumerate(leads[:100], 1):
            data.append([
                str(idx),
                lead['type'].upper(),
                lead['value'],
                f"{lead.get('confidence_score', 0)*100:.0f}%",
                lead.get('created_at', 'N/A')[:16]
            ])
        
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        
        elements.append(table)
        doc.build(elements)
        
        buffer.seek(0)
        return buffer.getvalue()
    
    @staticmethod
    def to_json(leads: List[Dict]) -> str:
        """Export to JSON with proper formatting"""
        export_data = {
            'export_date': datetime.now().isoformat(),
            'total_leads': len(leads),
            'leads': leads
        }
        return json.dumps(export_data, indent=2, default=str)
    
    @staticmethod
    def to_html(leads: List[Dict]) -> str:
        """Export to HTML for web viewing"""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>LeadForge Pro - Lead Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1 {{ color: #667eea; }}
                table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #667eea; color: white; }}
                tr:nth-child(even) {{ background-color: #f2f2f2; }}
                .stats {{ background: #f0f0f0; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <h1>LeadForge Pro - Lead Report</h1>
            <div class="stats">
                <strong>Total Leads:</strong> {len(leads)}<br>
                <strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </div>
            <table>
                <thead>
                    <tr><th>Type</th><th>Value</th><th>Confidence</th><th>Date</th></tr>
                </thead>
                <tbody>
        """
        for lead in leads[:500]:
            html += f"""
                    <tr>
                        <td>{lead['type'].upper()}</td>
                        <td><strong>{lead['value']}</strong></td>
                        <td>{lead.get('confidence_score', 0)*100:.0f}%</td>
                        <td>{lead.get('created_at', 'N/A')[:16]}</td>
                    </tr>
            """
        html += """
                </tbody>
            </table>
        </body>
        </html>
        """
        return html

# ==================== API Routes ====================
@app.route('/api/scrape', methods=['POST'])
@limiter.limit(Config.RATE_LIMIT_PER_IP)
def scrape():
    """Main scraping endpoint - no authentication required"""
    data = request.get_json()
    url = data.get('url')
    deep_crawl = data.get('deep_crawl', False)
    max_pages = min(data.get('max_pages', 20), 30)  # Cap at 30 pages
    verify_leads = data.get('verify_leads', False)
    enrich_leads = data.get('enrich_leads', False)
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    if not validators.url(url):
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        if not validators.url(url):
            return jsonify({'error': 'Invalid URL format'}), 400
    
    # Check blacklist
    domain = urlparse(url).netloc
    conn = sqlite3.connect(Config.DATABASE)
    c = conn.cursor()
    c.execute('SELECT * FROM blacklist WHERE domain = ?', (domain,))
    if c.fetchone():
        conn.close()
        return jsonify({'error': 'This domain is blacklisted'}), 403
    conn.close()
    
    # Generate session ID
    session_id = str(uuid.uuid4())[:8]
    
    # Run scraping asynchronously
    def run_scraping():
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            scraper = ProWebScraper()
            
            try:
                if deep_crawl:
                    results = loop.run_until_complete(scraper.deep_crawl(url, max_pages, max_depth=2))
                else:
                    page_data = loop.run_until_complete(scraper.fetch_page(url))
                    if page_data['success']:
                        parsed = scraper.parse_html(page_data['html'], url)
                        results = [{
                            'url': url,
                            'depth': 0,
                            'entities': parsed['entities'],
                            'metadata': parsed['metadata']
                        }]
                    else:
                        results = []
                
                # Save results to database
                conn = sqlite3.connect(Config.DATABASE)
                c = conn.cursor()
                
                total_emails = 0
                total_phones = 0
                total_social = 0
                
                for result in results:
                    # Save emails
                    for email in result['entities']['emails']:
                        verified = False
                        enrichment = None
                        
                        if verify_leads:
                            valid, _, _ = AdvancedExtractor.validate_email(email)
                            verified = valid
                        
                        if enrich_leads:
                            enrichment = AdvancedExtractor.enrich_lead(email, 'email')
                        
                        c.execute('''INSERT INTO leads (session_id, type, value, source_url, confidence_score, verified, enrichment_data) 
                                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                                 (session_id, 'email', email, result['url'], 0.9, verified, 
                                  json.dumps(enrichment) if enrichment else None))
                        total_emails += 1
                    
                    # Save phones
                    for phone in result['entities']['phones']:
                        verified = False
                        enrichment = None
                        
                        if verify_leads:
                            valid, _, _ = AdvancedExtractor.validate_phone(phone)
                            verified = valid
                        
                        if enrich_leads:
                            enrichment = AdvancedExtractor.enrich_lead(phone, 'phone')
                        
                        c.execute('''INSERT INTO leads (session_id, type, value, source_url, confidence_score, verified, enrichment_data) 
                                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                                 (session_id, 'phone', phone, result['url'], 0.85, verified,
                                  json.dumps(enrichment) if enrichment else None))
                        total_phones += 1
                    
                    # Save social media
                    for platform, handles in result['entities']['social'].items():
                        for handle in handles:
                            c.execute('''INSERT INTO leads (session_id, type, value, source_url, confidence_score) 
                                        VALUES (?, ?, ?, ?, ?)''',
                                     (session_id, f'social_{platform}', f'{platform}:{handle}', result['url'], 0.7))
                            total_social += 1
                
                # Update session record
                c.execute('''INSERT INTO scraping_sessions (id, url, status, emails_found, phones_found, social_found, pages_scraped, 
                            completed_at, ip_address, user_agent)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                         (session_id, url, 'completed', total_emails, total_phones, total_social, len(results),
                          datetime.now(), request.remote_addr, request.headers.get('User-Agent', '')))
                
                # Update statistics
                today = datetime.now().date()
                c.execute('''INSERT INTO statistics (date, total_sessions, total_emails, total_phones, total_pages_scraped)
                            VALUES (?, 1, ?, ?, ?)
                            ON CONFLICT(date) DO UPDATE SET
                            total_sessions = total_sessions + 1,
                            total_emails = total_emails + ?,
                            total_phones = total_phones + ?,
                            total_pages_scraped = total_pages_scraped + ?''',
                         (today, total_emails, total_phones, len(results), total_emails, total_phones, len(results)))
                
                conn.commit()
                conn.close()
                
                app.logger.info(f"Scraping completed for {url}: {total_emails} emails, {total_phones} phones")
                
            except Exception as e:
                app.logger.error(f"Scraping error for {url}: {str(e)}")
                conn = sqlite3.connect(Config.DATABASE)
                c = conn.cursor()
                c.execute('INSERT INTO scraping_sessions (id, url, status, completed_at) VALUES (?, ?, ?, ?)',
                         (session_id, url, 'failed', datetime.now()))
                conn.commit()
                conn.close()
            finally:
                loop.close()
                
        except Exception as e:
            app.logger.error(f"Thread error for {url}: {str(e)}")
    
    # Start async task
    thread = threading.Thread(target=run_scraping)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'success': True,
        'session_id': session_id,
        'message': 'Scraping started',
        'url': url,
        'deep_crawl': deep_crawl
    })

@app.route('/api/status/<session_id>', methods=['GET'])
def get_status(session_id):
    """Get scraping session status and results"""
    conn = sqlite3.connect(Config.DATABASE)
    c = conn.cursor()
    
    c.execute('SELECT * FROM scraping_sessions WHERE id = ?', (session_id,))
    session = c.fetchone()
    
    if not session:
        conn.close()
        return jsonify({'error': 'Session not found'}), 404
    
    c.execute('SELECT * FROM leads WHERE session_id = ?', (session_id,))
    leads = c.fetchall()
    
    # Group leads by type
    emails = [{'value': l[3], 'source': l[4], 'verified': bool(l[6])} for l in leads if l[2] == 'email']
    phones = [{'value': l[3], 'source': l[4], 'verified': bool(l[6])} for l in leads if l[2] == 'phone']
    social = [{'value': l[3], 'source': l[4]} for l in leads if l[2].startswith('social_')]
    
    conn.close()
    
    return jsonify({
        'session_id': session[0],
        'url': session[1],
        'status': session[2],
        'emails_found': session[3],
        'phones_found': session[4],
        'social_found': session[5],
        'pages_scraped': session[6],
        'created_at': session[7],
        'completed_at': session[8],
        'emails': emails,
        'phones': phones,
        'social': social,
        'total_leads': len(emails) + len(phones) + len(social)
    })

@app.route('/api/export/<session_id>', methods=['GET'])
def export_leads(session_id):
    """Export leads in various formats"""
    format_type = request.args.get('format', 'csv').lower()
    
    conn = sqlite3.connect(Config.DATABASE)
    c = conn.cursor()
    
    c.execute('SELECT * FROM leads WHERE session_id = ?', (session_id,))
    leads_data = c.fetchall()
    conn.close()
    
    if not leads_data:
        return jsonify({'error': 'No leads found for this session'}), 404
    
    leads = []
    for l in leads_data:
        lead = {
            'type': l[2],
            'value': l[3],
            'source_url': l[4],
            'confidence_score': l[5],
            'verified': bool(l[6]),
            'created_at': l[8]
        }
        leads.append(lead)
    
    if format_type == 'csv':
        content = ExportManager.to_csv(leads)
        return Response(content, mimetype='text/csv', 
                       headers={'Content-Disposition': f'attachment; filename=leads_{session_id}.csv'})
    elif format_type in ['excel', 'xlsx']:
        content = ExportManager.to_excel(leads)
        return Response(content, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                       headers={'Content-Disposition': f'attachment; filename=leads_{session_id}.xlsx'})
    elif format_type == 'pdf':
        content = ExportManager.to_pdf(leads)
        return Response(content, mimetype='application/pdf', 
                       headers={'Content-Disposition': f'attachment; filename=leads_{session_id}.pdf'})
    elif format_type == 'json':
        content = ExportManager.to_json(leads)
        return Response(content, mimetype='application/json', 
                       headers={'Content-Disposition': f'attachment; filename=leads_{session_id}.json'})
    elif format_type == 'html':
        content = ExportManager.to_html(leads)
        return Response(content, mimetype='text/html', 
                       headers={'Content-Disposition': f'inline; filename=leads_{session_id}.html'})
    else:
        return jsonify({'error': 'Invalid format. Use: csv, excel, pdf, json, html'}), 400

@app.route('/api/verify/batch', methods=['POST'])
@limiter.limit("50 per minute")
def verify_batch():
    """Batch verify emails or phone numbers"""
    data = request.get_json()
    items = data.get('items', [])
    item_type = data.get('type', 'email')
    
    if not items or len(items) > 100:
        return jsonify({'error': 'Please provide 1-100 items'}), 400
    
    results = []
    
    for item in items:
        if item_type == 'email':
            valid, normalized, info = AdvancedExtractor.validate_email(item)
            results.append({
                'original': item,
                'valid': valid,
                'normalized': normalized if valid else None,
                'info': info if valid else None
            })
        elif item_type == 'phone':
            valid, normalized, info = AdvancedExtractor.validate_phone(item)
            results.append({
                'original': item,
                'valid': valid,
                'normalized': normalized if valid else None,
                'info': info if valid else None
            })
        else:
            return jsonify({'error': 'Invalid type. Use "email" or "phone"'}), 400
    
    return jsonify({
        'success': True,
        'type': item_type,
        'total': len(results),
        'valid_count': sum(1 for r in results if r['valid']),
        'results': results
    })

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get global statistics"""
    conn = sqlite3.connect(Config.DATABASE)
    c = conn.cursor()
    
    c.execute('SELECT COUNT(*) FROM scraping_sessions WHERE status = "completed"')
    total_sessions = c.fetchone()[0] or 0
    
    c.execute('SELECT COUNT(*) FROM leads')
    total_leads = c.fetchone()[0] or 0
    
    c.execute('SELECT COUNT(DISTINCT value) FROM leads WHERE type = "email"')
    unique_emails = c.fetchone()[0] or 0
    
    c.execute('SELECT COUNT(DISTINCT value) FROM leads WHERE type = "phone"')
    unique_phones = c.fetchone()[0] or 0
    
    # Get last 7 days stats
    c.execute('''SELECT date, total_sessions, total_emails, total_phones 
                 FROM statistics 
                 WHERE date >= date("now", "-7 days")
                 ORDER BY date''')
    weekly_stats = c.fetchall()
    
    conn.close()
    
    return jsonify({
        'total_sessions': total_sessions,
        'total_leads': total_leads,
        'unique_emails': unique_emails,
        'unique_phones': unique_phones,
        'weekly_stats': [
            {
                'date': stat[0],
                'sessions': stat[1] or 0,
                'emails': stat[2] or 0,
                'phones': stat[3] or 0
            } for stat in weekly_stats
        ]
    })

@app.route('/api/search', methods=['POST'])
@limiter.limit("50 per minute")
def search_leads():
    """Search through collected leads"""
    data = request.get_json()
    query = data.get('query', '').lower()
    lead_type = data.get('type', 'all')
    
    if not query:
        return jsonify({'error': 'Search query required'}), 400
    
    conn = sqlite3.connect(Config.DATABASE)
    c = conn.cursor()
    
    if lead_type == 'all':
        c.execute('''SELECT DISTINCT value, type, source_url, created_at 
                     FROM leads 
                     WHERE LOWER(value) LIKE ? 
                     ORDER BY created_at DESC 
                     LIMIT 100''', (f'%{query}%',))
    else:
        c.execute('''SELECT DISTINCT value, type, source_url, created_at 
                     FROM leads 
                     WHERE type = ? AND LOWER(value) LIKE ? 
                     ORDER BY created_at DESC 
                     LIMIT 100''', (lead_type, f'%{query}%'))
    
    results = c.fetchall()
    conn.close()
    
    return jsonify({
        'query': query,
        'type': lead_type,
        'total_found': len(results),
        'results': [
            {
                'value': r[0],
                'type': r[1],
                'source': r[2],
                'date': r[3]
            } for r in results
        ]
    })

# ==================== Web Interface ====================
@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

# ==================== HTML Template (same as before) ====================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LeadForge Pro - Lead Generation Platform</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        * { font-family: 'Inter', sans-serif; }
        .gradient-bg { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .card-hover { transition: all 0.3s ease; }
        .card-hover:hover { transform: translateY(-5px); box-shadow: 0 20px 40px rgba(0,0,0,0.1); }
    </style>
</head>
<body class="bg-gray-50">
    <!-- Navigation -->
    <nav class="gradient-bg text-white shadow-xl">
        <div class="container mx-auto px-6 py-4">
            <div class="flex justify-between items-center">
                <div class="flex items-center space-x-3">
                    <i class="fas fa-fire fa-2x"></i>
                    <span class="text-2xl font-bold">LeadForge Pro</span>
                    <span class="text-xs bg-white bg-opacity-20 px-2 py-1 rounded-full">Premium Edition</span>
                </div>
                <div class="flex space-x-4">
                    <a href="#scraper" class="hover:text-gray-200">Scraper</a>
                    <a href="#stats" class="hover:text-gray-200">Statistics</a>
                </div>
            </div>
        </div>
    </nav>

    <!-- Hero Section -->
    <div class="gradient-bg text-white py-16">
        <div class="container mx-auto px-6 text-center">
            <h1 class="text-4xl font-bold mb-4">Extract. Verify. Enrich.</h1>
            <p class="text-xl opacity-90">Professional lead generation platform</p>
        </div>
    </div>

    <!-- Main Content -->
    <div class="container mx-auto px-6 py-12">
        <!-- Scraper Card -->
        <div id="scraper" class="bg-white rounded-2xl shadow-xl p-8 mb-8 card-hover">
            <h2 class="text-2xl font-bold mb-4"><i class="fas fa-search text-purple-600 mr-2"></i>Lead Scraper</h2>
            
            <div class="mb-4">
                <label class="block text-gray-700 font-semibold mb-2">Target URL</label>
                <input type="url" id="scrapeUrl" class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:border-purple-500" 
                       placeholder="https://example.com/contact">
            </div>
            
            <div class="grid md:grid-cols-2 gap-4 mb-6">
                <label class="flex items-center">
                    <input type="checkbox" id="deepCrawl" class="mr-2 w-5 h-5">
                    <span>Deep Crawl <span class="text-sm text-gray-500">(crawl multiple pages)</span></span>
                </label>
                <label class="flex items-center">
                    <input type="checkbox" id="verifyLeads" class="mr-2 w-5 h-5">
                    <span>Auto-Verify <span class="text-sm text-gray-500">(validate emails/phones)</span></span>
                </label>
            </div>
            
            <button onclick="startScraping()" id="scrapeBtn" class="w-full gradient-bg text-white font-bold py-3 rounded-lg hover:shadow-lg transition">
                <i class="fas fa-rocket mr-2"></i>Start Scraping
            </button>
            
            <div id="progress" style="display:none;" class="mt-4 text-center">
                <i class="fas fa-spinner fa-spin mr-2"></i>Scraping in progress...
            </div>
        </div>

        <!-- Statistics -->
        <div id="stats" class="bg-white rounded-2xl shadow-xl p-8 mb-8">
            <h2 class="text-2xl font-bold mb-4"><i class="fas fa-chart-bar text-purple-600 mr-2"></i>Global Statistics</h2>
            <div class="grid md:grid-cols-4 gap-4">
                <div class="text-center p-4 bg-gray-50 rounded-lg">
                    <div id="totalSessions" class="text-2xl font-bold text-purple-600">0</div>
                    <div class="text-gray-600">Total Scrapes</div>
                </div>
                <div class="text-center p-4 bg-gray-50 rounded-lg">
                    <div id="totalEmails" class="text-2xl font-bold text-blue-600">0</div>
                    <div class="text-gray-600">Emails Found</div>
                </div>
                <div class="text-center p-4 bg-gray-50 rounded-lg">
                    <div id="totalPhones" class="text-2xl font-bold text-green-600">0</div>
                    <div class="text-gray-600">Phone Numbers</div>
                </div>
                <div class="text-center p-4 bg-gray-50 rounded-lg">
                    <div id="totalLeads" class="text-2xl font-bold text-orange-600">0</div>
                    <div class="text-gray-600">Total Leads</div>
                </div>
            </div>
        </div>

        <!-- Results -->
        <div id="results" style="display:none;" class="bg-white rounded-2xl shadow-xl p-8">
            <div class="flex justify-between items-center mb-4">
                <h2 class="text-2xl font-bold"><i class="fas fa-trophy text-purple-600 mr-2"></i>Results</h2>
                <div class="flex space-x-2">
                    <button onclick="exportData('csv')" class="px-3 py-1 bg-green-600 text-white rounded">CSV</button>
                    <button onclick="exportData('excel')" class="px-3 py-1 bg-blue-600 text-white rounded">Excel</button>
                    <button onclick="exportData('pdf')" class="px-3 py-1 bg-red-600 text-white rounded">PDF</button>
                </div>
            </div>
            <div id="resultsContent"></div>
        </div>
    </div>

    <script>
        let currentSessionId = null;
        let statusInterval = null;
        
        loadStats();
        setInterval(loadStats, 30000);
        
        async function loadStats() {
            try {
                const response = await fetch('/api/stats');
                const data = await response.json();
                document.getElementById('totalSessions').textContent = data.total_sessions || 0;
                document.getElementById('totalEmails').textContent = data.unique_emails || 0;
                document.getElementById('totalPhones').textContent = data.unique_phones || 0;
                document.getElementById('totalLeads').textContent = data.total_leads || 0;
            } catch(e) { console.error(e); }
        }
        
        async function startScraping() {
            const url = document.getElementById('scrapeUrl').value;
            const deepCrawl = document.getElementById('deepCrawl').checked;
            const verifyLeads = document.getElementById('verifyLeads').checked;
            
            if (!url) {
                alert('Please enter a URL');
                return;
            }
            
            const btn = document.getElementById('scrapeBtn');
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Starting...';
            document.getElementById('progress').style.display = 'block';
            
            try {
                const response = await fetch('/api/scrape', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        url: url,
                        deep_crawl: deepCrawl,
                        max_pages: 20,
                        verify_leads: verifyLeads,
                        enrich_leads: false
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    currentSessionId = data.session_id;
                    if (statusInterval) clearInterval(statusInterval);
                    statusInterval = setInterval(checkStatus, 3000);
                } else {
                    alert('Error: ' + data.error);
                    resetButton();
                }
            } catch(e) {
                alert('Error: ' + e.message);
                resetButton();
            }
        }
        
        async function checkStatus() {
            if (!currentSessionId) return;
            
            try {
                const response = await fetch(`/api/status/${currentSessionId}`);
                const data = await response.json();
                
                if (data.status === 'completed') {
                    clearInterval(statusInterval);
                    displayResults(data);
                    resetButton();
                    loadStats();
                } else if (data.status === 'failed') {
                    clearInterval(statusInterval);
                    alert('Scraping failed');
                    resetButton();
                }
            } catch(e) {
                console.error(e);
            }
        }
        
        function displayResults(data) {
            document.getElementById('results').style.display = 'block';
            
            let html = '<div class="space-y-4">';
            
            if (data.emails && data.emails.length > 0) {
                html += '<div><h3 class="font-bold text-lg mb-2">📧 Emails</h3><div class="space-y-1">';
                data.emails.forEach(email => {
                    html += `<div class="flex justify-between items-center p-2 bg-gray-50 rounded">
                                <span class="font-mono">${escapeHtml(email.value)}</span>
                                <button onclick="copyToClipboard('${escapeHtml(email.value)}')" class="text-purple-600">Copy</button>
                             </div>`;
                });
                html += '</div></div>';
            }
            
            if (data.phones && data.phones.length > 0) {
                html += '<div><h3 class="font-bold text-lg mb-2 mt-4">📞 Phone Numbers</h3><div class="space-y-1">';
                data.phones.forEach(phone => {
                    html += `<div class="flex justify-between items-center p-2 bg-gray-50 rounded">
                                <span class="font-mono">${escapeHtml(phone.value)}</span>
                                <button onclick="copyToClipboard('${escapeHtml(phone.value)}')" class="text-purple-600">Copy</button>
                             </div>`;
                });
                html += '</div></div>';
            }
            
            if (data.emails.length === 0 && data.phones.length === 0) {
                html += '<p class="text-center text-gray-500">No leads found. Try enabling Deep Crawl or a different URL.</p>';
            }
            
            html += '</div>';
            document.getElementById('resultsContent').innerHTML = html;
        }
        
        async function exportData(format) {
            if (!currentSessionId) {
                alert('No active session');
                return;
            }
            window.open(`/api/export/${currentSessionId}?format=${format}`, '_blank');
        }
        
        function resetButton() {
            const btn = document.getElementById('scrapeBtn');
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-rocket mr-2"></i>Start Scraping';
            document.getElementById('progress').style.display = 'none';
        }
        
        function copyToClipboard(text) {
            navigator.clipboard.writeText(text);
            alert('Copied: ' + text);
        }
        
        function escapeHtml(str) {
            if (!str) return '';
            return String(str).replace(/[&<>]/g, function(m) {
                if (m === '&') return '&amp;';
                if (m === '<') return '&lt;';
                if (m === '>') return '&gt;';
                return m;
            });
        }
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    print("=" * 70)
    print("🔥 LeadForge Pro v5.0 - Windows Edition")
    print("=" * 70)
    print(f"📍 Server: http://127.0.0.1:5000")
    print(f"💻 OS: {platform.system()} {platform.release()}")
    print(f"🐍 Python: {platform.python_version()}")
    print("=" * 70)
    print("📊 Features:")
    print("   • No login required")
    print("   • Async scraping (Windows optimized)")
    print("   • Email & phone validation")
    print("   • Multiple export formats")
    print("   • SQLite database")
    print("=" * 70)
    print("🎯 Test URLs:")
    print("   • https://www.python.org/contact")
    print("   • https://www.yellowpages.com")
    print("   • https://www.bbc.com/contact")
    print("=" * 70)
    
    app.run(debug=True, host='127.0.0.1', port=5000, threaded=True)