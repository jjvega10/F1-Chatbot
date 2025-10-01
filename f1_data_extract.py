from typing import Annotated
from webdriver_manager.chrome import ChromeDriverManager
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
import htmltabletomd
import re
from bs4 import BeautifulSoup
from openai import OpenAI
import json
import pandas as pd
import htmlmin
from io import StringIO
import sys
import pandas as pd
import numpy as np
import os
from IPython.display import display, Markdown

# Parse dynamic (javascript) sites
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

# Clean html
def get_info(x):
    x = x.prettify()
    x = re.sub(" class=\"[^\"]*\"", "", x)
    x = re.sub("<img[^>]*>", "", x)
    x = re.sub("<svg[^>]*>", "", x)
    x = re.sub("</svg[^>]*>", "", x)
    x = re.sub("<path[^>]*>", "", x)
    x = re.sub("</path[^>]*>", "", x)
    x = re.sub("<a[^>]*>", "", x)
    x = re.sub("<span[^>]*>", "<span>", x)
    x = re.sub("</span[^>]*>", "</span>", x)
    x = re.sub("<defs[^>]*>", "", x)
    x = re.sub("</defs[^>]*>", "", x)
    x = re.sub("<g[^>]*>", "", x)
    x = re.sub("</g[^>]*>", "", x)
    x = re.sub("<clippath[^>]*>", "", x)
    x = re.sub("</clippath[^>]*>", "", x)
    x = re.sub("<br>", "", x)
    x = re.sub("<p>", "", x)
    x = x.splitlines()
    y = []
    for line in x:
        if line.strip() != "":
            y.append(line.strip())
    event_text = ''.join(y)
    event_info = re.findall(r"(?<=>)[^<>]+(?=<)", event_text)
    return event_info

# Get race cards (Links to races)
url = f"https://www.formula1.com/en/racing/2025.html"
soup_og = extract_text_from_dynamic_site(url, wait_time=3)
possible_races = soup_og.find_all(attrs={"data-f1rd-a7s-click": "event_tile_click"})
race_cards = []
for race in possible_races:
    if len(race.find_all('title')) > 0:
        race_cards.append(race)

# Extract timesheet (aprox 3 min.)
if os.path.exists('data-cache/2025_timesheet.pqt'):
    timesheet_df = pd.read_parquet('data-cache/2025_timesheet.pqt')
else:
    base_url = 'https://www.formula1.com'
    timesheet_dfs = []
    for race in race_cards[1:]:
        event_url = base_url+race['href']
        url_name = event_url.split('/')[-1]
        year = event_url.split('/')[-2]
        event_links_soup = extract_text_from_dynamic_site(base_url+race['href'], wait_time=1)
        sessions_dict = {}
        if len(event_links_soup.find_all('a', string='Results'))==0:
            sessions_iter = event_links_soup.find_all('time')[0].parent.parent.parent.parent.children
            future_event = True
        else:
            sessions_iter = event_links_soup.find_all('time')[0].parent.parent.parent.parent.parent.children
            future_event = False
        for session in sessions_iter:
            spans = []
            for span in session.find_all('span'):
                if len(span.find_all())==0:
                    spans.append(span.text)
            times = []
            for time_list in session.find_all('time'):
                times.append(time_list.text)
            if len(times)==0 and len(spans)==0:
                continue
            if future_event:
                session_name = spans[-2]
            else:
                session_name = spans[-1]
            if len(times)==2:
                sessions_dict[session_name] = {'RACE':url_name, 
                                            'DATE': f"{spans[1]} {spans[0]}, {year}",
                                            'START_HOUR':times[0],
                                            'END_HOUR':times[1]}
            elif len(times)==1:
                sessions_dict[session_name] = {'RACE':url_name, 
                                            'DATE': f"{spans[1]} {spans[0]}, {year}",
                                            'START_HOUR':times[0]}
        session_timesheet = pd.DataFrame(sessions_dict).T.reset_index().rename({'index':'SESSION'}, axis=1)
        session_timesheet['YEAR'] = year
        timesheet_dfs.append(session_timesheet)
    timesheet_df = pd.concat(timesheet_dfs).reset_index(drop=True)
    timesheet_df = timesheet_df[['YEAR', 'RACE', 'SESSION', 'DATE', 'START_HOUR', 'END_HOUR']]
    timesheet_df['START_TIME'] = pd.to_datetime(timesheet_df['DATE']+' '+timesheet_df['START_HOUR'])
    timesheet_df['END_TIME'] = pd.to_datetime(np.where(timesheet_df['END_HOUR'].notna(), (timesheet_df['DATE']+' '+timesheet_df['END_HOUR']), pd.NaT))
    timesheet_df.to_parquet('data-cache/2025_timesheet.pqt')

# Find last update
tz_timedelta = pd.Timestamp('now').tz_localize('utc') - pd.Timestamp('now', tz='utc')
f1_2025_last_update = pd.to_datetime(os.path.getmtime('data-cache/f1_2025.pqt'), unit='s')
f1_2025_last_update = f1_2025_last_update + tz_timedelta

