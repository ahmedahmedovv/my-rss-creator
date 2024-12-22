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
        
        titles = soup.select(title_selector)
        descriptions = soup.select(description_selector)
        
        for title, desc in zip(titles, descriptions):
            feed.add_item(
                title=title.text.strip(),
                link=url,
                description=desc.text.strip(),
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
