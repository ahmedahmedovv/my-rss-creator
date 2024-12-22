from flask import Flask, render_template, request, jsonify
from lxml import html, etree
from cssselect import GenericTranslator
import feedgenerator
import datetime
import requests

app = Flask(__name__)

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
            
            if len(matching_elements) >= 3:
                content_samples = [
                    ' '.join(el.text_content().split())[:100]
                    for el in matching_elements[:3]
                    if el.text_content().strip()
                ]
                
                if content_samples:
                    selector_data.append({
                        'css': selector,
                        'xpath': xpath,
                        'example': len(matching_elements),
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
                pubdate=datetime.datetime.now()
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

if __name__ == '__main__':
    app.run(debug=True)
