Here's a comprehensive README for LeadForge:

```markdown
# 🔗 LeadForge - Email & Phone Number Extractor

A powerful web scraping tool that extracts emails and phone numbers from websites. Perfect for lead generation, market research, and contact discovery.

## ✨ Features

- 🚀 **Fast & Lightweight** - Uses simple HTTP requests, no browser overhead
- 📧 **Email Extraction** - Finds email addresses from text and mailto: links
- 📞 **Phone Number Extraction** - Detects phone numbers in multiple formats
- 🔍 **Deep Crawl Mode** - Explores contact/about pages for more leads
- 📊 **Business Insights** - Extracts company names and descriptions
- 💾 **CSV Export** - Download all leads as a CSV file
- 🎨 **Modern UI** - Clean, responsive web interface
- 🌐 **Works with** - Business directories, contact pages, public listings

## 📋 Requirements

- Python 3.7+
- Internet connection
- 10-30 seconds per scrape (depending on deep crawl)

## 🛠️ Installation

### 1. Clone or Download
```bash
# Download the file
curl -O https://your-server/app.py
# Or save the app.py file manually
```

### 2. Install Dependencies
```bash
pip install flask requests beautifulsoup4
```

### 3. Run the Application
```bash
python app.py
```

### 4. Open in Browser
```
http://127.0.0.1:5000
```

## 🚀 How to Use

### Quick Start (30 seconds)

1. **Enter a URL** - Try `https://www.python.org` first
2. **Click "Start Scraping"** 
3. **View Results** - Emails and phone numbers appear instantly
4. **Download CSV** - Save leads to your computer

### Step-by-Step Guide

#### Step 1: Find Target Websites

**✅ Good targets (will work):**
- Business directories (Yellow Pages, Yelp, BBB)
- Contact pages (example.com/contact)
- About pages (example.com/about)
- Open source projects (github.com, python.org)

