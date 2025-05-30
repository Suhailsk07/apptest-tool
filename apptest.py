import sys
import requests
from bs4 import BeautifulSoup
from mitmproxy import http, ctx
import threading
import logging
import re
from urllib.parse import urljoin, urlparse
import time
import urllib3

# Disable SSL warnings for testing (use cautiously)
urllib3.disable_warnings()

# Configure logging
logging.basicConfig(filename='apptest.log', level=logging.INFO,
                    format='%(asctime)s - %(message)s')

class APPTEST:
    def __init__(self):
        self.visited_urls = set()
        self.vulnerabilities = []
        self.base_url = None
        self.forms = []
        self.requests_log = []

    def check_security_headers(self, response):
        """Check for missing or misconfigured security headers."""
        headers = response.headers
        issues = []
        security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": ["DENY", "SAMEORIGIN"],
            "X-XSS-Protection": "1; mode=block",
            "Content-Security-Policy": None,
            "Strict-Transport-Security": None,
            "Access-Control-Allow-Origin": None
        }

        for header, expected in security_headers.items():
            if header not in headers:
                if header == "Strict-Transport-Security" and not response.url.startswith("https"):
                    continue
                issues.append(f"Missing {header}")
            else:
                value = headers[header]
                if expected and isinstance(expected, list):
                    if value not in expected:
                        issues.append(f"{header}: {value} (Expected one of {expected})")
                elif expected and value.lower() != expected.lower():
                    issues.append(f"{header}: {value} (Expected {expected})")
                if header == "Access-Control-Allow-Origin" and value == "*":
                    issues.append("CORS: Overly permissive (*)")

        return issues

    def check_xss(self, url, response):
        """Check for reflected XSS patterns."""
        issues = []
        soup = BeautifulSoup(response.text, 'html.parser')
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string and any(keyword in script.string.lower() for keyword in ['alert(', 'document.write']):
                issues.append(f"Potential XSS in script tag")
        params = urlparse(url).query
        if params:
            for param in params.split('&'):
                value = param.split('=')[-1]
                if value in response.text:
                    issues.append(f"Reflected parameter '{value}' in response")
        return issues

    def check_sqli(self, response):
        """Check for SQL injection error patterns."""
        issues = []
        error_patterns = [
            r"mysql_fetch_array",
            r"syntax error.*SQL",
            r"unclosed quotation mark",
            r"sql server.*error"
        ]
        for pattern in error_patterns:
            if re.search(pattern, response.text, re.IGNORECASE):
                issues.append(f"Potential SQLi error pattern: {pattern}")
        return issues

    def check_open_redirect(self, url, response):
        """Check for open redirect vulnerabilities."""
        issues = []
        params = urlparse(url).query
        if params and 'redirect' in params.lower():
            redirect_url = params.split('redirect=')[-1].split('&')[0]
            try:
                resp = requests.head(redirect_url, allow_redirects=True, timeout=5)
                if resp.url != url:
                    issues.append(f"Open redirect to {resp.url}")
            except requests.RequestException:
                pass
        return issues

    def crawl(self, url, max_depth=2, depth=0):
        """Crawl the website to find URLs and forms."""
        if depth > max_depth or url in self.visited_urls:
            return
        self.visited_urls.add(url)
        logging.info(f"Crawling: {url}")

        try:
            response = requests.get(url, timeout=5, verify=False)
            if response.status_code != 200:
                return

            header_issues = self.check_security_headers(response)
            xss_issues = self.check_xss(url, response)
            sqli_issues = self.check_sqli(response)
            redirect_issues = self.check_open_redirect(url, response)

            if any([header_issues, xss_issues, sqli_issues, redirect_issues]):
                self.vulnerabilities.append({
                    "url": url,
                    "header_issues": header_issues,
                    "xss_issues": xss_issues,
                    "sqli_issues": sqli_issues,
                    "redirect_issues": redirect_issues
                })
                logging.info(f"Found issues at {url}")

            soup = BeautifulSoup(response.text, 'html.parser')
            for link in soup.find_all('a', href=True):
                href = link['href']
                full_url = urljoin(url, href)
                parsed = urlparse(full_url)
                if parsed.netloc == urlparse(self.base_url).netloc:
                    self.crawl(full_url, max_depth, depth + 1)

            for form in soup.find_all('form'):
                action = form.get('action', '')
                method = form.get('method', 'GET').upper()
                inputs = [inp.get('name') for inp in form.find_all('input') if inp.get('name')]
                self.forms.append({"url": url, "action": urljoin(url, action), "method": method, "inputs": inputs})

        except requests.RequestException as e:
            logging.error(f"Error crawling {url}: {e}")

    def intruder(self, url, param, payloads=None):
        """Fuzz a parameter with payloads."""
        if not payloads:
            payloads = ["<script>alert(1)</script>", "' OR 1=1 --", "http://evil.com"]
        results = []
        logging.info(f"Fuzzing {url} with param {param}")

        for payload in payloads:
            try:
                parsed = urlparse(url)
                params = dict([p.split('=') for p in parsed.query.split('&') if '=' in p])
                params[param] = payload
                new_query = '&'.join([f"{k}={v}" for k, v in params.items()])
                fuzzed_url = parsed._replace(query=new_query).geturl()
                response = requests.get(fuzzed_url, timeout=5, verify=False)
                issues = self.check_xss(fuzzed_url, response) + self.check_sqli(response)
                if issues:
                    results.append({"payload": payload, "issues": issues})
                    logging.info(f"Intruder found issues with payload {payload}")
            except requests.RequestException as e:
                logging.error(f"Error fuzzing {fuzzed_url}: {e}")
        return results

    def repeater(self, url, method="GET", headers=None, data=None, iterations=1):
        """Resend a request with modifications."""
        results = []
        logging.info(f"Repeating {method} {url}")
        headers = headers or {}
        data = data or {}

        for i in range(iterations):
            try:
                if method.upper() == "POST":
                    response = requests.post(url, headers=headers, data=data, timeout=5, verify=False)
                else:
                    response = requests.get(url, headers=headers, params=data, timeout=5, verify=False)
                results.append({
                    "iteration": i + 1,
                    "status": response.status_code,
                    "length": len(response.text),
                    "issues": self.check_xss(url, response) + self.check_sqli(response)
                })
                logging.info(f"Repeater iteration {i + 1}: {response.status_code}")
            except requests.RequestException as e:
                logging.error(f"Repeater error: {e}")
        return results

    def report(self):
        """Generate a Markdown report."""
        with open('apptest_report.md', 'w') as f:
            f.write("# APPTEST Report\n\n")
            f.write(f"Target: {self.base_url}\n")
            f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            f.write("## Vulnerabilities\n")
            for vuln in self.vulnerabilities:
                f.write(f"### URL: {vuln['url']}\n")
                if vuln['header_issues']:
                    f.write("- **Header Issues**:\n  - " + "\n  - ".join(vuln['header_issues']) + "\n")
                if vuln['xss_issues']:
                    f.write("- **XSS Issues**:\n  - " + "\n  - ".join(vuln['xss_issues']) + "\n")
                if vuln['sqli_issues']:
                    f.write("- **SQLi Issues**:\n  - " + "\n  - ".join(vuln['sqli_issues']) + "\n")
                if vuln['redirect_issues']:
                    f.write("- **Redirect Issues**:\n  - " + "\n  - ".join(vuln['redirect_issues']) + "\n")
                f.write("\n")

            f.write("## Forms Found\n")
            for form in self.forms:
                f.write(f"- **URL**: {form['url']}\n")
                f.write(f"  - Action: {form['action']}\n")
                f.write(f"  - Method: {form['method']}\n")
                f.write(f"  - Inputs: {', '.join(form['inputs'])}\n")
            f.write("\n")

        logging.info("Report generated: apptest_report.md")

