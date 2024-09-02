from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import boto3
import json
import logging
import os
import random
import requests

from dotenv import load_dotenv
load_dotenv()  # take environment variables from .env.

class Unifi:
    """
    Connects to Unifi Controller at the base_url, logs in, and fetches some data.

    Arguments
    =========
    unifi_api_base_url: str, the URL of your Unifi-APIBrowser instance, without the scheme in
              front (e.g. www.myapibrowserurl.com NOT https://www.myapibrowserurl.com)
    unifi_api_user
    unifi_api_password
    TODO: Docstring

    Usage
    =====
    u = Unifi(
        unifi_api_base_url,
        unifi_api_user,
        unifi_api_password,
    u.login()
    ... do whatever fetching and scraping you like
    u.fetch_collection('stat_5minutes_site')


    """

    URL_PATHS = {
        "login": "/login.php",
        "fetch_collection": "/ajax/fetch_collection.php",
    }

    def __init__(
        self,
        unifi_api_base_url,
        unifi_api_user,
        unifi_api_password,
    ):
        self.BASE_URL = "http://" + unifi_api_base_url
        self.HEADERS = {}
        self.PATH_TO_PAYLOADS_FILE = (
            Path(__file__).parent / "data/list_devices.json"
            # Path(__file__).parent / "data/collection_payloads.json"
        )
        self.UNIFI_LOGIN = (unifi_api_user, unifi_api_password)
        self.PAYLOADS = load_collection_payloads(self.PATH_TO_PAYLOADS_FILE)
        self.CURRENT_SCRAPE_START_TIME = datetime.now(tz=timezone.utc)
        self.CURRENT_SCRAPE_ID = (
            str(self.CURRENT_SCRAPE_START_TIME.timestamp())
            + "-"
            + str(random.randint(0, 10))
        )

    def login(self):
        self.session = self.login_unifi_api(*self.UNIFI_LOGIN)
        # self.boto3_client = self.login_boto3(self.BOTO3_CONFIG)

    def login_unifi_api(self, user, password):
        """
        Logs you in and prepares the site. NOTE: This fn assumes you only have ONE
        controller on you site, and automatically goes to controller #1.

        Arguments
        =========
        user: str, the username you use to log into APIBrowser
        password: str, the password for that user

        Returnsp
        =======
        None. Just makes it so the requests session attached to this object is logged in
        and ready to fetch data.

        """
        logging.info(
            "Doing log_in with user "
            + str(user)
        )

        # sw to 'user_name', not 'username'
        login_payload = {"user_name": user, "password": password}
        s = requests.Session()
        s.headers.update(self.HEADERS)
        login_response = s.post(
            self.BASE_URL + self.URL_PATHS["login"], data=login_payload 
        )
        # check for bad auth
        if ("user name and password do not match, please try again" in login_response.text):
            raise Exception("Login Failed!")
        try:
            login_response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            self.handle_bad_response(e)

        # Auth is handled by PHP setting the PHPSESSID on our session.
        # We don't need to do either of the below I don't think, but not deleting them yet.
        # https://stackoverflow.com/questions/41350762/python-requests-logging-into-website-using-post-and-cookies
        # s.cookies.set('PHPSESSID', requests.utils.dict_from_cookiejar(s.cookies)['PHPSESSID'])
        # self.HEADERS['Cookie'] = 'PHPSESSID=' + requests.utils.dict_from_cookiejar(s.cookies)['PHPSESSID']
        # self.session = s            

        logging.info("Logged in successfully")
        return s

    def handle_bad_response(self, response):
        logging.error("Bad response - code=" + str(response.status_code))
        logging.error(response.text)

    def fetch_collection(self, collection_name):
        payload = self.PAYLOADS.get(collection_name)
        if not payload:
            raise Exception("Passed collection not implemented.")
        
        # set headers 
        cookies = self.session.cookies
        php_sessid = cookies.get_dict()['PHPSESSID']
        print(php_sessid)

        r = self.session.post(
            self.BASE_URL + "/ajax/fetch_collection.php",
            headers=self.HEADERS,
            data=payload,
        )
        return r.json().get("data")
    
def load_collection_payloads(path_to_collection_json):
    p = Path()
    with path_to_collection_json.open() as f:
        data = json.load(f)
    payloads = data["payloads"]
    addl_keys = data["required_additional_payload_keys"]
    # We need to add back in the required keys that are
    # needed to complete the payloads
    for key in payloads.keys():
        payloads[key].update(addl_keys)
    return payloads


def do_full_scrape():
    logging.basicConfig(filename="tmp.log", level=logging.INFO)
    UNIFI_API_BASE_URL = os.getenv("UNIFI_API_BASE_URL")
    UNIFI_API_USER = os.getenv("UNIFI_API_USERNAME")
    UNIFI_API_PASSWORD = os.getenv("UNIFI_API_PASSWORD")
    u = Unifi(
        UNIFI_API_BASE_URL,
        UNIFI_API_USER,
        UNIFI_API_PASSWORD,
    )
    u.login()
    all_collections = u.PAYLOADS.keys()
    for collection in all_collections:
        logging.info("Scraping and uploading " + collection)
        u.fetch_and_upload_collection(collection)
    logging.info("Success! Check your object storage for the results.")

def get_aps():
    logging.basicConfig(level=logging.INFO, handlers=[
        logging.FileHandler("tmp.log"),
        logging.StreamHandler()
    ])
    logging.info("grabbing APs...")

    UNIFI_API_BASE_URL = os.getenv("UNIFI_API_BASE_URL")
    UNIFI_API_USER = os.getenv("UNIFI_API_USER")
    UNIFI_API_PASSWORD = os.getenv("UNIFI_API_PASSWORD")
    
    u = Unifi(
        UNIFI_API_BASE_URL,
        UNIFI_API_USER,
        UNIFI_API_PASSWORD,
    )

    u.login()

    logging.info("grabbing devices...")
    all_collections = u.PAYLOADS.keys()
    for collection_name in all_collections:
        print(collection_name)
        collection = u.fetch_collection(collection_name)
        print(collection)

    logging.info("done")

