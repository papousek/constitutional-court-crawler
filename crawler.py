# -*- coding: utf-8 -*-
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
from pprint import pprint
import os.path
import os
import json
import codecs


def switch_to_main(browser):
    browser.switch_to_window(browser.window_handles[0])


def switch_to_popup(browser):
    if len(browser.window_handles) == 1:
        raise Exception('There is no popup window')
    browser.switch_to_window(browser.window_handles[-1])


def close_search_popup(browser):
    save_button = browser.find_element_by_xpath('//*[@id="bSave2"]')
    save_button.click()
    switch_to_main(browser)


def setup_search(browser):
    browser.get('http://nalus.usoud.cz/Search/Results.aspx')
    proceedings_type_button = WebDriverWait(browser, 10).until(
        EC.presence_of_element_located((By.XPATH, '//*[@id="ctl00_MainContent_pnlMainForm"]/table/tbody/tr[3]/td/table/tbody/tr/td[1]/table/tbody/tr[5]/td[2]/a/input'))
    )
    proceedings_type_button.click()
    switch_to_popup(browser)
    proceedings_type_wanted = browser.find_element_by_xpath(
        '//*[@id="aspnetForm"]/div[3]/table/tbody/tr[2]/td/table/tbody/tr[2]/td[1]/input'
    )
    proceedings_type_wanted.click()
    close_search_popup(browser)
    proposer_button = WebDriverWait(browser, 10).until(
        EC.presence_of_element_located((By.XPATH, '//*[@id="ctl00_MainContent_pnlMainForm"]/table/tbody/tr[3]/td/table/tbody/tr/td[1]/table/tbody/tr[12]/td[2]/a/input'))
    )
    proposer_button.click()
    switch_to_popup(browser)
    for i in [2, 3]:
        proposer_wanted = WebDriverWait(browser, 10).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="aspnetForm"]/div[3]/table/tbody/tr[2]/td/table/tbody/tr[{}]/td[1]/input'.format(i)))
        )
        proposer_wanted.click()
    close_search_popup(browser)
    search_button = browser.find_element_by_xpath('//*[@id="ctl00_MainContent_but_search"]')
    search_button.click()
    WebDriverWait(browser, 10).until(
        EC.presence_of_element_located((By.XPATH, '//*[@id="Content"]/table'))
    )


def load_proceedings_item(html_content, key):
    matched = re.match(r'.*<tr>.*?({}).*?<td.*?>(.*?)</td>.*</tr>.*'.format(key), html_content, flags=re.DOTALL)
    if matched is None:
        raise Exception('Key "{}" not found.'.format(key))
    return matched.group(2)


def load_proceedings(browser):
    html_content = browser.page_source.encode('utf-8')
    found = re.findall('<tr.*?>(.*?)</tr>',
        re.match('.*<tbody.*?>(.+)</tbody>.*',
            re.match('.*<table.*?class="recordCardTable".*?>(.*?)</table>.*',
                html_content, flags=re.DOTALL
            ).group(1),
        flags=re.DOTALL).group(1),
    flags=re.DOTALL)
    content = browser.find_element_by_xpath('//*[@id="uc_vytah_cellContent"]').text.encode('utf-8')
    attributes = sorted(map(lambda text: tuple(map(lambda item: re.match('.*>(.*?)<.*', item, flags=re.DOTALL).group(1).strip(), text.split('>\n<'))), found))
    lawyer_matched = re.match('.*?[Zz]astoupen[^,]*? (.*?),.*', content.split('\n')[0], flags=re.DOTALL)
    if lawyer_matched is not None and len(lawyer_matched.group(1)) > 40:
        lawyer_matched = None
    without_lawyer = 'bez právního zastoupení' in content.split('\n')[0]
    attributes.append(('lawyer', ('bez právního zastoupení' if without_lawyer else '') if lawyer_matched is None else lawyer_matched.group(1)))
    return attributes, content, html_content


def load_paging(browser):
    paging_text = WebDriverWait(browser, 10).until(
        EC.presence_of_element_located((By.XPATH, '//*[@id="lbPosition"]'))
    ).text
    matched = re.match(r'.*?(\d+) \/ (\d+)', paging_text)
    return int(matched.group(1)), int(matched.group(2))


def goto_first_proceedings(browser):
    switch_to_main(browser)
    browser.find_element_by_xpath('//*[@id="Content"]/table/tbody/tr[2]/td/table[2]/tbody/tr/td/table/tbody/tr[3]/td[2]/a').click()
    WebDriverWait(browser, 10).until(
        EC.presence_of_element_located((By.XPATH, '//*[@id="GotoNextId"]'))
    )


def goto_next_proceedings(browser):
    switch_to_main(browser)
    current, total = load_paging(browser)
    print current, total
    if current == total:
        return False
    browser.find_element_by_xpath('//*[@id="GotoNextId"]').click()
    for i in range(10):
        time.sleep(1)
        if current != load_paging(browser)[0]:
            return True
    raise Exception('Waiting too long')


def save_proceedings(f, directory, (attributes, content, html_content)):
    identifier = dict(attributes)['Identifikátor evropské judikatury']
    identifier_dir = os.path.join(directory, '-'.join(identifier.split(':')[:-1]))
    identifier_file = os.path.join(identifier_dir, identifier.replace(':', '-').replace('.', '-'))
    if not os.path.exists(identifier_dir):
        os.makedirs(identifier_dir)
    with codecs.open(identifier_file + '.json', 'w', 'utf-8') as idf:
        json.dump(dict(attributes), idf)
    with codecs.open(identifier_file + '.txt', 'w', 'utf-8') as idf:
        idf.write(content.decode('utf-8'))
    with codecs.open(identifier_file + '.html', 'w', 'utf-8') as idf:
        idf.write(html_content.decode('utf-8'))
    f.write('\n' + ';'.join(map(lambda a: a[1].replace(';', '--').replace('\n', '---'), attributes)).decode('utf-8'))

#browser = webdriver.PhantomJS()
browser = webdriver.Firefox()
target_dir = './target'

if not os.path.exists(target_dir):
    os.makedirs(target_dir)

with codecs.open(os.path.join(target_dir, 'data.csv'), 'w', 'utf-8') as f:
    setup_search(browser)
    goto_first_proceedings(browser)
    should_next = True
    first = True
    proceedings_attr_size = None
    while should_next:
        proceedings = load_proceedings(browser)
        if first:
            proceedings_attr_size = len(proceedings[0])
            f.write(';'.join(map(lambda a: a[0].replace(';', '--'), proceedings[0])).decode('utf-8'))
            first = False
        if len(proceedings[0]) != proceedings_attr_size:
            raise Exception('Proceeding attributes do not match.')
        save_proceedings(f, target_dir, proceedings)
        should_next = goto_next_proceedings(browser)


