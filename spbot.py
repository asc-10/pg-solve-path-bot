import praw
import json
import requests
import time
import sys

print("---Starting up---")

## Reddit authorisation
reddit = praw.Reddit(user_agent='',
                     client_id='', client_secret='',
                     username='', password='')

## Subreddit to monitor
subreddit = reddit.subreddit('PictureGame')

## Time an user has to reply to the bot
cutOffTime = 1800 # seconds

## Loading "playerDB.json" in "playerDB" list
print("Loading playerDB")
with open("/home/pi/solvepathbot/playerDB.json", 'r') as f:
    playerDB = json.load(f)
## A list with player names and a number of how many times the player hasn't replied to the bot.
## After three ignored comments in a row, we won't anymore ask this player the solve path.
## Player gets removed from this list if he (or anyone else) answers the bot before the counter reaches 3.
## [playerName, numberOfCommentsIgnored]

## Loading "commentDB.json" in "commentsToTrack" list
print("Loading commentDB")
with open("/home/pi/solvepathbot/commentDB.json", 'r') as f:
    commentsToTrack = json.load(f)
## A list with comments that we're waiting for a reply. Comment gets deleted if nobody replies it within 30 minutes.
## [commentID, personPinged]

## Loading "roundDB.json" in lastRoundCommentedOn
print("Loading roundDB")
with open("/home/pi/solvepathbot/roundDB.json", 'r') as f:
    roundDB = json.load(f)
lastRoundCommentedOn = roundDB
## This is neccessary to avoid bot double posting after a deleted round

## Function for requesting data from the API
def requestFromAPI(url):
    response = requests.get(url, headers={'User-Agent': ''}, timeout=10)
    if response.status_code == 200:
        print("----- API request successful (200)")
    data = response.json()
    return data

