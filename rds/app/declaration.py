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
from io import StringIO
import requests
from requests.exceptions import ReadTimeout, ConnectionError, ProxyError
from lxml import html

class TestSite(unittest.TestCase):
    def setUp(self):
        # initialize logget
        self.logger = logging.getLogger(__name__)
        logger_path = os.getenv('RDS_LOG_PATH', './')
        logger_handler = logging.FileHandler(os.path.join(logger_path, '{}.log'.format(__name__)))
        logger_formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        logger_handler.setFormatter(logger_formatter)
        self.logger.addHandler(logger_handler)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

        self.worker_number = 5
        self.worker_timeout = 10
        self.queue_size = 100
        self.tasks = Queue(maxsize=self.queue_size)
        self.semaphore = BoundedSemaphore(1)

        self.POSTGRES_DB = os.getenv('POSTGRES_DB', '')
        self.POSTGRES_USER = os.getenv('POSTGRES_USER', '')
        self.POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', '')
        self.POSTGRES_HOST = os.getenv('POSTGRES_HOST', '')
        self.POSTGRES_PORT = os.getenv('POSTGRES_PORT', 5432)

    def get_selector_root(self, url):
        root = None
        proxy_url = None

        with requests.session() as req:
            try:
                proxy = self.get_available_proxy()
                if proxy:
                    print(proxy)
                    proxy_url = proxy[0]
                    schema = proxy[1]
                    # if schema == 'http':
                    #     proxies = {
                    #       'http': proxy_url,
                    #       'https': proxy_url,
                    #     }
                    # elif schema == 'https':
                    #     proxies = {
                    #       'https': proxy_url,
                    #     }
                    proxies = {
                        'http': proxy_url,
                        'https': proxy_url,
                    }
                    response = req.get(url, timeout=7, proxies=proxies)
                else:
                    response = req.get(url)
                response.encoding = 'utf-8'
                stream = StringIO(response.text)
                root = html.parse(stream).getroot()
            except (ReadTimeout, ConnectionError, ProxyError) as e:
                self.set_proxy_frozen(proxy_url)
                root, proxy_url = self.get_selector_root(url)
                print(e)
            except Exception as e:
                print(str(e))

        return (root, proxy_url)

# import requests
# from lxml import html
# from io import StringIO

