from flask import Flask, render_template, request, Response, jsonify
import requests
from bs4 import BeautifulSoup
import re
import logging
from datetime import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom

app = Flask(__name__)

# Configure logging
logging.basicConfig(
    filename='rss_creator.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

@app.route('/', methods=['GET', 'POST'])
def hello_world():
    content = None
    url = None
    if request.method == 'POST':
        url = request.form.get('url')
        try:
            content = True
        except:
            content = "Error fetching URL"
    return render_template('index.html', message='Hello, World!', content=content, url=url)

@app.route('/proxy')
def proxy():
    url = request.args.get('url')
    if not url:
        return "No URL provided", 400
    
    try:
        response = requests.get(url)
        content_type = response.headers.get('content-type', '')
        
        if 'text/html' in content_type:
            # Parse and modify HTML content
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Add base tag for relative URLs
            base_tag = soup.new_tag('base', href=url)
            soup.head.insert(0, base_tag)
            
            # Remove existing Content-Security-Policy
            if soup.find('meta', {'http-equiv': 'Content-Security-Policy'}):
                soup.find('meta', {'http-equiv': 'Content-Security-Policy'}).decompose()
            
            # Convert response content to string
            content = str(soup)
        else:
            content = response.content

        headers = {
            'Content-Type': content_type,
            'X-Frame-Options': 'SAMEORIGIN',
            'Content-Security-Policy': "frame-ancestors 'self'",
        }
        
        return Response(content, headers=headers)
    except Exception as e:
        return str(e), 500

@app.route('/log', methods=['POST'])
def log_message():
    data = request.get_json()
    message = data.get('message', '')
    level = data.get('level', 'info')
    
    if level == 'error':
        logging.error(message)
    elif level == 'warning':
        logging.warning(message)
    else:
        logging.info(message)
        
    return jsonify({'status': 'success'})

@app.route('/preview-rss', methods=['POST'])
def preview_rss():
    try:
        data = request.get_json()
        url = data['url']
        config = data['config']
        
        # Fetch the page content
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Create RSS feed
        rss = ET.Element('rss', version='2.0')
        channel = ET.SubElement(rss, 'channel')
        
        # Add channel information
        ET.SubElement(channel, 'title').text = 'RSS Feed for ' + url
        ET.SubElement(channel, 'link').text = url
        ET.SubElement(channel, 'description').text = 'Generated RSS feed'
        ET.SubElement(channel, 'lastBuildDate').text = datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')
        
        # Find all items using the title as the base selector
        titles = soup.find_all(text=lambda text: text and config['title'] in text)
        
        for title_element in titles[:5]:  # Limit to 5 items for preview
            item = ET.SubElement(channel, 'item')
            
            # Find closest parent that contains all required elements
            parent = title_element.parent
            while parent and parent.name != 'body':
                # Try to find description and link within this parent
                desc = parent.find(text=lambda text: text and config['description'] in text)
                link = parent.find('a', href=True) if config['link'] else None
                
                if desc and (link or not config['link']):
                    ET.SubElement(item, 'title').text = title_element.strip()
                    ET.SubElement(item, 'description').text = desc.strip()
                    if link:
                        ET.SubElement(item, 'link').text = link['href']
                    ET.SubElement(item, 'pubDate').text = datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')
                    break
                    
                parent = parent.parent
        
        # Convert to string with proper formatting
        xml_str = minidom.parseString(ET.tostring(rss)).toprettyxml(indent="   ")
        
        return xml_str, 200, {'Content-Type': 'text/xml'}
        
    except Exception as e:
        logging.error(f"Error generating RSS preview: {str(e)}")
        return str(e), 500

if __name__ == '__main__':
    app.run(debug=True)
