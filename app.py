from flask import Flask, render_template, request, jsonify
from bs4 import BeautifulSoup
import requests
import feedgenerator
import datetime
import re

app = Flask(__name__)

def create_rss_feed(url, title_selector, description_selector):
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        feed = feedgenerator.Rss201rev2Feed(
            title=f"Custom RSS - {url}",
            link=url,
            description=f"Custom RSS feed for {url}",
            language="en"
        )
        
        # Find all article containers
        articles = soup.select(title_selector)
        
        for article in articles:
            # Find title
            title = article.text.strip()
            
            # Find link - try different common patterns
            link = None
            # 1. Check if the title is wrapped in an <a> tag
            if article.name == 'a':
                link = article.get('href')
            # 2. Look for nearest parent <a> tag
            elif article.find_parent('a'):
                link = article.find_parent('a').get('href')
            # 3. Look for nearest child <a> tag
            elif article.find('a'):
                link = article.find('a').get('href')
            
            # Make relative URLs absolute
            if link and not link.startswith(('http://', 'https://')):
                if link.startswith('/'):
                    # Handle absolute paths
                    base_url = '/'.join(url.split('/')[:3])  # Get domain part
                    link = base_url + link
                else:
                    # Handle relative paths
                    link = url.rstrip('/') + '/' + link

            # Find description using the same container
            description = ''
            desc_element = soup.select(description_selector)
            if desc_element:
                description = desc_element[0].text.strip()
            
            feed.add_item(
                title=title,
                link=link or url,  # Fallback to main URL if no specific link found
                description=description,
                pubdate=datetime.datetime.now()
            )
            
        return feed.writeString('utf-8')
    except Exception as e:
        return str(e)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate_rss', methods=['POST'])
def generate_rss():
    data = request.json
    url = data.get('url')
    title_selector = data.get('title_selector')
    description_selector = data.get('description_selector')
    
    rss_content = create_rss_feed(url, title_selector, description_selector)
    return jsonify({'rss_content': rss_content})

if __name__ == '__main__':
    app.run(debug=True)
