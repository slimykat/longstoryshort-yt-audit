# module docstring
"""
This script is used to run the experiment for YouTube long/short video audit.
"""

import json
import sys

# for multi-threading
from multiprocessing.pool import ThreadPool
from random import sample

# for firebase output
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

# custom sock_puppet
import sock_puppet as sp
import time

SAMPLE_TRAIN_SIZE = 10
HOPS = 50
WATCHTIME = 10
PROCESS = 2
PROCESSOR_SERVER = 0


def init_database():
    """
    Initialize the connection to firebase database.

    The function will be called before running the experiment. It checks if the
    connection to the database has been established. If not, it establishes the
    connection using the certificate json file.

    Parameters
    ----------
    None

    Returns
    -------
    None

    """

    if firebase_admin._apps:
        return
    # connect to firebase
    cert_path = "secret_keys.json"
    cred = credentials.Certificate("./certificate.json")
    firebase_admin.initialize_app(
        cred, {"databaseURL": ""}
    )


# init database
init_database()


def output_firebase(num: str, long_result, short_result, exp_name):
    """
    Updates the Firebase database with experiment results and queues video IDs for metadata collection.

    This function stores the results of an experiment in a Firebase database under a specified experiment
    name. It also processes video URLs from the experiment results to extract video IDs, which are then
    distributed across multiple server queues for further metadata collection.

    Parameters
    ----------
    num : str
        A unique identifier for the experiment result entry.
    long_result : dict
        A dictionary containing the recommendations and other data from the long video result.
    short_result : dict
        A dictionary containing the recommendations and other data from the short video result.
    exp_name : str
        The name of the experiment under which the results are stored in the database.

    Raises
    ------
    AssertionError
        If either `long_result` or `short_result` is None.

    """

    if long_result.get("recommendations") is None or short_result.get("recommendations") is None:
        raise Exception(
            "Either long_result or short_result does not contain recommendations"
        )
    elif long_result.get("recommendations").get("autoplay_rec") is None or short_result.get("recommendations").get("autoplay_rec") is None:
        print("one is None")
        raise Exception(
            "Either long_result or short_result does not contain autoplay_rec"
        )
    db.reference(exp_name).update({num: [long_result, short_result]})
    assert long_result is not None, "long result is None"
    assert short_result is not None, "Short result is None"

    if PROCESSOR_SERVER == 0:
        return  # skip if no processor server is available

    # update the video id to the queue for meta data collection
    ## pick one of the four quese based on the video's id to avoid collision
    all_urls = set(
        short_result["recommendations"]["autoplay_rec"]
        + sum(short_result["recommendations"]["sidebar_rec"], [])
        + sum(short_result["recommendations"]["preload_rec"], [])
    )
    all_urls.update(
        set(
            long_result["recommendations"]["autoplay_rec"]
            + sum(long_result["recommendations"]["sidebar_rec"], [])
            + sum(long_result["recommendations"]["preload_rec"], [])
        )
    )
    all_short_ids = [
        url.split("shorts/")[-1]
        for url in all_urls
        if url.startswith("https://www.youtube.com/shorts")
    ]
    all_long_ids = [
        url.split("watch?v=")[-1].split("&")[0]
        for url in all_urls
        if url.startswith("https://www.youtube.com/watch?v=")
    ]

    short_bucket = [{}] * PROCESSOR_SERVER
    long_bucket = [{}] * PROCESSOR_SERVER
    for vid in all_short_ids:
        if not vid:
            continue
        server_num = (
            int.from_bytes(vid.encode("utf-8"), byteorder="big", signed=False)
            % PROCESSOR_SERVER
        )
        short_bucket[server_num].update({vid: "0"})
    for vid in all_long_ids:
        if not vid:
            continue
        server_num = (
            int.from_bytes(vid.encode("utf-8"), byteorder="big", signed=False)
            % PROCESSOR_SERVER
        )
        long_bucket[server_num].update({vid: "0"})

    for server_num, bucket in enumerate(short_bucket):
        if not bucket:
            continue
        db.reference("UrlQueue").child(str(server_num)).child("short").update(bucket)

    for server_num, bucket in enumerate(long_bucket):
        if not bucket:
            continue
        db.reference("UrlQueue").child(str(server_num)).child("long").update(bucket)


