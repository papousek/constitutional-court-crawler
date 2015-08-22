# -*- coding: utf-8 -*-
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
import os.path
import os
import json
import codecs
import shutil
from argparse import ArgumentParser


WAIT_TIME = 10
PROCEEDINGS_PER_PAGE = 20


def parser_init(required=None):
    parser = ArgumentParser()
    parser.add_argument(
        '-o',
        '--output',
        metavar='FILE',
        dest='output',
        default='./target',
        help='path to the output directory')
    parser.add_argument(
        '-c',
        '--clean',
        action='store_true',
        dest='clean',
        help='clean previous output')
    parser.add_argument(
        '-r',
        '--reload',
        action='store_true',
        dest='reload',
        help='reload crawling')
    return parser


def find_element_safely(browser, method, locator):
    return WebDriverWait(browser, WAIT_TIME).until(
        EC.presence_of_element_located((method, locator))
    )


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


def load_number_of_search_results(browser):
    text = find_element_safely(browser, By.XPATH, '(//tr[contains(@class, "resultHeaderCount")])[1]').text
    return int(re.match('.*?z celkem (\d+);.*', text).group(1))


def load_main_paging(browser):
    return int(find_element_safely(browser, By.XPATH, '//input[@name="pageNumber"]').get_attribute('value'))


def load_number_of_main_pages(browser):
    return int(find_element_safely(browser, By.XPATH, '//*[@id="Content"]/table/tbody/tr[1]/td/table/tbody/tr/td/a[last() - 1]').text.strip())


def back_to_search_results(browser):
    find_element_safely(browser, By.XPATH, '//*[@id="GotoList"]').click()
    wait_for_search_results(browser)


def wait_for_search_results(browser):
    find_element_safely(browser, By.XPATH, '//*[@id="Content"]/table')


def wait_for_proceedings(browser):
    find_element_safely(browser, By.XPATH, '//*[@id="GotoNextId"]')


def goto_main_page(browser, main_page):
    if main_page > load_number_of_main_pages(browser):
        raise Exception("Page out of the given range.")
    current = load_main_paging(browser)
    pages_to_go = main_page - current
    if pages_to_go < 0:
        raise Exception("We can go forward only.")
    for next_page in range(pages_to_go):
        current = load_main_paging(browser)
        find_element_safely(browser, By.XPATH, '//*[@id="Content"]/table/tbody/tr[1]/td/table/tbody/tr/td/a[last()]').click()
        for i in range(WAIT_TIME):
            time.sleep(1)
            if current != load_main_paging(browser):
                break
            if i == WAIT_TIME - 1:
                raise Exception("Can not change page!")


def setup_search(browser):
    browser.get('http://nalus.usoud.cz/Search/Results.aspx')

    proceedings_type_button = find_element_safely(browser, By.XPATH, '//*[@id="ctl00_MainContent_pnlMainForm"]/table/tbody/tr[3]/td/table/tbody/tr/td[1]/table/tbody/tr[5]/td[2]/a/input')
    proceedings_type_button.click()
    switch_to_popup(browser)
    proceedings_type_wanted = find_element_safely(browser, By.XPATH, '//*[@id="aspnetForm"]/div[3]/table/tbody/tr[2]/td/table/tbody/tr[2]/td[1]/input')
    proceedings_type_wanted.click()
    close_search_popup(browser)

    proposer_button = find_element_safely(browser, By.XPATH, '//*[@id="ctl00_MainContent_pnlMainForm"]/table/tbody/tr[3]/td/table/tbody/tr/td[1]/table/tbody/tr[12]/td[2]/a/input')
    proposer_button.click()
    switch_to_popup(browser)
    for i in [2, 3]:
        proposer_wanted = find_element_safely(browser, By.XPATH, '//*[@id="aspnetForm"]/div[3]/table/tbody/tr[2]/td/table/tbody/tr[{}]/td[1]/input'.format(i))
        proposer_wanted.click()
    close_search_popup(browser)
    search_button = find_element_safely(browser, By.XPATH, '//*[@id="ctl00_MainContent_but_search"]')
    search_button.click()
    wait_for_search_results(browser)


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
    attributes = sorted(map(
        lambda text: tuple(map(lambda x: x.replace('<br />', '---').strip(), re.findall('<td.*?>(.*?)</td>', text, flags=re.DOTALL))),
        found
    ))
    lawyer_matched = re.match('.*?[Zz]ast[^,]*? (.*?),.*', content.split('\n')[0], flags=re.DOTALL)
    residence_matched = re.match('.*?[Ss]e sídlem (.*?), (.*?),.*', content.split('\n')[0], flags=re.DOTALL)
    if lawyer_matched is not None and len(lawyer_matched.group(1)) > 40:
        lawyer_matched = None
    if residence_matched is not None and len(residence_matched.group(1) + residence_matched.group(2)) > 60:
        residence_matched = None
    without_lawyer = 'bez právního zastoupení' in content.split('\n')[0]
    attributes.append(('lawyer', ('bez právního zastoupení' if without_lawyer else '') if lawyer_matched is None else lawyer_matched.group(1)))
    attributes.append(('residence', '' if residence_matched is None else '{}, {}'.format(residence_matched.group(1), residence_matched.group(2))))
    return attributes, content, html_content


