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
            # Add draggable attribute and class
            a['draggable'] = 'true'
            a['class'] = a.get('class', []) + ['draggable-link']
            a['data-href'] = href  # Store the full URL
            
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

if __name__ == '__main__':
    app.run(debug=True)
