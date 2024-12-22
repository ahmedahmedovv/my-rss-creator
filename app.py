from flask import Flask, render_template, request
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    content = []
    if request.method == 'POST':
        url = request.form.get('url')
        selector = request.form.get('class_name')
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            elements = soup.select(selector)
            
            if not elements:
                content = [f"No elements found with the selector: {selector}"]
            else:
                content = []
                for element in elements:
                    # Find link in the element or its children
                    link = element.find('a')
                    href = link.get('href') if link else None
                    
                    # If href is relative, make it absolute
                    if href and not href.startswith(('http://', 'https://')):
                        from urllib.parse import urljoin
                        href = urljoin(url, href)
                    
                    content.append({
                        'text': element.get_text(strip=True),
                        'html': str(element),
                        'link': href
                    })
                
                if not any(item['text'] for item in content):
                    content = ["Elements found but they contain no text content."]
            
            print(f"Found {len(elements)} elements with selector '{selector}'")
            
        except requests.exceptions.RequestException as e:
            content = [f"Error accessing URL: {str(e)}"]
        except Exception as e:
            content = [f"Error: {str(e)}"]
    
    return render_template('index.html', content=content)

if __name__ == '__main__':
    app.run(debug=True)
