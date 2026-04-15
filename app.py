# app.py - LeadForge v2 with Real Progress Bar
from flask import Flask, request, render_template_string, Response, stream_with_context
import re
from datetime import datetime
import csv
import io
import asyncio
import random
import time
from urllib.parse import urlparse

from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from bs4 import BeautifulSoup

app = Flask(__name__)

EMAIL_REGEX = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
PHONE_REGEX = r'(\+?254|0)[17]\d{8}|\+?\d{1,4}[\s.-]?\(?\d{1,4}\)?[\s.-]?\d{1,4}[\s.-]?\d{1,4}'

def is_internal_link(base_url, link):
    base_domain = urlparse(base_url).netloc
    link_domain = urlparse(link).netloc
    return not link_domain or link_domain == base_domain

async def scrape_with_progress(url, deep_crawl=False):
    """Generator that yields progress updates"""
    yield "progress:10|Starting browser...\n"
    await asyncio.sleep(0.5)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=random.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36"
                ])
            )
            page = await context.new_page()
            await stealth_async(page)

            yield "progress:25|Navigating to website...\n"
            await page.goto(url, wait_until="networkidle", timeout=45000)
            await page.wait_for_timeout(2000)

            yield "progress:45|Extracting page content...\n"
            full_text = await page.inner_text("body")
            html = await page.content()

            if deep_crawl:
                yield "progress:55|Deep Crawl started - finding internal pages...\n"
                links = await page.evaluate('''() => Array.from(document.querySelectorAll('a[href]'))
                    .map(a => a.href)
                    .filter(h => h && (h.includes('contact') || h.includes('about') || h.includes('team') || h.includes('services')))''')

                visited = set()
                for i, link in enumerate(links[:8]):
                    if link in visited or not is_internal_link(url, link):
                        continue
                    visited.add(link)
                    try:
                        yield f"progress:{60 + i*5}|Crawling internal page {i+1}/5...\n"
                        await page.goto(link, wait_until="networkidle", timeout=20000)
                        await page.wait_for_timeout(1500)
                        full_text += " " + await page.inner_text("body")
                        html += await page.content()
                        if len(visited) >= 5:
                            break
                    except:
                        continue

            yield "progress:85|Extracting emails and phones...\n"
            await browser.close()

            yield "progress:100|Processing complete!\n"
            return html, full_text

    except Exception as e:
        yield f"error:Failed to scrape: {str(e)}\n"
        return None, None

def extract_insights(soup, text, keywords=None):
    insights = {"company_name": "", "description": "", "industry_keywords": [], "location": "", "detected_sections": []}
    
    title = soup.find('title')
    if title and title.string:
        insights["company_name"] = title.string.strip().split('|')[0].strip()
    
    meta = soup.find('meta', attrs={'name': 'description'})
    if meta and meta.get('content'):
        insights["description"] = meta['content'].strip()

    lower = text.lower()
    if keywords:
        kws = [k.strip().lower() for k in keywords.split(',')]
        insights["industry_keywords"] = [k.capitalize() for k in kws if k in lower]

    for word in ["tech", "software", "marketing", "sales", "ai"]:
        if word in lower and word.capitalize() not in insights["industry_keywords"]:
            insights["industry_keywords"].append(word.capitalize())

    for sec in ['contact', 'about', 'services', 'team']:
        if sec in lower:
            insights["detected_sections"].append(sec.capitalize())

    if 'nairobi' in lower or 'kenya' in lower:
        insights["location"] = "Nairobi, Kenya"

    return insights

# ===================== PROGRESS STREAM =====================
@app.route('/scrape')
def scrape_stream():
    url = request.args.get('url')
    keywords = request.args.get('keywords', '')
    deep_crawl = request.args.get('deep_crawl') == 'true'

    if not url:
        return "No URL provided", 400

    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    def generate():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            html, full_text = loop.run_until_complete(scrape_with_progress(url, deep_crawl))
            
            if not html:
                yield "error:Scraping failed\n"
                return

            soup = BeautifulSoup(html, 'html.parser')

            emails = re.findall(EMAIL_REGEX, full_text)
            phones = re.findall(PHONE_REGEX, full_text)

            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith('mailto:'):
                    email = href[7:].split('?')[0].strip()
                    if re.match(EMAIL_REGEX, email):
                        emails.append(email)
                elif href.startswith(('tel:', 'call:')):
                    phone = re.sub(r'[^0-9+\s-]', '', href[4:]).strip()
                    if phone:
                        phones.append(phone)

            valid_emails = sorted(list(set(e.lower() for e in emails if re.match(EMAIL_REGEX, e))))
            valid_phones = sorted(list(set(p for p in phones if len(re.sub(r'\D', '', p)) >= 8)))

            insights = extract_insights(soup, full_text, keywords)

            leads = {
                "emails": valid_emails,
                "phones": valid_phones,
                "insights": insights,
                "total_leads": len(valid_emails) + len(valid_phones),
                "url": url
            }

            # Send final data as JSON string
            import json
            yield "data:" + json.dumps(leads) + "\n"

        except Exception as e:
            yield f"error:Unexpected error: {str(e)}\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

