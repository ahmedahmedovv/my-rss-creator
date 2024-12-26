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
    """Analyze page structure and return potential selectors."""
    selectors = set()
    translator = GenericTranslator()
    selector_data = []
    
    # Tags that typically contain main content
    content_tags = {
        'article', 'main', 'section', 'div', 'span', 'p', 'h1', 'h2', 'h3', 'h4'
    }

    # Tags to exclude (expanded list)
    excluded_tags = {
        # Technical/Meta elements
        'script', 'style', 'noscript', 'iframe', 'meta', 
        'link', 'head', 'svg', 'path', 'source', 'img',
        
        # Navigation elements
        'nav', 'header', 'footer', 'sidebar',
        
        # Interactive elements
        'button', 'input', 'select', 'textarea',
        
        # Advertisement related
        'ads', 'advertisement', 'banner',
        
        # Social media
        'social', 'share-buttons', 'comments'
    }

    # Common patterns to exclude (expanded)
    excluded_text_patterns = {
        # Navigation patterns
        'show all', 'view all', 'load more', 'show more',
        'next page', 'previous page', 'next', 'prev', 'previous',
        'tümünü gör', 'daha fazla', 'devamı',
        
        # UI elements
        'menu', 'search', 'navigation', 'sidebar',
        'header', 'footer', 'copyright',
        
        # Social/Interactive
        'share', 'follow us', 'subscribe', 'sign up',
        'login', 'register', 'comments', 'related articles',
        
        # Common footer text
        'all rights reserved', 'privacy policy', 'terms of service',
        'contact us', 'about us',
        
        # Advertisement related
        'advertisement', 'sponsored', 'recommended for you',
        
        # Common UI buttons
        'read more', 'learn more', 'click here', 'find out more',
        'continue reading', 'more details'
    }

    # Common article container class/id patterns
    article_patterns = {
        'article', 'post', 'entry', 'content', 'main',
        'story', 'news', 'blog-post', 'article-content',
        'post-content', 'main-content', 'page-content'
    }

    def is_likely_article_container(element) -> bool:
        """Check if an element is likely to be an article container."""
        if element.tag in content_tags:
            # Check class names
            classes = element.get('class', '').lower().split()
            ids = element.get('id', '').lower().split('-')
            
            # Check if any class or id contains article patterns
            return any(pattern in ' '.join(classes + ids) 
                      for pattern in article_patterns)
        return False

    # Find all elements
    for element in tree.xpath('//*'):
        # Skip excluded tags
        if element.tag in excluded_tags:
            continue
            
        # Skip elements with no text content
        text_content = element.text_content().strip().lower()
        if not text_content:
            continue

        # Skip elements with common navigation/UI text
        if text_content.lower() in excluded_text_patterns:
            continue

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
                text_lower = text.lower()
                
                if (text and 
                    el.tag not in excluded_tags and 
                    text_lower not in excluded_text_patterns and
                    text not in seen_texts and
                    len(text) > 5):
                    
                    # Get the href attribute - either from the element itself or its parent/child a tag
                    href = None
                    if el.tag == 'a':
                        href = el.get('href')
                    elif el.getparent() is not None and el.getparent().tag == 'a':
                        href = el.getparent().get('href')
                    else:
                        # Look for nested a tag
                        a_tag = el.find('.//a')
                        if a_tag is not None:
                            href = a_tag.get('href')
                    
                    content_elements.append({
                        'text': text,
                        'href': href
                    })
                    seen_texts.add(text)
            
            if len(content_elements) >= 3:
                content_samples = []
                unique_hrefs = set()
                base_url = tree.base_url if hasattr(tree, 'base_url') else None
                
                for el in content_elements[:3]:
                    sample_html = el['text'][:100]
                    if el['href']:
                        sample_html = f'<a href="{el["href"]}">{sample_html}</a>'
                        unique_hrefs.add(el['href'])
                    content_samples.append(sample_html)
                
                # Only add selector if there are multiple unique URLs or URLs different from base
                if (content_samples and 
                    len(set(content_samples)) >= 2 and 
                    (len(unique_hrefs) > 1 or 
                     (base_url and any(href != base_url for href in unique_hrefs)))):
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

        # Try regular requests first
        try:
            content = get_page_content(url, use_selenium=False)
            tree = html.fromstring(content)
            selectors = analyze_page_structure(tree)
            
            if selectors:
                # Fix encoding in selector samples
                for selector in selectors:
                    selector['samples'] = [ftfy.fix_text(sample) for sample in selector['samples']]
                
                return jsonify({'selectors': selectors})
                
        except Exception as e:
            print(f"Regular request failed: {str(e)}")

        # If regular request fails or finds no selectors, try with Selenium
        try:
            content = get_page_content(url, use_selenium=True)
            tree = html.fromstring(content)
            selectors = analyze_page_structure(tree)
            
            if not selectors:
                return jsonify({
                    'error': 'No suitable selectors found. This might be due to:',
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
            return jsonify({
                'error': 'Failed to access the website',
                'details': [
                    'Website may be blocking automated access',
                    'Try manually inspecting the page and entering XPath selectors',
                    f'Technical details: {str(e)}'
                ]
            }), 400

    except Exception as e:
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
    app.run(debug=True)
