from flask import Flask, render_template, request
import requests

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def hello_world():
    content = None
    url = None
    if request.method == 'POST':
        url = request.form.get('url')
        try:
            response = requests.get(url)
            content = response.text
        except:
            content = "Error fetching URL"
    return render_template('index.html', message='Hello, World!', content=content, url=url)

if __name__ == '__main__':
    app.run(debug=True)
