from flask import Flask, render_template, request, jsonify
from lxml import html, etree
from cssselect import GenericTranslator
import feedgenerator
from datetime import datetime
import requests
from supabase import create_client
import os
from dotenv import load_dotenv
from urllib.parse import urlparse
from utils import (  # Add these imports
    validate_xpath_selector,
    create_rss_feed
)
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import WebDriverException
import time
import urllib3
import random
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import ftfy
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# Load environment variables from .env file
load_dotenv()

# Initialize Supabase client with service role key
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("Missing required environment variables SUPABASE_URL and/or SUPABASE_SERVICE_KEY")

supabase = create_client(
    supabase_url,
    supabase_key
)

# ---- Helper Functions ----

def analyze_page_structure(tree) -> list[dict]:
    """Analyze page structure and return all potential selectors."""
    selectors = set()
    translator = GenericTranslator()
    selector_data = []
    
    # Find all elements
    for element in tree.xpath('//*'):
        # Get element with classes
        if element.get('class'):
            for cls in element.get('class').split():
                selectors.add(f"{element.tag}.{cls}")
        
        # Get element with ID
        if element.get('id'):
            selectors.add(f"#{element.get('id')}")
            selectors.add(f"{element.tag}#{element.get('id')}")
        
        # Get element by tag
        selectors.add(element.tag)

    # Analyze each selector
    for selector in sorted(selectors):
        try:
            xpath = translator.css_to_xpath(selector)
            matching_elements = tree.xpath(xpath)
            
            content_elements = []
            seen_texts = set()
            
            for el in matching_elements:
                text = ' '.join(el.text_content().split()).strip()
                
                if text and text not in seen_texts and not text.startswith('var '):  # Skip script content
                    # Get the href attribute
                    href = None
                    if el.tag == 'a':
                        href = el.get('href')
                    elif el.getparent() is not None and el.getparent().tag == 'a':
                        href = el.getparent().get('href')
                    else:
                        a_tag = el.find('.//a')
                        if a_tag is not None:
                            href = a_tag.get('href')
                    
                    content_elements.append({
                        'text': text,
                        'href': href
                    })
                    seen_texts.add(text)
            
            # Only add selectors that have 3 or more unique text contents
            if len(content_elements) >= 3:
                content_samples = []
                for el in content_elements[:3]:
                    sample_html = el['text'][:100]
                    if el['href']:
                        sample_html = f'<a href="{el["href"]}">{sample_html}</a>'
                    content_samples.append(sample_html)
                
                selector_data.append({
                    'css': selector,
                    'xpath': xpath,
                    'example': len(content_elements),
                    'samples': content_samples
                })
        except:
            continue
            
    return selector_data

def get_page_content(url, use_selenium=False):
    """Fetch page content using enhanced techniques from old.py"""
    if not use_selenium:
        # Initialize session with retry mechanism
        session = requests.Session()
        retries = urllib3.util.Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504]
        )
        session.mount('https://', requests.adapters.HTTPAdapter(max_retries=retries))
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0'
        }
        
        try:
            response = session.get(
                url,
                headers=headers,
                verify=False,  # Similar to old.py
                timeout=(10, 30),  # Connection timeout, Read timeout
                allow_redirects=True
            )
            response.raise_for_status()
            return response.content
            
        except requests.RequestException as e:
            print(f"Regular request failed: {str(e)}")
            # If regular request fails, try with Selenium
            return get_page_content(url, use_selenium=True)
    
    # Enhanced Selenium configuration from old.py
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(url)
        
        # Add random delay and scrolling like in old.py
        total_height = int(driver.execute_script("return document.body.scrollHeight"))
        for i in range(3):
            scroll_height = random.randint(100, total_height)
            driver.execute_script(f"window.scrollTo(0, {scroll_height});")
            time.sleep(random.uniform(0.5, 2))
        
        # Wait for dynamic content
        time.sleep(random.uniform(3, 5))
        
        content = driver.page_source
        driver.quit()
        return content.encode('utf-8')
        
    except WebDriverException as e:
        if 'driver' in locals():
            driver.quit()
        raise Exception(f"Selenium error: {str(e)}")

