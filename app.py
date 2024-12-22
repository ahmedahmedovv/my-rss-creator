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

def validate_xpath_selector(selector: str) -> tuple[bool, str | None]:
    """Validate an XPath selector."""
    try:
        etree.XPath(selector)
        return True, None
    except etree.XPathSyntaxError as e:
        return False, str(e)

def extract_link(element) -> str | None:
    """Extract link from an element using various common patterns."""
    # Direct href attribute
    if element.get('href'):
        return element.get('href')
    
    # Parent anchor tag
    if element.getparent().tag == 'a':
        return element.getparent().get('href')
    
    # Child anchor tag
    if element.find('a') is not None:
        return element.find('a').get('href')
    
    return None

def make_absolute_url(relative_url: str, base_url: str) -> str:
    """Convert relative URLs to absolute URLs."""
    if relative_url.startswith(('http://', 'https://')):
        return relative_url
        
    if relative_url.startswith('/'):
        base_url = '/'.join(base_url.split('/')[:3])
        return base_url + relative_url
    
    return base_url.rstrip('/') + '/' + relative_url

def find_description(title_element, description_xpath: str, tree, index: int) -> str:
    """Find description text using various fallback methods."""
    try:
        # Try using the description xpath directly first
        all_descriptions = tree.xpath(description_xpath)
        if index < len(all_descriptions):
            return all_descriptions[index].text_content().strip()
        
        # If that fails, try relative xpath from the title element
        if description_xpath.startswith('//'):
            relative_xpath = '.' + description_xpath
            desc_elements = title_element.xpath(relative_xpath)
            if desc_elements:
                return desc_elements[0].text_content().strip()
            
        # Try searching in the title element's following siblings
        following_xpath = f"following::{description_xpath[2:]}"
        desc_elements = title_element.xpath(following_xpath)
        if desc_elements:
            return desc_elements[0].text_content().strip()
            
    except Exception as e:
        print(f"Error finding description: {e}")
    
    return 'No description available'  # Return a default message instead of empty string

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
            
            # Filter out elements with no meaningful content or navigation text
            content_elements = []
            seen_texts = set()  # To track duplicate content
            
            for el in matching_elements:
                text = ' '.join(el.text_content().split()).strip()
                text_lower = text.lower()
                
                if (text and 
                    el.tag not in excluded_tags and 
                    text_lower not in excluded_text_patterns and
                    text not in seen_texts and
                    len(text) > 5):  # Ignore very short text
                    
                    content_elements.append(el)
                    seen_texts.add(text)
            
            if len(content_elements) >= 3:
                content_samples = [
                    ' '.join(el.text_content().split())[:100]
                    for el in content_elements[:3]
                ]
                
                if content_samples and len(set(content_samples)) >= 2:  # Ensure at least 2 unique samples
                    selector_data.append({
                        'css': selector,
                        'xpath': xpath,
                        'example': len(content_elements),
                        'samples': content_samples
                    })
        except:
            continue
            
    return selector_data

# ---- RSS Generation ----

def create_rss_feed(url: str, title_xpath: str, description_xpath: str) -> str:
    """Generate RSS feed from webpage using XPath selectors."""
    try:
        response = requests.get(url)
        tree = html.fromstring(response.content)
        tree.make_links_absolute(url)  # Make all links absolute
        
        feed = feedgenerator.Rss201rev2Feed(
            title=f"Custom RSS - {url}",
            link=url,
            description=f"Custom RSS feed for {url}",
            language="en"
        )
        
        title_elements = tree.xpath(title_xpath)
        
        for i, title_element in enumerate(title_elements):
            title = title_element.text_content().strip()
            link = extract_link(title_element)
            
            if link:
                link = make_absolute_url(link, url)
            
            description = find_description(title_element, description_xpath, tree, i)
            
            # Debug print
            print(f"Found item {i+1}:")
            print(f"Title: {title}")
            print(f"Description: {description}")
            print(f"Link: {link}")
            print("---")
            
            feed.add_item(
                title=title or 'No title',
                link=link or url,
                description=description,
                pubdate=datetime.now()
            )
            
        return feed.writeString('utf-8')
    except Exception as e:
        return f"Error: {str(e)}"

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
            
        response = requests.get(url)
        tree = html.fromstring(response.content)
        selectors = analyze_page_structure(tree)
        
        return jsonify({'selectors': selectors})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