def task(arg):
    """
    Runs a single experiment task.

    Parameters
    ----------
    arg : tuple
        A tuple of four elements:
            - ids: a list of two video IDs (short and long)
            - watch_time: the time to watch a video in seconds
            - mode: either 'short' or 'long', indicating whether to use the
              short or long video player
            - hops: the number of hops to perform in the experiment

    Returns
    -------
    result : dict
        A dictionary containing the results of the experiment. If an error
        occurs, returns None.
    """
    ids, watch_time, mode, hops = arg
    puppet = sp.SockPuppet(
        adblock=True,
        incognito=False,
        headless=True,
        verbose=20,
    )
    puppet.InitDriver(mode, watch_time)
    try:
        if puppet.Train(ids) == -1:
            print(f"Train error with arg: {arg}")
            puppet.CleanUp(kill=True)
            return None
        puppet.Run(hops)
        result = puppet.Report()
    except Exception as e:
        print(f"Error with {arg}")
        print(e)
        result = None
    puppet.CleanUp(kill=True)
    # wait for 3 minutes
    time.sleep(sample(range(300, 901), 1)[0])

    return result


def main(batch: list[int], trained: bool, exp_name: str, input_json: str):
    """
    Executes a YouTube video audit experiment using multi-threading.

    This function processes a batch of video pairs from a specified JSON file,
    runs experiments on them to gather recommendations, and updates the results
    to a Firebase database. It uses multi-threading to run tasks for long and
    short videos concurrently.

    Parameters
    ----------
    batch : list[int]
        A list containing two integers, representing the start and end indices
        for processing video pairs.
    trained : bool
        A boolean indicating whether to use a training set of video IDs before
        the seed video.
    exp_name : str
        The name of the experiment under which the results are stored in the
        Firebase database.
    input_json : str
        The path to the JSON file containing the video pairs for the experiment.
        
    Raises
    ------
    AssertionError
        If `batch` does not contain exactly two integers, or if `trained` is
        not a boolean value.
    """

    assert len(batch) == 2, "batch should be a list of two integers, start and end"
    assert trained in [True, False], "trained should be a boolean value"
    # load all seed vid id from filtered.json
    with open(input_json, "r", encoding="utf-8") as f:
        pairs = json.load(f)
    print(len(pairs), " pairs loaded")
    print("running from ", batch[0], " to ", batch[1])
    
    # all_short = set(d["short"].split("/")[-1] for i, d in enumerate(pairs))
    # all_long = set(d["long"].split("/")[-1] for i, d in enumerate(pairs))

    index = 0
    with ThreadPool(PROCESS) as pool:
        # multi-threading to run all different settings
        m=0
        while m < len(pairs):
            # create different sets of settings
# d is this [
    #     {
    #         "short": {"id": "Nkv9eMcfrno"},
    #         "long": {"id": "Nkv9eMcfrno"}
    #     }
    # ],
            # short_seed = d["short"].split("/")[-1]
            # long_seed = d["long"].split("/")[-1]
            d = pairs[m]
            long_run = []
            short_run = []
            for i in d:
                long_run.append(i["long"].split("/")[-1])
                short_run.append(i["short"].split("/")[-1])


            print("running ... ", batch[0] + index, long_run, short_run)
            
            if trained:
                arg_long = [long_run, WATCHTIME, "long", HOPS]
                arg_short = [short_run, WATCHTIME, "short", HOPS]
            else:
                arg_long = [long_run, WATCHTIME, "long", HOPS]
                arg_short = [short_run, WATCHTIME, "short", HOPS]
            results = pool.map(task, [arg_long, arg_short])

            # output to firebase
            try:
                output_firebase(str(index + batch[0]), results[0], results[1], exp_name)
                m += 1
            except Exception as e:
                print("Error occur at index ", batch[0] + index)
                print("rerunning...")
                print(results)
                print(e)
            index += 1
            if index % 10 == 0:
                print("completed ", index, " tasks")

    print("finished")


if __name__ == "__main__":
    print("hello")
    assert (
        len(sys.argv) >= 6
    ), "Usage: python experiment_main.py start end trained exp_name"
    a, b, train_or_not, name, path = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
    assert train_or_not in ["True", "False"], "trained should be either True or False"
    train_or_not = train_or_not == "True"
    A = [int(a), int(b)]
    main(A, train_or_not, name, path)
