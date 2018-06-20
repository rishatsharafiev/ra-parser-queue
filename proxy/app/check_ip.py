import requests
from lxml import html
from io import StringIO

proxy_url = 'http://83.241.46.175:8080'
check_pi_url = 'http://speed-tester.info/check_ip.php'
response = requests.get(check_pi_url, timeout=5, proxies={'http': proxy_url})
stream = StringIO(response.text)
root = html.parse(stream).getroot()
element = root.cssselect('.center center font')
if element:
	print(proxy_url, ' => ', element[0].text)