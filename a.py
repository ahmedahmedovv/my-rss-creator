import requests
from bs4 import BeautifulSoup
from cssselect import GenericTranslator, SelectorError
from urllib.parse import urlparse

def is_valid_url(url):
    """
    Check if the URL is valid
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def get_css_selectors(html_content):
    """
    Extract CSS selectors from HTML content
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    selectors = set()

    # Extract class selectors
    for element in soup.find_all(class_=True):
        for class_name in element.get('class'):
            selectors.add(f".{class_name}")

    # Extract ID selectors
    for element in soup.find_all(id=True):
        selectors.add(f"#{element.get('id')}")

    # Extract elements with common attributes
    for element in soup.find_all():
        if element.name:
            # Add tag name
            selectors.add(element.name)
            # Add elements with href
            if element.get('href'):
                selectors.add(f"{element.name}[href]")
            # Add elements with src
            if element.get('src'):
                selectors.add(f"{element.name}[src]")

    return selectors

def css_to_xpath(css_selector):
    """
    Convert a CSS selector to XPath expression
    """
    try:
        translator = GenericTranslator()
        xpath = translator.css_to_xpath(css_selector)
        return xpath
    except SelectorError as e:
        return f"Error converting selector: {str(e)}"

def main():
    print("CSS to XPath Converter for Webpages")
    print("-" * 50)

    while True:
        url = input("\nEnter a URL (or 'q' to quit): ")
        if url.lower() == 'q':
            break

        if not is_valid_url(url):
            print("Invalid URL format. Please enter a valid URL.")
            continue

        try:
            # Fetch webpage content
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers)
            response.raise_for_status()

            # Extract CSS selectors
            selectors = get_css_selectors(response.text)

            print(f"\nFound {len(selectors)} unique CSS selectors")
            print("-" * 50)

            # Convert and display results
            for css in sorted(selectors):
                xpath = css_to_xpath(css)
                print(f"\nCSS Selector: {css}")
                print(f"XPath: {xpath}")

        except requests.RequestException as e:
            print(f"Error fetching webpage: {str(e)}")

if __name__ == "__main__":
    main()