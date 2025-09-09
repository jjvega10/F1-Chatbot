from typing import Annotated
from webdriver_manager.chrome import ChromeDriverManager
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
import htmltabletomd
import re
from bs4 import BeautifulSoup

def extract_text_from_dynamic_site(url, wait_time=10):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        driver.get(url)
        print(f"Loaded: {url}")
        time.sleep(wait_time)
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        return soup
    except Exception as e:
        print(f"Error: {e}")
        return None
    finally:
        driver.quit()

def get_f1_driver_standings(
    standings_type: Annotated[str, "Select 'drivers' or 'team' championship standings."]
) -> str:
    """Get the current F1 drivers or teams standings. 
    Use it to determine the points for each driver in the driver's championship or the points for each team in the teams' championship."""
    if standings_type=="team":
        url = f"https://www.formula1.com/en/results/2025/team"
    else:
        url = f"https://www.formula1.com/en/results/2025/drivers"
    soup_og = extract_text_from_dynamic_site(url, wait_time=3)
    html_table = soup_og.find_all('table')[0]
    html_text = str(html_table.prettify())
    html_text = re.sub(" class=\"[^\"]*\"", "", html_text)
    html_text = re.sub("<img[^>]*>", "", html_text)
    html_text = re.sub("<a[^>]*>", "", html_text)
    html_text = re.sub("<span[^>]*>", "", html_text)
    html_text = re.sub("</span[^>]*>", "", html_text)
    html_text = re.sub("<br>", "", html_text)
    html_text = re.sub("<p>", "", html_text)
    html_text = re.sub("\\\n *", "", html_text)
    drivers_standings_table = htmltabletomd.convert_table(html_text)
    return drivers_standings_table

# Retreive F1 schedule (with time zones)
def get_f1_schedule() -> str:
    # Parse the F1 schedule from the F1 website
    url = f"https://www.formula1.com/en/racing/2025.html"
    soup_og = extract_text_from_dynamic_site(url, wait_time=3)