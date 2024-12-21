from flask import Flask, render_template, request, Response
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

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

if __name__ == '__main__':
    app.run(debug=True)
