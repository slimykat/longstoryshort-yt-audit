"""Core YouTube audit automation using Selenium WebDriver."""

import time
import os
import logging
from typing import Literal, Callable, Optional

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
    WebDriverException,
)


VIDEO_URL_PREFIX_LONG = "https://www.youtube.com/watch?v="
VIDEO_URL_PREFIX_SHORT = "https://www.youtube.com/shorts/"


class YouTubeAuditor:
    """Automated YouTube recommendation audit tool.

    This class controls a browser to systematically audit YouTube's
    recommendation algorithm by watching videos and collecting recommendations.

    The workflow follows three phases:
    1. configure_browser() - Set up browser options
    2. launch_browser() - Initialize the WebDriver
    3. Train/Run - Execute the audit experiment

    Parameters
    ----------
    verbose : int, optional
        Logging level (default: logging.INFO)
    err_attempts : int, optional
        Number of retry attempts for failed operations (default: 5)
    on_progress : Callable, optional
        Callback function for progress updates. Called with event dict.
    log_file_path : str, optional
        Path to log file (default: "YouTubeAuditor.log")

    Attributes
    ----------
    driver : webdriver.Chrome
        Selenium WebDriver instance
    initialized : bool
        Whether driver has been initialized
    browser_type : str
        Browser type (Chrome, Firefox, Edge, Safari, Ie)
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
        verbose: int = logging.INFO,
        err_attempts: int = 5,
        on_progress: Optional[Callable[[dict], None]] = None,
        log_file_path: str = "YouTubeAuditor.log",
    ):
        # Error handling
        assert isinstance(log_file_path, str), "log_file_path must be a string"
        logging.basicConfig(filename=log_file_path, level=verbose)
        self.verbose = verbose
        self.err_attempts = err_attempts

        # Driver instance and flags
        self._driver = None
        self._driver_option = None
        self.initialized = False
        self.adblock = None
        self.browser_type = None
        # Experiment state
        self.seed_ids = []
        self.path = []
        self.sidebars = []  # only in long format
        self.preloads = []  # only in short format
        self.restricted = []
        self.max_duration = None
        self.mode = None

        # Call back hooks (optional)
        self.on_progress = on_progress or (lambda x: None)

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
        event = {"event": event_type, "timestamp": time.time(), **data}
        logging.debug("Progress event: %s", event)
        self.on_progress(event)

    def configure_browser(
        self,
        browser_type: Literal["Chrome", "Firefox", "Ie", "Edge", "Safari"] = "Chrome",
        adblock: bool | str = False,
        incognito: bool = False,
        headless: bool = True,
        custom_argument: list[str] = None,
    ):
        """Configure browser options before launching.

        This method must be called before launch_browser(). It sets up browser
        options including privacy mode, headless operation, and ad blocking.

        Parameters
        ----------
        browser_type : Literal["Chrome", "Firefox", "Ie", "Edge", "Safari"], optional
            Browser to use (default: "Chrome")
        adblock : bool | str, optional
            Enable ad blocker. If True, searches for .crx file in current directory.
            If string, uses provided path to extension (default: False)
        incognito : bool, optional
            Run browser in incognito/private mode (default: False)
        headless : bool, optional
            Run browser without GUI (default: True)
        custom_argument : list[str], optional
            Additional browser command-line arguments (default: None)

        Raises
        ------
        ValueError
            If browser_type is not supported
        FileNotFoundError
            If adblock extension file not found
        FileExistsError
            If multiple .crx files found and path not specified
        """
        assert browser_type in [
            "Chrome",
            "Firefox",
            "Ie",
            "Edge",
            "Safari",
        ], "Unsupported browser type"
        self.browser_type = browser_type
        method_name = self.browser_type + "Options"
        try:
            option_obj = getattr(webdriver, method_name)  # check if the method exists
        except AttributeError as e:
            logging.error("Unsupported browser type: %s", self.browser_type)
            raise ValueError(f"Unsupported browser type: {self.browser_type}") from e
        driver_option = option_obj()

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

        # Set up adblocker
        self.adblock = adblock
        if adblock:
            if isinstance(adblock, bool):
                # look for .crx file in the current working directory
                current_dir = os.getcwd()
                crx_files = [f for f in os.listdir(current_dir) if f.endswith(".crx")]
                if len(crx_files) > 1:
                    logging.error(
                        "Multiple .crx files found in %s, please specify the adblock extension path",
                        current_dir,
                    )
                    raise FileExistsError(
                        f"Multiple .crx files found in {current_dir}, please specify the adblock extension path"
                    )
                if len(crx_files) == 0:
                    logging.error(
                        "No .crx files found in %s, please specify the adblock extension path",
                        current_dir,
                    )
                    raise FileNotFoundError(
                        f"No .crx files found in {current_dir}, please specify the adblock extension path"
                    )
                extension_path = os.path.join(current_dir, crx_files[0])
            elif isinstance(adblock, str):
                # check if the provided path exists
                if not os.path.exists(adblock):
                    logging.error("Ad block extension not found at %s", adblock)
                    raise FileNotFoundError(
                        f"Ad block extension not found at {adblock}"
                    )
                extension_path = adblock
            else:
                logging.critical("Invalid adblock parameter: %s", adblock)
                raise ValueError(
                    "adblock must be a boolean or a string path to the extension"
                )
            driver_option.add_extension(extension_path)

        self._driver_option = driver_option
        self._emit_progress("browser_configured", browser_type=browser_type)

    def launch_browser(
        self, mode: Literal["long", "short"], max_duration: int | float = 10
    ) -> bool:
        """Launch the browser and initialize the WebDriver.

        This method creates the WebDriver instance with the options configured
        in configure_browser(). Must be called after configure_browser() and
        before any audit operations.

        Parameters
        ----------
        mode : Literal["long", "short"]
            Video player mode - "long" for regular videos, "short" for YouTube Shorts
        max_duration : int | float, optional
            Maximum time to watch each video. If int, time in seconds.
            If float (0-1), percentage of video length (default: 10)

        Returns
        -------
        bool
            True if initialization failed, False if successful

        Raises
        ------
        AssertionError
            If configure_browser() not called first or driver already initialized
        ValueError
            If browser_type is not supported
        RuntimeError
            If browser fails to launch
        """
        assert (
            self._driver_option is not None
        ), "Browser options not configured, call configure_browser() first"
        assert (
            not self.initialized
        ), "Driver is already initialized, please call CleanUp() first"

        assert isinstance(
            max_duration, (int, float)
        ), "max_duration must be an int or float"
        assert max_duration > 0, "max_duration must be greater than 0"
        assert mode in ["long", "short"], "mode must be either 'long' or 'short'"

        self.max_duration = max_duration
        self.mode = mode

        # Reset storage
        self.seed_ids = []
        self.path = []
        self.sidebars = []
        self.preloads = []
        self.restricted = []

        method_name = self.browser_type
        try:
            driver_class = getattr(webdriver, method_name)  # check if the class exists
            self._driver = driver_class(options=self._driver_option)
        except AttributeError as e:
            logging.error("Unsupported browser type: %s", self.browser_type)
            logging.error(e)
            raise ValueError(f"Unsupported browser type: {self.browser_type}") from e
        except WebDriverException as e:
            logging.error("Failed to launch the browser")
            logging.error(e)
            raise RuntimeError("Failed to launch the browser") from e

        self._emit_progress("driver_created", mode=mode)
        self._driver.implicitly_wait(2)

        # Clean up tabs opened by the driver and keep only one tab
        ## create a new tab first to ensure the driver is responsive
        self._driver.switch_to.new_window("tab")
        for attempt in range(self.err_attempts):
            # Wait until the new tab is created and the total number of windows is at least 2
            try:
                WebDriverWait(self._driver, 10).until(
                    lambda driver: len(driver.window_handles) >= 2
                )
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
        working_tab = self._driver.current_window_handle

        ## switch to the old tabs and close them
        for handle in self._driver.window_handles:
            if handle != working_tab:
                self._driver.switch_to.window(handle)
                self._driver.close()
        self._driver.switch_to.window(working_tab)
        time.sleep(1)

        assert (
            len(self._driver.window_handles) == 1
        ), "Failed to clean up tabs, more than 1 tab still open"
        self.initialized = True
        self._emit_progress("driver_ready", mode=mode)

    def log_in(self, username: str, password: str) -> bool:
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

        assert (
            self.initialized
        ), "Driver is not initialized, please call launch_browser() first"
        assert isinstance(username, str) and isinstance(
            password, str
        ), "username and password must be strings"
        assert (
            len(username) > 0 and len(password) > 0
        ), "username and password must not be empty"

        self.account = [username, password]
        self._emit_progress("login_started", username=username)

        try:
            self._driver.get("https://www.youtube.com/")

            # Find the login button
            WebDriverWait(self._driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//a[@aria-label="Sign in"]'))
            ).click()

            # Username
            WebDriverWait(self._driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//input[@id="identifierId"]')
                )
            ).send_keys(username)
            WebDriverWait(self._driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//div[@id="identifierNext"]'))
            ).click()

            # Password
            WebDriverWait(self._driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//input[@name="Passwd"]'))
            ).send_keys(password)
            WebDriverWait(self._driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//div[@id="passwordNext"]'))
            ).click()

            # Wait until YouTube title appears
            WebDriverWait(self._driver, 10).until(
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
            while len(self._driver.window_handles) > 1:
                self._driver.switch_to.window(self._driver.window_handles[-1])
                self._driver.close()
                self._driver.switch_to.window(self._driver.window_handles[0])
        except:
            logging.error("Failed to close extra tabs during cleanup")

        try:
            if not kill:
                self._driver.delete_all_cookies()
                self._driver.get("chrome://settings/clearBrowserData")
                time.sleep(1)
                # Complex shadow DOM navigation to clear browser data
                # (Original implementation kept as-is)
                try:
                    dom = self._driver.find_element(By.XPATH, ".//settings-ui")
                    shadow = self._driver.execute_script(
                        "return arguments[0].shadowRoot", dom
                    )
                    dom2 = shadow.find_element(By.ID, "main")
                    shadow2 = self._driver.execute_script(
                        "return arguments[0].shadowRoot", dom2
                    )
                    dom3 = shadow2.find_element(By.CSS_SELECTOR, "settings-basic-page")
                    shadow3 = self._driver.execute_script(
                        "return arguments[0].shadowRoot", dom3
                    )
                    dom4 = shadow3.find_element(By.ID, "basicPage").find_elements(
                        By.CSS_SELECTOR, "settings-section"
                    )[4]
                    assert dom4.get_attribute("page-title") == "Privacy and security"
                    dom5 = dom4.find_element(By.CSS_SELECTOR, "settings-privacy-page")
                    shadow5 = self._driver.execute_script(
                        "return arguments[0].shadowRoot", dom5
                    )
                    dom6 = shadow5.find_element(
                        By.CSS_SELECTOR, "settings-clear-browsing-data-dialog"
                    )
                    shadow6 = self._driver.execute_script(
                        "return arguments[0].shadowRoot", dom6
                    )
                    dom7 = shadow6.find_element(By.ID, "clearBrowsingDataDialog")
                    dom7.find_element(By.ID, "clearButton").click()
                except:
                    logging.error("Failed to clean up browser history")

                self.logged_in = False
                self.account = ["", ""]
        except:
            logging.error("Failed to clean up the driver")

        if self._driver and kill:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None

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
        assert (
            self.initialized
        ), "Driver is not initialized, please call launch_browser() first"
        assert isinstance(seed_ids, list), "seed_ids must be a list"
        assert all(
            isinstance(vid, str) for vid in seed_ids
        ), "seed_ids must be a list of strings"
        assert len(seed_ids) > 0, "seed_ids must not be empty"

        self.seed_ids = seed_ids
        total = len(seed_ids)

        logging.info("Start Training %d videos in %s mode", total, self.mode)
        self._emit_progress("training_started", total_videos=total, mode=self.mode)

        for idx, vid in enumerate(seed_ids):
            self._emit_progress(
                "training_progress", current=idx + 1, total=total, video_id=vid
            )
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
        assert isinstance(
            max_duration, (int, float)
        ), "max_duration must be an int or float"
        assert max_duration > 0, "max_duration must be greater than 0"

        logging.debug("Watching %s video: %s", mode, video_id)
        self._emit_progress("watch_started", video_id=video_id, mode=mode)

        url = (
            VIDEO_URL_PREFIX_LONG + video_id
            if mode == "long"
            else VIDEO_URL_PREFIX_SHORT + video_id
        )
        self._driver.get(url)
        WebDriverWait(self._driver, 10).until(
            lambda driver: video_id in driver.current_url
        )
        logging.info("Opened %s video: %s", mode, video_id)

        # Wait until the video is playing
        for i in range(self.err_attempts):
            try:
                path = (
                    ".//video"
                    if mode == "long"
                    else ".//ytd-reel-video-renderer[@is-active]//video"
                )

                WebDriverWait(self._driver, 10).until(
                    lambda driver: WebDriverWait(driver, 10)
                    .until(EC.presence_of_element_located((By.XPATH, path)))
                    .get_attribute("paused")
                    != "true"
                )
                vid = self._driver.find_element(By.XPATH, path)
                break
            except Exception as e:
                logging.error(
                    "Failed to get video element... try again %d/%d",
                    i + 1,
                    self.err_attempts,
                )
                logging.error(e)
                self._driver.refresh()
                time.sleep(2)
        else:
            logging.error("Video %s is not playing", self._driver.current_url)
            self._emit_progress(
                "watch_failed", video_id=video_id, error="video_not_playing"
            )
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
        self._emit_progress(
            "watching", video_id=video_id, duration=video_len, wait_time=wait_time
        )
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
                rec_list = WebDriverWait(self._driver, 10).until(
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
                rec_list = self._driver.find_elements(
                    By.XPATH,
                    ".//ytd-reel-video-renderer[not(@is-active)]//div[@id='player-container']",
                )
                styles = [div.get_attribute("style") for div in rec_list]
                batch = [
                    _prefix_short_url(style.split("vi/")[-1].split("/")[0])
                    for style in styles
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
        assert type(max_duration) in [
            int,
            float,
        ], "max_duration must be an int or float"
        assert max_duration >= 0, "max_duration must be >= 0"

        count = collect_video_num
        logging.info(
            "Start running from %s for %d videos",
            self._driver.current_url,
            collect_video_num,
        )
        self._emit_progress(
            "collection_started", total=collect_video_num, mode=self.mode
        )

        err_attempts = self.err_attempts
        while count > 0 and err_attempts > 0:
            current_idx = collect_video_num - count
            self._emit_progress(
                "collection_progress", current=current_idx + 1, total=collect_video_num
            )

            current_url = self._driver.current_url

            # Play next video
            try:
                if self.mode == "long":
                    ActionChains(self._driver).key_down(Keys.SHIFT).send_keys(
                        "n"
                    ).key_up(Keys.SHIFT).perform()
                elif self.mode == "short":
                    ActionChains(self._driver).send_keys(Keys.ARROW_DOWN).perform()
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
                WebDriverWait(self._driver, 10).until(EC.url_changes(current_url))
            except Exception as e:
                logging.error("URL not changed, try again")
                logging.error(e)
                err_attempts -= 1
                continue

            time.sleep(1)
            current_url = self._driver.current_url
            logging.info("Current video: %s", current_url)

            # Check if the current video is age restricted
            try:
                if self.mode == "short":
                    error_handle = WebDriverWait(self._driver, 10).until(
                        EC.presence_of_element_located(
                            (
                                By.XPATH,
                                ".//ytd-reel-video-renderer[@is-active]//yt-playability-error-supported-renderers",
                            )
                        )
                    )
                    if error_handle.get_attribute("hidden") is None:
                        logging.info("Encountered restricted video %s", current_url)
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

                        self.restricted.append([current_url, reason])
                        self._emit_progress(
                            "restricted_video", url=current_url, reason=reason
                        )

                        if "sign in" in reason.lower():
                            logging.error("Age Restricted video %s", current_url)
                            return -1

                        WebDriverWait(error_handle, 10).until(
                            EC.element_to_be_clickable(
                                (By.XPATH, ".//button-view-model")
                            )
                        ).click()

                else:  # long mode
                    error_handle = WebDriverWait(self._driver, 10).until(
                        EC.presence_of_element_located(
                            (
                                By.XPATH,
                                ".//div[@id='player']/yt-playability-error-supported-renderers",
                            )
                        )
                    )
                    if error_handle.get_attribute("hidden") is None:
                        logging.info("Encountered restricted video %s", current_url)
                        try:
                            reason = (
                                WebDriverWait(self._driver, 10)
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
                        self._emit_progress(
                            "restricted_video", url=current_url, reason=reason
                        )

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
                    path = (
                        ".//video"
                        if self.mode == "long"
                        else ".//ytd-reel-video-renderer[@is-active]//video"
                    )
                    vid = WebDriverWait(self._driver, 60).until(
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

        self._emit_progress(
            "collection_complete", total_collected=collect_video_num - count
        )
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
        self._driver.get("https://www.youtube.com/")
        time.sleep(10)
        print("Test done")
