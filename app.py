from flask import Flask, render_template, request, jsonify
from bs4 import BeautifulSoup
import requests
import feedgenerator
import datetime
import re
from cssselect import parse
from lxml.cssselect import SelectorSyntaxError
from cssselect import GenericTranslator
from lxml import html, etree

app = Flask(__name__)

def create_rss_feed(url, title_xpath, description_xpath):
    try:
        response = requests.get(url)
        tree = html.fromstring(response.content)
        
        feed = feedgenerator.Rss201rev2Feed(
            title=f"Custom RSS - {url}",
            link=url,
            description=f"Custom RSS feed for {url}",
            language="en"
        )
        
        # Find all article titles using XPath
        titles = tree.xpath(title_xpath)
        
        for title_element in titles:
            # Get title text
            title = title_element.text_content().strip()
            
            # Find link - try different common patterns
            link = None
            # 1. Check if the title element has an href attribute
            if title_element.get('href'):
                link = title_element.get('href')
            # 2. Look for parent anchor tag
            elif title_element.getparent().tag == 'a':
                link = title_element.getparent().get('href')
            # 3. Look for child anchor tag
            elif title_element.find('a') is not None:
                link = title_element.find('a').get('href')
            
            # Make relative URLs absolute
            if link and not link.startswith(('http://', 'https://')):
                if link.startswith('/'):
                    base_url = '/'.join(url.split('/')[:3])
                    link = base_url + link
                else:
                    link = url.rstrip('/') + '/' + link
            
            # Find description using XPath
            description = ''
            desc_elements = tree.xpath(description_xpath)
            if desc_elements:
                description = desc_elements[0].text_content().strip()
            
            feed.add_item(
                title=title,
                link=link or url,
                description=description,
                pubdate=datetime.datetime.now()
            )
            
        return feed.writeString('utf-8')
    except Exception as e:
        return str(e)

def validate_xpath_selector(selector):
    try:
        etree.XPath(selector)
        return True, None
    except etree.XPathSyntaxError as e:
        return False, str(e)

def get_all_selectors(url):
    try:
        response = requests.get(url)
        tree = html.fromstring(response.content)
        
        selectors = set()
        translator = GenericTranslator()
        
        # Find all elements
        elements = tree.xpath('//*')
        
        for element in elements:
            # Get element with classes
            if element.get('class'):
                classes = element.get('class').split()
                for cls in classes:
                    selectors.add(f"{element.tag}.{cls}")
            
            # Get element with ID
            if element.get('id'):
                selectors.add(f"#{element.get('id')}")
                selectors.add(f"{element.tag}#{element.get('id')}")
            
            # Get element by tag
            selectors.add(element.tag)
        
        # Convert to list of dicts with xpath equivalents and content samples
        selector_data = []
        for selector in sorted(selectors):
            try:
                xpath = translator.css_to_xpath(selector)
                matching_elements = tree.xpath(xpath)
                content_samples = []
                
                # Get content samples from first 3 matching elements
                for el in matching_elements[:3]:
                    text = ' '.join(el.text_content().split())[:100]  # First 100 chars
                    if text:
                        content_samples.append(text)
                
                selector_data.append({
                    'css': selector,
                    'xpath': xpath,
                    'example': len(matching_elements),
                    'samples': content_samples
                })
            except:
                continue
                
        return selector_data
    except Exception as e:
        return str(e)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate_rss', methods=['POST'])
def generate_rss():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400
            
        url = data.get('url')
        title_xpath = data.get('title_selector')
        description_xpath = data.get('description_selector')
        
        # Validate title XPath
        is_valid, error = validate_xpath_selector(title_xpath)
        if not is_valid:
            return jsonify({'error': f'Invalid title XPath: {error}'}), 400
            
        # Validate description XPath
        is_valid, error = validate_xpath_selector(description_xpath)
        if not is_valid:
            return jsonify({'error': f'Invalid description XPath: {error}'}), 400
            
        if not all([url, title_xpath, description_xpath]):
            return jsonify({
                'error': 'Missing required fields: url, title_selector, or description_selector'
            }), 400
            
        feed_title = data.get('feed_title') or f"RSS Feed for {url}"
        feed_description = data.get('feed_description') or f"Generated RSS feed from {url}"

        rss_content = create_rss_feed(url, title_xpath, description_xpath)
        
        if isinstance(rss_content, str) and rss_content.startswith('Error'):
            return jsonify({
                'error': rss_content
            }), 400
            
        return jsonify({
            'rss_content': rss_content
        })
        
    except Exception as e:
        return jsonify({
            'error': f'Server error: {str(e)}'
        }), 500

@app.route('/get_selectors', methods=['POST'])
def fetch_selectors():
    try:
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
            
        selectors = get_all_selectors(url)
        
        if isinstance(selectors, str):
            return jsonify({'error': selectors}), 400
            
        return jsonify({'selectors': selectors})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
