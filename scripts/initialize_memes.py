import os
import subprocess
from time import sleep
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import urllib3
import ssl

# Disable SSL verification warnings and context
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Setup directories
script_dir = os.path.dirname(os.path.abspath(__file__))
download_dir = os.path.join(script_dir, "static", "memes")
os.makedirs(download_dir, exist_ok=True)

# Create a requests session with retry strategy and better headers
session = requests.Session()
retry_strategy = Retry(
    total=3,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS"]
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)

# Set comprehensive headers to avoid blocking
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'image/webp,image/apng,image/jpeg,image/png,image/*,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,de;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Referer': 'https://bitcoinmemes.info/',
    'Origin': 'https://bitcoinmemes.info',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'image',
    'Sec-Fetch-Mode': 'no-cors',
    'Sec-Fetch-Site': 'same-origin',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache'
})

base_url = "https://bitcoinmemes.info/assets/images/"
image_number = 1
consecutive_failures = 0
max_failures = 10

def is_valid_image(file_path):
    """Check if the downloaded file is actually an image"""
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return False
    
    # Read first few bytes to check for image headers
    with open(file_path, 'rb') as f:
        header = f.read(10)
        
    # Check for common image file signatures
    if header.startswith(b'\xff\xd8\xff'):  # JPEG
        return True
    import os
import subprocess
from time import sleep
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3
import ssl

# Disable SSL verification warnings and context
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Setup directories
script_dir = os.path.dirname(os.path.abspath(__file__))
download_dir = os.path.join(script_dir, "static", "memes")
os.makedirs(download_dir, exist_ok=True)

base_url = "https://bitcoinmemes.info/assets/images/"
image_number = 1
consecutive_failures = 0
max_failures = 10

def is_valid_image(file_path):
    """Check if the downloaded file is actually an image"""
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return False
    
    # Read first few bytes to check for image headers
    with open(file_path, 'rb') as f:
        header = f.read(10)
        
    # Check for common image file signatures
    if header.startswith(b'\xff\xd8\xff'):  # JPEG
        return True
    elif header.startswith(b'\x89PNG\r\n\x1a\n'):  # PNG
        return True
    elif header.startswith(b'GIF87a') or header.startswith(b'GIF89a'):  # GIF
        return True
    elif header.startswith(b'RIFF') and b'WEBP' in header:  # WebP
        return True
    elif header.startswith(b'<!DOCTYPE') or header.startswith(b'<html'):  # HTML (blocked page)
        return False
    
    return False

def show_manual_download_instructions():
    print("\nManual Download Instructions:")
    print("1. Visit https://bitcoinmemes.info/ in your browser.")
    print("2. Download the images manually and place them in the folder:")
    print(f"   {os.path.join(script_dir, 'static', 'memes')}")

# Check if we're being blocked
print("Testing connection to bitcoinmemes.info...")
try:
    test_response = requests.get("https://bitcoinmemes.info/assets/images/1.jpeg", timeout=10, verify=False)
    if 'FortiClient' in test_response.text or 'blockiert' in test_response.text or test_response.headers.get('content-type', '').startswith('text/html'):
        print("❌ FortiClient firewall is blocking access to bitcoinmemes.info")
        show_manual_download_instructions()
        exit(1)
    elif test_response.status_code == 404:
        print("✓ Connection successful (received 404, which means we can reach the server)")
    elif test_response.status_code == 200:
        print("✓ Connection successful and image found!")
    else:
        print(f"Connection test returned status code: {test_response.status_code}")
except Exception as e:
    print(f"❌ Connection failed: {e}")
    show_manual_download_instructions()
    exit(1)

# Create session with proper headers
session = requests.Session()
retry_strategy = Retry(
    total=3,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS"]
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)

session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'image/webp,image/apng,image/jpeg,image/png,image/*,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,de;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Referer': 'https://bitcoinmemes.info/',
    'Connection': 'keep-alive',
    'Cache-Control': 'no-cache'
})

print("Starting download process...")

