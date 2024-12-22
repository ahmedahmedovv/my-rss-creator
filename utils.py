from lxml import html, etree
from cssselect import GenericTranslator
from datetime import datetime
from urllib.parse import urlparse
import requests
import feedgenerator

def validate_xpath_selector(selector: str) -> tuple[bool, str | None]:
    """Validate an XPath selector."""
    try:
        etree.XPath(selector)
        return True, None
    except etree.XPathSyntaxError as e:
        return False, str(e)

def extract_link(element) -> str | None:
    """Extract link from an element using various common patterns."""
    if element.get('href'):
        return element.get('href')
    
    if element.getparent().tag == 'a':
        return element.getparent().get('href')
    
    if element.find('.//a') is not None:
        return element.find('.//a').get('href')
    
    return None

def make_absolute_url(relative_url: str, base_url: str) -> str:
    """Convert relative URLs to absolute URLs."""
    if relative_url.startswith(('http://', 'https://')):
        return relative_url
        
    return f"{base_url.rstrip('/')}/{relative_url.lstrip('/')}"

def find_description(title_element, description_xpath: str, tree, index: int) -> str:
    """Find description text using various fallback methods."""
    try:
        all_descriptions = tree.xpath(description_xpath)
        if index < len(all_descriptions):
            return all_descriptions[index].text_content().strip()
        
        if description_xpath.startswith('//'):
            relative_xpath = '.' + description_xpath
            desc_elements = title_element.xpath(relative_xpath)
            if desc_elements:
                return desc_elements[0].text_content().strip()
            
        following_xpath = f"following::{description_xpath[2:]}"
        desc_elements = title_element.xpath(following_xpath)
        if desc_elements:
            return desc_elements[0].text_content().strip()
            
    except Exception as e:
        print(f"Error finding description: {e}")
    
    return 'No description available'

def create_rss_feed(url: str, title_xpath: str, description_xpath: str) -> str:
    """Generate RSS feed from webpage using XPath selectors."""
    try:
        response = requests.get(url)
        tree = html.fromstring(response.content)
        tree.make_links_absolute(url)
        
        feed = feedgenerator.Rss201rev2Feed(
            title=f"Custom RSS - {url}",
            link=url,
            description=f"Custom RSS feed for {url}",
            language="en"
        )
        
        title_elements = tree.xpath(title_xpath)
        
        for i, title_element in enumerate(title_elements):
            title = title_element.text_content().strip()
            link = extract_link(title_element)
            
            if link:
                link = make_absolute_url(link, url)
            
            description = find_description(title_element, description_xpath, tree, i)
            
            feed.add_item(
                title=title or 'No title',
                link=link or url,
                description=description,
                pubdate=datetime.now()
            )
            
        return feed.writeString('utf-8')
    except Exception as e:
        return f"Error: {str(e)}" 