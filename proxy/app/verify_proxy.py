# -*- coding: utf-8 -*-

import gevent.monkey
gevent.monkey.patch_all()
import gevent
from gevent.queue import Queue, Empty
from gevent.lock import BoundedSemaphore

import os
from dotenv import load_dotenv

BASE_PATH = os.path.dirname(os.path.realpath(__file__))
DOTENV_PATH = os.path.join(BASE_PATH, '.env')
load_dotenv(DOTENV_PATH)

import logging
import unittest
import re
import psycopg2
from datetime import datetime
import time
from io import StringIO
import requests
from lxml import html

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

        self.worker_number = 10
        self.worker_timeout = 20
        self.proxy_timeout=15
        self.queue_size = 100
        self.tasks = Queue(maxsize=self.queue_size)
        self.semaphore = BoundedSemaphore(1)

        self.POSTGRES_DB = os.getenv('POSTGRES_DB', '')
        self.POSTGRES_USER = os.getenv('POSTGRES_USER', '')
        self.POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', '')
        self.POSTGRES_HOST = os.getenv('POSTGRES_HOST', '')
        self.POSTGRES_PORT = os.getenv('POSTGRES_PORT', 5432)

    def get_selector_root(self, url):
        response = requests.get(url)
        response.encoding = 'utf-8'
        stream = StringIO(response.text)
        root = html.parse(stream).getroot()
        return root

    def get_proxy_links(self):
        urls = []

        try:
            with psycopg2.connect(dbname=self.POSTGRES_DB, user=self.POSTGRES_USER, password=self.POSTGRES_PASSWORD, host=self.POSTGRES_HOST, port=self.POSTGRES_PORT) as connection:
                with connection.cursor() as cursor:
                    sql_string = """
                        SELECT "url", "schema"
                        FROM "proxy"
                        WHERE "is_deleted" = FALSE
                        ORDER BY "created_at", "updated_at";
                    """
                    cursor.execute(sql_string)
                    urls = [(url[0], url[1]) for url in cursor.fetchall()]
        except Exception as e:
            self.logger.exception(str(e))

        return list(set(urls))

    def verify_proxy(self, proxy_url, schema):
        verify_url = 'https://ya.ru'
        title = 'Яндекс'
        proxy = None

        try:
            # make request and get ping
            start = datetime.now()
            response = requests.get(verify_url, timeout=self.proxy_timeout, proxies={schema: proxy_url})
            end = datetime.now()
            ping = end - start

            # get title
            stream = StringIO(response.text)
            root = html.parse(stream).getroot()
            page_title = root.cssselect('title')[0]

            # check that proxy is available
            if response.status_code == 200 and title == page_title.text:
                proxy = {
                    'is_deleted': False,
                    'url': proxy_url,
                    'schema': schema,
                    'ping': int(ping.microseconds / 1000)
                }
            else:
                proxy = {
                    'is_deleted': True,
                    'url': proxy_url,
                    'schema': schema
                }
        except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout) as e:
            proxy = {
                'is_deleted': True,
                'url': proxy_url,
                'schema': schema
            }
        except Exception as e:
            self.logger.exception(str(e))

        return proxy

    def worker(self, n):
        try:
            while True:
                url, schema = self.tasks.get(timeout=self.worker_timeout)
                with psycopg2.connect(dbname=self.POSTGRES_DB, user=self.POSTGRES_USER, password=self.POSTGRES_PASSWORD, host=self.POSTGRES_HOST, port=self.POSTGRES_PORT) as connection:
                    proxy = self.verify_proxy(url, schema)
                    if proxy and not proxy['is_deleted']:
                        with connection.cursor() as cursor:
                            sql_string = """
                                UPDATE
                                    "proxy"
                                SET
                                    "ping" = %s,
                                    "updated_at" = NOW(),
                                    "is_deleted" = FALSE
                                WHERE
                                    "url" = %s AND
                                    "schema" = %s;
                            """
                            parameters = (proxy['ping'], proxy['url'], proxy['schema'],)
                            cursor.execute(sql_string, parameters)
                            connection.commit()
                    elif proxy and proxy['is_deleted']:
                        with connection.cursor() as cursor:
                            sql_string = """
                                UPDATE
                                    "proxy"
                                SET
                                    "updated_at" = NOW(),
                                    "is_deleted" = TRUE
                                WHERE
                                    "url" = %s AND
                                    "schema" = %s;
                            """
                            parameters = (proxy['url'], proxy['schema'],)
                            cursor.execute(sql_string, parameters)
                            connection.commit()
        except Empty:
            print('Worker #{} exited!'.format(n))

    def main(self):
        urls = self.get_proxy_links()
        for url in urls:
            self.tasks.put(url)

    def run_parallel(self):
        gevent.joinall([
            gevent.spawn(self.main),
            *[gevent.spawn(self.worker, n) for n in range(self.worker_number)],
        ])

    def test_loop(self):
        while True:
            self.run_parallel()
            time.sleep(5)

if __name__ == '__main__':
    unittest.main()