## The main loop
for submission in subreddit.stream.submissions(skip_existing=True):
    print("----- New submission detected...")
    ## Checking whether the submission is a round
    if submission.title[0:6].lower() == "[round":
        print("----- It is a round")


        ## Getting information about the current round from the PictureGame API
        print("----- Getting /current information from PG API")
        currentRoundAPI = requestFromAPI("https://api.picturegame.co/current")

        ## Making sure that we are not faster than the API ( "/current" with "winnerName" indicates that a round has been solved, but a new one hasn't been posted yet)
        while "winnerName" in currentRoundAPI["round"]:
            print("----- PG API hasn't registered a new round. Waiting 10 seconds")
            time.sleep(10)
            currentRoundAPI = requestFromAPI("https://api.picturegame.co/current")

        ## Getting info about the previous round
        print("----- Getting previous round information from PG API...")
        previousRoundNumber = currentRoundAPI["round"]["roundNumber"] - 1
        previousRoundAPI = requestFromAPI("https://api.picturegame.co/rounds/" + str(previousRoundNumber))
        previousRoundWinner = previousRoundAPI["winnerName"]
        previousRoundThread = previousRoundAPI["id"]
        print(str(previousRoundNumber) + " " + previousRoundThread + " was solved by " + previousRoundWinner)

        ## Looking player up in the playerDB to determine whether we should ping them
        print(str(previousRoundNumber) + " " + "Looking up in playerDB whether they are pingable")
        playerToTrack = previousRoundWinner
        playerPingable = False
        if playerToTrack in [playerToTrack[0] for playerToTrack in playerDB]:
            playerToTrackIndex = [playerToTrack[0] for playerToTrack in playerDB].index(playerToTrack)
            print(str(previousRoundNumber) + " " + "Player shouldn't be pinged")
            ## If they have less than 3 no-answers, they are still pingable
            if playerDB[playerToTrackIndex][1] < 3:
                playerPingable = True
        else: 
            playerPingable = True

        ## Doing the post      
        if playerPingable and (lastRoundCommentedOn != previousRoundNumber):
            print(str(previousRoundNumber) + " " + "Player is pingable; doing the ping")
            threadToPostTo = reddit.submission(previousRoundThread)
            comment = threadToPostTo.reply("How did you find the answer /u/" + str(previousRoundWinner) + "?")
            commentsToTrack.append([comment.id, playerToTrack])
            
            print(str(previousRoundNumber) + " " + "Noting lastRoundCommentedOn in roundDB ")
            lastRoundCommentedOn = previousRoundNumber
            with open("/home/pi/solvepathbot/roundDB.json", "w") as write_file:
                json.dump(lastRoundCommentedOn, write_file)
        
        ## Audit of the past comments
        print(str(previousRoundNumber) + " " + "Starting comment audit")
        newCommentsToTrack = list()
        for i in commentsToTrack:
            try:
                playerToTrack = i[1]
                comment = reddit.comment(i[0])
                comment.refresh() # PRAW requires this

                ## Checking if enough time has passed
                if (time.time() - comment.created_utc) > cutOffTime:
                
                    ## If nobody has replied, we'll delete the comment
                    if comment.replies.__len__() == 0:
                        comment.delete()
                        print(str(previousRoundNumber) + " " + "Deleted comment " + str(comment) + " for " + playerToTrack)

                        ## We'll add +1 to the times player hasn't replied   
                        ## Checking if the player is in our list
                        ## If yes, we'll get the index
                        if playerToTrack in [playerToTrack[0] for playerToTrack in playerDB]:
                            playerToTrackIndex = [playerToTrack[0] for playerToTrack in playerDB].index(playerToTrack)

                            ## Incrementing the no-replies counter
                            playerDB[playerToTrackIndex][1] = playerDB[playerToTrackIndex][1] + 1 
                            print(str(previousRoundNumber) + " " + "Added no-answer for " + playerToTrack)

                        else: ## If the player is not in the list, we'll add it
                            playerDB.append([playerToTrack, 1])
                            print(str(previousRoundNumber) + " " + "Added new player to playerDB: " + playerToTrack)

                    ## In case if it did get answered, and the player is on our list, we'll remove them
                    else:  
                        if playerToTrack in [playerToTrack[0] for playerToTrack in playerDB]:
                            playerToTrackIndex = [playerToTrack[0] for playerToTrack in playerDB].index(playerToTrack)

                            ## Removing player
                            playerDB.remove(playerDB[playerToTrackIndex])
                            print(str(previousRoundNumber) + " " + "Removed " + playerToTrack + " from playerDB")
                        
                ## If not enough time has passed, we'll check the comments later
                else:
                    newCommentsToTrack.append(i)
                    print(str(previousRoundNumber) + " " + "Not enough time has passed, checking comment next time " + str(comment))
            except Exception as e: # We need this in case a mod deletes our comment
                print("Error: " + str(e))
        commentsToTrack = newCommentsToTrack
        print(str(previousRoundNumber) + " " + "Comment audit done. Starting inbox audit")

        ## Inbox audit (to remove players from playerDB)
        inbox = reddit.inbox.unread()
        for message in inbox:
            if message.body == "pingmeagain":
                playerToTrack = str(message.author)
                print(str(previousRoundNumber) + " " + "Reiceived message from " + playerToTrack + " asking to ping them again")
                if playerToTrack in [playerToTrack[0] for playerToTrack in playerDB]:
                    playerToTrackIndex = [playerToTrack[0] for playerToTrack in playerDB].index(playerToTrack)

                    ## Removing player
                    playerDB.remove(playerDB[playerToTrackIndex])
                    print(str(previousRoundNumber) + " " + "Removed " + playerToTrack + " from playerDB")
                else:
                    print(str(previousRoundNumber) + " " + "However player was not in the playerDB")
            message.mark_read()
        print(str(previousRoundNumber) + " " + "Inbox audit done")

        ## Saving "commentsToTrack" to "commentDB.json" in SDcard
        with open("/home/pi/solvepathbot/commentDB.json", "w") as write_file:
            json.dump(commentsToTrack, write_file)

        ## Saving "playerDB" to "playerDB.json" in SDcard
        with open("/home/pi/solvepathbot/playerDB.json", "w") as write_file:
            json.dump(playerDB, write_file)

        print(str(previousRoundNumber) + " " + "Saved commentDB and playerDB to SD card")
        print(str(previousRoundNumber) + " " + "Waiting for a new round ---------------")
