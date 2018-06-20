# -*- coding: utf-8 -*-

import os
from dotenv import load_dotenv

BASE_PATH = os.path.dirname(os.path.realpath(__file__))
DOTENV_PATH = os.path.join(BASE_PATH, '.env')
load_dotenv(DOTENV_PATH)

import logging
import unittest
import psycopg2
import time
from io import StringIO
import requests
from lxml import html
import time

class TestSite(unittest.TestCase):
    def setUp(self):
        # initialize logget
        self.logger = logging.getLogger(__name__)
        logger_path = os.getenv('PROXY_LOG_PATH', './')
        logger_handler = logging.FileHandler(os.path.join(logger_path, '{}.log'.format(__name__)))
        logger_formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        logger_handler.setFormatter(logger_formatter)
        self.logger.addHandler(logger_handler)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

        self.POSTGRES_DB = os.getenv('POSTGRES_DB', '')
        self.POSTGRES_USER = os.getenv('POSTGRES_USER', '')
        self.POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', '')
        self.POSTGRES_HOST = os.getenv('POSTGRES_HOST', '')
        self.POSTGRES_PORT = os.getenv('POSTGRES_PORT', 5432)

        self.proxy_url = 'http://www.ip-adress.com/proxy_list/'

    def get_selector_root(self, url):
        response = requests.get(url)
        response.encoding = 'utf-8'
        stream = StringIO(response.text)
        root = html.parse(stream).getroot()
        return root

    def get_proxy_links(self):
        urls = []
        proxy_url = self.proxy_url

        try:
            root = self.get_selector_root(proxy_url)
            urls = root.cssselect('.htable > tbody > tr > td:first-child')
            urls = ['http://{address}'.format(address=url.text_content())for url in urls]
        except Exception as e:
            self.logger.exception(str(e))

        return list(set(urls))

    def write_to_db(self):
        urls = self.get_proxy_links()
        with psycopg2.connect(dbname=self.POSTGRES_DB, user=self.POSTGRES_USER, password=self.POSTGRES_PASSWORD, host=self.POSTGRES_HOST, port=self.POSTGRES_PORT) as connection:
            with connection.cursor() as cursor:
                counter = 1
                buffered_values = []
                for url in urls:
                    buffered_values.append(url)
                    if counter % 100 == 0 or len(urls) == counter:
                        values = ["('{url}', 'http', '{source}')".format(url=value, source=self.proxy_url) for value in buffered_values]
                        values = ", ".join(values)
                        sql_string = """
                            INSERT INTO
                                "proxy" ("url", "schema", "source")
                            VALUES {values}
                            ON CONFLICT (url, schema) DO NOTHING;
                        """.format(values=values)
                        cursor.execute(sql_string)
                        connection.commit()
                    counter +=1

    def test_loop(self):
        while True:
            self.write_to_db()
            time.sleep(30)

if __name__ == '__main__':
    unittest.main()
