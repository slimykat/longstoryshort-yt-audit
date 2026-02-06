## import method:
## from sock_puppet import SockPuppet
### check the main function for example usage

import time
import os
import logging

from pathlib import Path

# for selenium
from selenium import webdriver

# import undetected_chromedriver as webdriver #optimized port of selenium
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (
    StaleElementReferenceException,
    NoSuchElementException,
    TimeoutException,
)


VIDEO_URL_PREFIX_LONG = "https://www.youtube.com/watch?v="
VIDEO_URL_PREFIX_SHORT = "https://www.youtube.com/shorts/"


class SockPuppet:
    def __init__(
        self,
        adblock: bool|str = False,
        incognito: bool = False,
        headless: bool = True,
        custom_argument: list[str] = None,
        verbose: int = logging.INFO,
        err_attempts: int = 5,
    ):

        logging.basicConfig(filename="SockPuppet.log", level=verbose)
        driver_option = webdriver.ChromeOptions()
        # set up adblocker
        if adblock:
            driver_option.add_extension(
                os.path.join(
                    os.path.dirname(__file__),
                    adblock,
                )
            )

        # set up options for the chrome driver
        if incognito:
            driver_option.add_argument("--incognito")
        if headless:
            driver_option.add_argument("--headless")

        # disable this to avoid being treated as un-secure browser
        driver_option.add_argument("--disable-blink-features=AutomationControlled")
        driver_option.add_argument("--disable-gpu")

        if custom_argument:
            for arg in custom_argument:
                driver_option.add_argument(arg)

        # flags for the driver
        self.initialized = False
        self.driver_option = driver_option
        self.verbose = verbose
        self.adblock = adblock
        # if adblock is enabled, we will clean up the tabs after training

        self.driver = None  # the driver itself, will be initialized later
        self.err_attempts = err_attempts  # number of attempts when the driver encounters errors, default to 5

        # flags for the puppet
        self.seed_ids = []
        self.path = []
        self.sidebars = []
        self.preloads = []
        self.restricted = []
        self.max_duration = None
        self.mode = None

        # account information
        self.logged_in = False
        self.account = ["", ""]  # username and password

    def InitDriver(self, mode: str, max_duration: int | float = 10) -> bool:
        assert isinstance(
            max_duration, (int, float)
        ), "max_duration must be an int or float"
        assert max_duration > 0, "max_duration must be greater than 0"
        assert mode in ["long", "short"], "mode must be either 'long' or 'short'"
        assert (
            not self.initialized
        ), "Driver is already initialized, please call CleanUp() first"
        self.max_duration = max_duration
        self.mode = mode
        # storage for results
        self.seed_ids = []
        self.path = []
        self.sidebars = []
        self.preloads = []
        self.restricted = []
        self.driver = webdriver.Chrome(options=self.driver_option)
        # initialize the driver
        for attempt in range(self.err_attempts):
            try:
                WebDriverWait(self.driver, 10).until(EC.number_of_windows_to_be(2))
                break
            except TimeoutException:
                logging.error(
                    "Failed to initialize... try again %d/%d",
                    attempt + 1,
                    self.err_attempts,
                )
        else:
            logging.error(
                "Failed to initialize the driver, please check your internet connection and try again"
            )
            return True

        logging.info("New driver is initialized")

        # clean tabs if ad blocker is enabled
        if not self.adblock:
            return False  # return without error

        # create a new tab
        self.driver.execute_script("""window.open("");""")
        for attempt in range(self.err_attempts):
            try:
                WebDriverWait(self.driver, 10).until(EC.number_of_windows_to_be(3))
                break
            except TimeoutException:
                logging.error(
                    "Failed to create new tab... try again %d/%d",
                    attempt + 1,
                    self.err_attempts,
                )

        else:
            logging.error(
                "Failed to create new tab, please check your internet connection and try again"
            )
            return True
        logging.info("New tab is created")

        # switch to the old tabs and close them
        while len(self.driver.window_handles) > 1:
            self.driver.switch_to.window(self.driver.window_handles[0])
            self.driver.close()
            time.sleep(1)
        self.driver.switch_to.window(self.driver.window_handles[-1])
        time.sleep(1)
        logging.info("Started")
        self.initialized = True
        return False

    def LogIn(self, username: str, password: str) -> bool:
        logging.debug("Logging in as %s", username)
        assert (
            self.initialized
        ), "Driver is not initialized, please call InitDriver() first"
        assert isinstance(username, str), "username and password must be strings"
        assert isinstance(password, str), "username and password must be strings"
        assert len(username) > 0, "username and password must not be empty"
        assert len(password) > 0, "username and password must not be empty"
        self.account = [username, password]
        try:
            self.driver.get("https://www.youtube.com/")

            # use WebDriverWait to wait for the element to be presence or clickable

            # find the login button
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//a[@aria-label="Sign in"]'))
            ).click()

            # username
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//input[@id="identifierId"]')
                )
            ).send_keys(username)
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//div[@id="identifierNext"]'))
            ).click()

            # password
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//input[@name="Passwd"]'))
            ).send_keys(password)
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//div[@id="passwordNext"]'))
            ).click()

            # wait until YouTube title appears
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//a[@title="YouTube Home"]'))
            )
            logging.info("Login successful")
            time.sleep(1)
            self.logged_in = True
            return True
        except Exception as e:
            logging.error("Login failed")
            logging.error(e)
            return False

    def CleanUp(self, kill=True):
        assert (
            self.initialized
        ), "Driver is not initialized, please call InitDriver() first"

        try:
            while len(self.driver.window_handles) > 1:
                self.driver.switch_to.window(self.driver.window_handles[-1])
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
        except:
            logging.error("Failed to close extra tabs during cleanup")
        # delete all activities, this will also log out the account
        # if self.logged_in:
        #     self.driver.get("https://myactivity.google.com/myactivity?hl=en")
        #     time.sleep(1)
        #     try:

        #         WebDriverWait(self.driver, 5).until(
        #             EC.element_to_be_clickable(
        #                 (By.XPATH, '//button[@aria-label="Delete"]')
        #             )
        #         ).click()

        #         WebDriverWait(self.driver, 5).until(
        #             EC.element_to_be_clickable(
        #                 (
        #                     By.XPATH,
        #                     '//li[@role="menuitem" and .//*[text()="All time"]] ',
        #                 )
        #             )
        #         ).click()

        #         try:
        #             WebDriverWait(self.driver, 5).until(
        #                 EC.element_to_be_clickable(
        #                     (By.XPATH, '//button[.//*[text()="Next"]] ')
        #                 )
        #             ).click()
        #         except TimeoutException:
        #             # expected to not show up if no ads activity
        #             pass
        #         WebDriverWait(self.driver, 5).until(
        #             EC.element_to_be_clickable(
        #                 (
        #                     By.XPATH,
        #                     '//button[not(@aria-label="Delete") and .//*[text()="Delete"]]',
        #                 )
        #             )
        #         ).click()

        #         WebDriverWait(self.driver, 5).until(
        #             EC.element_to_be_clickable(
        #                 (By.XPATH, '//button[.//*[text()="Got it"]] ')
        #             )
        #         ).click()
        #         self.driver.get("https://www.youtube.com/")
        #         self.driver.delete_all_cookies()
        #         logging.info("Clean up done")
        #     except Exception as e:
        #         logging.error(
        #             "Failed to delete activities, could be the account is not logged in or there is not activity to delete"
        #         )
        #         logging.error(e)
        #         return
        try:
            if not kill:
                # if not logged in, clean up cookies and browser history
                self.driver.delete_all_cookies()
                self.driver.get("chrome://settings/clearBrowserData")
                time.sleep(1)
                try:
                    dom = self.driver.find_element(By.XPATH, ".//settings-ui")
                    shadow = self.driver.execute_script(
                        "return arguments[0].shadowRoot", dom
                    )
                    dom2 = shadow.find_element(By.ID, "main")
                    shadow2 = self.driver.execute_script(
                        "return arguments[0].shadowRoot", dom2
                    )
                    dom3 = shadow2.find_element(By.CSS_SELECTOR, "settings-basic-page")
                    shadow3 = self.driver.execute_script(
                        "return arguments[0].shadowRoot", dom3
                    )

                    dom4 = shadow3.find_element(By.ID, "basicPage").find_elements(
                        By.CSS_SELECTOR, "settings-section"
                    )[4]
                    # SSSShadow = self.driver.execute_script('return arguments[0].shadowRoot', DOM4)
                    # print(DOM4.get_attribute("page-title"))
                    assert dom4.get_attribute("page-title") == "Privacy and security"
                    dom5 = dom4.find_element(By.CSS_SELECTOR, "settings-privacy-page")
                    shadow5 = self.driver.execute_script(
                        "return arguments[0].shadowRoot", dom5
                    )
                    dom6 = shadow5.find_element(
                        By.CSS_SELECTOR, "settings-clear-browsing-data-dialog"
                    )
                    shadow6 = self.driver.execute_script(
                        "return arguments[0].shadowRoot", dom6
                    )
                    dom7 = shadow6.find_element(By.ID, "clearBrowsingDataDialog")

                    dom7.find_element(By.ID, "clearButton").click()

                except:
                    logging.error("Failed to clean up browser history")
                    return
                self.logged_in = False
                self.account = ["", ""]

        except:
            logging.error("Failed to clean up the driver")

        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
        self.driver = None        
        self.initialized = False

        logging.info("Puppet is cleaned up")
        return

    def __del__(self):
        if self.initialized:
            self.CleanUp()

    def __exit__(self, exc_type, exc_value, traceback):
        if self.initialized:
            self.CleanUp()

    def Train(self, seed_ids: list[str]) -> bool:
        # seed_ids: list of video ids to start with
        assert (
            self.initialized
        ), "Driver is not initialized, please call InitDriver() first"
        assert isinstance(seed_ids, list), "seed_ids must be a list"
        assert all(
            isinstance(vidID, str) for vidID in seed_ids
        ), "seed_ids must be a list of strings"
        assert len(seed_ids) > 0, "seed_ids must not be empty"

        self.seed_ids = seed_ids

        logging.info("Start Training %d videos in %s mode", len(seed_ids), self.mode)

        # watch the seed videos
        for vid in seed_ids:
            if self.watch(vid):
                logging.error(
                    "Train error... Skip the seed %s in %s mode with %d training videos",
                    seed_ids[-1],
                    self.mode,
                    len(self.seed_ids) - 1,
                )
                return True
        logging.info("Training done")
        return False

    def watch(
        self, video_id: str, mode: str = None, max_duration: int | float = None
    ) -> bool:
        # video_id: the id of the video to watch
        assert (
            self.initialized
        ), "Driver is not initialized, please call InitDriver() first"
        if mode is None:
            mode = self.mode
        if max_duration is None:
            max_duration = self.max_duration
        assert isinstance(video_id, str), "video_id must be a string"
        assert mode in ["long", "short"], "mode must be either 'long' or 'short'"
        assert isinstance(max_duration, int) or isinstance(
            max_duration, float
        ), "maxDuration must be an int or float"
        assert max_duration > 0, "maxDuration must be greater than 0"

        logging.debug("Watching %s video: %s", mode, video_id)
        if mode == "long":
            url = VIDEO_URL_PREFIX_LONG + video_id
        else:
            url = VIDEO_URL_PREFIX_SHORT + video_id
        self.driver.get(url)
        WebDriverWait(self.driver, 10).until(
            lambda driver: video_id in driver.current_url
        )
        logging.info("Opened %s video: %s", mode, video_id)
        # wait until the video is playing
        for i in range(self.err_attempts):
            try:
                if mode == "long":
                    path = ".//video"
                else:
                    path = ".//ytd-reel-video-renderer[@is-active]//video"

                # wait until the video is playing
                WebDriverWait(self.driver, 10).until(
                    lambda driver: WebDriverWait(driver, 10)
                    .until(EC.presence_of_element_located((By.XPATH, path)))
                    .get_attribute("paused")
                    != "true"
                )
                vid = self.driver.find_element(By.XPATH, path)
                break
            except Exception as e:
                logging.error(
                    "Failed to get video element... try again %d/ %d",
                    i + 1,
                    self.err_attempts,
                )
                logging.error(e)
                # refresh the page
                self.driver.refresh()
                time.sleep(2)
        else:
            logging.error("Video %s is not playing", self.driver.current_url)
            return True

        # get the video length
        video_len = 180  # default to 3 minutes
        try:
            video_len = vid.get_attribute("duration")
            video_len = float(video_len)
            logging.info("video length: %d", video_len)
            if video_len in ("", None, 0):
                # error in getting video length
                video_len = 180  # default to 3 minutes
        except Exception as e:
            # error in getting video length
            logging.error("Failed to get video length... defaulting to 3 minutes")
            logging.error(e)
            video_len = 180  # default to 3 minutes

        if isinstance(max_duration, float):  # in percentage
            wait_time = int(video_len * max_duration)
        else:  # in seconds (int)
            wait_time = min(video_len, max_duration) - 1

        # watch the video
        logging.info("Watching %s video for %d seconds", mode, max(wait_time, 0))
        time.sleep(max(wait_time, 0))
        logging.info("Finished %s video: %s", mode, video_id)

    def GetSidebar(self) -> list[str]:
        # get the sidebar recommendations
        for i in range(self.err_attempts):
            try:
                rec_list = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located(
                        (By.XPATH, ".//ytd-watch-next-secondary-results-renderer")
                    )
                )
                links = [
                    thumbnail.get_attribute("href")
                    for thumbnail in rec_list.find_elements(
                        By.XPATH, ".//a[@id='thumbnail']"
                    )
                ]
                return links
            except StaleElementReferenceException:
                logging.error(
                    "Failed to get sidebar... try again %d/%d", i + 1, self.err_attempts
                )
                time.sleep(1)
            except Exception as e:
                logging.error(
                    "Critical Error when getting sidebar... try again %d/%d",
                    i + 1,
                    self.err_attempts,
                )
                logging.error(e)
                time.sleep(1)

    def GetPreloadRec(self) -> list[str]:
        # get the preload recommendations
        for i in range(self.err_attempts):
            try:
                rec_list = self.driver.find_elements(
                    By.XPATH,
                    ".//ytd-reel-video-renderer[not(@is-active)]//div[@id='player-container']",
                )
                styles = [div.get_attribute("style") for div in rec_list]

                batch = [
                    __prefix(style.split("vi/")[-1].split("/")[0]) for style in styles
                ]
                return batch
            except NoSuchElementException:
                logging.error(
                    "Failed to get preload recommendation... try again %d/%d",
                    i + 1,
                    self.err_attempts,
                )
                time.sleep(1)
            except Exception as e:
                logging.error(
                    "Critical Error when getting batch recommendation... try again %d/%d",
                    i + 1,
                    self.err_attempts,
                )
                logging.error(e)
                time.sleep(1)

    def Run(
        self, collect_video_num: int = 15, max_duration: int | float = None
    ) -> list:
        assert (
            self.initialized
        ), "Driver is not initialized, please call InitDriver() first"
        assert isinstance(collect_video_num, int), "collect_video_num must be an int"
        assert collect_video_num > 0, "collect_video_num must be greater than 0"
        if max_duration is None:
            max_duration = self.max_duration
        assert type(max_duration) in [int, float], "waitTime must be an int or float"
        assert max_duration >= 0, "waitTime must be greater than 0"

        count = collect_video_num
        logging.info(
            "Start running from %s for %d videos",
            self.driver.current_url,
            collect_video_num,
        )
        err_attempts = self.err_attempts
        while count > 0 and err_attempts > 0:
            current_url = self.driver.current_url

            # play next video
            try:
                if self.mode == "long":
                    # keyboard shortcut : shift+n
                    ActionChains(self.driver).key_down(Keys.SHIFT).send_keys(
                        "n"
                    ).key_up(Keys.SHIFT).perform()
                    # WebDriverWait(self.driver, 10).until(
                    #     EC.presence_of_element_located(
                    #         (By.XPATH, './/a[@class="ytp-next-button ytp-button"]')
                    #     )
                    # ).click()
                elif self.mode == "short":
                    # keyboard shortcut : down arrow
                    ActionChains(self.driver).send_keys(Keys.ARROW_DOWN).perform()
                    # WebDriverWait(self.driver, 10).until(
                    #     EC.element_to_be_clickable(
                    #         (By.XPATH, './/div[@id="navigation-button-down"]//button')
                    #     )
                    # ).click()
                else:
                    logging.error("Unknown mode %s", self.mode)
                    return -1
                logging.info("next button pressed")
            except Exception as e:
                logging.error("play next error, button didn't work in %s", self.mode)
                logging.error(e)
                return -1
            # wait until the url changes
            try:
                WebDriverWait(self.driver, 10).until(EC.url_changes(current_url))
            except Exception as e:
                # if the url does not change, the input might not be registered
                logging.error("URL not changed, try again")
                logging.error(e)
                err_attempts -= 1
                continue
            time.sleep(1)
            current_url = self.driver.current_url
            logging.info("Current video: %s", current_url)
            # check if the current video is age restricted
            try:
                if self.mode == "short":
                    error_handle = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located(
                            (
                                By.XPATH,
                                ".//ytd-reel-video-renderer[@is-active]//yt-playability-error-supported-renderers",
                            )
                        )
                    )
                    if error_handle.get_attribute("hidden") is None:
                        logging.info(
                            "Encountered restricted video %s", self.driver.current_url
                        )

                        # error handelr will show up if the vid is restricted
                        try:
                            reason = error_handle.find_element(
                                By.XPATH, ".//div[@id='container']"
                            ).text
                        except NoSuchElementException:
                            logging.error(
                                "Can't get the reason for age restriction at %s",
                                current_url,
                            )
                            reason = "unknown(error)"

                        # record the reason and url
                        self.restricted.append([current_url, reason])

                        # check if logged in is required
                        if "sign in" in reason.lower():
                            # end early
                            logging.error("Age Restricted video %s", current_url)
                            return -1
                        # try to watch the content anyway
                        WebDriverWait(error_handle, 10).until(
                            EC.element_to_be_clickable(
                                (By.XPATH, ".//button-view-model")
                            )
                        ).click()

                else:  # self.mode == "long"
                    error_handle = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located(
                            (
                                By.XPATH,
                                ".//div[@id='player']/yt-playability-error-supported-renderers",
                            )
                        )
                    )
                    if error_handle.get_attribute("hidden") is None:
                        logging.info(
                            "Encountered restricted video %s", self.driver.current_url
                        )
                        # error handelr will show up if the vid is restricted
                        try:
                            reason = (
                                WebDriverWait(self.driver, 10)
                                .until(
                                    EC.presence_of_element_located(
                                        (
                                            By.XPATH,
                                            './/yt-playability-error-supported-renderers//div[@id="info"]',
                                        )
                                    )
                                )
                                .text
                            )
                        except TimeoutException:
                            logging.error("Can't get the reason for age restriction")
                            reason = "unknown(error)"
                        self.restricted.append([current_url, reason])

                        # check if logged in is required
                        if "sign in" in reason.lower():
                            # end early
                            logging.error("Age Restricted video %s", current_url)
                            return -1
                        # try to watch the content anyway
                        WebDriverWait(error_handle, 10).until(
                            EC.element_to_be_clickable((By.XPATH, ".//button"))
                        ).click()

            except Exception as e:
                logging.error(
                    "ageRestriction detection failed ... mode: %s, seed_vid %s, training_seeks %s }",
                    self.mode,
                    self.seed_ids[-1],
                    str(self.seed_ids[:-1]),
                )
                logging.error(e)

            # example(age restricted): https://www.youtube.com/shorts/vkxf_OPsY_U
            # example(self harm warning): https://www.youtube.com/shorts/SplAV2NQZl4
            if self.mode == "short":
                try:
                    self.preloads.append(self.GetPreloadRec())
                except Exception as e:
                    logging.error(
                        "Failed to get preload at %s... done trying"
                        , self.driver.current_url
                    )
                    logging.error(e)
            elif self.mode == "long":
                try:
                    self.sidebars.append(self.GetSidebar())
                except Exception as e:
                    logging.error(
                        "Failed to get sidebar at %s... done trying"
                        , self.driver.current_url
                    )
                    logging.error(e)

            self.path.append(current_url)
            count -= 1
            video_len = 180  # default to 3 minutes
            if max_duration > 0:
                try:
                    if self.mode == "long":
                        path = ".//video"
                    else:
                        path = ".//ytd-reel-video-renderer[@is-active]//video"
                    vid = WebDriverWait(self.driver, 60).until(
                        EC.presence_of_element_located((By.XPATH, path))
                    )
                    video_len = vid.get_attribute("duration")
                    video_len = float(video_len)
                    logging.info("video length: %s", video_len)
                    if video_len in ["", None , 0, float("nan")]:
                        # error in getting video length
                        video_len = 180  # default to 3 minutes
                except Exception as e:
                    # error in getting video length
                    video_len = 180  # default to 3 minutes

                if isinstance(max_duration, float):  # in percentage
                    wait_time = int(video_len * max_duration)
                else:  # in seconds (int)
                    wait_time = min(video_len, max_duration) - 1
            else:
                wait_time = 0
            # watch the video
            logging.info("waiting for %d seconds" , wait_time)
            time.sleep(max(wait_time, 0))

        if err_attempts < 0:
            logging.error(
                "Run error... too many refresh in %s ... ending early", self.mode
            )

    def Report(self):
        # return every result without writing to a file
        return {
            "training_ids": self.seed_ids[:-1],
            "seed_id": self.seed_ids[-1],
            "player_mode": self.mode,
            "maxduration": self.max_duration,
            "recommendations": {
                "autoplay_rec": self.path,
                "sidebar_rec": self.sidebars,
                "preload_rec": self.preloads,
                "restricted": self.restricted,
            },
        }

    def HelloWorld(self):
        print("Testing")
        self.driver.get("https://www.youtube.com/")
        time.sleep(10)
        print("Test done")


def __prefix(s):
    return VIDEO_URL_PREFIX_SHORT * (s != "") + s
