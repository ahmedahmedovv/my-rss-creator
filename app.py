from flask import Flask, render_template, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_page', methods=['POST'])
def get_page():
    url = request.json.get('url')
    try:
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-notifications')
        chrome_options.add_argument('--disable-popup-blocking')
        chrome_options.add_argument('--disable-infobars')
        chrome_options.add_experimental_option('prefs', {
            'profile.default_content_settings.popups': 0,
            'profile.default_content_setting_values': {
                'notifications': 2,
                'auto_select_certificate': 2,
                'cookies': 2
            }
        })
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_window_size(1920, 1080)
        driver.get(url)
        time.sleep(2)
        
        remove_overlay_script = """
            const selectors = [
                '[class*="cookie"]',
                '[id*="cookie"]',
                '[class*="consent"]',
                '[id*="consent"]',
                '[class*="popup"]',
                '[id*="popup"]',
                '[class*="overlay"]',
                '[id*="overlay"]'
            ];
            selectors.forEach(selector => {
                document.querySelectorAll(selector).forEach(element => {
                    element.remove();
                });
            });
        """
        driver.execute_script(remove_overlay_script)
        
        page_content = driver.page_source
        page_content = page_content.replace('<base', '<!-- base').replace('</base>', '</base -->')
        page_content = page_content.replace('<a ', '<a target="_blank" ')
        
        driver.quit()
        return jsonify({'content': page_content})
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True)