# ===================== MAIN PAGE =====================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LeadForge v2</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
        :root { --primary: #00d4ff; }
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family:'Inter',sans-serif; background:linear-gradient(135deg,#0f172a 0%,#1e2937 100%); color:#e2e8f0; min-height:100vh; padding:40px 20px; }
        .container { max-width:1200px; margin:0 auto; }
        h1 { font-size:2.8rem; text-align:center; background:linear-gradient(90deg,#00d4ff,#a5f4ff); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
        .card { background:#1e2937; border-radius:20px; padding:40px; margin-bottom:30px; box-shadow:0 20px 40px rgba(0,212,255,0.1); }
        label { display:block; margin-bottom:8px; font-weight:500; color:#cbd5e1; }
        input[type="text"] { width:100%; padding:18px 24px; font-size:1.1rem; border:2px solid #334155; border-radius:12px; background:#0f172a; color:white; margin-bottom:15px; }
        button { padding:18px 40px; font-size:1.1rem; font-weight:600; background:var(--primary); color:#0f172a; border:none; border-radius:12px; cursor:pointer; width:100%; }
        .progress-container { display:none; margin:20px 0; }
        .progress-bar { height:8px; background:#334155; border-radius:4px; overflow:hidden; }
        .progress-fill { height:100%; background:linear-gradient(90deg,#00d4ff,#a5f4ff); width:0%; transition:width 0.4s ease; }
        .insights { background:#0f172a; border-radius:16px; padding:25px; margin:25px 0; border-left:5px solid var(--primary); }
        table { width:100%; border-collapse:collapse; background:#0f172a; border-radius:12px; overflow:hidden; margin-top:15px; }
        th { background:#1e2937; padding:18px 24px; text-align:left; color:#64748b; }
        td { padding:18px 24px; border-top:1px solid #334155; }
        .badge { padding:6px 16px; border-radius:50px; background:#22c55e; color:#052e16; }
        .download-btn { background:#22c55e; color:white; border:none; padding:16px 40px; font-size:1.05rem; border-radius:12px; cursor:pointer; }
        .stat-card { flex:1; background:#0f172a; padding:20px; border-radius:12px; text-align:center; }
    </style>
</head>
<body>
<div class="container">
    <h1>LeadForge v2</h1>
    <p style="text-align:center;color:#94a3b8;margin-bottom:40px;">Async Scraper with Live Progress</p>

    <div class="card">
        <form id="leadForm">
            <label>Website URL</label>
            <input type="text" id="urlInput" placeholder="https://www.apollo.io" required>

            <label>Keywords (optional)</label>
            <input type="text" id="keywordsInput" placeholder="sales, contact, ceo, nairobi">

            <div style="margin:15px 0;">
                <input type="checkbox" id="deepCrawl">
                <label for="deepCrawl">Deep Crawl (follow Contact/About/Team pages)</label>
            </div>

            <button type="button" id="extractBtn">🚀 Extract Leads & Insights</button>
        </form>

        <div id="progressContainer" class="progress-container">
            <div style="margin-bottom:8px;" id="progressText">Starting scrape...</div>
            <div class="progress-bar">
                <div id="progressFill" class="progress-fill"></div>
            </div>
        </div>
    </div>

    <div id="errorBox" class="card" style="display:none; background:#7f1d1d;color:#fda4af;"></div>

    <div id="results" style="display:none;">
        <!-- Results will be injected here by JS -->
    </div>
</div>

<footer>LeadForge v2 • Live Progress Bar + Async Scraper</footer>

<script>
const eventSource = null;

document.getElementById('extractBtn').addEventListener('click', async function() {
    const url = document.getElementById('urlInput').value.trim();
    const keywords = document.getElementById('keywordsInput').value.trim();
    const deepCrawl = document.getElementById('deepCrawl').checked;

    if (!url) {
        alert("Please enter a website URL");
        return;
    }

    // Show progress
    document.getElementById('progressContainer').style.display = 'block';
    document.getElementById('progressFill').style.width = '0%';
    document.getElementById('progressText').textContent = 'Connecting to browser...';

    const params = new URLSearchParams({
        url: url,
        keywords: keywords,
        deep_crawl: deepCrawl
    });

    const source = new EventSource('/scrape?' + params);

    source.onmessage = function(event) {
        if (event.data.startsWith('progress:')) {
            const [_, progressStr] = event.data.split('|');
            const [percent, text] = progressStr.split('|');
            document.getElementById('progressFill').style.width = percent + '%';
            document.getElementById('progressText').textContent = text;
        } 
        else if (event.data.startsWith('data:')) {
            const leads = JSON.parse(event.data.substring(5));
            renderResults(leads, url);
            source.close();
        } 
        else if (event.data.startsWith('error:')) {
            showError(event.data.substring(6));
            source.close();
        }
    };

    source.onerror = function() {
        showError("Connection lost. Please try again.");
        source.close();
    };
});

function renderResults(data, url) {
    document.getElementById('progressContainer').style.display = 'none';
    document.getElementById('results').style.display = 'block';
    document.getElementById('results').innerHTML = `
        <div class="card">
            <h2>Results for <span style="color:var(--primary);">${url}</span></h2>
            <p style="color:#94a3b8;">Processed at ${new Date().toLocaleTimeString()}</p>

            <div class="insights">
                <h3>📊 Business Insights</h3>
                <p><strong>Company:</strong> ${data.insights.company_name || 'Not detected'}</p>
                <p><strong>Description:</strong> ${data.insights.description ? data.insights.description.substring(0, 280) + '...' : 'Not available'}</p>
                <p><strong>Location:</strong> ${data.insights.location || 'Not detected'}</p>
                <p><strong>Industry:</strong> ${data.insights.industry_keywords.join(', ') || 'None'}</p>
            </div>

            <div style="display:flex; gap:20px; margin:30px 0;">
                <div class="stat-card"><div style="font-size:2.5rem;color:#22c55e;">${data.emails.length}</div><div>Emails</div></div>
                <div class="stat-card"><div style="font-size:2.5rem;color:#eab308;">${data.phones.length}</div><div>Phones</div></div>
                <div class="stat-card"><div style="font-size:2.5rem;">${data.total_leads}</div><div>Total Leads</div></div>
            </div>

            <h3>✉️ Emails (${data.emails.length})</h3>
            <table>
                <thead><tr><th>Email</th><th>Status</th><th>Action</th></tr></thead>
                <tbody>
                    ${data.emails.map(email => `
                        <tr>
                            <td><strong>${email}</strong></td>
                            <td><span class="badge">✅ VALID</span></td>
                            <td><button onclick="copyToClipboard('${email}')">Copy</button></td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>

            <h3 style="margin-top:40px;">📞 Phones (${data.phones.length})</h3>
            <table>
                <thead><tr><th>Phone</th><th>Status</th><th>Action</th></tr></thead>
                <tbody>
                    ${data.phones.map(phone => `
                        <tr>
                            <td><strong>${phone}</strong></td>
                            <td><span class="badge">✅ VALID</span></td>
                            <td><button onclick="copyToClipboard('${phone}')">Copy</button></td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>

            <div style="text-align:center;margin-top:50px;">
                <form action="/download_csv" method="get" target="_blank">
                    ${data.emails.map(email => `<input type="hidden" name="emails" value="${email}">`).join('')}
                    ${data.phones.map(phone => `<input type="hidden" name="phones" value="${phone}">`).join('')}
                    <input type="hidden" name="domain" value="${data.url}">
                    <button type="submit" class="download-btn">📤 Download All Leads as CSV</button>
                </form>
            </div>
        </div>
    `;
}

function showError(msg) {
    document.getElementById('progressContainer').style.display = 'none';
    document.getElementById('errorBox').innerHTML = `<h2>⚠️ Error</h2><p>${msg}</p>`;
    document.getElementById('errorBox').style.display = 'block';
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        const n = document.createElement('div');
        n.textContent = '✅ Copied!';
        n.style.cssText = 'position:fixed;bottom:30px;right:30px;background:#22c55e;color:white;padding:14px 28px;border-radius:12px;';
        document.body.appendChild(n);
        setTimeout(() => n.remove(), 1800);
    });
}
</script>
</body>
</html>
"""

if __name__ == '__main__':
    print("🚀 LeadForge v2 with Live Progress Bar running at http://127.0.0.1:5000")
    app.run(debug=True, port=5000)