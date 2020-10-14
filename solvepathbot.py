import praw
import prawcore
import requests
import time
import yaml
import logging


# Enable logging
logging.basicConfig(filename='solvepathbot.log',
                    level=logging.INFO,
                    format='%(asctime)s %(levelname)s: %(message)s')


players = None                  # dict with players and their no-answer scores
last_round = None               # dict with last round the bot has commented on
reddit = None                   # PRAW reddit instance
tracked_comments = dict()       # dict with comments the bot still has to audit
cutOffTime = 1800  # seconds


# Import backup files and initiate PRAW stream
def main():
    logging.warning("***PROGRAM (RE)STARTED***")
    print("***PROGRAM (RE)STARTED***")

    global players
    players = load_yaml("players.yaml")

    global last_round
    last_round = load_yaml("last_round.yaml")

    global tracked_comments
    tracked_comments = load_yaml("tracked_comments.yaml")
    if tracked_comments is None:
        tracked_comments = dict()

    config = load_yaml("config.yaml")
    global reddit
    reddit = initialise_reddit(config)
    submission_stream(config)


# Load yaml file
def load_yaml(filename):
    with open(filename, 'r') as stream:
        try:
            data = yaml.safe_load(stream)
            return data
        except yaml.YAMLError as e:
            logging.critical(e)
            logging.critical("Trouble loading " + filename)


# Write yaml file
def write_yaml(filename, dict):
    with open(filename, 'w') as stream:
        try:
            yaml.dump(dict, stream, default_flow_style=False)
        except yaml.YAMLError as e:
            logging.critical(e)
            logging.critical("Trouble writing to " + filename)


# Return reddit instance
def initialise_reddit(config):
    reddit = praw.Reddit(user_agent=config["user_agent"],
                         client_id=config["client_id"],
                         client_secret=config["client_secret"],
                         username=config["username"],
                         password=config["password"])
    return reddit


# Submission stream
def submission_stream(config):
    while True:
        try:
            for submission in reddit.subreddit(config["subreddit"]).stream.submissions(skip_existing=True):
                worker(submission)
        except (prawcore.exceptions.ResponseException, prawcore.exceptions.RequestException) as e:
            logging.error(e)
            logging.warning("Sleeping for 60 seconds")
            time.sleep(60)


# Do all the practical aspects of the bot
def worker(submission):
    if check_if_round(submission) is True:                              # Check if a round or another type of post
        current_round_api_data = check_pg_api()                         # Make sure we're not faster than PictureGame API
        round_data = round_info(current_round_api_data)                 # Gather information about the round

        if is_player_pingable(round_data[0]) is True:                   # Check if player is pingable (round_data[1] is winner_name
            post_comment(round_data[0], round_data[1], round_data[2])   # Do the ping (0 - round_winner; 1 - round_number; 2 - round_thread_id)

    comment_audit()     # Check past comments the bot made
    inbox_audit()       # Check for players asking to be pinged again
    backup()            # Write dicts to yaml files

    logging.info("____________________________________")


# Check if it is a round
def check_if_round(submission):
    if submission.title[0:6].lower() == "[round":
        logging.info("__________New round posted: " + submission.id)
        return True
    else:
        logging.info("__________New thread posted, not a round " + submission.id)
        return False


# Check if PictureGame API has registered it
def check_pg_api():
    current_round_api_data = request_from_pg_api("https://api.picturegame.co/current")

    # Make sure that we are not faster than the PictureGame API
    while "winnerName" in current_round_api_data["round"]:
        logging.warning("PG API hasn't registered a new round. Waiting 10 seconds")
        time.sleep(10)
        current_round_api_data = request_from_pg_api("https://api.picturegame.co/current")

    return current_round_api_data


# Request data from PictureGame API
def request_from_pg_api(url):
    while True:
        try:
            response = requests.get(url, headers={'User-Agent': ''}, timeout=10)
            logging.info("Got (" + str(response.status_code) + ") response from API for " + url)
            data = response.json()
            return data
        except requests.exceptions.RequestException as e:
            logging.error(e)
            logging.warning("Sleeping for 60 seconds")
            time.sleep(60)


# Collect info about the round
def round_info(current_round_api_data):
    round_number = current_round_api_data["round"]["roundNumber"] - 1
    round_api_data = request_from_pg_api("https://api.picturegame.co/rounds/" + str(round_number))
    round_winner = round_api_data["winnerName"]
    round_thread_id = round_api_data["id"]
    logging.info(str(round_number) + " " + round_thread_id + " was solved by " + round_winner)

    return round_winner, round_number, round_thread_id


# Check if player is pingable
def is_player_pingable(round_winner):
    if round_winner not in players or (round_winner in players and int(players[round_winner]) < 3):
        logging.info(str(round_winner) + " is pingable")
        return True
    else:
        logging.info(str(round_winner) + " is NOT pingable")
        return False


# Comment on the thread
def post_comment(round_winner, round_number, round_thread_id):
    global last_round
    if round_number != last_round["round"]:
        comment = reddit.submission(round_thread_id).reply("How did you find the answer /u/" + str(round_winner) + "?")
        logging.info("Left a comment: " + comment.id)

        tracked_comments[comment.id] = round_winner

    else:
        logging.warning("We've already commented on this round!")

    last_round["round"] = round_number


# Audit comments
def comment_audit():
    logging.info("___Doing comment audit")
    for key in tracked_comments.copy():
        comment = reddit.comment(key)
        comment.refresh()

        # Check if enough time has passed
        if (time.time() - comment.created_utc) > cutOffTime:

            # If no reply, delete comment
            if comment.replies.__len__() == 0:
                comment.delete()
                logging.info(tracked_comments[key] + " didn't answer. Deleted " + key)

                # Add +1 to the times player hasn't replied (Or make a new entry if none)
                if tracked_comments[key] in players:
                    players[tracked_comments[key]] = players[tracked_comments[key]] + 1
                else:
                    players[tracked_comments[key]] = 1

                logging.info(tracked_comments[key] + " hasn't answered " + str(players[tracked_comments[key]]) + " times total" )


            # If reply exists and player in the list, remove them from the list
            else:
                if tracked_comments[key] in players:
                    del players[tracked_comments[key]]
                    logging.info(tracked_comments[key] + " answered. Removed from players.yaml")


            # Remove comment from tracked_comments
            del tracked_comments[key]


# Audit inbox
def inbox_audit():
    logging.info("___Doing inbox audit")
    inbox = reddit.inbox.unread()
    for message in inbox:
        print(message.body)
        if message.body == "pingmeagain":
            player = str(message.author)
            if player in players:
                del players[player]
                reddit.redditor(player).message("Automated message", "Thanks, you'll get pinged again.")
                logging.info("Inbox audit: " + player + " removed from players.yaml as per their request")
            else:
                reddit.redditor(player).message("Automated message", "Hey, you already are on the ping list. If you still don't get pinged, please contact ASCIO on Discord")
                logging.info("Inbox audit: " + player + "  requests removal from players.yaml, but they aren't in it.")
        message.mark_read()


# Backup
def backup():
    logging.info("___Doing backup")
    write_yaml("tracked_comments.yaml", tracked_comments)
    write_yaml("last_round.yaml", last_round)
    write_yaml("players.yaml", players)

if __name__ == "__main__":
    main()
