from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/fetch-page', methods=['POST'])
def fetch_page():
    url = request.json.get('url')
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Make all links draggable and add necessary classes
        for a in soup.find_all('a', href=True):
            href = a.get('href')
            if not href.startswith(('http://', 'https://')):
                href = requests.compat.urljoin(url, href)
            
            # Generate CSS selector for the link
            selector = generate_css_selector(a)
            
            # Add draggable attribute and class
            a['draggable'] = 'true'
            a['class'] = a.get('class', []) + ['draggable-link']
            a['data-href'] = href  # Store the full URL
            a['data-selector'] = selector  # Store the CSS selector
            a['data-text'] = a.get_text().strip()  # Store the link text
            a['data-similar-selector'] = generate_article_pattern(a)
            
        # Add custom CSS and JS to the page
        style_tag = soup.new_tag('style')
        style_tag.string = '''
            .draggable-link { cursor: move; }
            .draggable-link:hover { background-color: #f0f0f0; }
        '''
        soup.head.append(style_tag)
        
        # Add custom script to handle drag events
        script_tag = soup.new_tag('script')
        script_tag.string = '''
            document.addEventListener('DOMContentLoaded', function() {
                document.querySelectorAll('.draggable-link').forEach(link => {
                    link.addEventListener('dragstart', function(e) {
                        e.dataTransfer.setData('text/plain', this.getAttribute('data-href'));
                    });
                });
            });
        '''
        soup.body.append(script_tag)
        
        return jsonify({
            'html': str(soup)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

def generate_css_selector(element):
    """Generate a CSS selector for the given element"""
    selector_parts = []
    
    while element and element.name:
        # Get the element's tag name
        current = element.name
        
        # Add id if present
        if element.get('id'):
            current += f'#{element["id"]}'
        # Add classes if present
        elif element.get('class'):
            classes = [c for c in element['class'] if c != 'draggable-link']
            if classes:
                current += '.' + '.'.join(classes)
                
        # Add position if needed
        siblings = element.find_previous_siblings(element.name)
        if siblings:
            current += f':nth-of-type({len(siblings) + 1})'
            
        selector_parts.append(current)
        element = element.parent
        
    return ' > '.join(reversed(selector_parts))

def generate_article_pattern(element):
    """Generate a more generic selector pattern for article links"""
    # Get parent elements up to 3 levels
    parents = []
    current = element
    for _ in range(3):
        if not current.parent:
            break
        current = current.parent
        parents.append(current)
    
    # Find common patterns
    pattern = {
        'tag': element.name,
        'classes': [c for c in element.get('class', []) if c != 'draggable-link'],
        'parent_tags': [p.name for p in parents],
        'parent_classes': [c for p in parents for c in p.get('class', [])]
    }
    
    return str(pattern)  # Convert to string for data attribute

if __name__ == '__main__':
    app.run(debug=True)
