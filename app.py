from flask import Flask, render_template, request
import requests

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    source_code = None
    url = None
    rendered_content = None
    
    if request.method == 'POST':
        url = request.form.get('url')
        try:
            response = requests.get(url)
            source_code = response.text
            # Add draggable attribute and data-classname attribute to elements
            modified_content = response.text
            modified_content = modified_content.replace('<div class="', '<div draggable="true" ondragstart="handleDragStart(event)" class="')
            modified_content = modified_content.replace('<p class="', '<p draggable="true" ondragstart="handleDragStart(event)" class="')
            modified_content = modified_content.replace('<span class="', '<span draggable="true" ondragstart="handleDragStart(event)" class="')
            # Handle elements without class attributes
            modified_content = modified_content.replace('<div>', '<div draggable="true" ondragstart="handleDragStart(event)">')
            modified_content = modified_content.replace('<p>', '<p draggable="true" ondragstart="handleDragStart(event)">')
            modified_content = modified_content.replace('<span>', '<span draggable="true" ondragstart="handleDragStart(event)">')
            rendered_content = modified_content
        except:
            source_code = "Error: Could not fetch the webpage"
            rendered_content = "Error: Could not fetch the webpage"
    
    return render_template('index.html', 
                         source_code=source_code, 
                         url=url, 
                         rendered_content=rendered_content)

if __name__ == '__main__':
    app.run(debug=True)
