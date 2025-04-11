# APPTEST

APPTEST is a Burp-inspired web security testing tool for ethical bug bounty hunting. It includes an intercepting proxy, crawler, scanner, intruder, repeater, and report generator.

## Features
- **Intercepting Proxy**: Capture and modify HTTP/HTTPS traffic.
- **Crawler**: Map URLs and forms.
- **Scanner**: Detect XSS, SQLi, open redirects, and header issues.
- **Intruder**: Fuzz parameters.
- **Repeater**: Resend requests.
- **Reports**: Generate Markdown reports.

## Installation
1. Install Python 3 and dependencies:
   ```bash
   pip install mitmproxy requests beautifulsoup4 urllib3
