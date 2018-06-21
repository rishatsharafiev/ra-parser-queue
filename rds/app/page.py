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

import unittest
import re
import time
import psycopg2
import logging

from selenium import webdriver
from selenium.webdriver.common import proxy
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.remote_connection import RemoteConnection

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

        self.POSTGRES_DB = os.getenv('POSTGRES_DB', '')
        self.POSTGRES_USER = os.getenv('POSTGRES_USER', '')
        self.POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', '')
        self.POSTGRES_HOST = os.getenv('POSTGRES_HOST', '')
        self.POSTGRES_PORT = os.getenv('POSTGRES_PORT', 5432)

        self.SELENIUM_HUB_URL = os.getenv('SELENIUM_HUB_URL', '')

        # drivers
        self.drivers = []

        # gevent queue
        nodes = os.getenv('SELENIUM_NODE_MAX_CONTAINERS', 1)
        instances = os.getenv('SELENIUM_NODE_MAX_INSTANCES', 1)
        self.maxsize = int(nodes) * int(instances)
        self.worker_number = int(self.maxsize - 1)
        self.worker_timeout = 60*60

        self.tasks = Queue(maxsize=self.maxsize*20)
        self.semaphore = BoundedSemaphore(1)

        # page config
        self.page_object_count = 100
        self.page_url = 'http://public.fsa.gov.ru/table_rds_pub_ts/'


    def get_available_proxy(self):
        with psycopg2.connect(dbname=self.POSTGRES_DB, user=self.POSTGRES_USER, password=self.POSTGRES_PASSWORD, host=self.POSTGRES_HOST, port=self.POSTGRES_PORT) as connection:
            with connection.cursor() as cursor:
                sql_string = """
                    SELECT "url", "schema"
                    FROM "proxy"
                    WHERE "is_frozen" = FALSE AND
                        "is_deleted" = FALSE
                    ORDER BY "updated_at", "ping";
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

    def get_links_by_page_boost(self, worker, range_start, range_end, per_page):
        driver = None
        links = []

        try:
            # proxy = self.get_available_proxy()
            # if not proxy:
            #     return list(set(links))
            # url, schema = proxy
            # proxy_address = url.strip('{}://'.format(schema))

            self.capabilities = {
              'browserName': 'chrome',
              'chromeOptions':  {
                'useAutomationExtension': False,
                'forceDevToolsScreenshot': True,
                'directConnect': True,
                'args': [
                    # '--start-maximized',
                    '--disable-infobars',
                    '--disable-extensions',
                    '--disable-web-security',
                    # '--disable-gpu',
                    # '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--headless',
                    '--window-size=600,480',
                    # '--remote-debugging-port=9222',
                    # '--crash-dumps-dir=/tmp',
                    '--silent',
                    '--ignore-certificate-errors',
                    '--disable-popup-blocking',
                    '--incognito',
                ]
              }
            }

            # self.capabilities['chromeOptions']['args'].append('--proxy-server={url}'.format(url=proxy_address))

            # remote driver
            self.semaphore.acquire()
            executor = RemoteConnection(self.SELENIUM_HUB_URL, resolve_ip=False)
            driver = webdriver.Remote(command_executor=executor, desired_capabilities=self.capabilities)
            driver.set_page_load_timeout(10*60)
            self.drivers.append(driver)
            self.semaphore.release()

            driver.get(self.page_url)
            wait = WebDriverWait(driver, 10*60)
            btn_find = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '#btn_find'))
            )
            btn_find.click()

            container_grid = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '#ContainerGrid'))
            )

            script = """downloadPage('index.php',
                'ajax=main&' + tableManager.getControlsData() + '&idid_=content-table'+getDivContent('tableContent-content-table')+
                '&page_byid_={count}&page_noid_={page_id}',
                'tableContent-content-table');
            """

            long_wait = WebDriverWait(driver, 10*60)

            with psycopg2.connect(dbname=self.POSTGRES_DB, user=self.POSTGRES_USER, password=self.POSTGRES_PASSWORD, host=self.POSTGRES_HOST, port=self.POSTGRES_PORT) as connection:
                with connection.cursor() as cursor:
                    sql_string = """
                        SELECT "page_id"
                        FROM "declaration"
                        WHERE "page_id" >= %s AND "page_id" <= %s;
                    """
                    parameters = (range_start, range_end,)
                    cursor.execute(sql_string, parameters)

                    pages = [row[0] for row in cursor.fetchall()]

                    for page_id in range(range_start, range_end):
                        if page_id not in pages:
                            driver.execute_script(script.format(count=self.page_object_count, page_id=page_id))
                            container_grid = long_wait.until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, '.cl_navigPage'))
                            )
                            links = driver.find_elements_by_css_selector('.dl_cert_num.object.link')
                            links = [link.get_attribute('href') for link in links]
                            print(page_id, ' => ', len(links))

                            values = []
                            for link in links:
                                values.append("('{link}', {page_id})".format(link=link, page_id=page_id))
                            values = ", ".join(values)

                            sql_string = """
                                INSERT INTO "declaration" ("url", "page_id")
                                    VALUES {values}
                                ON CONFLICT ("url") DO UPDATE
                                    SET "page_id" = %s;
                            """.format(values=values)
                            parameters = (page_id,)
                            cursor.execute(sql_string, parameters)

                            sql_string = """
                                UPDATE
                                    "page"
                                SET
                                    "is_done" = TRUE,
                                    "updated_at" = NOW()
                                WHERE
                                    "code" = %s AND per_page = %s;
                            """
                            parameters = (page_id, per_page,)
                            cursor.execute(sql_string, parameters)

                            connection.commit()
                        elif not range_start <= page_id < range_end:
                            pass
                        else:
                            print('worker: {worker}, page: {page_id} already done!'.format(worker=worker, page_id=page_id))

            print('Done worker: {worker}'.format(worker=worker))
        except WebDriverException as e:
            print('Error worker: {worker}, error: {error}'.format(worker=worker, error=str(e)))
            if driver:
                driver.quit()
            self.get_links_by_page_boost(worker, range_start, range_end, per_page)
            print('save_links')
        finally:
            if driver:
                driver.quit()
            if driver in self.drivers:
                self.drivers.remove(driver)

    # def get_links_by_page(self, worker, code, per_page):
    #     driver = None
    #     links = []

    #     try:
    #         # proxy = self.get_available_proxy()
    #         # if not proxy:
    #         #     return list(set(links))
    #         # url, schema = proxy
    #         # proxy_address = url.strip('{}://'.format(schema))

    #         self.capabilities = {
    #           'browserName': 'chrome',
    #           'chromeOptions':  {
    #             'useAutomationExtension': False,
    #             'forceDevToolsScreenshot': True,
    #             'directConnect': True,
    #             'args': [
    #                 # '--start-maximized',
    #                 '--disable-infobars',
    #                 '--disable-extensions',
    #                 '--disable-web-security',
    #                 # '--disable-gpu',
    #                 # '--disable-dev-shm-usage',
    #                 '--no-sandbox',
    #                 '--headless',
    #                 '--window-size=600,480',
    #                 # '--remote-debugging-port=9222',
    #                 # '--crash-dumps-dir=/tmp',
    #                 '--silent',
    #                 '--ignore-certificate-errors',
    #                 '--disable-popup-blocking',
    #                 '--incognito',
    #             ]
    #           }
    #         }

    #         # self.capabilities['chromeOptions']['args'].append('--proxy-server={url}'.format(url=proxy_address))

    #         # remote driver
    #         self.semaphore.acquire()
    #         executor = RemoteConnection(self.SELENIUM_HUB_URL, resolve_ip=False)
    #         driver = webdriver.Remote(command_executor=executor, desired_capabilities=self.capabilities)
    #         driver.set_page_load_timeout(10*60)
    #         self.drivers.append(driver)
    #         self.semaphore.release()

    #         driver.get(self.page_url)
    #         wait = WebDriverWait(driver, 10*60)
    #         btn_find = wait.until(
    #             EC.presence_of_element_located((By.CSS_SELECTOR, '#btn_find'))
    #         )
    #         btn_find.click()

    #         container_grid = wait.until(
    #             EC.presence_of_element_located((By.CSS_SELECTOR, '#ContainerGrid'))
    #         )

    #         script = """downloadPage('index.php',
    #             'ajax=main&' + tableManager.getControlsData() + '&idid_=content-table'+getDivContent('tableContent-content-table')+
    #             '&page_byid_={count}&page_noid_={page_id}',
    #             'tableContent-content-table');
    #         """

    #         long_wait = WebDriverWait(driver, 10*60)

    #         page_per_worker = int(self.last_page / self.maxsize)
    #         range_start = page_per_worker * worker
    #         range_end = page_per_worker * worker + page_per_worker

    #         if worker + 1 == self.maxsize:
    #             range_end += self.last_page % self.maxsize + 1

    #         with psycopg2.connect(dbname=self.POSTGRES_DB, user=self.POSTGRES_USER, password=self.POSTGRES_PASSWORD, host=self.POSTGRES_HOST, port=self.POSTGRES_PORT) as connection:
    #             with connection.cursor() as cursor:
    #                 for page_id in range(int(self.last_page)):
    #                     if range_start <= page_id < range_end:
    #                         driver.execute_script(script.format(count=self.page_object_count, page_id=page_id))
    #                         container_grid = long_wait.until(
    #                             EC.presence_of_element_located((By.CSS_SELECTOR, '.cl_navigPage'))
    #                         )
    #                         links = driver.find_elements_by_css_selector('.dl_cert_num.object.link')
    #                         links = [link.get_attribute('href') for link in links]
    #                         print(page_id, ' => ', len(links))

    #                         values = []
    #                         for link in links:
    #                             values.append("('{link}', {page_id})".format(link=link, page_id=page_id))
    #                         values = ", ".join(values)

    #                         sql_string = """
    #                             INSERT INTO "declaration" ("url", "page_id")
    #                                 VALUES {values}
    #                             ON CONFLICT ("url") DO UPDATE
    #                                 SET "page_id" = %s;
    #                         """.format(values=values)
    #                         parameters = (page_id,)
    #                         cursor.execute(sql_string, parameters)

    #                         sql_string = """
    #                             UPDATE
    #                                 "page"
    #                             SET
    #                                 "is_done" = TRUE,
    #                                 "updated_at" = NOW()
    #                             WHERE
    #                                 "code" = %s AND per_page = %s;
    #                         """
    #                         parameters = (page_id, per_page,)
    #                         cursor.execute(sql_string, parameters)

    #                         connection.commit()
    #                     elif not range_start <= page_id < range_end:
    #                         pass
    #                     else:
    #                         print('worker: {worker}, page: {page_id} already done!'.format(worker=worker, page_id=page_id))

    #         print('Done worker: {worker}'.format(worker=worker))
    #     except WebDriverException as e:
    #         print('Error worker: {worker}, error: {error}'.format(worker=worker, error=str(e)))
    #         if driver:
    #             driver.quit()
    #         self.get_links_by_page(worker, code, per_page)
    #         print('save_links')
    #     finally:
    #         if driver:
    #             driver.quit()
    #         if driver in self.drivers:
    #             self.drivers.remove(driver)

    # def worker(self, worker):
    #     try:
    #         while True:
    #             code, per_page = self.tasks.get(timeout=self.worker_timeout)
    #             with psycopg2.connect(dbname=self.POSTGRES_DB, user=self.POSTGRES_USER, password=self.POSTGRES_PASSWORD, host=self.POSTGRES_HOST, port=self.POSTGRES_PORT) as connection:
    #                 links = self.get_links_by_page(worker, code, per_page)

    #     except Empty:
    #         print('Worker #{} exited!'.format(n))

    # def main(self):
    #     with psycopg2.connect(dbname=self.POSTGRES_DB, user=self.POSTGRES_USER, password=self.POSTGRES_PASSWORD, host=self.POSTGRES_HOST, port=self.POSTGRES_PORT) as connection:
    #         with connection.cursor() as cursor:
    #             sql_string = """
    #                 SELECT "code", "per_page"
    #                 FROM "page"
    #                 ORDER BY "code", "per_page";
    #             """
    #             cursor.execute(sql_string)

    #             pages = [(row[0], row[1]) for row in cursor.fetchall()]
    #             self.last_page = max(pages, key=lambda x: x[0])[0]

    #             [self.tasks.put(page) for page in pages]

    def worker(self, worker):
        try:
            while True:
                i, per_page = self.tasks.get(timeout=self.worker_timeout)
                with psycopg2.connect(dbname=self.POSTGRES_DB, user=self.POSTGRES_USER, password=self.POSTGRES_PASSWORD, host=self.POSTGRES_HOST, port=self.POSTGRES_PORT) as connection:
                    page_per_worker = int(self.last_page / self.maxsize)
                    range_start = page_per_worker * worker
                    range_end = page_per_worker * worker + page_per_worker

                    if worker + 1 == self.maxsize:
                        range_end += self.last_page % self.maxsize + 1
                    links = self.get_links_by_page_boost(worker, range_start, range_end, per_page)
        except Empty:
            print('Worker #{} exited!'.format(n))
        except KeyboardInterrupt as e:
            print('KeyboardInterrupt')
        except WebDriverException as e:
            print('WebDriverException')
        except Exception as e:
            print('Exception')
        finally:
            [driver.quit() for driver in self.drivers]
            self.drivers = []

    def main(self):
        with psycopg2.connect(dbname=self.POSTGRES_DB, user=self.POSTGRES_USER, password=self.POSTGRES_PASSWORD, host=self.POSTGRES_HOST, port=self.POSTGRES_PORT) as connection:
            with connection.cursor() as cursor:
                sql_string = """
                    SELECT "code", "per_page"
                    FROM "page"
                    WHERE "per_page" = 100
                    ORDER BY "code", "per_page";
                """
                cursor.execute(sql_string)

                pages = [(row[0], row[1]) for row in cursor.fetchall()]
                self.last_page = max(pages, key=lambda x: x[0])[0]

                [self.tasks.put((i, 100)) for i in range(int(len(pages)/self.worker_number))]

    def run_parallel(self):
        try:
            gevent.joinall([
                gevent.spawn(self.main),
                *[gevent.spawn(self.worker, n) for n in range(self.worker_number)],
            ])
        except KeyboardInterrupt as e:
            print('KeyboardInterrupt')
        except WebDriverException as e:
            print('WebDriverException')
        except Exception as e:
            print('Exception')
        finally:
            [driver.quit() for driver in self.drivers]
            self.drivers = []

    def test_loop(self):
        while True:
            self.run_parallel()
            time.sleep(5)

if __name__ == '__main__':
    unittest.main()
