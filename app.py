# app.py - LeadForge v4 (Working with AJAX)
from flask import Flask, request, render_template_string, jsonify
import re
from datetime import datetime
import csv
import io
import requests
import json
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

app = Flask(__name__)

EMAIL_REGEX = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
PHONE_REGEX = r'(\+?254|0)[17]\d{8}|\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'

def clean_text(text):
    if not text:
        return ""
    try:
        return text.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
    except:
        return re.sub(r'[\ud800-\udfff]', '', text)

def is_internal_link(base_url, link):
    try:
        base_domain = urlparse(base_url).netloc
        link_domain = urlparse(link).netloc
        return not link_domain or link_domain == base_domain
    except:
        return False

def scrape_page(url, timeout=15):
    """Simple page scraper using requests"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, timeout=timeout, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        text = soup.get_text()
        text = ' '.join(text.split())
        
        return {
            'success': True,
            'text': clean_text(text),
            'soup': soup,
            'url': url
        }
    except Exception as e:
        return {'success': False, 'error': str(e), 'url': url}

def extract_emails_and_phones(text, soup):
    """Extract emails and phones from text and HTML"""
    emails = set()
    phones = set()
    
    # Find emails in text
    found_emails = re.findall(EMAIL_REGEX, text, re.IGNORECASE)
    for email in found_emails:
        email = email.lower().strip()
        if '@' in email and '.' in email.split('@')[1]:
            emails.add(email)
    
    # Find phones in text (simplified)
    # Look for common phone patterns
    phone_patterns = [
        r'\+\d{1,3}[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}',
        r'\d{3}[-.\s]?\d{3}[-.\s]?\d{4}',
        r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
        r'0[17]\d{8}',  # Kenyan numbers
        r'\+254[17]\d{8}',
    ]
    
    for pattern in phone_patterns:
        found_phones = re.findall(pattern, text)
        for phone in found_phones:
            phone = re.sub(r'\s+', ' ', phone).strip()
            digits = re.sub(r'\D', '', phone)
            if len(digits) >= 8 and len(digits) <= 15:
                phones.add(phone)
    
    # Check mailto: links
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('mailto:'):
            email = href[7:].split('?')[0].strip()
            if '@' in email:
                emails.add(email.lower())
        elif href.startswith('tel:'):
            phone = href[4:].strip()
            if phone:
                phones.add(phone)
    
    return sorted(list(emails)), sorted(list(phones))

@app.route('/scrape', methods=['POST'])
def scrape():
    data = request.get_json()
    url = data.get('url', '')
    deep_crawl = data.get('deep_crawl', False)
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        # Scrape main page
        result = scrape_page(url)
        
        if not result['success']:
            return jsonify({'error': f"Failed to load page: {result.get('error', 'Unknown error')}"}), 400
        
        all_text = result['text']
        all_soup = result['soup']
        all_emails, all_phones = extract_emails_and_phones(all_text, all_soup)
        
        if deep_crawl:
            # Find relevant links
            links = []
            for a in all_soup.find_all('a', href=True):
                href = a['href']
                full_url = urljoin(url, href)
                if is_internal_link(url, full_url):
                    link_text = a.get_text().lower()
                    if any(keyword in link_text for keyword in ['contact', 'about', 'team', 'contact us', 'get in touch', 'support']):
                        links.append(full_url)
            
            # Remove duplicates and limit
            links = list(dict.fromkeys(links))[:5]
            
            # Scrape additional pages
            for link in links:
                page_result = scrape_page(link, timeout=10)
                if page_result['success']:
                    new_emails, new_phones = extract_emails_and_phones(
                        page_result['text'], 
                        page_result['soup']
                    )
                    all_emails.extend(new_emails)
                    all_phones.extend(new_phones)
        
        # Deduplicate
        all_emails = sorted(list(set(all_emails)))
        all_phones = sorted(list(set(all_phones)))
        
        # Get company info
        title = "Not detected"
        if all_soup.find('title') and all_soup.find('title').string:
            title = clean_text(all_soup.find('title').string.strip())[:100]
        
        # Simple meta description extraction
        description = ""
        meta_desc = all_soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            description = clean_text(meta_desc['content'])[:200]
        
        insights = {
            "company_name": title,
            "description": description,
            "pages_scraped": 1 + (len(links) if deep_crawl else 0)
        }
        
        return jsonify({
            'success': True,
            'emails': all_emails,
            'phones': all_phones,
            'insights': insights,
            'total_leads': len(all_emails) + len(all_phones),
            'url': url
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download_csv', methods=['POST'])
def download_csv():
    data = request.get_json()
    emails = data.get('emails', [])
    phones = data.get('phones', [])
    domain = data.get('domain', 'leads')
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Type', 'Value', 'Domain', 'Scraped Date'])
    
    for email in emails:
        writer.writerow(['Email', email, domain, datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
    
    for phone in phones:
        writer.writerow(['Phone', phone, domain, datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
    
    output.seek(0)
    response_content = output.getvalue().encode('utf-8', errors='ignore')
    safe_filename = re.sub(r'[^a-zA-Z0-9_-]', '_', domain)[:50]
    
    return Response(
        response_content,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={safe_filename}_leads.csv'}
    )

@app.route('/', methods=['GET'])
def home():
    return render_template_string(HTML_TEMPLATE)

# ===================== HTML TEMPLATE =====================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LeadForge - Email & Phone Extractor</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 {
            text-align: center;
            color: white;
            margin-bottom: 10px;
            font-size: 2.5rem;
        }
        .subtitle {
            text-align: center;
            color: rgba(255,255,255,0.9);
            margin-bottom: 30px;
        }
        .card {
            background: white;
            border-radius: 20px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.2);
        }
        label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #333;
        }
        input[type="text"] {
            width: 100%;
            padding: 12px 16px;
            font-size: 1rem;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            margin-bottom: 15px;
            transition: border-color 0.3s;
        }
        input[type="text"]:focus {
            outline: none;
            border-color: #667eea;
        }
        button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 14px 30px;
            font-size: 1rem;
            font-weight: 600;
            border-radius: 10px;
            cursor: pointer;
            width: 100%;
            transition: transform 0.2s;
        }
        button:hover:not(:disabled) {
            transform: translateY(-2px);
        }
        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        .loading {
            display: none;
            text-align: center;
            margin-top: 20px;
        }
        .spinner {
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 10px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .test-buttons {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 15px;
        }
        .test-btn {
            background: #f0f0f0;
            color: #333;
            padding: 8px 16px;
            font-size: 0.85rem;
            width: auto;
            background: #f8f9fa;
            border: 1px solid #dee2e6;
        }
        .test-btn:hover {
            background: #e9ecef;
            transform: translateY(-1px);
        }
        .results-stats {
            display: flex;
            gap: 20px;
            margin: 20px 0;
        }
        .stat-box {
            flex: 1;
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }
        .stat-number {
            font-size: 2rem;
            font-weight: bold;
            color: #667eea;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e0e0e0;
        }
        th {
            background: #f8f9fa;
            font-weight: 600;
        }
        .copy-btn {
            background: #28a745;
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 0.85rem;
            width: auto;
        }
        .copy-btn:hover {
            background: #218838;
            transform: none;
        }
        .error {
            background: #f8d7da;
            color: #721c24;
            padding: 15px;
            border-radius: 10px;
            margin-top: 15px;
        }
        .insights {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
        }
        .download-btn {
            background: #28a745;
            margin-top: 20px;
        }
        .download-btn:hover {
            background: #218838;
        }
        @media (max-width: 768px) {
            .results-stats { flex-direction: column; }
            .test-buttons { justify-content: center; }
        }
    </style>
</head>
<body>
<div class="container">
    <h1>🔗 LeadForge</h1>
    <div class="subtitle">Extract emails and phone numbers from any website</div>
    
    <div class="card">
        <form id="leadForm" onsubmit="return false;">
            <label>🌐 Website URL</label>
            <input type="text" id="urlInput" placeholder="https://example.com" value="https://www.yellowpages.com">
            
            <label>🔍 Keywords (optional)</label>
            <input type="text" id="keywordsInput" placeholder="contact, email, phone, support">
            
            <div style="margin: 15px 0;">
                <label style="display: inline-block; margin-left: 10px;">
                    <input type="checkbox" id="deepCrawl"> 
                    Deep Crawl (finds more leads, takes longer)
                </label>
            </div>
            
            <button type="button" id="extractBtn">🚀 Start Scraping</button>
        </form>
        
        <div class="test-buttons">
            <button class="test-btn" onclick="setUrl('https://www.yellowpages.com')">Yellow Pages</button>
            <button class="test-btn" onclick="setUrl('https://www.python.org')">Python.org</button>
            <button class="test-btn" onclick="setUrl('https://www.bbc.com/contact')">BBC Contact</button>
            <button class="test-btn" onclick="setUrl('https://www.github.com/contact')">GitHub Contact</button>
            <button class="test-btn" onclick="setUrl('https://www.yelp.com')">Yelp</button>
            <button class="test-btn" onclick="setUrl('https://www.trustpilot.com')">Trustpilot</button>
        </div>
        
        <div id="loading" class="loading">
            <div class="spinner"></div>
            <p>Scraping website... This may take a few seconds.</p>
        </div>
    </div>
    
    <div id="errorBox" style="display: none;"></div>
    <div id="results"></div>
</div>

<script>
let isScraping = false;

function setUrl(url) {
    document.getElementById('urlInput').value = url;
}

document.getElementById('extractBtn').addEventListener('click', async function() {
    if (isScraping) return;
    
    const url = document.getElementById('urlInput').value.trim();
    const keywords = document.getElementById('keywordsInput').value.trim();
    const deepCrawl = document.getElementById('deepCrawl').checked;
    
    if (!url) {
        alert('Please enter a URL');
        return;
    }
    
    const btn = document.getElementById('extractBtn');
    const loading = document.getElementById('loading');
    const errorBox = document.getElementById('errorBox');
    const resultsDiv = document.getElementById('results');
    
    isScraping = true;
    btn.disabled = true;
    btn.textContent = '⏳ Scraping...';
    loading.style.display = 'block';
    errorBox.style.display = 'none';
    resultsDiv.innerHTML = '';
    
    try {
        const response = await fetch('/scrape', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                url: url,
                keywords: keywords,
                deep_crawl: deepCrawl
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        if (data.success) {
            displayResults(data);
        } else {
            throw new Error('Unknown error occurred');
        }
    } catch (error) {
        showError(error.message);
    } finally {
        isScraping = false;
        btn.disabled = false;
        btn.textContent = '🚀 Start Scraping';
        loading.style.display = 'none';
    }
});

function displayResults(data) {
    const resultsDiv = document.getElementById('results');
    
    if (data.emails.length === 0 && data.phones.length === 0) {
        resultsDiv.innerHTML = `
            <div class="card">
                <h3>📭 No leads found</h3>
                <p>No emails or phone numbers were found on ${escapeHtml(data.url)}</p>
                <p style="margin-top: 15px;">Try:</p>
                <ul style="margin-left: 20px;">
                    <li>Enabling "Deep Crawl"</li>
                    <li>Trying a business directory like Yellow Pages</li>
                    <li>Checking a contact or about page</li>
                </ul>
                <p style="margin-top: 15px;">Example URLs that work well:</p>
                <ul style="margin-left: 20px;">
                    <li>https://www.yellowpages.com</li>
                    <li>https://www.python.org</li>
                    <li>https://www.bbc.com/contact</li>
                </ul>
            </div>
        `;
        return;
    }
    
    resultsDiv.innerHTML = `
        <div class="card">
            <h2>📊 Results for ${escapeHtml(data.url)}</h2>
            
            <div class="results-stats">
                <div class="stat-box">
                    <div class="stat-number">${data.emails.length}</div>
                    <div>📧 Emails Found</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">${data.phones.length}</div>
                    <div>📞 Phone Numbers</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">${data.total_leads}</div>
                    <div>🎯 Total Leads</div>
                </div>
            </div>
            
            ${data.insights ? `
            <div class="insights">
                <h3>ℹ️ Page Insights</h3>
                <p><strong>Title:</strong> ${escapeHtml(data.insights.company_name)}</p>
                <p><strong>Description:</strong> ${escapeHtml(data.insights.description || 'Not available')}</p>
                <p><strong>Pages Scraped:</strong> ${data.insights.pages_scraped || 1}</p>
            </div>
            ` : ''}
            
            ${data.emails.length > 0 ? `
            <h3>📧 Emails (${data.emails.length})</h3>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr><th>Email Address</th><th>Action</th></tr>
                    </thead>
                    <tbody>
                        ${data.emails.map(email => `
                            <tr>
                                <td><strong>${escapeHtml(email)}</strong></td>
                                <td><button class="copy-btn" onclick="copyToClipboard('${escapeHtml(email)}')">Copy</button></td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
            ` : ''}
            
            ${data.phones.length > 0 ? `
            <h3 style="margin-top: 30px;">📞 Phone Numbers (${data.phones.length})</h3>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr><th>Phone Number</th><th>Action</th></tr>
                    </thead>
                    <tbody>
                        ${data.phones.map(phone => `
                            <tr>
                                <td><strong>${escapeHtml(phone)}</strong></td>
                                <td><button class="copy-btn" onclick="copyToClipboard('${escapeHtml(phone)}')">Copy</button></td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
            ` : ''}
            
            <button onclick="downloadCSV(${JSON.stringify(escapeHtml(data.emails))}, ${JSON.stringify(escapeHtml(data.phones))}, '${escapeHtml(data.url)}')" class="download-btn" style="width: 100%;">📥 Download CSV</button>
        </div>
    `;
}

async function downloadCSV(emails, phones, domain) {
    try {
        const response = await fetch('/download_csv', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                emails: emails,
                phones: phones,
                domain: domain
            })
        });
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${domain.replace(/[^a-zA-Z0-9]/g, '_')}_leads.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    } catch (error) {
        showError('Failed to download CSV: ' + error.message);
    }
}

function showError(msg) {
    const errorBox = document.getElementById('errorBox');
    errorBox.innerHTML = `<div class="error">⚠️ Error: ${escapeHtml(msg)}</div>`;
    errorBox.style.display = 'block';
    setTimeout(() => {
        errorBox.style.display = 'none';
    }, 5000);
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        const toast = document.createElement('div');
        toast.textContent = '✅ Copied!';
        toast.style.cssText = 'position:fixed;bottom:20px;right:20px;background:#28a745;color:white;padding:10px 20px;border-radius:10px;z-index:1000;';
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 2000);
    });
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
    print("=" * 60)
    print("🚀 LeadForge v4 - Working Version")
    print("=" * 60)
    print("📍 Running at: http://127.0.0.1:5000")
    print("📝 Try these test URLs:")
    print("   - https://www.yellowpages.com")
    print("   - https://www.python.org")
    print("   - https://www.bbc.com/contact")
    print("   - https://www.github.com/contact")
    print("=" * 60)
    app.run(debug=True, port=5000, threaded=True)