def load_paging(browser):
    paging_text = find_element_safely(browser, By.XPATH, '//*[@id="lbPosition"]').text
    matched = re.match(r'.*?(\d+) \/ (\d+)', paging_text)
    return int(matched.group(1)), int(matched.group(2))


def goto_proceedings(browser, index=0):
    switch_to_main(browser)
    if index + 1 == load_number_of_search_results(browser):
        return False
    page = index / PROCEEDINGS_PER_PAGE + 1
    index_on_page = index % PROCEEDINGS_PER_PAGE + 1
    goto_main_page(browser, page)
    find_element_safely(browser, By.XPATH, '//*[@id="Content"]/table/tbody/tr[2]/td/table[2]/tbody/tr/td/table/tbody/tr[{}]/td[2]/a'.format(2 * index_on_page + 1)).click()
    wait_for_proceedings(browser)
    return True


def save_proceedings(f, directory, (attributes, content, html_content), last_saved=None):
    identifier = dict(attributes)['Identifikátor evropské judikatury']
    identifier_dir = os.path.join(directory, '-'.join(identifier.split(':')[:-1]))
    identifier_file = os.path.join(identifier_dir, identifier.replace(':', '-').replace('.', '-'))
    if os.path.exists(identifier_file + '.save') or (last_saved is not None and last_saved['Identifikátor evropské judikatury'] == identifier):
        print ' -- SKIPPING SAVING OF', identifier
        return False
    attributes += [
        ('html_file', identifier_file + '.html'),
        ('txt_file', identifier_file + '.txt'),
        ('json_file', identifier_file + '.json'),
    ]
    if not os.path.exists(identifier_dir):
        os.makedirs(identifier_dir)
    with codecs.open(identifier_file + '.json', 'w', 'utf-8') as idf:
        json.dump(dict(attributes), idf)
    with codecs.open(identifier_file + '.txt', 'w', 'utf-8') as idf:
        idf.write(content.decode('utf-8'))
    with codecs.open(identifier_file + '.html', 'w', 'utf-8') as idf:
        idf.write(html_content.decode('utf-8'))
    f.write('\n' + ';'.join(map(lambda a: re.sub('<[^<]+?>', '', a[1]).replace(';', '--').replace('\n', '---'), attributes)).decode('utf-8'))
    with open(identifier_file + '.save', 'w') as idf:
        idf.write('done')
    return True


def get_last_saved_proceedings(target_file):
    if not os.path.exists(target_file):
        return None, None
    keys = os.popen("head -n 1 {}".format(target_file)).read().split(';')
    values = os.popen("tail -n 1 {}".format(target_file)).read().split(';')
    number = int(os.popen("wc -l {}".format(target_file)).read().split(' ')[0]) - 1
    return dict(zip(keys, values)), number


if __name__ == "__main__":
    args = parser_init().parse_args()
    browser = webdriver.Firefox()
    target_dir = args.output
    target_file = os.path.join(target_dir, 'data.csv')

    if args.clean:
        shutil.rmtree(target_dir)

    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    last_proceedings, index_of_last_proceedings = get_last_saved_proceedings(target_file)

    with codecs.open(target_file, 'a' if os.path.exists(target_file) else 'w', 'utf-8') as f:
        setup_search(browser)
        last_proceedings_index = index_of_last_proceedings if args.reload else 0
        first = index_of_last_proceedings is None
        proceedings_attr_size = None if last_proceedings is None else len(last_proceedings) - 3
        while goto_proceedings(browser, last_proceedings_index):
            print last_proceedings_index
            proceedings = load_proceedings(browser)
            if first:
                proceedings_attr_size = len(proceedings[0])
                f.write(';'.join(map(lambda a: a[0].replace(';', '--'), proceedings[0] + [('html_file', ), ('json_file', ), ('txt_file', )])).decode('utf-8'))
                first = False
            if len(proceedings[0]) != proceedings_attr_size:
                raise Exception('Proceeding attributes do not match, found {}, expected {}.'.format(len(proceedings[0]), proceedings_attr_size))
            saved = save_proceedings(f, target_dir, proceedings, last_saved=last_proceedings)
            if not args.reload and not saved:
                print ' -- THERE ARE NO NEW PROCEEDINGS'
                break
            last_proceedings_index += 1
            back_to_search_results(browser)