# proxy_url = 'http://83.241.46.175:8080'
# check_pi_url = 'http://speed-tester.info/check_ip.php'
# response = requests.get(check_pi_url, timeout=5, proxies={'http': proxy_url})
# stream = StringIO(response.text)
# root = html.parse(stream).getroot()
# element = root.cssselect('.center center font')
# if element:
# print(proxy_url, ' => ', element[0].text)

    def get_xpath_root(self, url):
        response = requests.get(url)
        response.encoding = 'utf-8'
        root = html.fromstring(response.text)
        return root

    def get_text_by_selector(self, root, selector):
        result = ''
        try:
            element = root.cssselect(selector)
            element
            if len(element):
                result = element[0].text
        except (Exception, IndexError) as e:
            print(str(e))

        return result

    def get_available_proxy(self):
        with psycopg2.connect(dbname=self.POSTGRES_DB, user=self.POSTGRES_USER, password=self.POSTGRES_PASSWORD, host=self.POSTGRES_HOST, port=self.POSTGRES_PORT) as connection:
            with connection.cursor() as cursor:
                sql_string = """
                    SELECT "url", "schema"
                    FROM "proxy"
                    WHERE "is_frozen" = FALSE AND
                        "is_deleted" = FALSE
                    ORDER BY RANDOM()
                    LIMIT 1;
                """
                cursor.execute(sql_string)

                result = cursor.fetchone()

                if result:
                    url = result[0]
                    schema = result[1]
                    return (url, schema,)
                else:
                    return None

    def set_proxy_frozen(self, url):
        with psycopg2.connect(dbname=self.POSTGRES_DB, user=self.POSTGRES_USER, password=self.POSTGRES_PASSWORD, host=self.POSTGRES_HOST, port=self.POSTGRES_PORT) as connection:
            with connection.cursor() as cursor:
                sql_string = """
                    UPDATE "proxy"
                    SET "is_frozen" = TRUE
                    WHERE "url"=%s;
                """
                parameters = (url,)
                cursor.execute(sql_string, parameters)
                connection.commit()

    def get_product_by_link(self, page_url):
        a_reg_number = None

        root, proxy_url = self.get_selector_root(page_url)

        captcha = self.get_text_by_selector(root, 'body > form')
        counter = 0
        while captcha:
            self.set_proxy_frozen(proxy_url)
            root, proxy_url = self.get_selector_root(page_url)
            print(root.text_content())
            captcha = self.get_text_by_selector(root, 'body > form')
            print(counter ,proxy_url)
            counter+=1

        ### 'Реквизиты сертификата'
        # 'Регистрационный номер',
        a_reg_number = self.get_text_by_selector(root, '#a_reg_number > .form-right-col')
        # a_reg_number = self.get_text_by_selector(root, '.center center font')

        return a_reg_number

    def worker(self, n):
        try:
            while True:
                url, category_id, pk = self.tasks.get(timeout=self.worker_timeout)
                with psycopg2.connect(dbname=self.POSTGRES_DB, user=self.POSTGRES_USER, password=self.POSTGRES_PASSWORD, host=self.POSTGRES_HOST, port=self.POSTGRES_PORT) as connection:
                    with connection.cursor() as cursor:
                        sql_string = """
                            SELECT
                                "id",
                                "url"
                            FROM "product"
                            WHERE "is_done" = TRUE;
                        """
                        cursor.execute(sql_string)

                        if (pk, url,) not in cursor.fetchall():
                            product = self.get_product_by_link(url)
                            if product:
                                sql_string = """
                                    INSERT INTO "product"
                                        (
                                            "page_id",
                                            "url",
                                            "name_url",
                                            "back_picture",
                                            "colors",
                                            "description_html",
                                            "description_text",
                                            "front_picture",
                                            "manufacturer",
                                            "name",
                                            "price_cleaned",
                                            "is_done"
                                        )
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                                    ON CONFLICT (url, page_id) DO UPDATE
                                        SET
                                            "updated_at"=NOW(),
                                            "is_done" = TRUE,
                                            "name_url" = %s,
                                            "back_picture" = %s,
                                            "colors" = %s,
                                            "description_html" = %s,
                                            "description_text" = %s,
                                            "front_picture" = %s,
                                            "manufacturer" = %s,
                                            "name" = %s,
                                            "price_cleaned" = %s
                                    RETURNING id;
                                """
                                page_id = pk,
                                name_url = url.split('/')[-1][:2044],
                                url = url[:2044],
                                back_picture = product['back_picture'][:2044],
                                colors = product['colors'][:2044],
                                description_html = product['description_html'][:5000],
                                description_text = product['description_text'][:5000],
                                front_picture = product['front_picture'][:2044],
                                manufacturer = product['manufacturer'][:2044],
                                name = product['name'][:2044],
                                price_cleaned = product['price_cleaned'][:2044],

                                parameters = (
                                    page_id,
                                    url,
                                    name_url,
                                    back_picture,
                                    colors,
                                    description_html,
                                    description_text,
                                    front_picture,
                                    manufacturer,
                                    name,
                                    price_cleaned,
                                    name_url,
                                    back_picture,
                                    colors,
                                    description_html,
                                    description_text,
                                    front_picture,
                                    manufacturer,
                                    name,
                                    price_cleaned,
                                )
                                cursor.execute(sql_string, parameters)
                                product_id = cursor.fetchone()[0]
                                connection.commit()

        except Empty:
            print('Worker #{} exited!'.format(n))

    def main(self):
        # TODO: join url with page_id in stream, split to parallel routines
        with psycopg2.connect(dbname=self.POSTGRES_DB, user=self.POSTGRES_USER, password=self.POSTGRES_PASSWORD, host=self.POSTGRES_HOST, port=self.POSTGRES_PORT) as connection:
            with connection.cursor() as cursor:
                sql_string = """
                    SELECT
                        "url",
                        "category_id",
                        "id"
                    FROM "page"
                    WHERE "is_done" = FALSE;
                """
                cursor.execute(sql_string)
                for row in cursor.fetchall():
                    url = row[0]
                    category_id = row[1]
                    pk = row[2]
                    self.tasks.put((url, category_id, pk,))

    def run_parallel(self):
        gevent.joinall([
            gevent.spawn(self.main),
            *[gevent.spawn(self.worker, n) for n in range(self.worker_number)],
        ])

    def test_loop(self):
        id_object = 'http://188.254.71.82/rds_ts_pub/?show=view&id_object=556AE866F9B347A497651EBAD80B3EEE'
        # id_object = 'http://speed-tester.info/check_ip.php'
        while True:
            print(self.get_product_by_link(id_object).replace(' ', ''))
        # while True:
        #     self.run_parallel()

if __name__ == '__main__':
    unittest.main()