# Extract results (aprox 12 min.)
base_url = 'https://www.formula1.com'
dfs = []
refresh_all = False
pending_f1 = timesheet_df[(timesheet_df['START_TIME']>f1_2025_last_update) & (timesheet_df['START_TIME']<pd.Timestamp.now())]
#pending_f1 = timesheet_df[(timesheet_df['START_TIME']>pd.Timestamp('2025-09-20')) & (timesheet_df['START_TIME']<pd.Timestamp('2025-09-21'))]
#map_to_df = dict(zip(df_og['SESSION'].unique(), timesheet_df['SESSION'].unique()))
map_to_df = {'1': 'Practice 1', '2': 'Practice 2', '3': 'Practice 3',
 'qualifying': 'Qualifying', 'race-result': 'Race',
 'sprint-qualifying': 'Sprint Qualifying', 'sprint-results': 'Sprint'}
if not refresh_all and os.path.exists('data-cache/f1_2025.pqt'):
    df_og = pd.read_parquet('data-cache/f1_2025.pqt')
# If no results are pending, use cache
if len(pending_f1)==0:
    df = df_og.copy()
    df['SESSION'] = df['SESSION'].map(map_to_df)
    df.to_parquet('data-cache/f1_2025.pqt')
    del df_og
else:
    if not os.path.exists('data-cache/f1_2025.pqt'):
        df_og = pd.DataFrame(columns=['YEAR', 'RACE'])
    for race in race_cards:
        event_url = base_url+race['href']
        url_name = event_url.split('/')[-1]
        if not refresh_all and not url_name in pending_f1['RACE'].unique():
            continue
        else:
            year = event_url.split('/')[-2]
            event_links_soup = extract_text_from_dynamic_site(base_url+race['href'], wait_time=1)
            results_links = event_links_soup.find_all('a', string='Results')
            for session_a in results_links:
                session_url = session_a['href']
                session_name = session_url.split('/')[-1]
                session_soup = extract_text_from_dynamic_site(base_url+session_url, wait_time=1)
                try:
                    session_df = pd.read_html(StringIO(session_soup.find_all('table')[0].prettify()))[0]
                    og_cols = list(session_df.columns)
                    session_df['YEAR'] = year
                    session_df['RACE'] = url_name
                    session_df['SESSION'] = session_name
                    session_df = session_df[['YEAR', 'RACE', 'SESSION']+og_cols]
                    session_df = session_df[~session_df['DRIVER'].str.contains('Note')]
                    dfs.append(session_df)
                    print(year, url_name, session_name)
                except Exception as e:
                    print(year, url_name, session_name, e)
    df_og = df_og.set_index(['YEAR', 'RACE'])
    df_extra = pd.concat(dfs).reset_index(drop=True).set_index(['YEAR', 'RACE'])
    df_extra['SESSION'] = df_extra['SESSION'].map(map_to_df)
    df = pd.concat([df_og[~df_og.index.isin(df_extra.index)], df_extra]).reset_index()
    df['POS.'] = df['POS.'].astype('str')
    df['NO.'] = df['NO.'].astype('int')
    df['LAPS'] = df['LAPS'].astype('float')
    df['PTS.'] = df['PTS.'].astype('float')
    df['RACE_NUM'] = df['RACE'].map(dict((v,k) for k,v in enumerate(df['RACE'].unique(), start=1)))
    df.to_parquet('data-cache/f1_2025.pqt')

# Drivers
drivers_last_update = pd.to_datetime(os.path.getmtime('data-cache/drivers_standings.html'), unit='s')
drivers_last_update = drivers_last_update + tz_timedelta
pending_points = timesheet_df[(timesheet_df['SESSION'].isin(['Sprint', 'Race'])) & (timesheet_df['START_TIME']>drivers_last_update) & (timesheet_df['START_TIME']<pd.Timestamp.now())]
# If standings are up to date use cache
if len(pending_points)==0:
    with open("data-cache/drivers_standings.html", "r") as f:
        dr_minified = f.read()
# Else fetch standings
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
    drivers = pd.read_html(StringIO(html_text))[0]
    dr_html_table = drivers.set_index('POS.')[['DRIVER', 'TEAM', 'PTS.']].to_html(border='')
    dr_minified = htmlmin.minify(dr_html_table, remove_empty_space=True).replace(" class=dataframe", "").replace(' style="text-align: right;"', "")
    # Write dr_minified to an html file
    with open("data-cache/drivers_standings.html", "w") as f:
        f.write(dr_minified)

# Teams
teams_last_update = pd.to_datetime(os.path.getmtime('data-cache/team_standings.html'), unit='s')
teams_last_update = teams_last_update + tz_timedelta
pending_points = timesheet_df[(timesheet_df['SESSION'].isin(['Sprint', 'Race'])) & (timesheet_df['START_TIME']>teams_last_update) & (timesheet_df['START_TIME']<pd.Timestamp.now())]
# If standings are up to date use cache
if len(pending_points)==0:
    with open("data-cache/team_standings.html", "r") as f:
        tm_minified = f.read()
# Else fetch standings
else:
    url = f"https://www.formula1.com/en/results/2025/team"
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
    teams = pd.read_html(StringIO(html_text))[0]
    tm_html_table = teams.set_index('POS.')[['TEAM', 'PTS.']].to_html(border='')
    tm_minified = htmlmin.minify(tm_html_table, remove_empty_space=True).replace(" class=dataframe", "").replace(' style="text-align: right;"', "")
    # Write tm_minified to an html file
    with open("data-cache/team_standings.html", "w") as f:
        f.write(tm_minified)