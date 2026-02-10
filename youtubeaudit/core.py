"""Core YouTube audit automation using Selenium WebDriver."""

import time
import os
import logging
from typing import Literal, Callable, Optional
from pathlib import Path

from selenium import webdriver
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


def _prefix_short_url(video_id: str) -> str:
    """Add URL prefix to video ID for shorts."""
    return VIDEO_URL_PREFIX_SHORT + video_id if video_id else ""


class YouTubeAuditor:
    """Automated YouTube recommendation audit tool.

    This class controls a Chrome browser to systematically audit YouTube's
    recommendation algorithm by watching videos and collecting recommendations.

    Parameters
    ----------
    adblock : bool | str, optional
        Enable ad blocker. If True, uses default extension. If string, path to extension.
    incognito : bool, optional
        Run browser in incognito mode
    headless : bool, optional
        Run browser in headless mode (no GUI)
    custom_argument : list[str], optional
        Additional Chrome command-line arguments
    verbose : int, optional
        Logging level (default: logging.INFO)
    err_attempts : int, optional
        Number of retry attempts for failed operations (default: 5)
    on_progress : Callable, optional
        Callback function for progress updates. Called with event dict.

    Attributes
    ----------
    driver : webdriver.Chrome
        Selenium WebDriver instance
    initialized : bool
        Whether driver has been initialized
    mode : Literal["long", "short"]
        Current video player mode
    seed_ids : list[str]
        Training video IDs
    path : list[str]
        Autoplay recommendation path (URLs)
    sidebars : list[list[str]]
        Sidebar recommendations for each video (long mode)
    preloads : list[list[str]]
        Preloaded recommendations for each video (short mode)
    restricted : list[list[str, str]]
        Restricted videos encountered (URL, reason)
    """

    def __init__(
        self,
        adblock: bool | str = False,
        incognito: bool = False,
        headless: bool = True,
        custom_argument: list[str] = None,
        verbose: int = logging.INFO,
        err_attempts: int = 5,
        on_progress: Optional[Callable[[dict], None]] = None,
    ):
        logging.basicConfig(filename="YouTubeAuditor.log", level=verbose)

        driver_option = webdriver.ChromeOptions()

        # Set up adblocker
        if adblock:
            extension_path = adblock if isinstance(adblock, str) else os.path.join(
                os.path.dirname(__file__), "adblock_extension"
            )
            if os.path.exists(extension_path):
                driver_option.add_extension(extension_path)

        # Set up options for the chrome driver
        if incognito:
            driver_option.add_argument("--incognito")
        if headless:
            driver_option.add_argument("--headless")

        # Disable automation detection
        driver_option.add_argument("--disable-blink-features=AutomationControlled")
        driver_option.add_argument("--disable-gpu")

        if custom_argument:
            for arg in custom_argument:
                driver_option.add_argument(arg)

        # Driver flags
        self.initialized = False
        self.driver_option = driver_option
        self.verbose = verbose
        self.adblock = adblock
        self.err_attempts = err_attempts
        self.on_progress = on_progress or (lambda x: None)

        # Driver instance
        self.driver = None

        # Experiment state
        self.seed_ids = []
        self.path = []
        self.sidebars = []
        self.preloads = []
        self.restricted = []
        self.max_duration = None
        self.mode = None

        # Account information
        self.logged_in = False
        self.account = ["", ""]

    def _emit_progress(self, event_type: str, **data):
        """Emit progress event to callback.

        Parameters
        ----------
        event_type : str
            Type of event (e.g., "phase_changed", "video_progress", "error")
        **data
            Additional event data
        """
        event = {
            "event": event_type,
            "timestamp": time.time(),
            **data
        }
        self.on_progress(event)

    def InitDriver(self, mode: Literal["long", "short"], max_duration: int | float = 10) -> bool:
        """Initialize the Chrome WebDriver.

        Parameters
        ----------
        mode : Literal["long", "short"]
            Video player mode - "long" for regular videos, "short" for YouTube Shorts
        max_duration : int | float, optional
            Maximum time to watch each video. If int, time in seconds. If float, percentage of video length.

        Returns
        -------
        bool
            True if initialization failed, False if successful
        """
        assert isinstance(max_duration, (int, float)), "max_duration must be an int or float"
        assert max_duration > 0, "max_duration must be greater than 0"
        assert mode in ["long", "short"], "mode must be either 'long' or 'short'"
        assert not self.initialized, "Driver is already initialized, please call CleanUp() first"

        self.max_duration = max_duration
        self.mode = mode

        # Reset storage
        self.seed_ids = []
        self.path = []
        self.sidebars = []
        self.preloads = []
        self.restricted = []

        self._emit_progress("driver_init", mode=mode, max_duration=max_duration)

        self.driver = webdriver.Chrome(options=self.driver_option)

        # Wait for browser to initialize
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
            logging.error("Failed to initialize the driver")
            self._emit_progress("driver_init_failed", error="timeout")
            return True

        logging.info("New driver is initialized")

        # Clean tabs if ad blocker is enabled
        if not self.adblock:
            self.initialized = True
            return False

        # Create a new tab
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
            logging.error("Failed to create new tab")
            return True

        # Switch to the old tabs and close them
        while len(self.driver.window_handles) > 1:
            self.driver.switch_to.window(self.driver.window_handles[0])
            self.driver.close()
            time.sleep(1)
        self.driver.switch_to.window(self.driver.window_handles[-1])
        time.sleep(1)

        logging.info("Driver started")
        self.initialized = True
        self._emit_progress("driver_ready", mode=mode)
        return False

    def LogIn(self, username: str, password: str) -> bool:
        """Log in to YouTube with Google account.

        Parameters
        ----------
        username : str
            Google account username/email
        password : str
            Google account password

        Returns
        -------
        bool
            True if login successful, False otherwise
        """
        logging.debug("Logging in as %s", username)
        assert self.initialized, "Driver is not initialized, please call InitDriver() first"
        assert isinstance(username, str) and isinstance(password, str), "username and password must be strings"
        assert len(username) > 0 and len(password) > 0, "username and password must not be empty"

        self.account = [username, password]
        self._emit_progress("login_started", username=username)

        try:
            self.driver.get("https://www.youtube.com/")

            # Find the login button
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//a[@aria-label="Sign in"]'))
            ).click()

            # Username
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//input[@id="identifierId"]'))
            ).send_keys(username)
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//div[@id="identifierNext"]'))
            ).click()

            # Password
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//input[@name="Passwd"]'))
            ).send_keys(password)
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//div[@id="passwordNext"]'))
            ).click()

            # Wait until YouTube title appears
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//a[@title="YouTube Home"]'))
            )
            logging.info("Login successful")
            time.sleep(1)
            self.logged_in = True
            self._emit_progress("login_success", username=username)
            return True
        except Exception as e:
            logging.error("Login failed")
            logging.error(e)
            self._emit_progress("login_failed", error=str(e))
            return False

    def CleanUp(self, kill=True):
        """Clean up browser session and driver.

        Parameters
        ----------
        kill : bool, optional
            If True, quit the driver. If False, just clean cookies/history.
        """
        assert self.initialized, "Driver is not initialized"

        self._emit_progress("cleanup_started", kill=kill)

        try:
            while len(self.driver.window_handles) > 1:
                self.driver.switch_to.window(self.driver.window_handles[-1])
                self.driver.close()
                self.driver.switch_to.window(self.driver.window_handles[0])
        except:
            logging.error("Failed to close extra tabs during cleanup")

        try:
            if not kill:
                self.driver.delete_all_cookies()
                self.driver.get("chrome://settings/clearBrowserData")
                time.sleep(1)
                # Complex shadow DOM navigation to clear browser data
                # (Original implementation kept as-is)
                try:
                    dom = self.driver.find_element(By.XPATH, ".//settings-ui")
                    shadow = self.driver.execute_script("return arguments[0].shadowRoot", dom)
                    dom2 = shadow.find_element(By.ID, "main")
                    shadow2 = self.driver.execute_script("return arguments[0].shadowRoot", dom2)
                    dom3 = shadow2.find_element(By.CSS_SELECTOR, "settings-basic-page")
                    shadow3 = self.driver.execute_script("return arguments[0].shadowRoot", dom3)
                    dom4 = shadow3.find_element(By.ID, "basicPage").find_elements(
                        By.CSS_SELECTOR, "settings-section"
                    )[4]
                    assert dom4.get_attribute("page-title") == "Privacy and security"
                    dom5 = dom4.find_element(By.CSS_SELECTOR, "settings-privacy-page")
                    shadow5 = self.driver.execute_script("return arguments[0].shadowRoot", dom5)
                    dom6 = shadow5.find_element(By.CSS_SELECTOR, "settings-clear-browsing-data-dialog")
                    shadow6 = self.driver.execute_script("return arguments[0].shadowRoot", dom6)
                    dom7 = shadow6.find_element(By.ID, "clearBrowsingDataDialog")
                    dom7.find_element(By.ID, "clearButton").click()
                except:
                    logging.error("Failed to clean up browser history")

                self.logged_in = False
                self.account = ["", ""]
        except:
            logging.error("Failed to clean up the driver")

        if self.driver and kill:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

        self.initialized = False
        logging.info("Cleanup complete")
        self._emit_progress("cleanup_complete")

    def __del__(self):
        if self.initialized:
            self.CleanUp()

    def __exit__(self, exc_type, exc_value, traceback):
        if self.initialized:
            self.CleanUp()

    def Train(self, seed_ids: list[str]) -> bool:
        """Train the recommendation algorithm by watching seed videos.

        Parameters
        ----------
        seed_ids : list[str]
            List of video IDs to watch for training

        Returns
        -------
        bool
            True if training failed, False if successful
        """
        assert self.initialized, "Driver is not initialized, please call InitDriver() first"
        assert isinstance(seed_ids, list), "seed_ids must be a list"
        assert all(isinstance(vid, str) for vid in seed_ids), "seed_ids must be a list of strings"
        assert len(seed_ids) > 0, "seed_ids must not be empty"

        self.seed_ids = seed_ids
        total = len(seed_ids)

        logging.info("Start Training %d videos in %s mode", total, self.mode)
        self._emit_progress("training_started", total_videos=total, mode=self.mode)

        for idx, vid in enumerate(seed_ids):
            self._emit_progress("training_progress", current=idx + 1, total=total, video_id=vid)
            if self.watch(vid):
                logging.error("Train error... Skip the seed %s", vid)
                self._emit_progress("training_failed", video_id=vid)
                return True

        logging.info("Training done")
        self._emit_progress("training_complete", total_videos=total)
        return False

    def watch(
        self, video_id: str, mode: str = None, max_duration: int | float = None
    ) -> bool:
        """Watch a single video.

        Parameters
        ----------
        video_id : str
            YouTube video ID
        mode : str, optional
            Override mode (default: use self.mode)
        max_duration : int | float, optional
            Override max duration (default: use self.max_duration)

        Returns
        -------
        bool
            True if watch failed, False if successful
        """
        assert self.initialized, "Driver is not initialized"

        if mode is None:
            mode = self.mode
        if max_duration is None:
            max_duration = self.max_duration

        assert isinstance(video_id, str), "video_id must be a string"
        assert mode in ["long", "short"], "mode must be either 'long' or 'short'"
        assert isinstance(max_duration, (int, float)), "max_duration must be an int or float"
        assert max_duration > 0, "max_duration must be greater than 0"

        logging.debug("Watching %s video: %s", mode, video_id)
        self._emit_progress("watch_started", video_id=video_id, mode=mode)

        url = VIDEO_URL_PREFIX_LONG + video_id if mode == "long" else VIDEO_URL_PREFIX_SHORT + video_id
        self.driver.get(url)
        WebDriverWait(self.driver, 10).until(lambda driver: video_id in driver.current_url)
        logging.info("Opened %s video: %s", mode, video_id)

        # Wait until the video is playing
        for i in range(self.err_attempts):
            try:
                path = ".//video" if mode == "long" else ".//ytd-reel-video-renderer[@is-active]//video"

                WebDriverWait(self.driver, 10).until(
                    lambda driver: WebDriverWait(driver, 10)
                    .until(EC.presence_of_element_located((By.XPATH, path)))
                    .get_attribute("paused")
                    != "true"
                )
                vid = self.driver.find_element(By.XPATH, path)
                break
            except Exception as e:
                logging.error("Failed to get video element... try again %d/%d", i + 1, self.err_attempts)
                logging.error(e)
                self.driver.refresh()
                time.sleep(2)
        else:
            logging.error("Video %s is not playing", self.driver.current_url)
            self._emit_progress("watch_failed", video_id=video_id, error="video_not_playing")
            return True

        # Get the video length
        video_len = 180  # default to 3 minutes
        try:
            video_len = float(vid.get_attribute("duration") or 180)
            logging.info("video length: %d", video_len)
            if video_len == 0:
                video_len = 180
        except Exception as e:
            logging.error("Failed to get video length... defaulting to 3 minutes")
            logging.error(e)
            video_len = 180

        if isinstance(max_duration, float):  # percentage
            wait_time = int(video_len * max_duration)
        else:  # seconds
            wait_time = min(video_len, max_duration) - 1

        # Watch the video
        logging.info("Watching %s video for %d seconds", mode, max(wait_time, 0))
        self._emit_progress("watching", video_id=video_id, duration=video_len, wait_time=wait_time)
        time.sleep(max(wait_time, 0))
        logging.info("Finished %s video: %s", mode, video_id)
        self._emit_progress("watch_complete", video_id=video_id)

        return False

    def GetSidebar(self) -> list[str]:
        """Get sidebar recommendations (long-form videos only).

        Returns
        -------
        list[str]
            List of recommendation URLs
        """
        for i in range(self.err_attempts):
            try:
                rec_list = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, ".//ytd-watch-next-secondary-results-renderer"))
                )
                links = [
                    thumbnail.get_attribute("href")
                    for thumbnail in rec_list.find_elements(By.XPATH, ".//a[@id='thumbnail']")
                ]
                return links
            except StaleElementReferenceException:
                logging.error("Failed to get sidebar... try again %d/%d", i + 1, self.err_attempts)
                time.sleep(1)
            except Exception as e:
                logging.error("Critical Error when getting sidebar... try again %d/%d", i + 1, self.err_attempts)
                logging.error(e)
                time.sleep(1)
        return []

    def GetPreloadRec(self) -> list[str]:
        """Get preloaded recommendations (short-form videos only).

        Returns
        -------
        list[str]
            List of recommendation video IDs
        """
        for i in range(self.err_attempts):
            try:
                rec_list = self.driver.find_elements(
                    By.XPATH,
                    ".//ytd-reel-video-renderer[not(@is-active)]//div[@id='player-container']",
                )
                styles = [div.get_attribute("style") for div in rec_list]
                batch = [
                    _prefix_short_url(style.split("vi/")[-1].split("/")[0]) for style in styles
                ]
                return batch
            except NoSuchElementException:
                logging.error("Failed to get preload recommendation... try again %d/%d", i + 1, self.err_attempts)
                time.sleep(1)
            except Exception as e:
                logging.error("Critical Error when getting batch recommendation... try again %d/%d", i + 1, self.err_attempts)
                logging.error(e)
                time.sleep(1)
        return []

    def Run(self, collect_video_num: int = 15, max_duration: int | float = None) -> int:
        """Collect recommendations by following autoplay path.

        Parameters
        ----------
        collect_video_num : int, optional
            Number of videos to collect (default: 15)
        max_duration : int | float, optional
            Override max watch duration

        Returns
        -------
        int
            0 if successful, -1 if failed
        """
        assert self.initialized, "Driver is not initialized"
        assert isinstance(collect_video_num, int), "collect_video_num must be an int"
        assert collect_video_num > 0, "collect_video_num must be greater than 0"

        if max_duration is None:
            max_duration = self.max_duration
        assert type(max_duration) in [int, float], "max_duration must be an int or float"
        assert max_duration >= 0, "max_duration must be >= 0"

        count = collect_video_num
        logging.info("Start running from %s for %d videos", self.driver.current_url, collect_video_num)
        self._emit_progress("collection_started", total=collect_video_num, mode=self.mode)

        err_attempts = self.err_attempts
        while count > 0 and err_attempts > 0:
            current_idx = collect_video_num - count
            self._emit_progress("collection_progress", current=current_idx + 1, total=collect_video_num)

            current_url = self.driver.current_url

            # Play next video
            try:
                if self.mode == "long":
                    ActionChains(self.driver).key_down(Keys.SHIFT).send_keys("n").key_up(Keys.SHIFT).perform()
                elif self.mode == "short":
                    ActionChains(self.driver).send_keys(Keys.ARROW_DOWN).perform()
                else:
                    logging.error("Unknown mode %s", self.mode)
                    return -1
                logging.info("next button pressed")
            except Exception as e:
                logging.error("play next error, button didn't work in %s", self.mode)
                logging.error(e)
                self._emit_progress("collection_failed", error="next_button_failed")
                return -1

            # Wait until the URL changes
            try:
                WebDriverWait(self.driver, 10).until(EC.url_changes(current_url))
            except Exception as e:
                logging.error("URL not changed, try again")
                logging.error(e)
                err_attempts -= 1
                continue

            time.sleep(1)
            current_url = self.driver.current_url
            logging.info("Current video: %s", current_url)

            # Check if the current video is age restricted
            try:
                if self.mode == "short":
                    error_handle = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located(
                            (By.XPATH, ".//ytd-reel-video-renderer[@is-active]//yt-playability-error-supported-renderers")
                        )
                    )
                    if error_handle.get_attribute("hidden") is None:
                        logging.info("Encountered restricted video %s", current_url)
                        try:
                            reason = error_handle.find_element(By.XPATH, ".//div[@id='container']").text
                        except NoSuchElementException:
                            logging.error("Can't get the reason for age restriction at %s", current_url)
                            reason = "unknown(error)"

                        self.restricted.append([current_url, reason])
                        self._emit_progress("restricted_video", url=current_url, reason=reason)

                        if "sign in" in reason.lower():
                            logging.error("Age Restricted video %s", current_url)
                            return -1

                        WebDriverWait(error_handle, 10).until(
                            EC.element_to_be_clickable((By.XPATH, ".//button-view-model"))
                        ).click()

                else:  # long mode
                    error_handle = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located(
                            (By.XPATH, ".//div[@id='player']/yt-playability-error-supported-renderers")
                        )
                    )
                    if error_handle.get_attribute("hidden") is None:
                        logging.info("Encountered restricted video %s", current_url)
                        try:
                            reason = (
                                WebDriverWait(self.driver, 10)
                                .until(
                                    EC.presence_of_element_located(
                                        (By.XPATH, './/yt-playability-error-supported-renderers//div[@id="info"]')
                                    )
                                )
                                .text
                            )
                        except TimeoutException:
                            logging.error("Can't get the reason for age restriction")
                            reason = "unknown(error)"

                        self.restricted.append([current_url, reason])
                        self._emit_progress("restricted_video", url=current_url, reason=reason)

                        if "sign in" in reason.lower():
                            logging.error("Age Restricted video %s", current_url)
                            return -1

                        WebDriverWait(error_handle, 10).until(
                            EC.element_to_be_clickable((By.XPATH, ".//button"))
                        ).click()

            except Exception as e:
                logging.error("Age restriction detection failed")
                logging.error(e)

            # Collect recommendations
            if self.mode == "short":
                try:
                    preload = self.GetPreloadRec()
                    self.preloads.append(preload)
                except Exception as e:
                    logging.error("Failed to get preload at %s", current_url)
                    logging.error(e)
            elif self.mode == "long":
                try:
                    sidebar = self.GetSidebar()
                    self.sidebars.append(sidebar)
                except Exception as e:
                    logging.error("Failed to get sidebar at %s", current_url)
                    logging.error(e)

            self.path.append(current_url)
            count -= 1

            # Watch the current video
            video_len = 180
            if max_duration > 0:
                try:
                    path = ".//video" if self.mode == "long" else ".//ytd-reel-video-renderer[@is-active]//video"
                    vid = WebDriverWait(self.driver, 60).until(
                        EC.presence_of_element_located((By.XPATH, path))
                    )
                    video_len = float(vid.get_attribute("duration") or 180)
                    logging.info("video length: %s", video_len)
                    if video_len in ["", None, 0, float("nan")]:
                        video_len = 180
                except Exception as e:
                    video_len = 180

                if isinstance(max_duration, float):  # percentage
                    wait_time = int(video_len * max_duration)
                else:  # seconds
                    wait_time = min(video_len, max_duration) - 1
            else:
                wait_time = 0

            logging.info("waiting for %d seconds", wait_time)
            time.sleep(max(wait_time, 0))

        if err_attempts <= 0:
            logging.error("Run error... too many retries")
            self._emit_progress("collection_failed", error="too_many_retries")
            return -1

        self._emit_progress("collection_complete", total_collected=collect_video_num - count)
        return 0

    def Report(self) -> dict:
        """Generate report of collected data.

        Returns
        -------
        dict
            Report containing training IDs, seed ID, mode, and all recommendations
        """
        return {
            "training_ids": self.seed_ids[:-1] if len(self.seed_ids) > 1 else [],
            "seed_id": self.seed_ids[-1] if self.seed_ids else None,
            "player_mode": self.mode,
            "max_duration": self.max_duration,
            "recommendations": {
                "autoplay_rec": self.path,
                "sidebar_rec": self.sidebars,
                "preload_rec": self.preloads,
                "restricted": self.restricted,
            },
        }

    def HelloWorld(self):
        """Simple test function to verify driver works."""
        print("Testing")
        self.driver.get("https://www.youtube.com/")
        time.sleep(10)
        print("Test done")