# mitmproxy addon for intercepting traffic
class ProxyAddon:
    def request(self, flow: http.HTTPFlow):
        logging.info(f"Request: {flow.request.method} {flow.request.url}")
        flow.request.headers["User-Agent"] = "APPTEST/1.0"

    def response(self, flow: http.HTTPFlow):
        logging.info(f"Response: {flow.response.status_code} {flow.request.url}")

def start_proxy():
    """Start the mitmproxy server."""
    from mitmproxy.tools.main import mitmdump
    sys.argv = ['mitmdump', '-s', __file__]
    mitmdump()

def main():
    if len(sys.argv) < 2:
        print("Usage: python apptest.py <target_url> [--intruder <param>] [--repeater]")
        sys.exit(1)

    target_url = sys.argv[1]
    if not target_url.startswith("http"):
        target_url = "https://" + target_url

    apptest = APPTEST()
    apptest.base_url = target_url

    proxy_thread = threading.Thread(target=start_proxy)
    proxy_thread.daemon = True
    proxy_thread.start()

    print(f"Starting proxy on http://localhost:8080. Configure browser to use it.")
    print(f"Scanning {target_url}...")

    apptest.crawl(target_url)

    if "--intruder" in sys.argv:
        param_idx = sys.argv.index("--intruder") + 1
        if param_idx < len(sys.argv):
            param = sys.argv[param_idx]
            print(f"Running Intruder on {target_url} with param {param}")
            results = apptest.intruder(target_url, param)
            with open('apptest_report.md', 'a') as f:
                f.write("## Intruder Results\n")
                for res in results:
                    f.write(f"- Payload: {res['payload']}\n  - Issues: {', '.join(res['issues'])}\n")

    if "--repeater" in sys.argv:
        print(f"Running Repeater on {target_url}")
        results = apptest.repeater(target_url, iterations=2)
        with open('apptest_report.md', 'a') as f:
            f.write("## Repeater Results\n")
            for res in results:
                f.write(f"- Iteration {res['iteration']}: Status {res['status']}, Length {res['length']}\n")
                if res['issues']:
                    f.write(f"  - Issues: {', '.join(res['issues'])}\n")

    apptest.report()
    print("Done. Check apptest_report.md and apptest.log.")

# Register mitmproxy addon
addons = [ProxyAddon()]

if __name__ == "__main__":
    main()
