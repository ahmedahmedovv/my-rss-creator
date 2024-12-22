from supabase import create_client
import os
from dotenv import load_dotenv
from datetime import datetime
from urllib.parse import urlparse
import requests
from lxml import html, etree
import feedgenerator

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("Missing required environment variables")

supabase = create_client(supabase_url, supabase_key)

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
            
            # Extract link from title element or its parent/child
            link = None
            if title_element.get('href'):
                link = title_element.get('href')
            elif title_element.getparent().tag == 'a':
                link = title_element.getparent().get('href')
            elif title_element.find('.//a') is not None:
                link = title_element.find('.//a').get('href')
            
            # Make link absolute if it's relative
            if link and not link.startswith(('http://', 'https://')):
                link = f"{url.rstrip('/')}/{link.lstrip('/')}"
            
            # Find description using xpath
            try:
                description = tree.xpath(description_xpath)[i].text_content().strip()
            except:
                description = "No description available"
            
            feed.add_item(
                title=title or 'No title',
                link=link or url,
                description=description,
                pubdate=datetime.now()
            )
            
        return feed.writeString('utf-8')
    except Exception as e:
        return f"Error: {str(e)}"

def update_feed(feed_data):
    """Update a single feed in storage."""
    try:
        print(f"Updating feed: {feed_data['url']}")
        
        # Generate new RSS content
        rss_content = create_rss_feed(
            feed_data['url'],
            feed_data['title_xpath'],
            feed_data['description_xpath']
        )
        
        if rss_content.startswith('Error'):
            print(f"Error updating feed {feed_data['url']}: {rss_content}")
            return False
            
        # Create a stable filename that doesn't change
        domain = urlparse(feed_data['url']).netloc
        filename = f"{domain}.xml"  # Removed timestamp to keep filename constant
        
        # If there's an existing file, delete it first
        try:
            supabase.storage \
                .from_('rss-feed-storage') \
                .remove([filename])
        except:
            pass  # Ignore if file doesn't exist
            
        # Upload new content
        file_data = rss_content.encode('utf-8')
        storage_response = supabase.storage \
            .from_('rss-feed-storage') \
            .upload(filename, file_data)
            
        # Get public URL (this should remain constant now)
        file_url = supabase.storage \
            .from_('rss-feed-storage') \
            .get_public_url(filename)
            
        # Update database with URL only if it's different
        if feed_data.get('rss_file_url') != file_url:
            supabase.table('rss_feeds') \
                .update({'rss_file_url': file_url}) \
                .eq('id', feed_data['id']) \
                .execute()
            
        print(f"Successfully updated feed: {feed_data['url']}")
        return True
        
    except Exception as e:
        print(f"Error updating feed {feed_data['url']}: {str(e)}")
        return False

def main():
    """Main function to update all feeds once."""
    try:
        print(f"\nStarting feed updates at {datetime.now()}")
        
        # Get all feeds from database
        response = supabase.table('rss_feeds').select('*').execute()
        feeds = response.data
        
        if not feeds:
            print("No feeds found in database")
            return
            
        print(f"Found {len(feeds)} feeds to update")
        
        # Update each feed
        successful_updates = 0
        for feed in feeds:
            if update_feed(feed):
                successful_updates += 1
                
        print(f"\nUpdate completed at {datetime.now()}")
        print(f"Successfully updated {successful_updates} out of {len(feeds)} feeds")
        
    except Exception as e:
        print(f"Error in main function: {str(e)}")

if __name__ == "__main__":
    main() 