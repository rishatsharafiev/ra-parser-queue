# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv

BASE_PATH = os.path.dirname(os.path.realpath(__file__))
DOTENV_PATH = os.path.join(BASE_PATH, '.env')
load_dotenv(DOTENV_PATH)

import unittest
import time
import psycopg2
import logging

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

        self.RDS_MAX_PAGE = int(os.getenv('RDS_MAX_PAGE', 0))
        self.RDS_LINK_PER_PAGE = int(os.getenv('RDS_LINK_PER_PAGE', 100))

    def write_to_db(self):
        with psycopg2.connect(dbname=self.POSTGRES_DB, user=self.POSTGRES_USER, password=self.POSTGRES_PASSWORD, host=self.POSTGRES_HOST, port=self.POSTGRES_PORT) as connection:
            with connection.cursor() as cursor:
                counter = 0
                buffered_values = []
                for code in range(self.RDS_MAX_PAGE):
                    buffered_values.append(code)
                    if counter % 10000 == 0 or self.RDS_MAX_PAGE - 1 == counter:

                        values = ["('{code}', '{per_page}')".format(code=value, per_page=self.RDS_LINK_PER_PAGE) for value in buffered_values]
                        values = ", ".join(values)
                        sql_string = """
                            INSERT INTO
                                "page" ("code", "per_page")
                            VALUES {values}
                            ON CONFLICT ("code", "per_page") DO NOTHING;
                        """.format(values=values)
                        cursor.execute(sql_string)
                        connection.commit()
                    counter +=1

    def test_loop(self):
        while True:
            self.write_to_db()
            time.sleep(60)

if __name__ == '__main__':
    unittest.main()