# ---- Routes ----

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate_rss', methods=['POST'])
def generate_rss():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400
            
        # Extract and validate required fields
        url = data.get('url')
        title_xpath = data.get('title_selector')
        description_xpath = data.get('description_selector')
        
        if not all([url, title_xpath, description_xpath]):
            return jsonify({
                'error': 'Missing required fields'
            }), 400
            
        # Validate XPath selectors
        for selector, name in [(title_xpath, 'title'), (description_xpath, 'description')]:
            is_valid, error = validate_xpath_selector(selector)
            if not is_valid:
                return jsonify({'error': f'Invalid {name} XPath: {error}'}), 400
        
        # Generate RSS feed
        rss_content = create_rss_feed(url, title_xpath, description_xpath)
        
        if rss_content.startswith('Error'):
            return jsonify({'error': rss_content}), 400
            
        return jsonify({'rss_content': rss_content})
        
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/get_selectors', methods=['POST'])
def fetch_selectors():
    try:
        url = request.get_json().get('url')
        if not url:
            return jsonify({'error': 'URL is required'}), 400

        # Add URL validation
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        print(f"Fetching selectors for URL: {url}")  # Debug log

        # Try regular requests first
        try:
            content = get_page_content(url, use_selenium=False)
            print(f"Content length: {len(content)}")  # Debug log
            
            tree = html.fromstring(content)
            tree.make_links_absolute(url)  # Make all links absolute
            
            selectors = analyze_page_structure(tree)
            print(f"Found {len(selectors)} selectors")  # Debug log
            
            if selectors:
                # Sort selectors by example count in descending order
                selectors.sort(key=lambda x: x['example'], reverse=True)
                
                # Fix encoding in selector samples
                for selector in selectors:
                    selector['samples'] = [ftfy.fix_text(sample) for sample in selector['samples']]
                
                return jsonify({'selectors': selectors})
            else:
                print("No selectors found with regular request, trying Selenium...")
                
        except Exception as e:
            print(f"Regular request failed: {str(e)}")

        # If regular request fails or finds no selectors, try with Selenium
        try:
            content = get_page_content(url, use_selenium=True)
            print(f"Selenium content length: {len(content)}")  # Debug log
            
            tree = html.fromstring(content)
            tree.make_links_absolute(url)
            
            selectors = analyze_page_structure(tree)
            print(f"Found {len(selectors)} selectors with Selenium")  # Debug log
            
            if not selectors:
                return jsonify({
                    'error': 'No suitable selectors found',
                    'details': [
                        'Website blocking automated access',
                        'Content protected behind authentication',
                        'Complex website structure',
                        'Try manually inspecting the page and entering XPath selectors'
                    ]
                }), 404
                
            # Fix encoding in selector samples
            for selector in selectors:
                selector['samples'] = [ftfy.fix_text(sample) for sample in selector['samples']]
                
            return jsonify({'selectors': selectors})
            
        except Exception as e:
            print(f"Selenium request failed: {str(e)}")  # Debug log
            return jsonify({
                'error': 'Failed to access the website',
                'details': [
                    'Website may be blocking automated access',
                    'Try manually inspecting the page and entering XPath selectors',
                    f'Technical details: {str(e)}'
                ]
            }), 400

    except Exception as e:
        print(f"Server error: {str(e)}")  # Debug log
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/save_feed', methods=['POST'])
def save_feed():
    try:
        data = request.get_json()
        url = data.get('url')
        title_xpath = data.get('title_selector')
        description_xpath = data.get('description_selector')
        
        if not all([url, title_xpath, description_xpath]):
            return jsonify({'error': 'Missing required fields'}), 400
            
        # Generate RSS content
        rss_content = create_rss_feed(url, title_xpath, description_xpath)
        
        if rss_content.startswith('Error'):
            return jsonify({'error': rss_content}), 400

        # Create a unique filename using the domain and timestamp
        domain = urlparse(url).netloc
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{domain}_{timestamp}.xml"
        
        # Ensure the storage bucket exists
        try:
            supabase.storage.get_bucket('rss-feed-storage')
        except:
            supabase.storage.create_bucket('rss-feed-storage')
        
        # Convert string content to bytes
        file_data = rss_content.encode('utf-8')
        
        # Upload the RSS content to Supabase Storage
        storage_response = supabase.storage \
            .from_('rss-feed-storage') \
            .upload(filename, file_data)

        # Get the public URL for the uploaded file
        file_url = supabase.storage \
            .from_('rss-feed-storage') \
            .get_public_url(filename)
            
        # Save feed info to database with the storage URL
        result = supabase.table('rss_feeds').insert({
            'url': url,
            'title_xpath': title_xpath,
            'description_xpath': description_xpath,
            'rss_file_url': file_url
        }).execute()
        
        return jsonify({
            'message': 'Feed saved successfully',
            'data': result.data,
            'rss_url': file_url
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