**❌ Bad targets (won't work):**
- LinkedIn, ZoomInfo, Apollo.io (block scrapers)
- Facebook, Twitter (require login)
- Sites with "403 Forbidden" errors

#### Step 2: Enter URL

Copy-paste a URL into the input field:
```
https://www.yellowpages.com/business-listing
https://www.bbc.com/contact
https://www.python.org/psf/contact/
```

#### Step 3: Configure Options

| Option | When to Use |
|--------|-------------|
| **Deep Crawl OFF** | Quick test, homepage scraping |
| **Deep Crawl ON** | Directory sites, need more leads (takes 2-3x longer) |
| **Keywords** | Optional - filters results (e.g., "sales, ceo") |

#### Step 4: Start Scraping

Click the **"Start Scraping"** button and wait 5-15 seconds.

#### Step 5: Review Results

Results show:
- 📧 **Email addresses** - Click "Copy" to save individually
- 📞 **Phone numbers** - Validated and deduplicated
- 📊 **Statistics** - Total leads found
- ℹ️ **Page insights** - Title and description

#### Step 6: Download Data

Click **"Download CSV"** to get all leads in a spreadsheet-ready format.

## 🎯 Best Practices

### For Best Results

1. **Start with simple sites**
   ```
   ✅ https://www.python.org
   ✅ https://www.bbc.com/contact
   ❌ https://www.linkedin.com
   ```

2. **Use specific pages, not just homepages**
   ```
   ✅ https://example.com/contact
   ✅ https://example.com/about/team
   ❌ https://example.com
   ```

3. **Enable Deep Crawl for directories**
   ```
   ✅ https://www.yellowpages.com (Deep Crawl ON)
   ✅ https://www.yelp.com (Deep Crawl ON)
   ```

4. **Be specific with business directories**
   ```
   # Search first, then scrape individual listings
   1. Search: "plumber Chicago" on Yellow Pages
   2. Copy specific business URL
   3. Paste into LeadForge
   ```

### What to Scrape

| Industry | Working Examples |
|----------|------------------|
| **Local Businesses** | Yellow Pages, Yelp, BBB |
| **Tech Companies** | GitHub, Stack Overflow, Python.org |
| **News/Media** | BBC, CNN (contact pages) |
| **Education** | .edu domains, university directories |
| **Government** | .gov domains, public records |

### What NOT to Scrape

- 🚫 Social media sites (Facebook, Twitter, Instagram)
- 🚫 B2B data platforms (ZoomInfo, Apollo, Lusha)
- 🚫 Sites with login requirements
- 🚫 Sites with "403 Forbidden" errors
- 🚫 Rate-limited APIs

## 📊 Example Use Cases

### 1. Find Local Business Contacts
```
URL: https://www.yellowpages.com/los-angeles-ca/mip/example-business-123
Deep Crawl: ON
Expected: 2-5 emails, 1-3 phone numbers
```

### 2. Extract Open Source Project Contacts
```
URL: https://github.com/orgs/community
Deep Crawl: OFF
Expected: 1-2 emails, 0 phones
```

### 3. Build Lead List from Directory
```
1. Search Yellow Pages for "accountants"
2. Scrape 10-20 individual listings
3. Combine CSV exports
4. Import to CRM
```

## 🔧 Troubleshooting

### "Connection lost" Error
**Solution:** Try a different website or disable Deep Crawl
```bash
# Start with simple site
https://www.python.org
```

### "403 Forbidden" Error
**Cause:** Site blocks automated scraping
**Solution:** Use a different website (see "Good targets" above)

### "Failed to load page" Error
**Solutions:**
- Check URL format (include https://)
- Ensure site is publicly accessible
- Try a different website

### No emails found
**Solutions:**
- Enable Deep Crawl
- Try a contact or about page
- Use a business directory instead

### Slow scraping
**Solutions:**
- Disable Deep Crawl for quick tests
- Use specific pages, not entire sites
- Wait 10-15 seconds between requests

## 💡 Pro Tips

### Tip 1: Use Search First
Don't guess URLs. Search Google or Yellow Pages first:
```
site:yellowpages.com plumber austin
```

### Tip 2: Combine Results
Scrape multiple listings and merge CSV files:
```python
import pandas as pd
import glob

files = glob.glob('*_leads.csv')
df = pd.concat([pd.read_csv(f) for f in files])
df.to_csv('all_leads.csv', index=False)
```

### Tip 3: Verify Emails
Use a free email verifier before mass emailing:
- Hunter.io (free tier)
- NeverBounce
- ZeroBounce

### Tip 4: Respect Robots.txt
Check if scraping is allowed:
```
https://example.com/robots.txt
```

### Tip 5: Add Delays
For multiple URLs, wait between requests:
```python
import time
time.sleep(5)  # 5 second delay
```

## 📝 CSV Export Format

The downloaded CSV contains:

| Column | Description | Example |
|--------|-------------|---------|
| Type | Email or Phone | Email |
| Value | The extracted contact | john@example.com |
| Domain | Source website | https://example.com |
| Scraped Date | Timestamp | 2024-01-15 14:30:22 |

## 🎯 Quick Test URLs

Copy-paste these to verify everything works:

```bash
# Test #1 - Should find emails
https://www.python.org/psf/contact/

# Test #2 - Should find phone numbers
https://www.yellowpages.com/los-angeles-ca/mip/los-angeles-plaza-4847484

# Test #3 - Contact page
https://www.bbc.com/contact/complaints

# Test #4 - Open source
https://github.com/contact
```

## ⚖️ Legal & Ethical Guidelines

### ✅ Allowed
- Scraping public contact pages
- Extracting publicly listed emails
- Personal, non-commercial use
- Respecting robots.txt

### ❌ Not Allowed
- Bypassing login requirements
- Ignoring robots.txt disallow rules
- Overloading servers (use delays)
- Selling scraped data without permission
- Scraping personal/private information

### 📜 Compliance
- Check website's Terms of Service
- Respect rate limits (5-10 seconds between requests)
- Identify your bot with proper User-Agent
- For commercial use, consult a lawyer

## 🆘 Support

### Common Issues

**Q: Why can't I scrape LinkedIn?**
A: LinkedIn actively blocks scrapers. Use their official API instead.

**Q: How many URLs can I scrape?**
A: No limit, but be respectful. Add delays between requests.

**Q: Can I scrape behind login pages?**
A: No, LeadForge only accesses public pages.

**Q: Why are some phone numbers missing?**
A: Phone regex patterns may not catch all formats. You can customize PHONE_REGEX in app.py.

### Getting Help
1. Check the troubleshooting section above
2. Test with recommended URLs first
3. Enable Deep Crawl for better results
4. Use business directories for reliable data

## 🔄 Updates & Roadmap

### Current Version (v4)
- ✅ HTTP-based scraping (no browser)
- ✅ Email & phone extraction
- ✅ Deep crawl mode
- ✅ CSV export
- ✅ Modern web UI

### Planned Features
- ⏳ Batch URL processing
- ⏳ Email validation
- ⏳ Proxy support
- ⏳ Export to Excel
- ⏳ API endpoint

## 📄 License

This tool is for educational purposes. Users are responsible for compliance with website terms and applicable laws.

## 🙏 Credits

Built with:
- Flask (Web framework)
- BeautifulSoup4 (HTML parsing)
- Requests (HTTP client)

---

## 🚀 Quick Start Command Summary

```bash
# 1. Install
pip install flask requests beautifulsoup4

# 2. Run
python app.py

# 3. Open browser
http://127.0.0.1:5000

# 4. Test with
https://www.python.org
```

**Happy Lead Hunting! 🎯**
```

This README covers everything from installation to advanced usage. Save it as `README.md` in your LeadsForge folder. Users can read it on GitHub or any markdown viewer.