while consecutive_failures < max_failures:
    found = False
    for ext in ['jpeg', 'jpg', 'png']:
        url = f"{base_url}{image_number}.{ext}"
        output_path = os.path.join(download_dir, f"{image_number}.{ext}")

        if os.path.exists(output_path) and is_valid_image(output_path):
            print(f"✓ Already exists: {image_number}.{ext}")
            found = True
            consecutive_failures = 0
            break

        try:
            print(f"Downloading: {image_number}.{ext}", end="")
            response = session.get(url, timeout=30, verify=False, stream=True)
            
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '').lower()
                if 'text/html' in content_type or 'FortiClient' in response.text:
                    print(f" - ❌ Blocked by firewall")
                    continue
                
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                if is_valid_image(output_path):
                    print(f" - ✓ Success")
                    found = True
                    consecutive_failures = 0
                    break
                else:
                    print(f" - ❌ Invalid content")
                    if os.path.exists(output_path):
                        os.remove(output_path)
            elif response.status_code == 404:
                print(f" - Not found (404)")
                continue
            else:
                print(f" - HTTP {response.status_code}")
                
        except Exception as e:
            print(f" - ❌ Error: {e}")

    if not found:
        consecutive_failures += 1
        print(f"No image found for number {image_number} (failures: {consecutive_failures})")

    image_number += 1
    sleep(0.3)  # Be respectful to the server

print(f"\nDownload completed!")
print(f"Successfully downloaded images up to number {image_number - consecutive_failures - 1}")
if consecutive_failures >= max_failures:
    print("Stopped due to too many consecutive failures.")

# Count successfully downloaded files
downloaded_files = [f for f in os.listdir(download_dir) if f.endswith(('.jpeg', '.jpg', '.png')) and is_valid_image(os.path.join(download_dir, f))]
print(f"Total valid images in folder: {len(downloaded_files)}")

def show_manual_download_instructions():
    print("\nManual Download Instructions:")
    print("1. Visit https://bitcoinmemes.info/assets/images/ in your browser.")
    print("2. Download the images manually and place them in the folder:")
    print(f"   {os.path.join(script_dir, 'static', 'memes')}")
    print("3. Make sure the images are named as <number>.<ext> (e.g., 1.jpeg, 2.png, ...)")
    print("4. Restart this script after downloading.")

if len(downloaded_files) == 0:
    show_manual_download_instructions()
    
    exit(1)

while consecutive_failures < max_failures:
    found = False
    for ext in ['jpeg', 'jpg', 'png']:
        url = f"{base_url}{image_number}.{ext}"
        output_path = os.path.join(download_dir, f"{image_number}.{ext}")

        if os.path.exists(output_path) and is_valid_image(output_path):
            print(f"Already exists: {output_path}")
            found = True
            consecutive_failures = 0
            break

        print(f"Attempting to download: {url}")
        
        try:
            # Try with requests first (better header handling)
            response = session.get(url, timeout=30, verify=False, stream=True)
            
            if response.status_code == 200:
                # Check if we got HTML instead of an image (blocked page)
                content_type = response.headers.get('content-type', '').lower()
                if 'text/html' in content_type:
                    print(f"Blocked: Received HTML instead of image for {url}")
                    continue
                
                # Save the file
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # Verify it's actually an image
                if is_valid_image(output_path):
                    print(f"✓ Downloaded: {url}")
                    found = True
                    consecutive_failures = 0
                    break
                else:
                    print(f"✗ Invalid image content for {url}")
                    if os.path.exists(output_path):
                        os.remove(output_path)
            else:
                print(f"HTTP {response.status_code}: {url}")
                
        except Exception as e:
            print(f"Error downloading {url}: {e}")
            
            # Fallback to curl if requests fails
            try:
                print(f"Trying curl fallback for: {url}")
                curl_cmd = [
                    "curl", "-k", "-L", "--max-time", "30",
                    "-H", "Referer: https://bitcoinmemes.info/",
                    "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "-H", "Accept: image/webp,image/apng,image/jpeg,image/png,image/*,*/*;q=0.8",
                    "-H", "Accept-Language: en-US,en;q=0.9",
                    "-H", "Connection: keep-alive",
                    "-H", "Cache-Control: no-cache",
                    url,
                    "-o", output_path
                ]

                result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=45)

                if result.returncode == 0 and is_valid_image(output_path):
                    print(f"✓ Downloaded via curl: {url}")
                    found = True
                    consecutive_failures = 0
                    break
                else:
                    print(f"✗ Curl failed or invalid content: {url}")
                    if os.path.exists(output_path):
                        os.remove(output_path)
                        
            except Exception as curl_error:
                print(f"Curl also failed for {url}: {curl_error}")

    if not found:
        print(f"No valid image found for {image_number}")
        consecutive_failures += 1

    image_number += 1
    sleep(0.5)  # Increased delay to be more respectful

print(f"Download completed. Found images up to number {image_number - consecutive_failures - 1}")